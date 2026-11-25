"""File-based RPC between a containerized job worker and the host test runner.

The host owns Docker. No Docker socket, API key or host home directory is mounted
inside the generated-code test container. This is a LOCAL DEVELOPMENT protocol.
"""
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

RPC_ENV = "AI_CODER_BROKER_DIR"

# Writers in this process that target the same file take the same lock, so they
# never race each other's os.replace(). A fixed set of locks keeps memory bounded
# even though request/response file names are unique.
_WRITE_LOCKS = tuple(threading.Lock() for _ in range(64))
# On Windows, os.replace() fails while another handle has the destination open
# (e.g. a reader polling progress.json, antivirus, or a rename in another
# process). Such locks are short-lived, so only these errors are retried briefly:
#   5  ERROR_ACCESS_DENIED     32  ERROR_SHARING_VIOLATION
# Every other error, including real POSIX permission errors, is raised at once.
_ON_WINDOWS = os.name == "nt"
_TRANSIENT_WINERRORS = frozenset({5, 32})
_REPLACE_ATTEMPTS = 10
_REPLACE_FIRST_DELAY_S = 0.01
_REPLACE_MAX_DELAY_S = 0.1


def _lock_for(path: Path) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(path))
    return _WRITE_LOCKS[hash(key) % len(_WRITE_LOCKS)]


def _is_transient_windows_lock(exc: OSError) -> bool:
    return _ON_WINDOWS and getattr(exc, "winerror", None) in _TRANSIENT_WINERRORS


def _replace_with_retry(source: Path, target: Path) -> None:
    """os.replace(), retrying only transient Windows file-lock errors."""
    delay = _REPLACE_FIRST_DELAY_S
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(source, target)
            return
        except OSError as exc:
            if attempt == _REPLACE_ATTEMPTS or not _is_transient_windows_lock(exc):
                raise
            time.sleep(delay)
            delay = min(delay * 2, _REPLACE_MAX_DELAY_S)


def atomic_json(path: Path, data: dict) -> None:
    """Write JSON so readers see either the old or the new complete document.

    The content goes to a unique temporary file first and is then renamed over
    the target; the target is never written in place.
    """
    path = Path(path)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with _lock_for(path):
            _replace_with_retry(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def remote_run(run: Path, args: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Ask the host to execute ONLY an approved test or Streamlit app check."""
    from sandbox_runner import SandboxUnavailable
    directory = Path(os.environ[RPC_ENV])
    request_id = uuid.uuid4().hex
    if run.name.startswith("run_") is False:
        raise SandboxUnavailable("Invalid run directory")
    request = directory / f"request_{request_id}.json"
    response = directory / f"response_{request_id}.json"
    atomic_json(request, {"run_id": run.name, "args": args, "timeout": timeout})
    deadline = time.monotonic() + timeout + 260  # Covers one-time approved-image build.
    while time.monotonic() < deadline:
        if response.is_file():
            try:
                data = json.loads(response.read_text(encoding="utf-8"))
            finally:
                response.unlink(missing_ok=True)
            if data.get("error") == "timeout":
                raise subprocess.TimeoutExpired(args, timeout)
            if data.get("error"):
                raise SandboxUnavailable(str(data["error"]))
            return subprocess.CompletedProcess(args, data["returncode"], data["stdout"], data["stderr"])
        time.sleep(0.1)
    raise SandboxUnavailable("Host sandbox broker did not respond in time")
