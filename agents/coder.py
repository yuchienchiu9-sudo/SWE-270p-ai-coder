# Name: Yu-Chien Chiu
# Student ID: 56176405
"""
Coder Agent: writes one source file of the planned application at a time.
It only sees the files it depends on, which keeps prompts small and makes
it reuse the real class/function names from those files.
"""

from agents.planner import plan_to_text
from agents.validation import (
    check_imports,
    check_python,
    module_name,
    package_import_name,
)
from llm import Usage, generate_code

PROMPT = """You are the Coder Agent in a multi-agent AI coding system.

Software description and requirements:
{requirements}

Implementation plan:
{plan}

Files already written that {filename} may import (use their exact class names,
function names and parameter signatures; do not invent methods):
{existing}

Your task: write the complete content of {filename}.
Purpose of this file: {purpose}

Rules:
- Follow the plan and the requirements.
- Only import the project modules listed above, the Python standard library,
  and these packages: {packages}.
- Give every class and function a short docstring explaining what it does.
- Use plain ASCII text in string literals: no emoji, no \\u escapes, and no
  backslash-dollar; format money like f"${{price:.2f}}" or "USD 9.99".
- {ui_rule}
{feedback}
Reply with ONLY the complete Python source code of {filename}.
No explanations and no Markdown code fences.
"""

UI_RULE = (
    "This is the Streamlit UI. Keep st.session_state for state that must survive "
    "reruns, and call the logic modules instead of re-implementing logic."
)
LOGIC_RULE = "Do not import streamlit or read user input; this module must be unit-testable."


def _format_files(files: dict[str, str]) -> str:
    """Render {filename: content} as labelled blocks for the prompt."""
    if not files:
        return "(none)"
    return "\n\n".join(f"--- {name} ---\n{code}" for name, code in files.items())


def coder_agent(
    requirements: str,
    plan: dict,
    filename: str,
    existing_files: dict[str, str],
    feedback: str = "",
) -> tuple[str, Usage]:
    """
    Generate the content of `filename`; returns (code, usage).

    existing_files: contents of the files `filename` depends on.
    feedback:       optional error report (e.g. failing tests) for a repair attempt.
    """
    entry = next((f for f in plan["files"] if f["filename"] == filename), None)
    if entry is None:
        raise ValueError(f"{filename} is not in the plan.")

    is_ui = filename == "app.py"
    allowed_local = {module_name(d) for d in entry["depends_on"]}
    known_local = {module_name(f["filename"]) for f in plan["files"]}
    packages = {package_import_name(p) for p in plan["dependencies"]}
    if not is_ui:
        packages.discard("streamlit")
    packages.discard("pytest")

    def validate(code: str) -> None:
        """Check the generated code's syntax and imports."""
        if not code.strip():
            raise ValueError("The reply is empty.")
        tree = check_python(code, filename)
        check_imports(tree, filename, allowed_local, known_local, packages)

    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\nA previous version of {filename} had these problems. Fix them:\n"
            f"{feedback}\n"
        )

    prompt = PROMPT.format(
        requirements=requirements,
        plan=plan_to_text(plan),
        filename=filename,
        existing=_format_files(existing_files),
        purpose=entry["purpose"],
        packages=", ".join(sorted(packages)) or "(none)",
        ui_rule=UI_RULE if is_ui else LOGIC_RULE,
        feedback=feedback_block,
    )

    return generate_code(prompt, validate=validate)
