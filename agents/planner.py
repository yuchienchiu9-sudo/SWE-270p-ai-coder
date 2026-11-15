# Name: Yu-Chien Chiu
# Student ID: 56176405
"""
Planner Agent: turns the user's description and requirements into a
file-by-file implementation plan for a Python + Streamlit application.
"""

import json
import re

from agents.validation import FILENAME_PATTERN, TEST_FILENAME
from llm import Usage, generate_json

MAX_FILES = 6
REQUIRED_PACKAGES = ["streamlit", "pytest"]
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
DEFAULT_COLOR = "#E8590C"

PROMPT = """You are the Planner Agent in a multi-agent AI coding system.

Read the software description and requirements below and design a small,
runnable Python application with a Streamlit user interface.

Design rules:
- Put ALL business logic (data, validation, calculations, state changes) in
  plain Python modules that do not import streamlit, so they can be unit tested.
- app.py is the Streamlit UI only; it imports the logic modules.
- Use at most {max_files} files including app.py. Keep the design simple.
- Use in-memory data only (no database, no network calls, no real payments).
- Do not plan test files; a separate Tester Agent writes them.

Return ONLY a JSON object with exactly these keys:
{{
  "project_name": "short name",
  "summary": "one or two sentences",
  "features": ["feature 1", "feature 2"],
  "files": [
    {{
      "filename": "lowercase_name.py",
      "purpose": "what this file contains: classes, functions and their responsibilities",
      "depends_on": ["other_file.py"]
    }}
  ],
  "dependencies": ["streamlit"],
  "primary_color": "#RRGGBB"
}}

Rules for "files":
- List files in implementation order: a file may only depend on files listed before it.
- app.py must be the last file.
- Filenames are lowercase, end with .py, contain no folders, and do not start with "test_".
- "purpose" must name the main classes/functions so other agents can use them consistently.

"dependencies" lists pip packages needed to run the app (not the standard library).
"primary_color" is a hex brand color that fits the application's domain
(e.g. a warm orange for food, a calm blue for finance), dark enough for white text.

Software description and requirements:
{requirements}
"""


def _validate_plan(plan: dict) -> None:
    """Raise ValueError if the plan does not follow the required structure."""
    for key in ("project_name", "summary", "features", "files", "dependencies"):
        if key not in plan:
            raise ValueError(f'Missing key "{key}".')

    files = plan["files"]
    if not isinstance(files, list) or not files:
        raise ValueError('"files" must be a non-empty list.')
    if len(files) > MAX_FILES:
        raise ValueError(f"Plan has {len(files)} files; the maximum is {MAX_FILES}.")

    seen: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("Each item in \"files\" must be an object.")
        name = entry.get("filename", "")
        if not FILENAME_PATTERN.match(name) or name.startswith("test_"):
            raise ValueError(f'Invalid filename "{name}".')
        if name in seen:
            raise ValueError(f'Duplicate filename "{name}".')
        if not isinstance(entry.get("purpose"), str) or not entry["purpose"].strip():
            raise ValueError(f'"{name}" needs a non-empty "purpose".')
        deps = entry.get("depends_on", [])
        if not isinstance(deps, list):
            raise ValueError(f'"depends_on" of "{name}" must be a list.')
        for dep in deps:
            if dep not in seen:
                raise ValueError(
                    f'"{name}" depends on "{dep}", which is not listed before it.'
                )
        seen.append(name)

    if seen[-1] != "app.py":
        raise ValueError('"app.py" must be the last file.')
    if len(seen) < 2:
        raise ValueError("Plan needs at least one logic module besides app.py.")
    if not isinstance(plan["dependencies"], list):
        raise ValueError('"dependencies" must be a list.')


def planner_agent(requirements: str) -> tuple[dict, Usage]:
    """Create an implementation plan from the requirements; returns (plan, usage)."""
    if not requirements.strip():
        raise ValueError("Requirements cannot be empty.")

    plan, usage = generate_json(
        PROMPT.format(max_files=MAX_FILES, requirements=requirements),
        validate=_validate_plan,
    )

    # Normalize: every file gets a depends_on list, required packages are
    # always present, and the test file name is fixed for the Tester Agent.
    for entry in plan["files"]:
        entry.setdefault("depends_on", [])
    deps = [str(d).strip() for d in plan["dependencies"] if str(d).strip()]
    for pkg in REQUIRED_PACKAGES:
        if pkg not in deps:
            deps.append(pkg)
    plan["dependencies"] = deps
    plan["test_file"] = TEST_FILENAME
    # A bad color is not worth another API call; fall back to a default.
    if not HEX_COLOR.match(str(plan.get("primary_color", ""))):
        plan["primary_color"] = DEFAULT_COLOR

    return plan, usage


def plan_to_text(plan: dict) -> str:
    """Return the plan as pretty JSON, for prompts and display."""
    return json.dumps(plan, indent=2, ensure_ascii=False)
