# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Run untrusted generated Python in a restricted Docker container.

Docker is the default; local execution requires explicit developer opt-in.
The container receives only the generated run folder, mounted read-only.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

SANDBOX_IMAGE = "ai-coder-test-sandbox:local"
RUNNER_ENV = "AI_CODER_RUNNER"


class SandboxUnavailable(RuntimeError):
    """The sandbox cannot start; do not run generated code on the host."""


def run_generated_python(
    run: Path, args: list[str], *, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Execute generated Python in Docker, or in explicitly selected host mode.

    Docker limits are a defense-in-depth boundary, not a security guarantee.
    The image must be built separately; never install packages at runtime.
    """
    runner = os.environ.get(RUNNER_ENV, "docker").strip().lower()
    if runner == "host":
        # This mode is intentionally opt-in and is NOT a security sandbox.
        secret_words = ("KEY", "TOKEN", "SECRET", "PASSWORD")
        clean_env = {
            key: value for key, value in os.environ.items()
            if not any(word in key.upper() for word in secret_words)
        }
        return subprocess.run(
            [sys.executable, *args], cwd=run, env=clean_env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout,
        )
    if runner != "docker":
        raise SandboxUnavailable(
            f"Invalid {RUNNER_ENV}={runner!r}; expected 'docker' or 'host'."
        )

    path = run.resolve(strict=True)
    if not path.is_dir():
        raise SandboxUnavailable("Generated run folder is not a directory.")

    # A unique name lets us forcibly remove a container after a timeout.
    container_name = "ai-coder-test-" + uuid.uuid4().hex
    # No shell: generated filenames and arguments are passed as distinct argv.
    cmd = [
        "docker", "run", "--rm", "--name", container_name,
        "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=64", "--memory=512m", "--cpus=1",
        "--user=65534:65534", "--workdir=/workspace",
        "--tmpfs=/tmp:rw,nosuid,size=64m",
        "--env=HOME=/tmp", "--env=PYTHONDONTWRITEBYTECODE=1",
        "--env=PYTHONPATH=/workspace",
        "--env=STREAMLIT_BROWSER_GATHER_USAGE_STATS=false",
        "--env=PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "--mount", f"type=bind,source={path},target=/workspace,readonly",
        SANDBOX_IMAGE, "python", *args,
    ]
    try:
        result = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # Killing docker CLI alone may leave its container running.
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    except FileNotFoundError as exc:
        raise SandboxUnavailable(
            "Docker CLI not found. Install and start Docker Desktop, then "
            "build the sandbox image before generating apps."
        ) from exc
    except OSError as exc:
        raise SandboxUnavailable(f"Docker could not start: {exc}") from exc

    # Docker itself returns 125/126/127 for runtime/configuration failures.
    if result.returncode in (125, 126, 127):
        raise SandboxUnavailable(
            "Docker sandbox could not start. Build the image using "
            "'docker build -f Dockerfile.sandbox -t " + SANDBOX_IMAGE +
            " .' and check Docker Desktop. Details: " + result.stderr[-700:]
        )
    return result
