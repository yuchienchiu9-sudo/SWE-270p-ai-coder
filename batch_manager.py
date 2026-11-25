"""Local three-job concurrent container manager and host-owned sandbox broker.

Each trusted Worker gets its own container and directory. A separate host
broker executes *only* the two permitted generated-code verification commands
inside the existing keyless Docker sandbox. No Docker socket is shared.
"""
import html
import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from batch_rpc import atomic_json
from sandbox_runner import SandboxUnavailable, run_generated_python

PROJECT_ROOT = Path(__file__).resolve().parent
BATCH_ROOT = PROJECT_ROOT / "batch_runs"
WORKER_IMAGE = "ai-coder-worker:local"
RUN_ID = re.compile(r"^run_\d{8}_\d{6}(?:_\d+)?$")

# Demo-only specifications live alongside the canonical QuickDelivery example.
# Every entry uses the same file-based source of truth.
DEMO_PROJECTS = (
    ("QuickDelivery", "examples/quickdelivery.md"),
    ("BudgetMaster", "examples/demo_specs/budgetmaster.md"),
    ("GroupChat", "examples/demo_specs/groupchat.md"),
)


def load_demo_spec(relative_path: str) -> str:
    """Load a checked-in project specification before launching its worker."""
    path = PROJECT_ROOT / relative_path
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Empty demo specification: {relative_path}")
    return content


def allowed_verification_args(args: list[str]) -> bool:
    """Never grant a worker arbitrary host command execution."""
    if args == ["-m", "pytest", "test_app.py", "-q", "-p", "no:cacheprovider"]:
        return True
    if len(args) == 4 and args[:3] == ["-W", "ignore", "-c"]:
        from mcp_server import APP_CHECK_SCRIPT
        return args[3] == APP_CHECK_SCRIPT
    return False


@dataclass
class Job:
    job_id: str
    name: str
    folder: Path
    status: str = "STARTING"
    error: str = ""
    batch_id: str = ""


class BatchManager:
    """Demo manager starts all jobs without an application-level queue."""

    def __init__(self, root: Path = BATCH_ROOT):
        self.root = Path(root)
        self.jobs: dict[str, Job] = {}
        self.latest_batch_id: str | None = None
        self.lock = threading.Lock()

    def start_demo(self, count: int = 2) -> list[str]:
        """Start 1-3 independent jobs simultaneously; no application queue."""
        if type(count) is not int or not 1 <= count <= len(DEMO_PROJECTS):
            raise ValueError("Job count must be an integer from 1 to 3")
        # Protect against duplicate clicks that otherwise launch another batch.
        with self.lock:
            if any(j.status in ("STARTING", "RUNNING") for j in self.jobs.values()):
                raise RuntimeError("A demo batch is already running")
            # Validate inputs before creating any job folders.
            selected = [(name, load_demo_spec(path)) for name, path in DEMO_PROJECTS[:count]]
            self.root.mkdir(parents=True, exist_ok=True)
            jobs = []
            batch_id = "batch_" + uuid.uuid4().hex[:12]
            for name, spec in selected:
                job_id = "job_" + uuid.uuid4().hex[:12]
                folder = self.root / job_id
                folder.mkdir(mode=0o777)
                folder.chmod(0o777)  # Docker's unprivileged uid can write results
                (folder / "control").mkdir(mode=0o777)
                (folder / "control").chmod(0o777)
                (folder / "spec.md").write_text(spec, encoding="utf-8")
                job = Job(job_id, name, folder, batch_id=batch_id)
                self.jobs[job_id] = job
                jobs.append(job)
            self.latest_batch_id = batch_id
        for job in jobs:
            threading.Thread(target=self._run_job, args=(job,), daemon=True).start()
        return [j.job_id for j in jobs]

    def _handle_request(self, job: Job, request: Path) -> None:
        """Host receives an RPC, validates it, then creates a keyless test container."""
        response = request.with_name(request.name.replace("request_", "response_"))
        try:
            data = json.loads(request.read_text(encoding="utf-8"))
            run_id, args = data["run_id"], data["args"]
            if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
                raise ValueError("Invalid run ID")
            if not isinstance(args, list) or not allowed_verification_args(args):
                raise ValueError("Verification command not allowed")
            run_dir = job.folder / "generated" / run_id
            if not run_dir.is_dir() or run_dir.is_symlink():
                raise ValueError("Run directory does not exist")
            timeout = 60  # Host-controlled, not worker-controlled.
            result = run_generated_python(run_dir, args, timeout=timeout)
            payload = {"returncode": result.returncode,
                       "stdout": result.stdout[-12000:], "stderr": result.stderr[-12000:]}
        except subprocess.TimeoutExpired:
            payload = {"error": "timeout"}
        except (SandboxUnavailable, ValueError, OSError, KeyError, TypeError) as exc:
            payload = {"error": f"{type(exc).__name__}: {exc}"[:900]}
        finally:
            request.unlink(missing_ok=True)
        atomic_json(response, payload)

    def _broker(self, job: Job, stop: threading.Event):
        control = job.folder / "control"
        while not stop.is_set():
            for request in sorted(control.glob("request_*.json")):
                self._handle_request(job, request)
            stop.wait(0.08)

    def _run_job(self, job: Job):
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            job.status, job.error = "FAILED", "GEMINI_API_KEY missing in .env"
            return
        cmd = ["docker", "run", "--rm", "--pull=never", "--name", job.job_id,
               "--network=bridge", "--read-only", "--cap-drop=ALL",
               "--security-opt=no-new-privileges:true", "--pids-limit=128",
               "--memory=1g", "--cpus=1", "--user=65534:65534",
               "--tmpfs=/tmp:rw,nosuid,size=64m", "--env=HOME=/tmp",
               "--env=GEMINI_API_KEY", "--env=GEMINI_MODEL",
               "--env=AI_CODER_OUTPUT_DIR=/job/generated",
               "--env=AI_CODER_JOB_DIR=/job", "--env=AI_CODER_BROKER_DIR=/job/control",
               "--mount", f"type=bind,source={job.folder.resolve()},target=/job",
               WORKER_IMAGE]
        env = dict(os.environ)
        env["GEMINI_API_KEY"] = key  # Passed through Docker env; never on argv.
        env.setdefault("GEMINI_MODEL", "gemini-3.5-flash-lite")
        stop = threading.Event()
        broker = threading.Thread(target=self._broker, args=(job, stop), daemon=True)
        broker.start()
        job.status = "RUNNING"
        try:
            with (job.folder / "worker.log").open("w", encoding="utf-8") as output:
                proc = subprocess.Popen(cmd, env=env, stdout=output, stderr=subprocess.STDOUT)
                try:
                    code = proc.wait(timeout=1200)
                except subprocess.TimeoutExpired:
                    subprocess.run(["docker", "rm", "-f", job.job_id],
                                   capture_output=True, timeout=10)
                    job.status, job.error = "FAILED", "Job exceeded 20 minute limit"
                    return
            progress = self.progress(job.job_id)
            job.status = "COMPLETED" if code == 0 else "FAILED"
            if code != 0:
                job.error = progress.get("message", "Worker exited with error")
        except (OSError, subprocess.TimeoutExpired) as exc:
            job.status, job.error = "FAILED", f"Container launch failed: {exc}"
        finally:
            stop.set()
            broker.join(timeout=2)

    def progress(self, job_id: str) -> dict:
        job = self.jobs[job_id]
        path = job.folder / "progress.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return {"status": job.status, "percent": 0, "message": job.error or "Starting"}

    def snapshot(self, batch_id: str | None = None) -> list[dict]:
        """Return all known jobs, or only jobs belonging to one batch."""
        with self.lock:
            jobs = [job for job in self.jobs.values()
                    if batch_id is None or job.batch_id == batch_id]
        rows = []
        for job in jobs:
            prog = self.progress(job.job_id)
            # Manager terminal status is authoritative.
            status = job.status if job.status in ("COMPLETED", "FAILED") else prog["status"]
            rows.append({"job_id": job.job_id, "batch_id": job.batch_id, "name": job.name,
                         "status": status, "percent": prog.get("percent", 0),
                         "message": job.error or prog.get("message", ""),
                         "path": str(job.folder / "generated")})
        return rows

    def inspect(self, job_id: str) -> tuple[dict, dict, str]:
        if job_id not in self.jobs:
            return {}, {}, ""
        folder = self.jobs[job_id].folder
        runs = sorted((folder / "generated").glob("run_*")) if (folder / "generated").exists() else []
        trace, usage = {}, {}
        if runs:
            for source, name in (("trace", "execution_trace.json"), ("usage", "usage.json")):
                path = runs[-1] / name
                try:
                    value = json.loads(path.read_text())
                except (OSError, ValueError):
                    value = {}
                if source == "trace":
                    trace = value
                else:
                    usage = value
        log = folder / "worker.log"
        try:
            log_tail = "\n".join(log.read_text(encoding="utf-8").splitlines()[-25:])
        except OSError:
            log_tail = ""
        return trace, usage, log_tail


manager = BatchManager()


def progress_html(rows: list[dict]) -> str:
    """Render accessible progress bars without trusting text from the LLM."""
    return "".join(
        '<div style="margin:8px 0"><div style="display:flex;justify-content:space-between">'
        f'<b>{html.escape(r["name"])}</b><span>{html.escape(r["status"])} · {int(r["percent"])}%</span>'
        '</div><progress style="width:100%" max="100" value="'
        f'{max(0,min(100,int(r["percent"])))}"></progress>'
        f'<small>{html.escape(r["message"][-140:])}</small></div>' for r in rows
    ) or '<p>No batch launched yet.</p>'
