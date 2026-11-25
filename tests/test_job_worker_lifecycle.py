"""Regression tests: consume the pipeline's final event before closing MCP."""
import asyncio
import json

import job_worker


def test_worker_drains_pipeline_after_done(tmp_path, monkeypatch):
    (tmp_path / "spec.md").write_text("Demo project", encoding="utf-8")
    monkeypatch.setattr(job_worker, "ROOT", tmp_path)
    closed = []

    async def fake_pipeline(requirements):
        assert requirements == "Demo project"
        try:
            yield {"type": "log", "message": "Planner Agent: designing..."}
            yield {"type": "done", "result": {"run_id": "run_abc", "success": True}}
        finally:
            closed.append(True)

    monkeypatch.setattr(job_worker, "run_pipeline_steps", fake_pipeline)
    assert asyncio.run(job_worker.main()) == 0
    assert closed == [True]
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["status"] == "COMPLETED"
    assert progress["run_id"] == "run_abc"


def test_worker_failed_verification_still_closes_pipeline(tmp_path, monkeypatch):
    (tmp_path / "spec.md").write_text("Demo project", encoding="utf-8")
    monkeypatch.setattr(job_worker, "ROOT", tmp_path)
    closed = []

    async def fake_pipeline(_requirements):
        try:
            yield {"type": "done", "result": {"run_id": "run_fail", "success": False}}
        finally:
            closed.append(True)

    monkeypatch.setattr(job_worker, "run_pipeline_steps", fake_pipeline)
    assert asyncio.run(job_worker.main()) == 1
    assert closed == [True]
    status = json.loads((tmp_path / "progress.json").read_text())
    assert status["status"] == "FAILED"
    assert status["message"] == "Verification failed"
