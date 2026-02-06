import json
import os
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
    return available_functions[function_name](**kwargs)


def get_ai_response(user_input, conversation_history=None):
    """Get AI response with conversation context and tool calling."""

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

    try:
        # 2. First model call
        completion = client.chat.completions.create(
            model=os.getenv("OPEN_ROUTER_MODEL"),
            messages=messages,
            tools=tools,
        )

        response_message = completion.choices[0].message

        # 3. If no tool calls → return direct response
        if not response_message.tool_calls:
            return response_message.content

        # 4. Append assistant tool call message
        messages.append(response_message)

        # 5. Execute all tool calls
        last_function_name = None

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            last_function_name = function_name

            # Execute the tool
            function_result = call_function(function_name, **function_args)

            # Append tool result
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": json.dumps(function_result)
            })

        # 6. Second model call (after all tool results)
        if last_function_name == "get_weather":
            second_completion = client.chat.completions.parse(
                model=os.getenv("OPEN_ROUTER_MODEL"),
                messages=messages,
                tools=tools,
                response_format=WeatherResponse
            )

            # Now parsed is guaranteed to exist
            return str(second_completion.choices[0].message.parsed.response)

        else:
            second_completion = client.chat.completions.create(
                model=os.getenv("OPEN_ROUTER_MODEL"),
                messages=messages,
                tools=tools,
            )

            return second_completion.choices[0].message.content

    except Exception as e:
        print(f"Error: {e}")
        return "Sorry, I'm having trouble responding right now."
