"""File-based RPC between a containerized job worker and the host test runner.

The host owns Docker. No Docker socket, API key or host home directory is mounted
inside the generated-code test container. This is a LOCAL DEVELOPMENT protocol.
"""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

RPC_ENV = "AI_CODER_BROKER_DIR"


def atomic_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


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
