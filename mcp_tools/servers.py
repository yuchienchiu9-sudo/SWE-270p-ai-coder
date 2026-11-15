
# Name: YuChien Chiu
# Student ID: YOUR_STUDENT_ID

from pathlib import Path
from mcp.server.fastmcp import FastMCP
import subprocess
import sys


mcp = FastMCP("AI Coder Tools")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "generated" / "quickdelivery"

ALLOWED_FILES = {
    "plan.json",
    "models.py",
    "data.py",
    "payment.py",
    "app.py",
    "requirements.txt",
    "test_models.py",
    "mcp_test.py",
}


@mcp.tool()
def read_file(filename: str) -> str:
    """Read an allowed file from the generated project."""

    if filename not in ALLOWED_FILES:
        raise ValueError("File is not allowed.")

    file_path = OUTPUT_DIR / filename

    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {filename}")

    return file_path.read_text(encoding="utf-8")

@mcp.tool()
def save_file(filename: str, content: str) -> str:
    """Save an allowed file to the generated project directory."""

    if filename not in ALLOWED_FILES:
        raise ValueError(f"File is not allowed: {filename}")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("File content cannot be empty.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    file_path = OUTPUT_DIR / filename

    # Validate Python syntax before saving.
    if filename.endswith(".py"):
        compile(content, filename, "exec")

    # Prevent accidental overwriting of existing files.
    if file_path.exists():
        raise FileExistsError(f"File already exists: {filename}")

    file_path.write_text(content, encoding="utf-8")

    return f"Saved successfully: {filename}"

@mcp.tool()
def run_tests(filename: str = "test_models.py") -> str:
    """Run an allowed pytest file and return the test results."""

    # Only allow the approved test file.
    if filename != "test_models.py":
        raise ValueError(f"Test file is not allowed: {filename}")

    test_path = OUTPUT_DIR / filename

    if not test_path.is_file():
        raise FileNotFoundError(f"Test file not found: {filename}")

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                filename,
                "-v",
                "-q",
                "-p",
                "no:cacheprovider"
            ],
            cwd=OUTPUT_DIR,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )

    except subprocess.TimeoutExpired:
        return "Test execution timed out after 30 seconds."

    output = result.stdout + "\n" + result.stderr

    return (
        f"Exit code: {result.returncode}\n"
        f"Test results:\n{output[-12000:]}"
    )




if __name__ == "__main__":
    mcp.run(transport="stdio")
