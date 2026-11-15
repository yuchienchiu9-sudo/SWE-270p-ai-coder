
# Name: YOUR_NAME
# Student ID: YOUR_STUDENT_ID

import os

from dotenv import load_dotenv
from google import genai


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)


def generate_code(requirements: str) -> str:
    """Generate Python code based on software requirements."""

    prompt = f"""
    You are an experienced Python software engineer.

    Generate executable Python code based on the following
    software requirements.

    Requirements:
    {requirements}

    Return only Python code without Markdown formatting.
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    return response.text or ""
