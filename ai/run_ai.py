import asyncio
import contextvars
import inspect
import json
import logging
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.prompts import system_prompt
from ai.tools import get_weather, get_exchange_rate, get_products, tools, get_rate, search_similar_products, \
    search_by_image
from models import Message, Business
from payment.payment import initialize_payment, verify_payment

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_key = os.getenv("OPENAI_API_KEY")
ai_model = os.getenv("OPEN_ROUTER_MODEL")

client: AsyncOpenAI | None = None


def startup_ai_client():
    """Initialize the AI client. This should be called at application startup."""
    global client
    logger.info("Initializing OpenAI client...")
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    logger.info("OpenAI client initialized.")


# ✅ Store business_id as a context variable
_current_business_id = contextvars.ContextVar("current_business_id", default=None)


def set_business_context(business_id):
    """Set the business context for the current request"""
    _current_business_id.set(business_id)


def get_business_context():
    """Get the current business context"""
    return _current_business_id.get()


# Add a module-level variable alongside _current_business_id
_current_image_data = contextvars.ContextVar("current_image_data", default=None)  # base64 string


def set_image_context(image_data):
    _current_image_data.set(image_data)


def get_image_context():
    return _current_image_data.get()


available_functions = {
    "get_weather": get_weather,
    "get_exchange_rate": get_exchange_rate,
    "get_products": get_products,
    "get_rate": get_rate,
    "initialize_payment": initialize_payment,
    "verify_payment": verify_payment,
    "search_similar_products": search_similar_products,
    "search_by_image": search_by_image,

}


class WeatherResponse(BaseModel):
    temperature: float = Field(description="Temperature in degrees Celsius")
    response: str = Field(description="A natural language response to the user query.")


async def call_function(function_name, db, business_id=None, **kwargs):
    """Call a function, injecting business_id if needed"""
    # ✅ Inject business_id for get_products
    if function_name == "get_products" and business_id:
        kwargs['db'] = db
        kwargs['business_id'] = business_id
    # ✅ Inject db and business_id for search_similar_products
    if function_name == "search_similar_products" and business_id:
        kwargs['db'] = db
        kwargs['business_id'] = business_id
    if function_name == "initialize_payment" and 'callback_url' not in kwargs:
        # Inject the default callback URL if not provided by the AI
        kwargs['callback_url'] = f"{os.getenv('AI_BASE_URL')}/paystack/callback"
    if function_name == "search_by_image" and business_id:
        kwargs['db'] = db
        kwargs['business_id'] = business_id
        # Use the actual downloaded image data instead of whatever URL the AI invented
        if get_image_context():
            kwargs['image_data'] = get_image_context()
            kwargs.pop('image_url', None)  # remove hallucinated URL

    func = available_functions[function_name]

    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    else:
        return func(**kwargs)


async def get_ai_response(user_input, db, conversation_history=None, business_id=None, user_name=None, image_data=None,
                          image_url=None):
    """
    Get AI response with conversation context and tool calling.

    Args:
        user_input: The user's message
        db: Database session
        conversation_history: Optional list of previous messages
        business_id: Optional business ID for context (used for WhatsApp and tool calls)
        user_name: Optional name of the sender to personalize the response
        image_data: Optional base64-encoded image data for vision analysis
    """
    # ✅ Set business context for this request
    if business_id:
        set_business_context(business_id)
    if image_data:
        set_image_context(image_data)  # ← add this
    else:
        set_image_context(None)  # ← clear it if no image

    # 1. Build base messages
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    business_result = await db.execute(select(Business).filter_by(id=business_id))
    business_obj = business_result.scalar_one_or_none()
    business_prompt = business_obj.persona if business_obj else None
    if business_prompt:
        messages.append({"role": "system", "content": business_prompt})

    # ✅ Add user name context if available
    if user_name:
        messages.append({"role": "system", "content": f"The user's name is {user_name}."})

    conversation_history = await get_conversation_history(
        business_id=business_id,
        customer_id=None,
        customer_name=user_name,
        db=db
    )
    if conversation_history:
        for msg in conversation_history:
            role = "assistant" if msg["is_bot"] else "user"

            if role == "user":
                # Use customer_name if available, otherwise fallback to generic 'user'
                name_to_use = msg.get("customer_name") or "User"
                messages.append({
                    "role": "user",
                    "content": f"{name_to_use} said: {msg['text']}"
                })
            else:
                messages.append({
                    "role": "assistant",
                    "content": msg["text"]
                })

    # ✅ Append the current user message with optional image
    if image_data:
        # For vision models, use content array with text and image
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_input},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    }
                }
            ]
        })
    else:
        messages.append({"role": "user", "content": user_input})

    # Log messages safely (truncate base64 images)
    messages_log = []
    for msg in messages:
        if isinstance(msg.get("content"), list):
            # Create a copy to avoid modifying the actual payload
            msg_copy = msg.copy()
            msg_copy["content"] = [
                {"type": "image_url", "url": "TRUNCATED_BASE64"} if item.get("type") == "image_url" else item
                for item in msg["content"]
            ]
            messages_log.append(msg_copy)
        else:
            messages_log.append(msg)
    logger.info(f"Sending messages to AI: {messages_log}")

    try:
        # 2. First model call
        if not client:
            logger.error("AI client is not initialized. Make sure to run startup_ai_client() on app startup.")
            return "Sorry, the AI service is not configured correctly."

        completion = await client.chat.completions.create(
            model=ai_model,
            messages=messages,
            tools=tools,
        )
        completion.model_dump()
        response_message = completion.choices[0].message
        logger.info(f"AI First Response: {response_message}")

        # 3. If no tool calls → return direct response
        if response_message.tool_calls:
            logger.info("🔧 Tool calls detected!")
            messages.append(response_message)

            # 4. Execute all tool calls in parallel
            # We use a lock for tools that require the shared DB session to avoid race conditions
            db_lock = asyncio.Lock()
            db_tools = {"get_products", "search_similar_products", "search_by_image"}

            async def execute_tool(tool_call):
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                logger.info(f"Calling tool: {function_name} with {function_args}")

                # Execute the tool (business_id injected in call_function)
                # Acquire lock only if the tool uses the DB session
                if function_name in db_tools:
                    async with db_lock:
                        function_result = await call_function(function_name, db=db, business_id=business_id,
                                                              **function_args)
                else:
                    function_result = await call_function(function_name, db=db, business_id=business_id,
                                                          **function_args)

                # Log result safely (truncate if too long)
                result_str = str(function_result)
                logger.info(
                    f"Tool Result: {result_str[:200]}..." if len(result_str) > 200 else f"Tool Result: {result_str}")

                return {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(function_result)
                }

            tool_outputs = await asyncio.gather(*(execute_tool(tc) for tc in response_message.tool_calls))
            messages.extend(tool_outputs)

            # 5. Second API call with all function results
            second_completion = await client.chat.completions.create(
                model=ai_model,
                messages=messages,
                tools=tools,
            )
            final_response = second_completion.choices[0].message.content or ""
            logger.info(f"AI Final Response: {final_response}")
            return final_response
        else:
            # No tools needed, return direct response
            return response_message.content or ""

    except Exception as e:
        logger.error(f"AI Response Error: {e}", exc_info=True)
        return "Sorry, I'm having trouble responding right now."


async def get_conversation_history(business_id, customer_id: int | None, customer_name: str | None, db: AsyncSession,
                                   limit=20):
    """Retrieve recent conversation history for a specific business and customer."""
    from sqlalchemy import or_
    results = await db.execute(
        select(Message)
        .filter(
            Message.business_id == business_id,
            or_(Message.customer_id == customer_id, Message.customer_name == customer_name)
        )
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )

    recent_messages = results.scalars().all()

    return [
        {
            'sender': msg.sender,
            'text': msg.text,
            'customer_name': msg.customer_name,
            'is_bot': msg.is_bot
        }
        for msg in reversed(recent_messages)
    ]


async def update_conversation_history(db, business_id, text, sender, customer_id=None, customer_name=None, is_bot=False,
                                      platform="web"):
    """Save a message to the database with isolation support."""
    new_msg = Message(
        business_id=business_id,
        text=text,
        sender=sender,
        customer_id=customer_id,
        customer_name=customer_name,
        is_bot=is_bot,
        platform=platform
    )
    db.add(new_msg)
    await db.commit()
    return new_msg


async def clear_conversation_history(db, business_id, sender):
    """Delete all messages associated with a specific business."""
    from sqlalchemy import and_
    results = await db.execute(
        delete(Message).where(
            and_(
                Message.business_id == business_id,
                Message.sender == sender
            )
        )
    )
    logger.info(f"{results.rowcount} messages were deleted by {sender}")
    await db.commit()
