# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""
Checks shared by the agents. Each check raises ValueError or SyntaxError
with a clear message; llm.generate_json() sends that message back to
Gemini so it can fix its reply.
"""

import ast
import re
import sys
import warnings

# Generated modules: lowercase Python files in a single folder (no paths).
FILENAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.py$")
TEST_FILENAME = "test_app.py"


def module_name(filename: str) -> str:
    """Return the import name of a generated file, e.g. 'models.py' -> 'models'."""
    return filename[:-3]


def package_import_name(package: str) -> str:
    """Return the import name of a pip requirement, e.g. 'streamlit>=1.0' -> 'streamlit'."""
    name = re.split(r"[<>=!~\[ ]", package, maxsplit=1)[0]
    return name.strip().lower().replace("-", "_")


def check_python(code: str, filename: str) -> ast.Module:
    """
    Parse code without running it. Raises SyntaxError for syntax errors and
    for SyntaxWarnings (e.g. invalid escapes like '\\$'), and ValueError for
    string literals containing broken unicode (e.g. '\\ud83c' emoji escapes).
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            tree = ast.parse(code, filename=filename)
    except SyntaxError as exc:
        # SyntaxWarning promoted to an error also arrives here.
        raise SyntaxError(
            f"{filename} has a SyntaxError on line {exc.lineno}: {exc.msg}"
        ) from None
    except SyntaxWarning as exc:
        raise SyntaxError(f"{filename}: {exc}") from None

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any("\ud800" <= ch <= "\udfff" for ch in node.value):
                raise ValueError(
                    f"{filename} line {node.lineno}: string contains a broken "
                    "unicode escape (surrogate). Do not use emoji or \\u escapes."
                )
    return tree


def check_imports(
    tree: ast.Module,
    filename: str,
    allowed_local: set[str],
    known_local: set[str],
    packages: set[str],
) -> None:
    """
    Reject imports that would fail at runtime or skip a planned dependency.

    allowed_local: generated modules this file may import.
    known_local:   all generated modules in the plan.
    packages:      import names of the planned pip dependencies.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue

        for name in names:
            top = name.split(".")[0]
            if top in allowed_local:
                continue
            if top in known_local:
                raise ValueError(
                    f"{filename} imports '{top}', which is not in its allowed "
                    f"local modules {sorted(allowed_local)}."
                )
            if top in sys.stdlib_module_names or top.lower() in packages:
                continue
            raise ValueError(
                f"{filename} imports '{top}', which is neither a project module, "
                f"the standard library, nor a planned dependency {sorted(packages)}."
            )
