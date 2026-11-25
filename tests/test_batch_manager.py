"""Offline, no Docker/Gemini needed: concurrent job isolation and broker checks."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from batch_manager import BatchManager, DEMO_PROJECTS, load_demo_spec, allowed_verification_args, progress_html
from batch_rpc import atomic_json


def test_demo_specs_are_three_distinct_projects():
    assert {name for name, _ in DEMO_PROJECTS} == {"QuickDelivery", "BudgetMaster", "GroupChat"}
    assert all(path.endswith(".md") for _, path in DEMO_PROJECTS)
    assert all("Requirements:" in load_demo_spec(path) for _, path in DEMO_PROJECTS)
    assert DEMO_PROJECTS[0] == ("QuickDelivery", "examples/quickdelivery.md")


def test_broker_rejects_unapproved_commands():
    assert allowed_verification_args(["-m", "pytest", "test_app.py", "-q", "-p", "no:cacheprovider"])
    assert not allowed_verification_args(["-c", "import os; print(os.environ)"])
    assert not allowed_verification_args(["-m", "pytest", "../../other-job/test_app.py"])


def test_worker_requests_are_isolated(tmp_path):
    manager = BatchManager(tmp_path)
    # Simulate three worker completions without Docker or LLM.
    def fake_worker(job):
        atomic_json(job.folder / "progress.json", {"status": "COMPLETED", "percent": 100,
                                                     "message": job.name})
        job.status = "COMPLETED"
    with patch.object(manager, "_run_job", fake_worker):
        ids = manager.start_demo(3)
    # Threads might still be running; wait until all three status files exist.
    import time
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and len(manager.snapshot()) == 3 and any(
        j.status != "COMPLETED" for j in manager.jobs.values()
    ):
        time.sleep(0.01)
    assert len(set(ids)) == 3
    assert len({manager.jobs[i].folder for i in ids}) == 3
    assert {r["name"] for r in manager.snapshot()} == {"QuickDelivery", "BudgetMaster", "GroupChat"}
    assert all(r["status"] == "COMPLETED" for r in manager.snapshot())


def test_broker_rejects_bad_run_id_without_executing_code(tmp_path):
    manager = BatchManager(tmp_path)
    folder = tmp_path / "job_bad"
    folder.mkdir()
    (folder / "control").mkdir()
    from batch_manager import Job
    job = Job("job_bad", "Test", folder)
    req = folder / "control" / "request_abc.json"
    atomic_json(req, {"run_id": "../../secret", "args": ["-c", "print(1)"]})
    with patch("batch_manager.run_generated_python") as mock_exec:
        manager._handle_request(job, req)
    mock_exec.assert_not_called()
    response = json.loads((folder / "control" / "response_abc.json").read_text())
    assert "error" in response


def test_atomic_json_write(tmp_path):
    path = tmp_path / "trace.json"
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda i: atomic_json(path, {"job": i}), range(12)))
    assert json.loads(path.read_text())["job"] in range(12)
    assert not list(tmp_path.glob("*.tmp"))


def test_progress_html_escapes_untrusted_text():
    html = progress_html([{"name": "<script>", "job_id": "id", "status": "RUNNING",
                           "percent": 30, "message": "<img src=x>"}])
    assert "<script>" not in html
    assert "<img src=x>" not in html
    assert "&lt;script&gt;" in html


def test_broker_approved_command_runs_in_host_sandbox(tmp_path):
    from batch_manager import Job
    from subprocess import CompletedProcess
    manager = BatchManager(tmp_path)
    folder = tmp_path / "job_ok"
    control = folder / "control"
    run = folder / "generated" / "run_20261124_170000"
    control.mkdir(parents=True)
    run.mkdir(parents=True)
    job = Job("job_ok", "QuickDelivery", folder)
    req = control / "request_xyz.json"
    args = ["-m", "pytest", "test_app.py", "-q", "-p", "no:cacheprovider"]
    atomic_json(req, {"run_id": run.name, "args": args, "timeout": 999999})
    with patch("batch_manager.run_generated_python",
               return_value=CompletedProcess(args, 0, "3 passed", "")) as mock_exec:
        manager._handle_request(job, req)
    mock_exec.assert_called_once_with(run, args, timeout=60)
    response = json.loads((control / "response_xyz.json").read_text())
    assert response["returncode"] == 0
    assert response["stdout"] == "3 passed"


def test_worker_to_host_rpc_round_trip(tmp_path, monkeypatch):
    """A worker sends a request; a host broker returns a typed result."""
    from batch_manager import Job
    from batch_rpc import remote_run
    from subprocess import CompletedProcess
    manager = BatchManager(tmp_path)
    folder = tmp_path / "job_rpc"
    run = folder / "generated" / "run_20261124_170001"
    run.mkdir(parents=True)
    (folder / "control").mkdir()
    job = Job("job_rpc", "Sample", folder)
    monkeypatch.setenv("AI_CODER_BROKER_DIR", str(folder / "control"))
    # Mock the host's actual Docker call, but exercise the real file RPC.
    args = ["-m", "pytest", "test_app.py", "-q", "-p", "no:cacheprovider"]
    stop = threading.Event()
    broker = threading.Thread(target=manager._broker, args=(job, stop))
    with patch("batch_manager.run_generated_python",
               return_value=CompletedProcess(args, 0, "4 passed", "")):
        broker.start()
        try:
            result = remote_run(run, args, timeout=2)
        finally:
            stop.set()
            broker.join(timeout=2)
    assert result.returncode == 0
    assert result.stdout == "4 passed"


def test_two_job_default_and_canonical_quickdelivery(tmp_path):
    """Default demo launches two independent jobs with the canonical 11 FRs."""
    manager = BatchManager(tmp_path)
    with patch.object(manager, "_run_job", lambda job: None):
        ids = manager.start_demo()
    assert len(ids) == 2
    assert [manager.jobs[i].name for i in ids] == ["QuickDelivery", "BudgetMaster"]
    qd_spec = (manager.jobs[ids[0]].folder / "spec.md").read_text(encoding="utf-8")
    canonical = (Path(__file__).resolve().parents[1] / "examples" /
                 "quickdelivery.md").read_text(encoding="utf-8")
    assert qd_spec == canonical
    assert "11. The main sections" in qd_spec
    assert "10 seconds" in qd_spec


@pytest.mark.parametrize("count", [0, -1, 4, 2.5, "2", True])
def test_bad_batch_size_rejected_without_side_effects(tmp_path, count):
    manager = BatchManager(tmp_path)
    with pytest.raises(ValueError, match="Job count"):
        manager.start_demo(count)
    assert not manager.jobs
    assert not list(tmp_path.iterdir())


def test_three_job_mode_remains_available(tmp_path):
    manager = BatchManager(tmp_path)
    with patch.object(manager, "_run_job", lambda job: None):
        ids = manager.start_demo(3)
    assert len(ids) == 3
    assert [manager.jobs[i].name for i in ids] == ["QuickDelivery", "BudgetMaster", "GroupChat"]


def test_all_demo_jobs_use_exact_spec_files(tmp_path):
    """Every job loads its own canonical Markdown without inlined duplicates."""
    manager = BatchManager(tmp_path)
    with patch.object(manager, "_run_job", lambda job: None):
        ids = manager.start_demo(3)
    for job_id, (name, spec_path) in zip(ids, DEMO_PROJECTS):
        assert manager.jobs[job_id].name == name
        assert (manager.jobs[job_id].folder / "spec.md").read_text(encoding="utf-8") == load_demo_spec(spec_path)


def test_demo_spec_files_have_expected_requirement_counts():
    from agents.requirements_validator import extract_requirements
    expected = {"QuickDelivery": 11, "BudgetMaster": 7, "GroupChat": 7}
    for name, path in DEMO_PROJECTS:
        assert len(extract_requirements(load_demo_spec(path))) == expected[name]


def test_missing_demo_spec_does_not_launch_workers(tmp_path):
    """Read all specs before creating job folders to avoid partial batches."""
    manager = BatchManager(tmp_path)
    with patch("batch_manager.load_demo_spec", side_effect=FileNotFoundError("missing spec")):
        with pytest.raises(FileNotFoundError, match="missing spec"):
            manager.start_demo(2)
    assert manager.jobs == {}
    assert not list(tmp_path.iterdir())


def test_batches_are_isolated_and_history_is_retained(tmp_path):
    """A new batch should not erase historical trace or job information."""
    manager = BatchManager(tmp_path)

    def finish_worker(job):
        job.status = "COMPLETED"

    with patch.object(manager, "_run_job", finish_worker):
        first_ids = manager.start_demo(2)
        first_batch = manager.latest_batch_id
        second_ids = manager.start_demo(2)
        second_batch = manager.latest_batch_id

    assert first_batch != second_batch
    assert set(first_ids).isdisjoint(second_ids)
    assert {r["job_id"] for r in manager.snapshot(first_batch)} == set(first_ids)
    assert {r["job_id"] for r in manager.snapshot(second_batch)} == set(second_ids)
    assert len(manager.snapshot()) == 4
    assert manager.snapshot("batch_unknown") == []
    assert all(r["batch_id"] == second_batch for r in manager.snapshot(second_batch))


def test_latest_batch_is_none_before_any_generation(tmp_path):
    manager = BatchManager(tmp_path)
    assert manager.latest_batch_id is None
    assert manager.snapshot() == []
