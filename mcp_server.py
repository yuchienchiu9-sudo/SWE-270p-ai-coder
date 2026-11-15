# Name: Yu-Chien Chiu
# Student ID: 56176405
"""
MCP server of the AI Coder (stdio transport).

The three agents run behind MCP tools and never call each other directly.
They communicate through a per-run workspace managed by this server:

    Planner  -> writes plan.json             (tool: plan)
    Coder    -> reads plan.json + the files it depends on,
                writes one source file       (tool: write_code)
    Tester   -> reads plan.json + all source files,
                writes test_app.py           (tool: write_tests)

Other tools manage the workspace (create_run, list_files, read_file) and
verify the output (run_tests, check_app, get_usage).

Every agent tool records its LLM usage in usage.json and returns it.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from agents.coder import coder_agent
from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.validation import FILENAME_PATTERN, TEST_FILENAME
from llm import Usage

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.getenv("AI_CODER_OUTPUT_DIR", PROJECT_ROOT / "generated")).resolve()

RUN_ID_PATTERN = re.compile(r"^run_\d{8}_\d{6}(_\d+)?$")
WORKSPACE_FILES = {"requirements.md", "plan.json", "requirements.txt", "usage.json"}
TEST_TIMEOUT_S = 60
SECRET_ENV_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")

mcp = FastMCP("AI Coder")


# ---------- workspace helpers ----------

def _run_dir(run_id: str) -> Path:
    """Return the folder of an existing run, rejecting malformed run ids."""
    if not RUN_ID_PATTERN.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id}")
    path = OUTPUT_ROOT / run_id
    if not path.is_dir():
        raise FileNotFoundError(f"Run not found: {run_id}")
    return path


def _check_filename(name: str) -> None:
    """Allow only flat, known file names inside a run folder (no paths)."""
    if name in WORKSPACE_FILES or name == TEST_FILENAME or FILENAME_PATTERN.match(name):
        return
    raise ValueError(f"File name not allowed: {name}")


def _read(run: Path, name: str) -> str:
    """Read a file from a run folder."""
    _check_filename(name)
    path = run / name
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {name}")
    return path.read_text(encoding="utf-8")


def _write(run: Path, name: str, content: str) -> None:
    """Write a file into a run folder."""
    _check_filename(name)
    (run / name).write_text(content, encoding="utf-8")


def _load_plan(run: Path) -> dict:
    """Load plan.json written by the Planner Agent."""
    return json.loads(_read(run, "plan.json"))


def _record_usage(run: Path, agent: str, usage: Usage) -> dict:
    """Add one agent call's usage to usage.json and return the run totals."""
    path = run / "usage.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "by_agent": {}, "total": Usage().to_dict()
    }
    agent_total = Usage.from_dict(data["by_agent"].get(agent, {}))
    agent_total.add(usage)
    data["by_agent"][agent] = agent_total.to_dict()
    run_total = Usage.from_dict(data["total"])
    run_total.add(usage)
    data["total"] = run_total.to_dict()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data["total"]


def _safe_env() -> dict:
    """Environment for running generated code, without API keys or secrets."""
    return {
        k: v for k, v in os.environ.items()
        if not any(word in k.upper() for word in SECRET_ENV_WORDS)
    }


def _run_python(run: Path, args: list[str]) -> subprocess.CompletedProcess:
    """Run Python in the run folder with a timeout and no secrets in the env."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=run,
        env=_safe_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TEST_TIMEOUT_S,
    )


# ---------- workspace tools ----------

@mcp.tool()
def create_run(requirements: str) -> dict:
    """Create a new run folder and save the user's description and requirements."""
    if not requirements.strip():
        raise ValueError("Requirements cannot be empty.")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_id, n = base, 1
    while (OUTPUT_ROOT / run_id).exists():
        n += 1
        run_id = f"{base}_{n}"
    run = OUTPUT_ROOT / run_id
    run.mkdir()
    _write(run, "requirements.md", requirements)
    return {"run_id": run_id, "path": str(run)}


@mcp.tool()
def list_files(run_id: str) -> list[str]:
    """List the files in a run folder."""
    run = _run_dir(run_id)
    return sorted(p.name for p in run.iterdir() if p.is_file())


@mcp.tool()
def read_file(run_id: str, filename: str) -> str:
    """Read one file from a run folder."""
    return _read(_run_dir(run_id), filename)


# ---------- agent tools ----------

@mcp.tool()
def plan(run_id: str) -> dict:
    """Planner Agent: read requirements.md, write plan.json and requirements.txt."""
    run = _run_dir(run_id)
    requirements = _read(run, "requirements.md")
    result, usage = planner_agent(requirements)
    _write(run, "plan.json", json.dumps(result, indent=2, ensure_ascii=False))
    _write(run, "requirements.txt", "\n".join(result["dependencies"]) + "\n")
    total = _record_usage(run, "planner", usage)
    return {"plan": result, "usage": usage.to_dict(), "run_total": total}


@mcp.tool()
def write_code(run_id: str, filename: str, feedback: str = "") -> dict:
    """
    Coder Agent: write one planned source file. It reads plan.json and the
    files listed in that file's depends_on. `feedback` is an optional error
    report (e.g. failing tests) used to repair an existing file.
    """
    run = _run_dir(run_id)
    current_plan = _load_plan(run)
    entry = next((f for f in current_plan["files"] if f["filename"] == filename), None)
    if entry is None:
        raise ValueError(f"{filename} is not in the plan.")
    deps = {name: _read(run, name) for name in entry["depends_on"]}
    requirements = _read(run, "requirements.md")

    code, usage = coder_agent(requirements, current_plan, filename, deps, feedback)
    _write(run, filename, code)
    total = _record_usage(run, "coder", usage)
    return {
        "filename": filename,
        "lines": len(code.splitlines()),
        "usage": usage.to_dict(),
        "run_total": total,
    }


@mcp.tool()
def write_tests(run_id: str) -> dict:
    """Tester Agent: read plan.json and all source files, write test_app.py."""
    run = _run_dir(run_id)
    current_plan = _load_plan(run)
    sources = {f["filename"]: _read(run, f["filename"]) for f in current_plan["files"]}
    requirements = _read(run, "requirements.md")

    name, code, usage = tester_agent(requirements, current_plan, sources)
    _write(run, name, code)
    total = _record_usage(run, "tester", usage)
    return {
        "filename": name,
        "tests": code.count("def test_"),
        "usage": usage.to_dict(),
        "run_total": total,
    }


# ---------- verification tools ----------

@mcp.tool()
def run_tests(run_id: str) -> dict:
    """Run pytest on test_app.py in the run folder (60 s timeout, no secrets)."""
    run = _run_dir(run_id)
    _read(run, TEST_FILENAME)  # fails clearly if tests were not written yet
    try:
        result = _run_python(
            run, ["-m", "pytest", TEST_FILENAME, "-q", "-p", "no:cacheprovider"]
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "passed": 0, "failed": 0, "output": "Timed out."}

    output = (result.stdout + "\n" + result.stderr).strip()

    def count(word: str) -> int:
        """Read a count like '17 passed' from the pytest summary line."""
        match = re.search(rf"(\d+) {word}", output)
        return int(match.group(1)) if match else 0

    return {
        "ok": result.returncode == 0,
        "passed": count("passed"),
        "failed": count("failed") + count("error"),
        "output": output[-6000:],
    }


APP_CHECK_SCRIPT = """
import json
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=30).run()
print(json.dumps({
    "exceptions": [e.value for e in at.exception],
    "titles": [t.value for t in at.title],
    "buttons": len(at.button),
}))
"""


@mcp.tool()
def check_app(run_id: str) -> dict:
    """Load app.py once in headless Streamlit and report any exceptions."""
    run = _run_dir(run_id)
    _read(run, "app.py")
    try:
        result = _run_python(run, ["-W", "ignore", "-c", APP_CHECK_SCRIPT])
    except subprocess.TimeoutExpired:
        return {"ok": False, "exceptions": ["Timed out."]}

    lines = result.stdout.strip().splitlines()
    if result.returncode != 0 or not lines:
        return {"ok": False, "exceptions": [result.stderr.strip()[-2000:]]}
    report = json.loads(lines[-1])
    report["ok"] = not report["exceptions"]
    return report


@mcp.tool()
def get_usage(run_id: str) -> dict:
    """Return LLM usage (API calls and tokens) per agent and in total."""
    run = _run_dir(run_id)
    path = run / "usage.json"
    if not path.is_file():
        return {"by_agent": {}, "total": Usage().to_dict()}
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    mcp.run(transport="stdio")
