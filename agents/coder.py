
# Name: YuChien Chiu
# Student ID: 56176405

import json

from google.genai import types
from services.llm_client import client
from pathlib import Path


def coder_agent(plan: dict, target_file: str = "models.py") -> dict:
    """Generate a Python source file based on the implementation plan."""
    output_dir = Path("generated") / "quickdelivery"
    
    existing_files = {}
    
    for filename in ["models.py", "data.py", "payment.py"]:
        file_path = output_dir / filename
    
        if file_path.exists() and filename != target_file:
            existing_files[filename] = file_path.read_text(
                encoding="utf-8"
            )
    

    prompt = f"""
    You are a Python software engineer working on QuickDelivery.

    Project implementation plan:
    {json.dumps(plan, indent=2)}
    
    Existing project files:
    {json.dumps(existing_files, indent=2)}

    IMPORTANT:
    - Use the exact existing class and function names.
    - Use the actual parameter signatures from existing files.
    - Do not import classes or functions that do not exist.
    - Do not invent methods.
    - Make the generated file compatible with existing modules.

    Your task is to generate ONLY this file:
    {target_file}

    Requirements:
    1. Follow the implementation plan.
    2. Generate complete, executable code for the requested file.
    3. Keep the code compatible with other QuickDelivery modules.
    4. Do not generate unrelated files.
    5. Return a JSON object with exactly two fields:
       "filename": "{target_file}"
       "content": "Complete file content"
    6. Return valid JSON without Markdown code fences.
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

    try:
        result = json.loads(response.text)
    except json.JSONDecodeError as exc:
        print("\nCoder Agent returned invalid JSON.", flush=True)
        print(f"Error: {exc}", flush=True)

        print("\nRaw Gemini response:", flush=True)
        print(repr(response.text[:1500]), flush=True)

        raise

    if not isinstance(result, dict):
        raise ValueError("Coder response must be a JSON object.")

    if result.get("filename") != target_file:
        raise ValueError("Unexpected filename from Coder Agent.")

    code = result.get("content")

    if not isinstance(code, str) or not code.strip():
        raise ValueError("Coder Agent returned no source code.")

    # Check Python syntax without executing generated code.
    try:
        if target_file.endswith(".py"):
            compile(code, target_file, "exec")
    except SyntaxError as exc:
        print("\nGenerated code contains a SyntaxError:", flush=True)
        print(
            f"Line {exc.lineno}: {exc.msg}",
            flush=True
        )

        lines = code.splitlines()
        start = max(0, (exc.lineno or 1) - 6)
        end = min(len(lines), (exc.lineno or 1) + 3)

        print("\nCode near the error:", flush=True)

        for i in range(start, end):
            print(f"{i + 1:3}: {lines[i]}", flush=True)

        raise

    return result



if __name__ == "__main__":
    from save_results import save_code

    # Load the previously generated plan.
    plan_path = Path("generated/quickdelivery/plan.json")

    with plan_path.open("r", encoding="utf-8") as file:
        plan = json.load(file)

    # Generate the restaurant and menu data file.
    target_file = "payment.py"

    print(f"Running Coder Agent for {target_file}...", flush=True)

    # Step 1: Generate code using Gemini.
    result = coder_agent(plan, target_file=target_file)

    # Step 2: Save the generated code.
    saved_path = save_code(result)

    print(f"\nSaved generated file: {saved_path}")
    print("\nGenerated filename:", result["filename"])
    print("\nGenerated Python Code:\n")
    print(result["content"])
