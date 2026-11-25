# AI Coder: Multi-Agent Code Generation with MCP

SWE 270P Final Project. Authors: Yu-Chien Chiu (56176405), Mars Huang (79666292)

AI Coder takes a **software description and requirements** in a web UI and
generates a complete **Python + Streamlit application with pytest tests**.
Three agents (Planner, Coder, Tester) work behind an **MCP server**, and an MCP
client coordinates them. The system runs the generated tests, checks that the
app starts, repairs failures, reports **requirements-to-test traceability**,
tracks **LLM usage (API calls and tokens)**, and records **MCP tool execution traces**.

Our selected application is **QuickDelivery**, a simplified food delivery app.
QuickDelivery is the *output* of AI Coder; its requirements are in
[examples/quickdelivery.md](examples/quickdelivery.md), and a generated sample
is in [examples/sample_output/](examples/sample_output/).

---

## Quick start

Requirements: Python 3.12, a Gemini API key, and Docker Desktop (running) for sandboxed verification.

```bash
# 1. Create the environment (conda shown; venv works too)
conda create -n swe270p-ai python=3.12 -y
conda activate swe270p-ai
pip install -r requirements.txt

# 2. Add your API key
copy .env.example .env        # macOS/Linux: cp .env.example .env
#    then edit .env and set GEMINI_API_KEY

# 3. Build the verification sandbox and concurrent worker images
docker build -f Dockerfile.sandbox -t ai-coder-test-sandbox:local .
docker build -f Dockerfile.worker -t ai-coder-worker:local .

# 4. Start the UI (opens http://127.0.0.1:7860)
python app.py
```

In the UI:

1. Click **Load QuickDelivery example** (or type your own description and requirements).
2. Click **Generate**. Agent progress streams live (about 1–2 minutes).
3. Inspect the tabs: **Generated code**, **Generated tests**, **Test results**,
   **Plan**, **LLM usage**, **Requirements coverage**, **MCP execution trace**.
4. In **Run the app**, download the zip or click **Launch generated app**
   (opens the generated app at http://localhost:8502).

For parallel generation, open **Concurrent jobs (demo)**, choose 1–3 demo
projects, and click **Generate selected projects concurrently**. Track each
job's progress and inspect its trace, usage, and logs. **Current batch** shows
the latest batch; **All jobs** shows history from the running server process.

Command-line alternative (same pipeline, no UI):

```bash
python client.py                        # uses examples/quickdelivery.md
python client.py my_requirements.md     # any requirements file
```

Each run is saved to `generated/run_<timestamp>/`. To run a generated app
yourself, start Streamlit **from inside that folder** so its theme loads.
**These manual commands run on your host, outside the sandbox; only run trusted code:**

```bash
cd generated/run_<timestamp>
streamlit run app.py
pytest test_app.py
```

---

## Architecture

```
┌────────────────────┐
│ app.py (Gradio UI) │  description + requirements in; code, tests, results, usage out
└─────────┬──────────┘
          │ async events
┌─────────▼──────────┐
│ client.py          │  MCP client / orchestrator: calls tools in a fixed order
└─────────┬──────────┘
          │ MCP over stdio (client starts the server as a subprocess)
┌─────────▼──────────────────────────────────────────────────────────────┐
│ mcp_server.py  (MCP server, 10 tools)                                   │
│                                                                        │
│  Agent tools        plan ─────────► Planner Agent  ─┐                  │
│                     write_code ───► Coder Agent    ─┼─► llm.py ─► Gemini│
│                     write_tests ──► Tester Agent   ─┘   (retry + usage)│
│  Workspace tools    create_run, list_files, read_file                  │
│  Verification       run_tests (pytest), check_app (headless Streamlit) │
│  Coverage           validate_requirements (FR-to-test traceability)    │
│  Usage              get_usage                                          │
│                                                                        │
│  Shared workspace   generated/run_<timestamp>/                         │
│                     requirements.md → plan.json → *.py → test_app.py   │
└────────────────────────────────────────────────────────────────────────┘
```

### How the agents communicate through MCP

The agents never call each other. Each agent is exposed as an MCP tool, and
each one **reads its input from the workspace and writes its output back to
it**. The next agent picks that output up from the server:

1. `create_run` stores the user's requirements as `requirements.md`.
2. **Planner** (`plan`) reads `requirements.md` and writes `plan.json`.
3. **Coder** (`write_code`, once per file) reads `plan.json` plus only the files
   that file depends on, and writes one source file.
4. **Tester** (`write_tests`) reads `plan.json` and all source files, and writes `test_app.py`.
5. `run_tests` and `check_app` verify the result in short-lived Docker
   containers; failures are routed back to an agent.
6. `validate_requirements` maps numbered functional requirements (FR1, FR2, etc.)
   to generated pytest tests using docstring annotations. It runs after any
   repairs and saves `coverage_report.json`.

### Agents

| Agent | Role | Reads | Writes |
|---|---|---|---|
| Planner | Turns requirements into a file-by-file design: features, files in dependency order, each file's purpose and dependencies, pip packages, and a theme color | `requirements.md` | `plan.json`, `requirements.txt`, `.streamlit/config.toml` |
| Coder | Writes one file at a time. Logic modules are plain Python (unit-testable); `app.py` is the Streamlit UI | plan + dependency files (+ current file and error report when repairing) | `<module>.py` |
| Tester | Writes one pytest file covering the logic modules, using only names that exist in the code | plan + all source files (+ failure report when repairing) | `test_app.py` |

### MCP tools

| Tool | Purpose |
|---|---|
| `create_run(requirements)` | New workspace folder; saves the requirements |
| `list_files(run_id)`, `read_file(run_id, filename)` | Inspect the workspace |
| `plan(run_id)` | Planner Agent |
| `write_code(run_id, filename, feedback="")` | Coder Agent (feedback = repair mode) |
| `write_tests(run_id, feedback="")` | Tester Agent (feedback = repair mode) |
| `run_tests(run_id)` | Run pytest; returns passed/failed counts and output |
| `check_app(run_id)` | Load `app.py` once with Streamlit's headless `AppTest` and report exceptions |
| `validate_requirements(run_id)` | Maps functional requirements to generated tests and saves `coverage_report.json` |
| `get_usage(run_id)` | API calls and tokens per agent and in total |

### Collaboration pattern and repair

The client uses a **fixed pipeline** instead of letting an LLM choose tools.
This keeps the number of API calls small and predictable, which matters because
efficiency (tokens and API calls) is graded.

```
create_run → plan → write_code × N files → write_tests → run_tests + check_app
           → repair (only if needed) → validate_requirements → get_usage
```

Repair runs each stage at most once. The requirements are the source of truth,
so the code is fixed before the tests:

1. If `app.py` crashes on load, the Coder fixes `app.py` using the exception.
2. If tests fail, the client finds the responsible modules: modules in the
   traceback, plus modules whose classes or functions the failing tests import.
   The Coder gets each module's current code and the failure report, and must
   make the smallest change that keeps all names and signatures.
3. Only if tests still fail does the Tester fix tests that contradict the code.

---

## LLM usage tracking

Every Gemini request goes through [llm.py](llm.py), which reads
`usage_metadata` from each response and counts:

- **API calls**, including retried and failed requests
- **Input tokens**, **output tokens** (including thinking tokens), **total tokens**

The server adds each agent call to `usage.json` in the run folder. The UI shows
a per-agent table, and the CLI prints a summary. Usage from the sample run in
[examples/sample_output/usage.json](examples/sample_output/usage.json):

| Agent | API calls | Input tokens | Output tokens | Total tokens |
|---|---:|---:|---:|---:|
| Planner | 1 | 766 | 479 | 1,245 |
| Coder | 5 | 13,228 | 5,581 | 18,809 |
| Tester | 1 | 4,316 | 2,949 | 7,265 |
| **Total** | **7** | **18,310** | **9,009** | **27,319** |

In our runs, a QuickDelivery generation took 6–10 API calls and about
21k–41k tokens; the upper end includes a repair round.

Ways the design keeps usage low:

- The Coder only receives the files a module depends on, not the whole project.
- Code is returned as plain text, not inside JSON. Escaping errors in JSON were
  the main cause of retries in early versions.
- `requirements.txt` and the Streamlit theme are written by code, not by the LLM.
- One test file covers all logic modules (one Tester call).

---

## MCP execution tracing

The MCP client wraps tool calls with `ExecutionTrace` (in
[`execution_trace.py`](execution_trace.py)). Each call records its tool name,
execution order, UTC start time, duration, call status, and safe identifiers
(`run_id` and `filename` when available). The trace distinguishes a successful
MCP call from a failed tool-level check: for example, `run_tests` can complete
successfully but report `result_ok: false` when pytest fails.

A fresh recorder is created per generation run to keep event histories separate.
Completed events are saved incrementally to `execution_trace.json` inside that
run's `generated/run_<timestamp>/` directory. Only selected metadata is stored;
requirements, prompts, feedback, secrets, and tool response contents are not
included. Tracing does **not** make additional Gemini API calls.

The Gradio **MCP execution trace** tab shows a live call summary and event
table. The complete JSON trace is displayed after generation finishes to
avoid unnecessary UI re-rendering.

---

## Concurrent containerized generation

Each demo project runs its own **trusted worker container** with an independent
MCP client/server session, Planner → Coder → Tester pipeline, workspace, trace,
and token usage. The worker coordinates verification, but **generated Python
executes only in a separate restricted test sandbox**, not inside the worker.

```text
Mac host: Gradio (app.py) → BatchManager (batch_manager.py)
                             │ docker run ai-coder-worker:local
                             ▼
Worker container A           Worker container B           Worker container C
  client.py + MCP server       independent pipeline        independent pipeline
  Planner / Coder / Tester
  /job → host batch_runs/job_<id>/  (read-write bind mount)
          │
          └── run_tests / check_app → file-based broker (batch_rpc.py)
                                        │ host runs Docker
                                        ▼
                                    Test sandbox A
                                      no API key / no network
                                      read-only generated code
                                      pytest / Streamlit AppTest
```

**Worker startup:** `batch_manager.py` launches `docker run`; the worker image's
`CMD` starts `python -u job_worker.py`, which calls `client.py`'s
`run_pipeline_steps()` to drive MCP tools in order.

**LLM connection:** inside each worker, the MCP client talks to its MCP server
via **stdio** (no network required). The server's agents call `llm.py`, which
sends HTTPS requests through the worker's Docker **bridge network** and host
network/NAT to the **cloud-hosted Gemini API**. `GEMINI_API_KEY` is passed to
the trusted worker, **never to the test sandbox**. Workers share API rate limits
but do not share MCP sessions or LLM conversation state.

```text
batch_runs/                         # git-ignored
├── job_<unique-id-A>/
│   ├── spec.md
│   ├── progress.json
│   ├── worker.log
│   ├── control/                  # broker requests / responses
│   └── generated/
│       └── run_<timestamp>/
│           ├── app.py
│           ├── test_app.py
│           ├── requirements.txt
│           ├── execution_trace.json
│           └── usage.json
├── job_<unique-id-B>/
└── job_<unique-id-C>/
```

The job folders persist on disk, but the dashboard's job index lives in memory
and is not automatically restored after restarting the Gradio server.

---

## Sandboxed test and app verification

Generated code is executed during verification. By default, both MCP tools,
`run_tests` (pytest on `test_app.py`) and `check_app` (headless Streamlit
`AppTest` on `app.py`), use [`sandbox_runner.py`](sandbox_runner.py) to start
**separate, short-lived Docker containers**. In single-run mode, the agents
run on the host; in concurrent mode, they run inside trusted worker containers.
The Gradio UI remains on the host. Neither mode runs the agents or calls Gemini
inside the **test sandbox**; verification makes no additional Gemini calls.

Build the preinstalled verification environment before generating apps:

```bash
docker build -f Dockerfile.sandbox -t ai-coder-test-sandbox:local .
```

The base image, defined in [`Dockerfile.sandbox`](Dockerfile.sandbox), includes
Python 3.12, pytest, and Streamlit. For extra project dependencies, the Planner
writes `requirements.txt`; [`project_dependencies.py`](project_dependencies.py)
resolves only **approved packages at pinned versions**. The host's
`sandbox_runner.py` reuses an existing image for that dependency set, or builds
a new tagged image with `EXTRA_PACKAGES` if missing. Dependency installation
happens **at image build time** (with network access), never when generated
code executes. Projects without extras use `ai-coder-test-sandbox:local`.
Each test container bind-mounts only the
current generated run folder, **read-only**, at `/workspace`:

```text
Mac host: generated/run_<timestamp>/    Container: /workspace/
          models.py                                 models.py
          cart.py                                   cart.py
          app.py                                    app.py
          test_app.py                               test_app.py
```

The example filenames are illustrative; generated files differ by run. A bind
mount does not copy the app into the image. In concurrent mode, the worker
requests verification through a **file-based host broker** (`batch_rpc.py`),
without access to the host Docker socket. The test container runs mounted code;
its exit code, stdout, and stderr are returned to the MCP server. Containers
are removed after execution (`docker run --rm`); the image and generated files
remain. Test repairs use a new container with the updated generated files.

| `AI_CODER_RUNNER` | Behavior |
|---|---|
| Unset (default) or `docker` | Run verification inside Docker; require Docker Desktop and the built image |
| `host` | Explicit developer-only fallback; runs generated Python directly on the host (**not sandboxed**) |
| Any other value | Raise `SandboxUnavailable` |

The Docker runner uses `--network=none`, `--read-only`, a read-only bind mount,
`--memory=512m`, `--cpus=1`, `--pids-limit=64`, `--cap-drop=ALL`, a non-root
user, and a 60-second execution timeout. If Docker is unavailable it **fails
closed** rather than silently running on the host. These controls reduce risk,
but containers are not a complete security boundary for malicious code.

Verify the runner's behavior without Docker or Gemini:

```bash
python -m pytest tests/test_sandbox_runner.py -v
```

**Scope:** This sandbox is used by `run_tests` and `check_app` only. The
**Launch generated app** button and manually running `streamlit run app.py`
are **not sandboxed** and must only be used for trusted generated code.

---

## Reliability

| Problem | Handling |
|---|---|
| Gemini 429/500/503/504 | Waits and retries up to 4 times (2, 4, 8, 16 s); does not use up reply attempts |
| Invalid JSON or invalid plan | The error message is sent back to Gemini; up to 3 replies |
| Generated code with a SyntaxError, SyntaxWarning or broken unicode escape | Rejected before saving and sent back with the line number |
| Imports of modules that don't exist or weren't planned | Rejected (checked with `ast`, without running the code) |
| App that crashes when opened | Caught by `check_app` and repaired |
| Failing tests | Repair flow described above |

---

## Requirements-to-test traceability

After pytest and any repairs, the MCP client calls
`validate_requirements(run_id)`. The Tester Agent is instructed to label each
generated pytest test with the relevant requirement IDs (for example,
`FR3: Reject invalid cart quantities`) in its docstring. The validator uses
Python's AST to read those annotations and matches them to numbered input
requirements. It saves `coverage_report.json` in the run folder and displays
the result in the **Requirements coverage** tab.

The report includes declared mappings, unverified requirements, unmapped tests,
and unknown requirement IDs. This validation is deterministic and does **not**
make an additional LLM API call. **Declared coverage is not proof that the
requirement is correctly implemented or that the test assertions are adequate.**
UI-only requirements may have no corresponding logic-unit-test mapping, even
when the Streamlit app check succeeds.

To test the validator without a Gemini API key:

```bash
python -m pytest tests/test_requirements_validator.py -v
```

To verify the complete integration, run `python app.py`, select
**Load QuickDelivery example** and **Generate**, and check the
**Requirements coverage** tab and the new run's `coverage_report.json`.
The saved `examples/sample_output/` is an older reference generation, so it
is not expected to contain these new test annotations or a coverage report.

---

## QuickDelivery requirements

The requirements we defined are in
[examples/quickdelivery.md](examples/quickdelivery.md). In short: browse at
least four restaurants (cuisine, rating, delivery time) and their menus; a
single-restaurant cart with positive-integer quantities and totals; simulated
payment with basic card validation; orders with unique IDs whose status moves
automatically Pending → Preparing → Delivering → Delivered every 10 seconds;
and tabbed navigation.

The generated sample in [examples/sample_output/](examples/sample_output/)
passes all 15 of its tests (`cd examples/sample_output && pytest test_app.py`).

---

## Project structure

```text
app.py                   Gradio UI (single-run + concurrent demo)
client.py                MCP client: orchestration, repair, CLI
mcp_server.py            MCP server: agents, workspace, verification, usage
llm.py                   Gemini calls, retries, and token usage
execution_trace.py       MCP tool-call tracing and persistence
batch_manager.py         Concurrent job lifecycle and host verification broker
job_worker.py            Docker worker entry point
batch_rpc.py              File-based worker ↔ host verification requests
sandbox_runner.py        Restricted Docker test execution
project_dependencies.py  Approved, pinned project dependencies / image tags
Dockerfile.worker        Trusted worker image (Gemini network access)
requirements.worker.txt  Worker Python dependencies
Dockerfile.sandbox       Keyless test image (pytest / Streamlit / approved extras)
.dockerignore            Excludes local files from Docker build context
agents/
  planner.py             Planner Agent
  coder.py               Coder Agent
  tester.py              Tester Agent
  validation.py          Syntax/import validation
  requirements_validator.py  Functional requirement-to-test mapping
examples/
  quickdelivery.md       Canonical QuickDelivery requirements
  demo_specs/            BudgetMaster and GroupChat demo requirements
  sample_output/         Reference generated output
requirements.txt         Host Python dependencies
.env.example             API key configuration template
generated/               Single-run outputs (git-ignored)
batch_runs/              Per-job generated outputs, logs and traces (git-ignored)
tests/                   Validator, tracing, sandbox, dependencies and batch tests
```

---

## Security notes and limitations

- **Generated code is executed.** `run_tests` and `check_app` use restricted
  Docker containers by default (60-second timeout, no API key passed into the
  container). Container isolation reduces risk but is not a security guarantee.
  The **Launch generated app** button and manual Streamlit execution still run
  outside this sandbox. `AI_CODER_RUNNER=host` explicitly disables isolation.
- MCP tools only accept run IDs of the form `run_YYYYMMDD_HHMMSS` and flat file
  names, so paths like `../../.env` are rejected.
- The API key lives in `.env`, which is git-ignored and never committed.
- Generated apps are limited to Python + Streamlit with in-memory data (no
  database or network calls) and at most 6 files.
- The Streamlit UI (`app.py`) is checked by loading it once, not by unit tests.
- LLM output varies: file names, test counts and token usage differ between runs.

---

## Course requirements checklist

| Requirement | Where |
|---|---|
| Multi-agent system using MCP for communication between agents | Agents run as MCP tools and exchange work through the server's workspace ([mcp_server.py](mcp_server.py)) |
| Agent roles, tools and collaboration pattern | [Agents](#agents), [MCP tools](#mcp-tools), [Collaboration pattern and repair](#collaboration-pattern-and-repair) |
| MCP tooling, server and client | [mcp_server.py](mcp_server.py), [client.py](client.py) |
| UI receives description and requirements | [app.py](app.py): two input fields |
| UI returns executable code and tests | Code and test tabs, test results, zip download, Launch button |
| Track API calls and total tokens | [llm.py](llm.py), `usage.json`, LLM usage tab |
| Name and student ID in each code file; comments for each function | Header in every source file; docstrings on all functions |

LLM: Google Gemini (`gemini-3.5-flash-lite` by default, configurable with
`GEMINI_MODEL`). No third-party code was copied or adapted; the project uses
only the libraries listed in `requirements.txt`.
