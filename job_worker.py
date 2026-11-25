"""One independent containerized AI Coder generation job (no UI)."""
import asyncio
import json
import os
import sys
from pathlib import Path

from batch_rpc import atomic_json
from client import run_pipeline_steps

ROOT = Path(os.environ.get("AI_CODER_JOB_DIR", "/job"))


def progress(message: str, *, status: str = "RUNNING", percent: int = 0, result=None):
    payload = {"status": status, "percent": percent, "message": message}
    if result:
        payload.update({"run_id": result.get("run_id"), "success": result.get("success")})
    atomic_json(ROOT / "progress.json", payload)
    print(message, flush=True)


async def main():
    requirements = (ROOT / "spec.md").read_text(encoding="utf-8")
    progress("Starting MCP pipeline", percent=1)
    final_result = None
    async for event in run_pipeline_steps(requirements):
        if event["type"] == "done":
            result = event["result"]
            # Do not return while the MCP async generator is suspended at yield.
            # Let it resume and close its AnyIO context in the same asyncio Task.
            final_result = result
            continue
        message = event["message"]
        current = json.loads((ROOT / "progress.json").read_text())
        pct = current.get("percent", 1)
        if "Planner Agent:" in message:
            pct = max(pct, 15)
        if "Coder Agent:" in message:
            pct = max(pct, 35)
        if "Tester Agent:" in message:
            pct = max(pct, 65)
        if "pytest:" in message:
            pct = max(pct, 80)
        if "Requirements traceability:" in message:
            pct = max(pct, 90)
        if "LLM usage:" in message:
            pct = max(pct, 95)
        progress(message, percent=pct)
    if final_result is None:
        progress("Pipeline ended without a final result", status="FAILED", percent=100)
        return 1
    progress("Completed" if final_result["success"] else "Verification failed",
             status="COMPLETED" if final_result["success"] else "FAILED",
             percent=100, result=final_result)
    return 0 if final_result["success"] else 1


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception as exc:
        progress(f"Worker failed: {type(exc).__name__}: {exc}", status="FAILED")
        code = 1
    sys.exit(code)
