
# Name: YuChien Chiu
# Student ID: 56176405

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agents.planner import planner_agent
from agents.coder import coder_agent
from agents.tester import tester_agent


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "generated" / "quickdelivery"
SERVER_PATH = PROJECT_ROOT / "mcp_tools" / "servers.py"

REQUIREMENTS = """
Build a QuickDelivery application using Python and Streamlit.

Users should be able to:
1. Browse predefined restaurants and menus.
2. Add and remove food items from a shopping cart.
3. Place food orders.
4. Simulate payments without real transactions.
5. Track order status:
   Pending, Preparing, Delivering, Delivered.

Cart quantities must be positive integers.
Generate pytest tests for the application.
"""


async def call_mcp_tool(session, name: str, arguments: dict) -> str:
    """Call an MCP tool and return its text response."""

    result = await session.call_tool(
        name,
        arguments=arguments
    )

    if result.isError:
        raise RuntimeError(
            f"MCP tool '{name}' failed: {result.content}"
        )

    return "\n".join(
        item.text
        for item in result.content
        if item.type == "text"
    )


async def run_pipeline(requirements: str):
    """Run the AI Coder pipeline using MCP tools."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-u", str(SERVER_PATH)]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            await session.initialize()
            print("MCP connection established!", flush=True)

            # Step 1: Load or generate plan.
            plan_path = OUTPUT_DIR / "plan.json"

            if plan_path.exists():
                print("\nLoading saved plan through MCP...")

                plan_text = await call_mcp_tool(
                    session,
                    "read_file",
                    {"filename": "plan.json"}
                )

                plan = json.loads(plan_text)

            else:
                print("\nRunning Planner Agent...")

                plan = planner_agent(requirements)

                await call_mcp_tool(
                    session,
                    "save_file",
                    {
                        "filename": "plan.json",
                        "content": json.dumps(plan, indent=4)
                    }
                )

                print("Saved plan.json through MCP")

            # Step 2: Generate missing application files.
            print("\nGenerating application files...")

            generation_order = [
                "models.py",
                "data.py",
                "payment.py",
                "requirements.txt",
                "app.py"
            ]

            planned_files = plan["files_to_implement"]

            for filename in generation_order:

                if filename not in planned_files:
                    continue

                file_path = OUTPUT_DIR / filename

                if file_path.exists():
                    print(f"Skipping existing file: {filename}")
                    continue

                print(f"Generating {filename}...")

                code_result = coder_agent(
                    plan,
                    target_file=filename
                )

                message = await call_mcp_tool(
                    session,
                    "save_file",
                    {
                        "filename": filename,
                        "content": code_result["content"]
                    }
                )

                print(message)

            # Step 3: Generate tests if missing.
            print("\nChecking test files...")

            test_path = OUTPUT_DIR / "test_models.py"

            if test_path.exists():
                print("Using existing test_models.py")

            else:
                code = await call_mcp_tool(
                    session,
                    "read_file",
                    {"filename": "models.py"}
                )

                print("Running Tester Agent...")

                test_result = tester_agent(
                    requirements,
                    code
                )

                message = await call_mcp_tool(
                    session,
                    "save_file",
                    {
                        "filename": "test_models.py",
                        "content": test_result["content"]
                    }
                )

                print(message)

            # Step 4: Run pytest through MCP.
            print("\nRunning pytest through MCP...")

            test_output = await call_mcp_tool(
                session,
                "run_tests",
                {"filename": "test_models.py"}
            )

            print("\nTest Results:\n")
            print(test_output)

            if not test_output.startswith("Exit code: 0\n"):
                raise RuntimeError(
                    "Generated code tests did not complete "
                    "successfully. See results above."
                )

            print("\nAI Coder pipeline completed successfully!")
            print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(run_pipeline(REQUIREMENTS))
