"""Offline, no Docker/Gemini needed: concurrent job isolation and broker checks."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from batch_manager import BatchManager, DEMO_PROJECTS, load_demo_spec, allowed_verification_args, progress_html
from batch_rpc import atomic_json, read_json


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


def _run_reader_during_writes(path, payload, writes=200, writers=8):
    """Hammer `path` with writers while a reader polls it with no pause at all.

    The reader uses read_json(), the same reader the production code uses.
    Reader-thread failures are re-raised here so pytest reports a real failure,
    not just a thread warning. Returns the job numbers the reader observed.
    """
    stop = threading.Event()
    seen = []
    errors = []

    def reader():
        try:
            while not stop.is_set():
                data = read_json(path)  # must never be truncated/half-written JSON
                assert data["payload"] == payload, "reader saw a corrupted document"
                seen.append(data["job"])
        except BaseException as exc:  # re-raised in the test thread below
            errors.append(exc)

    reading = threading.Thread(target=reader)
    reading.start()
    try:
        with ThreadPoolExecutor(max_workers=writers) as pool:
            list(pool.map(lambda i: atomic_json(path, {"job": i, "payload": payload}),
                          range(writes)))
    finally:
        stop.set()
        reading.join(timeout=10)
    assert not reading.is_alive(), "reader thread did not stop"
    if errors:
        raise errors[0]
    assert seen, "reader never completed a read"
    return seen


def test_atomic_json_reader_never_sees_partial_document(tmp_path):
    """Concurrent writers + a tight-loop reader (far harsher than the 1 Hz UI poll)."""
    path = tmp_path / "progress.json"
    payload = "x" * 20000  # large enough that a torn write would be detectable
    atomic_json(path, {"job": -1, "payload": payload})
    _run_reader_during_writes(path, payload)
    assert read_json(path)["job"] in range(200)
    assert not list(tmp_path.glob("*.tmp"))


def test_open_reader_never_blocks_replace_with_windows_semantics(tmp_path, monkeypatch):
    """Regression for WinError 5 under a polling reader, reproducible on any OS.

    Emulates Windows sharing rules: os.replace() onto a file fails with
    WinError 5 while any reader still has it open (Python's open() does not use
    FILE_SHARE_DELETE). Readers and writers must be coordinated so this never
    happens; retries alone would only make the starvation less likely.
    """
    import batch_rpc
    path = tmp_path / "progress.json"
    payload = "y" * 2000
    atomic_json(path, {"job": -1, "payload": payload})
    real_read, real_replace = batch_rpc._read_bytes, batch_rpc.os.replace
    open_handles = 0
    counter = threading.Lock()
    collisions = []

    def windows_like_read(p):
        nonlocal open_handles
        with counter:
            open_handles += 1
        try:
            time.sleep(0.0005)  # keep the "handle" open for a moment
            return real_read(p)
        finally:
            with counter:
                open_handles -= 1

    def windows_like_replace(src, dst):
        if Path(dst) == path and open_handles:
            collisions.append(dst)
            raise _win_error(5)
        return real_replace(src, dst)

    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", True)
    monkeypatch.setattr(batch_rpc, "_read_bytes", windows_like_read)
    monkeypatch.setattr(batch_rpc.os, "replace", windows_like_replace)
    _run_reader_during_writes(path, payload, writes=100)
    assert collisions == [], f"{len(collisions)} replaces hit an open reader handle"
    assert read_json(path)["job"] in range(100)
    assert not list(tmp_path.glob("*.tmp"))


def test_read_json_retries_transient_windows_lock_then_reads(tmp_path, monkeypatch):
    """Another process (antivirus, indexer) may briefly hold the file."""
    import batch_rpc
    path = tmp_path / "progress.json"
    atomic_json(path, {"version": 1})
    real_read = batch_rpc._read_bytes
    failures = [_win_error(32), _win_error(5)]

    def flaky_read(p):
        if failures:
            raise failures.pop(0)
        return real_read(p)

    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", True)
    monkeypatch.setattr(batch_rpc, "_read_bytes", flaky_read)
    monkeypatch.setattr(batch_rpc.time, "sleep", lambda s: None)
    assert read_json(path) == {"version": 1}


def test_read_json_does_not_retry_real_errors(tmp_path, monkeypatch):
    import batch_rpc
    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", True)
    monkeypatch.setattr(batch_rpc.time, "sleep", lambda s: pytest.fail("must not retry"))
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / "missing.json")


def test_retry_sleep_does_not_hold_the_file_lock(tmp_path, monkeypatch):
    """While a writer backs off, the same file's lock is free for readers."""
    import batch_rpc
    path = tmp_path / "progress.json"
    atomic_json(path, {"version": 1})
    failures = [_win_error(5)]
    real_replace = batch_rpc.os.replace
    lock_free_during_sleep = []

    def flaky_replace(src, dst):
        if failures:
            raise failures.pop(0)
        return real_replace(src, dst)

    def sleep(seconds):
        lock = batch_rpc._lock_for(path)
        lock_free_during_sleep.append(lock.acquire(blocking=False))
        if lock_free_during_sleep[-1]:
            lock.release()

    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", True)
    monkeypatch.setattr(batch_rpc.os, "replace", flaky_replace)
    monkeypatch.setattr(batch_rpc.time, "sleep", sleep)
    atomic_json(path, {"version": 2})
    assert lock_free_during_sleep == [True]
    assert read_json(path) == {"version": 2}


def test_manager_progress_uses_coordinated_reader(tmp_path):
    """Production reader of progress.json goes through read_json()."""
    manager = BatchManager(tmp_path)
    folder = tmp_path / "job_p"
    folder.mkdir()
    from batch_manager import Job
    manager.jobs["job_p"] = Job("job_p", "QuickDelivery", folder)
    atomic_json(folder / "progress.json", {"status": "RUNNING", "percent": 42, "message": "m"})
    with patch("batch_manager.read_json", wraps=read_json) as reader:
        assert manager.progress("job_p")["percent"] == 42
    reader.assert_called_once_with(folder / "progress.json")


def _win_error(winerror: int) -> PermissionError:
    """A PermissionError shaped like the one Windows raises from os.replace()."""
    exc = PermissionError(13, "Access is denied", None, winerror)
    if getattr(exc, "winerror", None) != winerror:  # attribute only exists on Windows
        exc.winerror = winerror
    return exc


def _flaky_replace(batch_rpc, failures: list):
    """os.replace() that raises the queued exceptions before succeeding."""
    real_replace = batch_rpc.os.replace
    calls = []

    def replace(src, dst):
        calls.append(dst)
        if failures:
            raise failures.pop(0)
        return real_replace(src, dst)
    return replace, calls


@pytest.mark.parametrize("winerror", [5, 32])  # ACCESS_DENIED, SHARING_VIOLATION
def test_atomic_json_retries_transient_windows_lock(tmp_path, monkeypatch, winerror):
    import batch_rpc
    path = tmp_path / "progress.json"
    atomic_json(path, {"version": 1})
    replace, calls = _flaky_replace(batch_rpc, [_win_error(winerror) for _ in range(3)])
    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", True)
    monkeypatch.setattr(batch_rpc.os, "replace", replace)
    monkeypatch.setattr(batch_rpc.time, "sleep", lambda s: None)
    atomic_json(path, {"version": 2})
    assert len(calls) == 4
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2}
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_persistent_lock_raises_and_keeps_old_document(tmp_path, monkeypatch):
    """Retries are bounded; on failure the old file is intact and no temp file leaks."""
    import batch_rpc
    path = tmp_path / "progress.json"
    atomic_json(path, {"version": 1})
    replace, calls = _flaky_replace(
        batch_rpc, [_win_error(5) for _ in range(batch_rpc._REPLACE_ATTEMPTS + 5)])
    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", True)
    monkeypatch.setattr(batch_rpc.os, "replace", replace)
    monkeypatch.setattr(batch_rpc.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        atomic_json(path, {"version": 2})
    assert len(calls) == batch_rpc._REPLACE_ATTEMPTS
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("on_windows, error", [
    # A real permission problem (no winerror) must not be retried, even on Windows.
    (True, PermissionError(13, "Permission denied")),
    # Other Windows errors, e.g. 1314 ERROR_PRIVILEGE_NOT_HELD, are not file locks.
    (True, "winerror-1314"),
    # Off Windows nothing is retried, even if an error carries winerror 5.
    (False, "winerror-5"),
    (True, FileNotFoundError(2, "No such file or directory")),
])
def test_atomic_json_does_not_retry_non_transient_errors(tmp_path, monkeypatch, on_windows, error):
    import batch_rpc
    if isinstance(error, str):
        error = _win_error(int(error.split("-")[1]))
    path = tmp_path / "progress.json"
    atomic_json(path, {"version": 1})
    replace, calls = _flaky_replace(batch_rpc, [error])
    monkeypatch.setattr(batch_rpc, "_ON_WINDOWS", on_windows)
    monkeypatch.setattr(batch_rpc.os, "replace", replace)
    monkeypatch.setattr(batch_rpc.time, "sleep", lambda s: pytest.fail("must not retry"))
    with pytest.raises(type(error)):
        atomic_json(path, {"version": 2})
    assert len(calls) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}
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
