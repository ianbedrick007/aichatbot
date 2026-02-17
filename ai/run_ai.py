import json
import os
import traceback
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from ai.prompts import system_prompt
from ai.tools import get_weather, get_exchange_rate, get_products, tools, get_rate
from models import Message
from payment.payment import initialize_payment, verify_payment
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
ai_model = os.getenv("OPEN_ROUTER_MODEL")
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
)

# ✅ Store business_id as a context variable
_current_business_id = None


def set_business_context(business_id):
    """Set the business context for the current request"""
    global _current_business_id
    _current_business_id = business_id


def get_business_context():
    """Get the current business context"""
    return _current_business_id


available_functions = {
    "get_weather": get_weather,
    "get_exchange_rate": get_exchange_rate,
    "get_products": get_products,
    "get_rate": get_rate,
    "initialize_payment": initialize_payment,
    "verify_payment": verify_payment
}


class WeatherResponse(BaseModel):
    temperature: float = Field(description="Temperature in degrees Celsius")
    response: str = Field(description="A natural language response to the user query.")


def call_function(function_name, db, **kwargs):
    """Call a function, injecting business_id if needed"""
    # ✅ Inject business_id for get_products
    if function_name == "get_products" and _current_business_id:
        kwargs['db'] = db
        kwargs['business_id'] = _current_business_id
    if function_name == "initialize_payment" and 'callback_url' not in kwargs:
        # Inject the default callback URL if not provided by the AI
        kwargs['callback_url'] = f"{os.getenv('AI_BASE_URL')}/paystack/callback"

    return available_functions[function_name](**kwargs)


def get_ai_response(user_input, db, conversation_history=None, business_id=None, user_name=None, image_data=None):
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

    # 1. Build base messages
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    # ✅ Add user name context if available
    if user_name:
        messages.append({"role": "system", "content": f"The user's name is {user_name}."})

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

    print(f"Messages: {messages}")

    try:
        # 2. First model call
        completion = client.chat.completions.create(
            model=ai_model,
            messages=messages,
            tools=tools,
        )
        completion.model_dump()
        response_message = completion.choices[0].message
        print(response_message)

        # 3. If no tool calls → return direct response
        if response_message.tool_calls:
            print("🔧 Tool calls detected!")
            messages.append(response_message)

            # 4. Execute all tool calls
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                print(f"Calling: {function_name} with {function_args}")

                # Execute the tool (business_id injected in call_function)
                function_result = call_function(function_name, db=db, **function_args)
                print(f"Result: {function_result}")

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(function_result)
                })

            # 5. Second API call with all function results
            second_completion = client.chat.completions.create(
                model=ai_model,
                messages=messages,
                tools=tools,
            )
            return second_completion.choices[0].message.content or ""
        else:
            # No tools needed, return direct response
            return response_message.content or ""

    except Exception as e:
        traceback.print_exc()
        print(f"Error: {e}")
        return "Sorry, I'm having trouble responding right now."


def get_conversation_history(business_id, customer_id, db: Session, limit=20):
    """Retrieve recent conversation history for a specific business and customer."""

    recent_messages = db.query(Message).filter_by(
        business_id=business_id, 
        customer_id=customer_id
    ).order_by(Message.timestamp.desc()) \
        .limit(limit) \
        .all()

    return [
        {
            'sender': msg.sender, 
            'text': msg.text, 
            'customer_name': msg.customer_name,
            'is_bot': msg.is_bot
        }
        for msg in reversed(recent_messages)
    ]


def update_conversation_history(db, business_id, text, sender, customer_id=None, customer_name=None, is_bot=False, platform="web"):
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
    db.commit()
    return new_msg


def clear_conversation_history(db, business_id, sender):
    """Delete all messages associated with a specific business."""
    db.query(Message).filter_by(business_id=business_id, sender=sender).delete()
    db.commit()
