# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Per-run MCP client-side tool tracing without recording sensitive arguments."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Any


class ExecutionTrace:
    """Record MCP tool calls; save snapshots inside the generated run folder."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._output: Path | None = None

    def set_run_folder(self, folder: str | Path) -> None:
        """Enable persistence once create_run has returned a workspace path."""
        path = Path(folder)
        if not path.is_dir():
            raise ValueError(f"Run folder does not exist: {path}")
        self._output = path / "execution_trace.json"
        self._save()

    async def call(self, call_fn: Callable[..., Awaitable[Any]], session: Any,
                   name: str, **arguments: Any) -> Any:
        """Call the original MCP wrapper, including errors, and record its timing.

        Only non-sensitive identifiers are retained. A successful MCP tool call
        can still return {"ok": False} (e.g. pytest found failing tests).
        """
        started = datetime.now(timezone.utc).isoformat()
        begin = time.perf_counter()
        status = "success"
        result_ok = None
        try:
            result = await call_fn(session, name, **arguments)
            if isinstance(result, dict) and isinstance(result.get("ok"), bool):
                result_ok = result["ok"]
            return result
        except Exception:
            status = "error"
            raise
        finally:
            metadata = {
                key: arguments[key]
                for key in ("run_id", "filename")
                if isinstance(arguments.get(key), str)
            }
            self.events.append({
                "sequence": len(self.events) + 1,
                "tool": name,
                "started_at": started,
                "duration_ms": round((time.perf_counter() - begin) * 1000, 2),
                "status": status,
                "result_ok": result_ok,
                "metadata": metadata,
            })
            self._save()

    def to_dict(self) -> dict:
        """Return a JSON-serializable snapshot and aggregate statistics."""
        return {
            "summary": {
                "total_calls": len(self.events),
                "successful_calls": sum(e["status"] == "success" for e in self.events),
                "failed_calls": sum(e["status"] == "error" for e in self.events),
                "duration_ms": round(sum(e["duration_ms"] for e in self.events), 2),
            },
            "events": list(self.events),
        }

    def _save(self) -> None:
        """Persist a snapshot, including when a later MCP tool fails.

        Reporting must not interrupt code generation if the disk write fails.
        """
        if self._output is None:
            return
        try:
            temporary = self._output.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
            temporary.replace(self._output)
        except OSError:
            pass
