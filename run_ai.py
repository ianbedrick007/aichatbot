from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def get_ai_response(user_input):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_input,
        config=types.GenerateContentConfig(
            system_instruction="Keep your response very short"
        ),
    )
    return response.text
