
# Name: YuChien Chiu
# Student ID: 56176405

import json

from google.genai import types
from services.llm_client import client
from agents.planner import planner_agent


def coder_agent(plan: dict) -> dict:
    """Generate a Python source file based on the implementation plan."""

    prompt = f"""
    You are a Python software developer (Coder Agent).

    Your task is to generate ONE executable Python source file
    based on the implementation plan below.

    Implementation Plan:
    {json.dumps(plan, indent=2)}

    Requirements:
    1. Generate ONLY models.py for the QuickDelivery application.
    2. Implement cart management and basic order management.
    3. Use Python standard libraries only.
    4. Do not use external databases or payment APIs.
    5. Keep the code simple and executable.
    6. Include docstrings for implemented functions and methods.
    7. Return a JSON object with exactly two fields:
       "filename" and "content".
    8. The "content" field must contain valid Python source code.
    9. Do not include Markdown code fences.
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    if not response.text:
        raise ValueError("Coder Agent returned an empty response.")

    result = json.loads(response.text)

    if not isinstance(result, dict):
        raise ValueError("Coder response must be a JSON object.")

    if result.get("filename") != "models.py":
        raise ValueError("Unexpected filename from Coder Agent.")

    code = result.get("content")

    if not isinstance(code, str) or not code.strip():
        raise ValueError("Coder Agent returned no source code.")

    # Check Python syntax without executing generated code.
    compile(code, "models.py", "exec")

    return result


if __name__ == "__main__":
    requirements = """
    Build a QuickDelivery application.

    Users can:
    1. Browse predefined restaurants and menus.
    2. Add and remove items in a shopping cart.
    3. Place food orders.
    4. Track simulated order status.
    5. Simulate payments.

    Use Streamlit and pytest.
    """

    print("Step 1: Running Planner Agent...", flush=True)
    plan = planner_agent(requirements)

    print("Step 2: Running Coder Agent...", flush=True)
    result = coder_agent(plan)

    print("\nGenerated filename:", result["filename"])
    print("\nGenerated Python Code:\n")
    print(result["content"])
