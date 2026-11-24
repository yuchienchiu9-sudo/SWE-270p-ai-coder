# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Tests for client-side MCP execution tracing."""

import asyncio
import json

import pytest

from execution_trace import ExecutionTrace


def test_successful_tool_call_and_persistence(tmp_path):
    """Successful calls retain their result and appear in the run JSON."""
    async def fake_call(session, name, **kwargs):
        return {"ok": True, "result": "ready"}

    async def run():
        trace = ExecutionTrace()
        result = await trace.call(fake_call, None, "create_run", requirements="private")
        assert result["result"] == "ready"
        trace.set_run_folder(tmp_path)
        await trace.call(fake_call, None, "plan", run_id="run_20261123_111111")
        saved = json.loads((tmp_path / "execution_trace.json").read_text())
        assert saved == trace.to_dict()
        assert saved["summary"]["total_calls"] == 2
        assert saved["summary"]["failed_calls"] == 0
        assert saved["events"][1]["result_ok"] is True
        assert saved["events"][1]["tool"] == "plan"
        assert saved["events"][1]["duration_ms"] >= 0
    asyncio.run(run())


def test_failed_call_is_persisted_and_original_error_reraised(tmp_path):
    """Record exceptions even if the pipeline ends before its final result."""
    async def fail(session, name, **kwargs):
        raise RuntimeError("secret error details")

    async def run():
        trace = ExecutionTrace()
        trace.set_run_folder(tmp_path)
        with pytest.raises(RuntimeError, match="secret error details"):
            await trace.call(fail, None, "write_code", filename="cart.py")
        report = json.loads((tmp_path / "execution_trace.json").read_text())
        assert report["summary"]["failed_calls"] == 1
        assert report["events"][0]["status"] == "error"
        assert "secret error details" not in json.dumps(report)
    asyncio.run(run())


def test_mcp_success_can_have_failed_test_result():
    """pytest may report failed assertions without an MCP protocol failure."""
    async def fake(session, name, **kwargs):
        return {"ok": False, "passed": 1, "failed": 2}

    async def run():
        trace = ExecutionTrace()
        await trace.call(fake, None, "run_tests")
        event = trace.to_dict()["events"][0]
        assert event["status"] == "success"
        assert event["result_ok"] is False
    asyncio.run(run())


def test_sensitive_arguments_are_not_recorded(tmp_path):
    """Requirements, API keys, and repair feedback must never enter a trace."""
    async def fake(session, name, **kwargs):
        return {"source": "sensitive returned source"}

    async def run():
        trace = ExecutionTrace()
        trace.set_run_folder(tmp_path)
        await trace.call(fake, None, "write_code", run_id="run_20261123_111111",
                         filename="app.py", requirements="private requirement",
                         feedback="secret feedback", api_key="secret key")
        data = (tmp_path / "execution_trace.json").read_text()
        for private in ("private requirement", "secret feedback", "secret key",
                        "sensitive returned source"):
            assert private not in data
        metadata = trace.to_dict()["events"][0]["metadata"]
        assert metadata == {"run_id": "run_20261123_111111", "filename": "app.py"}
    asyncio.run(run())


def test_per_run_instances_do_not_mix_events():
    """Separate instances retain independent call histories."""
    async def fake(session, name, **kwargs):
        return "ok"

    async def run():
        first, second = ExecutionTrace(), ExecutionTrace()
        await first.call(fake, None, "plan")
        await second.call(fake, None, "write_tests")
        assert [e["tool"] for e in first.events] == ["plan"]
        assert [e["tool"] for e in second.events] == ["write_tests"]
    asyncio.run(run())
