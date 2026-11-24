# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""
Gradio user interface of the AI Coder (entry point: python app.py).

The user enters a software description and requirements; the UI runs the
multi-agent MCP pipeline (client.py) and shows, live:
- progress of the Planner, Coder and Tester agents,
- the plan, every generated source file and the generated tests,
- pytest results and the headless app check,
- LLM usage (API calls and tokens) per agent.
It can also zip the generated application and launch it with Streamlit.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import gradio as gr

from client import DEFAULT_REQUIREMENTS, run_pipeline_steps

APP_PORT = 8502
SECRET_ENV_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
_app_process: subprocess.Popen | None = None


# ---------- helpers ----------

def load_example() -> tuple[str, str]:
    """Split examples/quickdelivery.md into (description, requirements)."""
    text = DEFAULT_REQUIREMENTS.read_text(encoding="utf-8")
    description, _, requirements = text.partition("Requirements:")
    return description.strip(), requirements.strip()


def build_spec(description: str, requirements: str) -> str:
    """Combine the two input fields into the text given to the agents."""
    return f"{description.strip()}\n\nRequirements:\n{requirements.strip()}\n"


def usage_rows(usage: dict) -> list[list]:
    """Turn usage.json into table rows: one per agent plus a total row."""
    rows = []
    for agent, u in usage["by_agent"].items():
        rows.append([agent.capitalize(), u["api_calls"], u["input_tokens"],
                     u["output_tokens"], u["total_tokens"]])
    t = usage["total"]
    rows.append(["TOTAL", t["api_calls"], t["input_tokens"],
                 t["output_tokens"], t["total_tokens"]])
    return rows


def zip_run(run_path: str) -> str:
    """Zip the generated application (incl. .streamlit theme, without caches)."""
    folder = Path(run_path)
    zip_path = folder.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in folder.rglob("*"):
            if file.is_file() and "__pycache__" not in file.parts:
                zf.write(file, arcname=f"{folder.name}/{file.relative_to(folder).as_posix()}")
    return str(zip_path)


def error_message(exc: BaseException) -> str:
    """Unwrap exception groups raised by the async MCP client into one message."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


# ---------- event handlers ----------

USAGE_HEADERS = ["Agent", "API calls", "Input tokens", "Output tokens", "Total tokens"]
TRACE_HEADERS = ["#", "MCP tool", "File / Run", "MCP status", "Tool result", "Duration (ms)", "Started (UTC)"]


def trace_rows(trace: dict) -> list[list]:
    """Flatten the per-run trace into an easy-to-review tool-call table."""
    rows = []
    for event in trace.get("events", []):
        metadata = event.get("metadata", {})
        target = metadata.get("filename") or metadata.get("run_id", "")
        tool_result = event.get("result_ok")
        rows.append([
            event["sequence"], event["tool"], target, event["status"],
            "N/A" if tool_result is None else ("OK" if tool_result else "FAILED"),
            event["duration_ms"], event["started_at"],
        ])
    return rows


def trace_summary(trace: dict) -> str:
    """Summarize MCP-level outcomes (not the generated app's pytest pass rate)."""
    stats = trace.get("summary", {})
    return (
        f"**MCP calls:** {stats.get('total_calls', 0)} · "
        f"**MCP errors:** {stats.get('failed_calls', 0)} · "
        f"**Total tool-call time:** {stats.get('duration_ms', 0) / 1000:.2f}s"
    )


async def generate(description: str, requirements: str):
    """Run the pipeline and stream progress and results into the UI."""
    if not description.strip() or not requirements.strip():
        raise gr.Error("Please enter both a description and requirements.")

    log_lines: list[str] = []
    empty = gr.update()

    def ui(status: str, **updates):
        """Build one UI update; unspecified outputs are left unchanged."""
        return (
            "\n".join(log_lines),
            status,
            updates.get("plan", empty),
            updates.get("selector", empty),
            updates.get("code", empty),
            updates.get("tests", empty),
            updates.get("pytest", empty),
            updates.get("usage", empty),
            updates.get("coverage", empty),
            updates.get("trace_summary", empty),
            updates.get("trace_table", empty),
            updates.get("trace_json", empty),
            updates.get("download", empty),
            updates.get("result", empty),
        )

    yield ui(
        "**Running...** the agents are working.",
        trace_summary="**MCP calls:** 0 · **MCP errors:** 0 · **Total tool-call time:** 0.00s",
        trace_table=[], trace_json={},
    )
    try:
        async for event in run_pipeline_steps(build_spec(description, requirements)):
            if event["type"] == "log":
                log_lines.append(event["message"])
                trace = event.get("trace", {})
                yield ui(
                    "**Running...** the agents are working.",
                    trace_summary=trace_summary(trace),
                    trace_table=trace_rows(trace),
                    # Keep the expanding JSON tree stable while streaming.
                    # The full trace is populated in the final result update.
                )
                continue

            result = event["result"]
            tests = result["tests"]
            app_check = result["app_check"]
            ok = "PASSED" if result["success"] else "FAILED"
            status = (
                f"### {'✅' if result['success'] else '⚠️'} {ok}: "
                f"{tests['passed']} tests passed, {tests['failed']} failed; "
                f"app check {'OK' if app_check['ok'] else 'FAILED'}\n"
                f"Output folder: `{result['path']}`"
            )
            if result["repaired"]:
                status += f"\n\nRepaired by agents: {', '.join(result['repaired'])}"

            sources = [n for n in result["files"] if n != result["test_file"]]
            pytest_text = tests["output"]
            if not app_check["ok"]:
                pytest_text += "\n\nApp check errors:\n" + "\n".join(app_check["exceptions"])

            yield ui(
                status,
                plan=result["plan"],
                selector=gr.update(choices=sources, value=sources[0]),
                code=result["files"][sources[0]],
                tests=result["files"][result["test_file"]],
                pytest=pytest_text,
                usage=usage_rows(result["usage"]),
                coverage=result["coverage"],
                trace_summary=trace_summary(result["execution_trace"]),
                trace_table=trace_rows(result["execution_trace"]),
                trace_json=result["execution_trace"],
                download=zip_run(result["path"]),
                result=result,
            )
    except Exception as exc:  # show any failure in the UI instead of crashing
        log_lines.append(f"ERROR: {error_message(exc)}")
        yield ui(f"### ❌ Generation failed\n`{error_message(exc)}`")


def show_file(filename: str, result: dict | None) -> str:
    """Show the selected generated source file."""
    if not result or not filename:
        return ""
    return result["files"].get(filename, "")


def launch_app(result: dict | None) -> str:
    """Start the generated Streamlit app (replacing a previous one) and return a link."""
    global _app_process
    if not result:
        raise gr.Error("Generate an application first.")
    if _app_process and _app_process.poll() is None:
        _app_process.terminate()
        _app_process.wait(timeout=10)

    env = {k: v for k, v in os.environ.items()
           if not any(w in k.upper() for w in SECRET_ENV_WORDS)}
    _app_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(APP_PORT), "--server.headless", "true"],
        cwd=result["path"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://localhost:{APP_PORT}"
    return f"Generated app is starting at **[{url}]({url})** (give it a few seconds)."


# ---------- layout ----------

with gr.Blocks(title="AI Coder") as demo:
    gr.Markdown(
        "# AI Coder\n"
        "Multi-agent system (Planner, Coder, Tester) connected through MCP. "
        "Enter a software description and requirements to generate a Python + "
        "Streamlit application and its pytest tests."
    )
    result_state = gr.State(None)

    with gr.Row():
        with gr.Column(scale=1):
            description_in = gr.Textbox(label="Software description", lines=3)
            requirements_in = gr.Textbox(label="Requirements", lines=12)
            with gr.Row():
                example_btn = gr.Button("Load QuickDelivery example")
                generate_btn = gr.Button("Generate", variant="primary")
        with gr.Column(scale=1):
            status_md = gr.Markdown("Waiting for input.")
            log_box = gr.Textbox(label="Agent progress", lines=16, max_lines=16,
                                 autoscroll=True, interactive=False)

    with gr.Tabs():
        with gr.Tab("Generated code"):
            file_selector = gr.Dropdown(label="File", choices=[], interactive=True)
            code_view = gr.Code(language="python", label="Source", interactive=False)
        with gr.Tab("Generated tests"):
            tests_view = gr.Code(language="python", label="test_app.py", interactive=False)
        with gr.Tab("Test results"):
            pytest_view = gr.Textbox(label="pytest output", lines=18, interactive=False)
        with gr.Tab("Plan"):
            plan_view = gr.JSON(label="Planner Agent output")
        with gr.Tab("LLM usage"):
            usage_table = gr.Dataframe(headers=USAGE_HEADERS, label="API calls and tokens",
                                       interactive=False)
        with gr.Tab("Requirements coverage"):
            gr.Markdown(
                "**Declared test mappings only.** A tag such as FR3 means a test "
                "claims relevance; it does not prove the requirement is satisfied. "
                "Unmapped UI requirements may still be exercised by app checks."
            )
            coverage_view = gr.JSON(label="Requirements-to-test traceability")
        with gr.Tab("MCP execution trace"):
            gr.Markdown(
                "MCP client-side tool calls, including repairs and failures. "
                "A successful MCP call can still return a failed pytest/app check. "
                "Only safe identifiers are logged; prompts and tool results are omitted."
            )
            trace_summary_md = gr.Markdown("Generate an app to see MCP calls.")
            trace_table_view = gr.Dataframe(
                headers=TRACE_HEADERS, label="MCP tool calls", interactive=False
            )
            gr.Markdown("The complete JSON appears after generation finishes; the table above updates live.")
            trace_json_view = gr.JSON(label="Execution trace (saved as execution_trace.json)")
        with gr.Tab("Run the app"):
            download_file = gr.File(label="Download generated application (.zip)")
            launch_btn = gr.Button("Launch generated app")
            launch_md = gr.Markdown()

    example_btn.click(load_example, outputs=[description_in, requirements_in])
    generate_btn.click(
        generate,
        inputs=[description_in, requirements_in],
        outputs=[log_box, status_md, plan_view, file_selector, code_view, tests_view,
                 pytest_view, usage_table, coverage_view, trace_summary_md,
                 trace_table_view, trace_json_view, download_file, result_state],
    )
    file_selector.change(show_file, inputs=[file_selector, result_state], outputs=code_view)
    launch_btn.click(launch_app, inputs=result_state, outputs=launch_md)


if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), inbrowser=True)
