
# Name: YuChien Chiu
# Student ID: 56176405

import json

from google.genai import types

from services.llm_client import client
from agents.planner import planner_agent
from agents.coder import coder_agent


def tester_agent(requirements: str, generated_code: str) -> dict:
    """Generate pytest tests based on requirements and source code."""

    if not requirements.strip():
        raise ValueError("Requirements cannot be empty.")

    if not generated_code.strip():
        raise ValueError("Generated code cannot be empty.")

    prompt = f"""
    You are a Python QA engineer (Tester Agent).

    Generate executable pytest test cases for the following
    QuickDelivery application code.

    Original Software Requirements:
    {requirements}

    Generated models.py:
    {generated_code}

    Instructions:
    1. Generate pytest tests for the models.py module.
    2. Import classes and functions from models.py.
    3. Test normal functionality and edge cases.
    4. Include tests for:
       - Adding items to the cart
       - Removing items from the cart
       - Calculating cart totals
       - Creating and retrieving orders
       - Updating order status
       - Invalid quantities and invalid order statuses
    5. Do not silently ignore missing requirements.
    6. Use pytest.
    7. Return a JSON object with exactly two fields:
       "filename": "test_models.py"
       "content": "Python source code"
    8. Return valid JSON without Markdown code fences.
    
    Additional rules:
        - Every test function must have a valid name
        starting with test_.
        - Every function definition must follow valid
        Python syntax, such as:
        def test_cart_initialization():
        - Use only class names and method names that
        actually exist in the provided source code.
        - Do not invent methods or classes.
        - If a requirement is missing from the implementation,
        write a test that clearly exposes the missing behavior.
        - Ensure the generated test file has valid Python syntax.
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    if not response.text:
        raise ValueError("Tester Agent returned an empty response.")

    result = json.loads(response.text)

    if not isinstance(result, dict):
        raise ValueError("Tester response must be a JSON object.")

    if result.get("filename") != "test_models.py":
        raise ValueError("Unexpected test filename.")

    tests = result.get("content")

    if not isinstance(tests, str) or not tests.strip():
        raise ValueError("Tester Agent returned no test code.")

    # Display generated tests before checking syntax.
    print("\nGenerated test code:\n", tests, flush=True)

    # Check Python syntax without executing tests.
    compile(tests, "test_models.py", "exec")

    return result


if __name__ == "__main__":
    requirements = """
    Build a QuickDelivery application.

    Users can:
    1. Browse predefined restaurants and menus.
    2. Add and remove food items from a shopping cart.
    3. Place food orders.
    4. Track simulated order status.
    5. Simulate payments.

    Cart quantities must be positive integers.
    Order status must be one of:
    Pending, Preparing, Delivering, Delivered.
    """

    print("Step 1: Running Planner Agent...", flush=True)
    plan = planner_agent(requirements)

    print("Step 2: Running Coder Agent...", flush=True)
    code_result = coder_agent(plan)

    print("Step 3: Running Tester Agent...", flush=True)
    test_result = tester_agent(
        requirements,
        code_result["content"]
    )

    print("\nGenerated file:", test_result["filename"])
    print("\nGenerated pytest Code:\n")
    print(test_result["content"])
