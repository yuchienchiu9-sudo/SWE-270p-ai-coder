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
import threading

from project_dependencies import DependencyNotApproved, image_for_dependencies, resolve_dependencies
from pathlib import Path

SANDBOX_IMAGE = "ai-coder-test-sandbox:local"
RUNNER_ENV = "AI_CODER_RUNNER"
_IMAGE_BUILD_LOCK = threading.Lock()
_BUILT_IMAGES: set[str] = set()


class SandboxUnavailable(RuntimeError):
    """The sandbox cannot start; do not run generated code on the host."""



def _ensure_project_image(run: Path) -> str:
    """Build a cached image for this run's approved packages on the trusted host.

    Only this build stage has network access. Subsequent execution remains offline,
    keyless, read-only, and does not run pip or a shell.
    """
    try:
        packages = resolve_dependencies(run)
    except (DependencyNotApproved, OSError, UnicodeError) as exc:
        raise SandboxUnavailable(f"Project dependencies rejected: {exc}") from exc
    image = image_for_dependencies(packages)
    if not packages:
        return image  # The normal sandbox image is built during setup.
    with _IMAGE_BUILD_LOCK:
        if image in _BUILT_IMAGES:
            return image
        # Reuse an existing tagged image across server restarts.
        try:
            inspect = subprocess.run(
                ["docker", "image", "inspect", image], capture_output=True,
                text=True, timeout=10,
            )
            if inspect.returncode != 0:
                build = subprocess.run(
                    ["docker", "build", "--pull=false", "-f", "Dockerfile.sandbox",
                     "--build-arg", "EXTRA_PACKAGES=" + " ".join(packages),
                     "-t", image, "."],
                    cwd=Path(__file__).resolve().parent,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    timeout=240,
                )
                if build.returncode != 0:
                    raise SandboxUnavailable(
                        "Approved dependency image build failed: " + build.stderr[-1000:]
                    )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxUnavailable(f"Cannot prepare dependency image: {exc}") from exc
        _BUILT_IMAGES.add(image)
    return image


def run_generated_python(
    run: Path, args: list[str], *, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Execute generated Python in Docker, or in explicitly selected host mode.

    Docker limits are a defense-in-depth boundary, not a security guarantee.
    Approved per-run extras are installed during a trusted image build only.
    Never install packages while executing untrusted generated code.
    """
    # Job containers never access the host Docker socket. Instead, the host
    # dispatches approved verification commands to the existing Docker sandbox.
    if os.environ.get("AI_CODER_BROKER_DIR"):
        from batch_rpc import remote_run
        return remote_run(run, args, timeout)

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

    image = _ensure_project_image(path)

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
        image, "python", *args,
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
