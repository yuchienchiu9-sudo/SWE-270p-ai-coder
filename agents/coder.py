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
- Never write \\u escape sequences; write emoji as the characters themselves (e.g. "🍔").
- Money: write f"${{amount:.2f}}" so it displays like $12.50. In markdown text
  (st.markdown, st.caption, st.write, labels) that contains two or more amounts,
  write each dollar sign as \\\\$ (two backslashes in the source) so Streamlit does
  not read the text between them as a math formula.
- {ui_rule}
{feedback}
Reply with ONLY the complete Python source code of {filename}.
No explanations and no Markdown code fences.
"""

UI_RULE = """This is the Streamlit UI. Keep st.session_state for state that must survive
  reruns, and call the logic modules instead of re-implementing logic.
  The app has a theme (colors, rounded corners) in .streamlit/config.toml; do not
  add custom CSS or HTML. Make it look like a polished modern product:
  * st.set_page_config(page_title=..., page_icon=<one emoji>, layout="wide").
  * A header: st.title with a fitting emoji and a one-line st.caption tagline.
  * Main sections as st.tabs at the top (not a sidebar selectbox). Tab labels may
    start with Material icons, e.g. ":material/restaurant: Restaurants".
  * Show collections as a grid of cards: st.columns(3) with
    st.container(border=True) per item; inside a card put a bold name, a short
    st.caption with details, and the price or key value.
  * Buttons: type="primary" for the main action on each screen, and a Material
    icon where helpful, e.g. st.button("Add", icon=":material/add_shopping_cart:").
  * Status labels: st.badge(text, color=...) where color is one of red, orange,
    yellow, blue, green, violet, gray, primary.
  * Use st.metric for key numbers (e.g. totals), st.progress for progress,
    st.divider between groups, and st.success / st.error / st.toast for feedback.
  * Empty states: st.info with a friendly message telling the user what to do next.
  * For anything that changes over time, put it in a function decorated with
    @st.fragment(run_every="2s") so it refreshes automatically without clicks.
  * Disable buttons whose action is not currently allowed."""
LOGIC_RULE = (
    "Do not import streamlit or read user input; this module must be unit-testable. "
    "Functions whose result depends on the current time must accept the time as an "
    "optional parameter (e.g. now: float | None = None) so tests can pass a fixed time."
)


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
    current_code: str = "",
) -> tuple[str, Usage]:
    """
    Generate the content of `filename`; returns (code, usage).

    existing_files: contents of the files `filename` depends on.
    feedback:       optional error report (e.g. failing tests) for a repair attempt.
    current_code:   the file's current content, so a repair can make minimal changes.
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
            f"\nThis is a REPAIR. Current version of {filename}:\n"
            f"--- {filename} ---\n{current_code or '(missing)'}\n\n"
            f"Problems found by testing:\n{feedback}\n\n"
            "Make the smallest change that fixes the problems in this file. Keep all "
            "existing class names, function names and signatures. If a failing test "
            "contradicts the requirements, keep the behavior the requirements describe. "
            "If this file is not the cause, return it unchanged.\n"
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
