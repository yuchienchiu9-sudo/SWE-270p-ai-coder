# Name: Yu-Chien Chiu
# Student ID: 56176405
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
    """Zip the generated application (without caches) and return the zip path."""
    folder = Path(run_path)
    zip_path = folder.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in folder.iterdir():
            if file.is_file():
                zf.write(file, arcname=f"{folder.name}/{file.name}")
    return str(zip_path)


def error_message(exc: BaseException) -> str:
    """Unwrap exception groups raised by the async MCP client into one message."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


# ---------- event handlers ----------

USAGE_HEADERS = ["Agent", "API calls", "Input tokens", "Output tokens", "Total tokens"]


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
            updates.get("download", empty),
            updates.get("result", empty),
        )

    yield ui("**Running...** the agents are working.")
    try:
        async for event in run_pipeline_steps(build_spec(description, requirements)):
            if event["type"] == "log":
                log_lines.append(event["message"])
                yield ui("**Running...** the agents are working.")
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
        with gr.Tab("Run the app"):
            download_file = gr.File(label="Download generated application (.zip)")
            launch_btn = gr.Button("Launch generated app")
            launch_md = gr.Markdown()

    example_btn.click(load_example, outputs=[description_in, requirements_in])
    generate_btn.click(
        generate,
        inputs=[description_in, requirements_in],
        outputs=[log_box, status_md, plan_view, file_selector, code_view, tests_view,
                 pytest_view, usage_table, download_file, result_state],
    )
    file_selector.change(show_file, inputs=[file_selector, result_state], outputs=code_view)
    launch_btn.click(launch_app, inputs=result_state, outputs=launch_md)


if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), inbrowser=True)
