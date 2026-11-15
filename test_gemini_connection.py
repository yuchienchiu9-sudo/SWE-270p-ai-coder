# Name: YOUR_NAME
# Student ID: YOUR_STUDENT_ID

import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30000)
)

print("Sending request...", flush=True)
start = time.perf_counter()

try:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents="Reply with exactly: Hello",
        config=types.GenerateContentConfig(
            max_output_tokens=100
        )
    )

    print("Response:", response.text)
except Exception as exc:
    print("Error:", type(exc).__name__, str(exc))
finally:
    print(f"Elapsed: {time.perf_counter() - start:.1f} seconds")