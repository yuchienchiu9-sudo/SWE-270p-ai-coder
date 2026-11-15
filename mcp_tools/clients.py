
# Name: YuChien Chiu
# Student ID: YOUR_STUDENT_ID

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_PATH = Path(__file__).resolve().parent / "servers.py"


async def main():
    """Connect to MCP server and test read_file and save_file."""

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-u", str(SERVER_PATH)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            # Step 1: Connect to MCP server.
            await session.initialize()
            print("MCP connection established!")

            # Step 2: List available MCP tools.
            tools = await session.list_tools()

            print("\nAvailable MCP tools:")
            for tool in tools.tools:
                print(f"- {tool.name}")

            # Step 3: Read plan.json through MCP.
            read_result = await session.call_tool(
                "read_file",
                arguments={"filename": "plan.json"}
            )

            if read_result.isError:
                raise RuntimeError(
                    f"MCP read_file failed: {read_result.content}"
                )

            print("\nContents of plan.json:\n")

            for item in read_result.content:
                if item.type == "text":
                    print(item.text)

            # Step 4: Save a test file through MCP.
            print("\nTesting save_file...")

            test_content = (
                "# MCP save_file test\n"
                "print('Hello from MCP!')\n"
            )

            save_result = await session.call_tool(
                "save_file",
                arguments={
                    "filename": "mcp_test.py",
                    "content": test_content
                }
            )

            if save_result.isError:
                raise RuntimeError(
                    f"MCP save_file failed: {save_result.content}"
                )

            print("\nSave result:")

            for item in save_result.content:
                if item.type == "text":
                    print(item.text)
                    
            # Step 5: Run pytest through MCP.
            print("\nTesting run_tests...")

            test_result = await session.call_tool(
                "run_tests",
                arguments={"filename": "test_models.py"}
            )

            if test_result.isError:
                raise RuntimeError(
                    f"MCP run_tests failed: {test_result.content}"
                )

            print("\nPytest results:\n")

            for item in test_result.content:
                if item.type == "text":
                    print(item.text)



if __name__ == "__main__":
    asyncio.run(main())
