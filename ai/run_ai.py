import json
import os
import traceback
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from ai.prompts import system_prompt
from ai.tools import get_weather, get_exchange_rate, get_products, tools, get_rate

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")

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
    "get_rate": get_rate
}


class WeatherResponse(BaseModel):
    temperature: float = Field(description="Temperature in degrees Celsius")
    response: str = Field(description="A natural language response to the user query.")


def call_function(function_name, **kwargs):
    """Call a function, injecting business_id if needed"""
    # ✅ Inject business_id for get_products
    if function_name == "get_products" and _current_business_id:
        kwargs['business_id'] = _current_business_id

    return available_functions[function_name](**kwargs)


def get_ai_response(user_input, conversation_history=None, business_id=None):
    """
    Get AI response with conversation context and tool calling.

    Args:
        user_input: The user's message
        conversation_history: Optional list of previous messages
        business_id: Optional business ID for context (used for WhatsApp and tool calls)
    """
    # ✅ Set business context for this request
    if business_id:
        set_business_context(business_id)

    # 1. Build base messages
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    if conversation_history:
        for msg in conversation_history:
            messages.append({
                "role": "assistant" if msg["sender"] == "bot" else "user",
                "content": msg["text"]
            })

    messages.append({"role": "user", "content": user_input})
    print(messages)

    try:
        # 2. First model call
        completion = client.chat.completions.create(
            model=os.getenv("OPEN_ROUTER_MODEL"),
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

            # 4. Append assistant tool call message

            # 5. Execute all tool calls
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                print(f"Calling: {function_name} with {function_args}")

                # Execute the tool (business_id injected in call_function)
                function_result = call_function(function_name, **function_args)
                print(f"Result: {function_result}")

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(function_result)
                })

                # Second API call with function results
                if function_name == "get_weather":
                    second_completion = client.chat.completions.parse(
                        model="deepseek/deepseek-chat-v3.1",
                        messages=messages,
                        tools=tools,
                        response_format=WeatherResponse

                    )
                    if second_completion.choices[0].message.parsed:
                        return str(second_completion.choices[0].message.parsed.response)
                    return second_completion.choices[0].message.content
            else:
                second_completion = client.chat.completions.create(
                    model=os.getenv("OPEN_ROUTER_MODEL"),
                    messages=messages,
                    tools=tools,
                )
                return second_completion.choices[0].message.content
        else:
            # No tools needed, return direct response
            return response_message.content

    except Exception as e:
        traceback.print_exc()
        print(f"Error: {e}")
        return "Sorry, I'm having trouble responding right now."
