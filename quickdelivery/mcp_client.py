"""Use real MCP stdio calls to communicate with the QuickDelivery MCP server."""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = Path(__file__).resolve().parent / "mcp_server.py"


async def call_tools(calls: list[tuple[str, dict]]) -> tuple[list[object], list[dict]]:
    """Run one MCP session; return tool results and an inspectable tool trace."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    params = StdioServerParameters(command=sys.executable, args=["-u", str(SERVER)], cwd=str(ROOT), env=env)
    results, trace = [], []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, arguments in calls:
                response = await session.call_tool(name, arguments=arguments)
                trace.append({"tool": name, "arguments": arguments, "is_error": bool(response.isError)})
                if response.isError:
                    detail = " ".join(str(getattr(x,"text",x)) for x in response.content)
                    raise ValueError(f"MCP {name}: {detail}")
                if response.structuredContent is not None:
                    value = response.structuredContent
                    # FastMCP list outputs may be wrapped in {"result": [...]}.
                    if isinstance(value, dict) and set(value) == {"result"}:
                        value = value["result"]
                else:
                    text = next((x.text for x in response.content if getattr(x, "type", "") == "text"), "null")
                    value = json.loads(text)
                results.append(value)
    return results, trace


def call_tool(name: str, **arguments) -> tuple[object, list[dict]]:
    """Synchronous adapter for Streamlit; do not call from an event loop."""
    results, trace = asyncio.run(call_tools([(name, arguments)]))
    return results[0], trace
