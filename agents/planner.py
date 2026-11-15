
# Name: YuChien Chiu
# Student ID: 56176405

import json

from google.genai import types
from services.llm_client import client


def planner_agent(requirements: str) -> dict:
    """Analyze software requirements and generate an implementation plan."""

    if not requirements.strip():
        raise ValueError("Requirements cannot be empty.")

    prompt = f"""
    You are a software planning agent.

    Analyze the software requirements below and create
    an implementation plan for a Python application.

    Include:
    1. Project name
    2. Programming language (Python)
    3. Main features
    4. Files to implement
    5. Implementation steps

    Additional constraints:
    - Use Streamlit for the application UI.
    - Include executable pytest test files in the project plan.
    - Use mock payment processing instead of real payment APIs.
    - Use predefined restaurant and menu data.
    - Keep the application simple enough to run locally.

    Do not generate application code.
    Return a valid JSON object.

    Software Requirements:
    {requirements}
    """

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    plan = json.loads(response.text)
    return plan


if __name__ == "__main__":
    requirements = """
    Build a QuickDelivery application.

    Users can:
    1. Browse restaurants and food menus.
    2. Add food items to a shopping cart.
    3. Place orders.
    4. Track order status.
    5. Simulate payments.
    """

    result = planner_agent(requirements)
    print(json.dumps(result, indent=2, ensure_ascii=False))
