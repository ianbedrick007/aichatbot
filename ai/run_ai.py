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
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    # Add conversation history
    if conversation_history:
        for msg in conversation_history:
            messages.append({
                "role": "assistant" if msg['sender'] == 'bot' else "user",
                "content": msg['text']
            })

    # Add current user input
    messages.append({
        "role": "user",
        "content": user_input
    })
    print(messages)
    try:
        # First API call
        completion = client.chat.completions.create(
            model="nvidia/nemotron-3-nano-30b-a3b:free",
            messages=messages,
            tools=tools,
        )
        completion.model_dump()
        response_message = completion.choices[0].message
        print(response_message)
        # Check if AI wants to use a tool
        if response_message.tool_calls:
            print("🔧 Tool calls detected!")
            messages.append(response_message)

            # Execute each tool call
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                print(f"Calling: {function_name} with {function_args}")

                # Actually execute the function
                function_result = call_function(function_name, **function_args)
                print(f"Result: {function_result}")

                # Add function result to messages (correct format!)
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps(function_result)
                })

            # Second API call with function results
                if function_name == "get_weather":
                    second_completion = client.chat.completions.parse(
                    model="nvidia/nemotron-3-nano-30b-a3b:free",
                    messages=messages,
                    tools=tools,
                    response_format=WeatherResponse

                    )
                    return str(second_completion.choices[0].message.parsed.response)
                else:
                    second_completion = client.chat.completions.create(
                        model="nvidia/nemotron-3-nano-30b-a3b:free",
                        messages=messages,
                        tools=tools,
                    )
                    return second_completion.choices[0].message.content
        else:
            # No tools needed, return direct response
            return response_message.content

    except Exception as e:
        print(f"Error: {e}")
        return "Sorry, I'm having trouble responding right now."
