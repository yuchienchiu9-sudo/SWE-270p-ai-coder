# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""
Tester Agent: writes one pytest file covering every logic module of the
generated application. The Streamlit UI (app.py) is not unit tested.
"""

import ast

from agents.planner import plan_to_text
from agents.validation import TEST_FILENAME, check_imports, check_python, module_name
from llm import Usage, generate_code

PROMPT = """You are the Tester Agent in a multi-agent AI coding system.

Software description and requirements:
{requirements}

Implementation plan:
{plan}

Source code of the modules to test:
{sources}

Your task: write {test_file}, a pytest file for the modules above.

Rules:
- Import from these modules only: {modules} (plus pytest and the standard library).
  Never import app or streamlit.
- Use only classes, functions and signatures that exist in the source code above.
- Cover each requirement that the logic modules implement: normal cases,
  edge cases and invalid input (use pytest.raises where errors are raised).
- Tests must be independent: create fresh objects in each test or fixture.
- Every test function name starts with test_ and has a short docstring.
- Numbered input requirements map to IDs FR1, FR2, etc. in their original order.
  For each test, start its docstring with the matching IDs, for example:
      "FR3: Reject zero and negative cart quantities."
      "FR6, FR8: Successful checkout clears the cart."
- Only tag a requirement if the test actually asserts behavior relevant to it.
  Do not claim UI-only requirements are covered by logic unit tests.
- Prefer meaningful positive, negative, boundary-case assertions. Never add
  placeholder tests (e.g. 'assert True') merely to inflate coverage.
- Write between 10 and 25 tests.
{feedback}

Reply with ONLY the complete Python source code of {test_file}.
No explanations and no Markdown code fences.
"""


def tester_agent(
    requirements: str,
    plan: dict,
    source_files: dict[str, str],
    feedback: str = "",
) -> tuple[str, str, Usage]:
    """
    Generate pytest tests for the logic modules; returns (filename, code, usage).

    source_files: {filename: content} of all generated files (app.py is skipped).
    feedback:     optional pytest failure report for a repair attempt.
    """
    logic_files = {n: c for n, c in source_files.items() if n != "app.py"}
    if not logic_files:
        raise ValueError("No logic modules to test.")

    allowed_local = {module_name(n) for n in logic_files}
    known_local = allowed_local | {"app"}

    def validate(code: str) -> None:
        """Check syntax, imports, and that real test functions exist."""
        if not code.strip():
            raise ValueError("The reply is empty.")
        tree = check_python(code, TEST_FILENAME)
        check_imports(tree, TEST_FILENAME, allowed_local, known_local, {"pytest"})
        tests = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
        ]
        if not tests:
            raise ValueError("The file contains no test_ functions.")

    prompt = PROMPT.format(
        requirements=requirements,
        plan=plan_to_text(plan),
        sources="\n\n".join(f"--- {n} ---\n{c}" for n, c in logic_files.items()),
        test_file=TEST_FILENAME,
        modules=", ".join(sorted(allowed_local)),
        feedback=(
            "\nThe previous version of the tests failed as shown below. Where a test "
            "contradicts the source code but not the requirements, fix the test.\n"
            f"{feedback}\n" if feedback else ""
        ),
    )

    code, usage = generate_code(prompt, validate=validate)
    return TEST_FILENAME, code, usage
