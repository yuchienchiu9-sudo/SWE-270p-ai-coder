# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""
MCP client of the AI Coder: the orchestrator.

It starts mcp_server.py over stdio and calls its tools in a fixed order:

    create_run -> plan -> write_code (each planned file) -> write_tests ->
    run_tests + check_app -> repair if needed -> validate_requirements -> get_usage

Repair (each stage at most once): fix app.py if it crashes on load; fix the
modules used by failing tests; only then, if tests still fail, fix the tests.

A fixed order (instead of letting an LLM pick tools) keeps the number of
API calls and tokens small and predictable.

Command line:
    python client.py                        # uses examples/quickdelivery.md
    python client.py path/to/requirements.md
"""

import ast
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent
SERVER_PATH = PROJECT_ROOT / "mcp_server.py"
DEFAULT_REQUIREMENTS = PROJECT_ROOT / "examples" / "quickdelivery.md"
PASSTHROUGH_ENV = ("AI_CODER_OUTPUT_DIR", "GEMINI_MODEL")


class PipelineError(RuntimeError):
    """Raised when an MCP tool call fails."""


async def call_tool(session: ClientSession, name: str, **arguments):
    """Call an MCP tool and return its result as Python data (dict/list/str)."""
    result = await session.call_tool(name, arguments=arguments)
    text = "\n".join(c.text for c in result.content if c.type == "text")
    if result.isError:
        raise PipelineError(f"Tool '{name}' failed: {text}")
    if result.structuredContent is not None:
        data = result.structuredContent
    else:
        try:
            data = json.loads(text)
        except ValueError:
            return text
    # FastMCP wraps non-object results as {"result": ...}.
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data


def modules_to_repair(pytest_output: str, test_code: str, logic_files: list[str]) -> list[str]:
    """
    Pick the source modules most likely responsible for failing tests:
    - modules that appear in the traceback (an exception was raised inside them), and
    - modules whose classes/functions are used by the failing test functions
      (found via the test file's "from module import name" lines).
    """
    suspects = set(re.findall(r"([A-Za-z_]\w*\.py):\d+", pytest_output))

    failing = set(re.findall(r"FAILED \S+?::(\w+)", pytest_output))
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        tree = None
    if tree is not None and failing:
        name_to_module = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    name_to_module[alias.asname or alias.name] = f"{node.module}.py"
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in failing:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and sub.id in name_to_module:
                        suspects.add(name_to_module[sub.id])

    return [name for name in logic_files if name in suspects]


async def run_pipeline_steps(requirements: str) -> AsyncIterator[dict]:
    """
    Run the full pipeline and yield progress events:
        {"type": "log", "message": str}
        {"type": "done", "result": dict}   (last event)
    The UI shows the log live; the CLI prints it.
    """
    env = get_default_environment()
    for key in PASSTHROUGH_ENV:
        if key in os.environ:
            env[key] = os.environ[key]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-u", str(SERVER_PATH)],
        env=env,
        cwd=str(PROJECT_ROOT),
    )

    def log(message: str) -> dict:
        """Build a log event."""
        return {"type": "log", "message": message}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            yield log(f"Connected to MCP server ({len(tools.tools)} tools).")

            # 1. Workspace
            run = await call_tool(session, "create_run", requirements=requirements)
            run_id = run["run_id"]
            yield log(f"Created workspace {run_id}")

            # 2. Planner Agent
            yield log("Planner Agent: designing the application...")
            planned = await call_tool(session, "plan", run_id=run_id)
            plan = planned["plan"]
            filenames = [f["filename"] for f in plan["files"]]
            yield log(f"Planner Agent: {len(filenames)} files -> {', '.join(filenames)}")

            # 3. Coder Agent, one file at a time in dependency order
            for name in filenames:
                yield log(f"Coder Agent: writing {name}...")
                written = await call_tool(session, "write_code", run_id=run_id, filename=name)
                yield log(f"Coder Agent: {name} done ({written['lines']} lines)")

            # 4. Tester Agent
            yield log("Tester Agent: writing tests...")
            tests = await call_tool(session, "write_tests", run_id=run_id)
            yield log(f"Tester Agent: {tests['filename']} done ({tests['tests']} tests)")

            # 5. Verify: pytest + headless Streamlit check
            test_result = await call_tool(session, "run_tests", run_id=run_id)
            app_result = await call_tool(session, "check_app", run_id=run_id)
            yield log(
                f"pytest: {test_result['passed']} passed, {test_result['failed']} failed; "
                f"app check: {'OK' if app_result['ok'] else 'FAILED'}"
            )

            # 6. Repair, at most once per stage. Requirements are the source of
            #    truth, so the code is fixed first; the tests are only rewritten
            #    if they still fail afterwards.
            repaired = []

            def status() -> str:
                """One-line summary of the latest verification results."""
                return (
                    f"pytest: {test_result['passed']} passed, {test_result['failed']} failed; "
                    f"app check: {'OK' if app_result['ok'] else 'FAILED'}"
                )

            if not app_result["ok"]:
                yield log("Repair: Coder Agent fixing app.py startup error...")
                await call_tool(session, "write_code", run_id=run_id, filename="app.py",
                                feedback="\n".join(app_result["exceptions"])[-4000:])
                repaired.append("app.py")
                app_result = await call_tool(session, "check_app", run_id=run_id)
                yield log(f"After app repair - {status()}")

            if not test_result["ok"]:
                test_code = await call_tool(session, "read_file", run_id=run_id,
                                            filename=tests["filename"])
                logic_files = [n for n in filenames if n != "app.py"]
                suspects = modules_to_repair(test_result["output"], test_code, logic_files)
                for name in suspects:
                    yield log(f"Repair: Coder Agent checking {name} against failing tests...")
                    await call_tool(session, "write_code", run_id=run_id, filename=name,
                                    feedback=test_result["output"][-4000:])
                    repaired.append(name)
                if suspects:
                    test_result = await call_tool(session, "run_tests", run_id=run_id)
                    app_result = await call_tool(session, "check_app", run_id=run_id)
                    yield log(f"After code repair - {status()}")

            if not test_result["ok"]:
                yield log("Repair: Tester Agent fixing tests that contradict the code...")
                await call_tool(session, "write_tests", run_id=run_id,
                                feedback=test_result["output"][-4000:])
                repaired.append(tests["filename"])
                test_result = await call_tool(session, "run_tests", run_id=run_id)
                yield log(f"After test repair - {status()}")

            # 7. Requirement-to-test traceability after any test repairs.
            coverage = await call_tool(session, "validate_requirements", run_id=run_id)
            yield log(
                "Requirements traceability: "
                f"{coverage['declared_requirements']}/{coverage['total_requirements']} "
                "requirements have declared test mappings (not proof of correctness)."
            )

            # 8. Collect outputs and usage for display
            files = {
                name: await call_tool(session, "read_file", run_id=run_id, filename=name)
                for name in filenames + [tests["filename"]]
            }
            usage = await call_tool(session, "get_usage", run_id=run_id)
            total = usage["total"]
            yield log(
                f"LLM usage: {total['api_calls']} API calls, "
                f"{total['total_tokens']} tokens "
                f"({total['input_tokens']} in / {total['output_tokens']} out)"
            )

            yield {
                "type": "done",
                "result": {
                    "run_id": run_id,
                    "path": run["path"],
                    "plan": plan,
                    "files": files,
                    "test_file": tests["filename"],
                    "tests": test_result,
                    "app_check": app_result,
                    "repaired": repaired,
                    "usage": usage,
                    "coverage": coverage,
                    "success": test_result["ok"] and app_result["ok"],
                },
            }


async def run_pipeline(requirements: str) -> dict:
    """Run the pipeline, printing progress; returns the final result dict."""
    result = {}
    async for event in run_pipeline_steps(requirements):
        if event["type"] == "log":
            print(event["message"], flush=True)
        else:
            result = event["result"]
    return result


def main() -> None:
    """Command-line entry point."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REQUIREMENTS
    requirements = path.read_text(encoding="utf-8")
    result = asyncio.run(run_pipeline(requirements))

    print("\nUsage by agent:")
    for agent, used in result["usage"]["by_agent"].items():
        print(f"  {agent:8} {used['api_calls']:2} calls  {used['total_tokens']:6} tokens")
    print(f"\nOutput: {result['path']}")
    # Run from inside the folder so Streamlit picks up .streamlit/config.toml.
    print(f'Run the app:  cd "{result["path"]}"  then  streamlit run app.py')
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
