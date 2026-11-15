
# Name: YuChien Chiu
# Student ID: 56176405

import json
from pathlib import Path


# Directory for generated application files.
OUTPUT_DIR = Path("generated") / "quickdelivery"


def save_plan(plan: dict) -> Path:
    """Save the Planner Agent's implementation plan as JSON."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    file_path = OUTPUT_DIR / "plan.json"

    file_path.write_text(
        json.dumps(plan, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )

    return file_path


def save_code(code_result: dict) -> Path:
    """Save a generated QuickDelivery source file."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    filename = code_result["filename"]
    code = code_result["content"]

    allowed_files = {
        "models.py",
        "data.py",
        "payment.py",
        "app.py",
        "requirements.txt"
    }

    if filename not in allowed_files:
        raise ValueError(f"Unexpected filename: {filename}")

    # Check syntax for Python files only.
    if filename.endswith(".py"):
        compile(code, filename, "exec")

    file_path = OUTPUT_DIR / filename
    file_path.write_text(code, encoding="utf-8")

    return file_path


def save_tests(test_result: dict) -> Path:
    """Save generated pytest code to test_models.py."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tests = test_result["content"]

    # Validate Python syntax before saving.
    compile(tests, "test_models.py", "exec")

    file_path = OUTPUT_DIR / "test_models.py"
    file_path.write_text(tests, encoding="utf-8")

    return file_path
