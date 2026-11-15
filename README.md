# AI Coder: Multi-Agent Code Generation with MCP

SWE 270P Final Project. Author: Yu-Chien Chiu (56176405)

AI Coder takes a **software description and requirements** in a web UI and
generates a complete **Python + Streamlit application with pytest tests**.
Three agents (Planner, Coder, Tester) work behind an **MCP server**, and an MCP
client coordinates them. The system runs the generated tests, checks that the
app starts, repairs failures, and reports **LLM usage (API calls and tokens)**.

Our selected application is **QuickDelivery**, a simplified food delivery app.
QuickDelivery is the *output* of AI Coder; its requirements are in
[examples/quickdelivery.md](examples/quickdelivery.md), and a generated sample
is in [examples/sample_output/](examples/sample_output/).

---

## Quick start

Requirements: Python 3.12 and a Gemini API key.

```bash
# 1. Create the environment (conda shown; venv works too)
conda create -n swe270p-ai python=3.12 -y
conda activate swe270p-ai
pip install -r requirements.txt

# 2. Add your API key
copy .env.example .env        # macOS/Linux: cp .env.example .env
#    then edit .env and set GEMINI_API_KEY

# 3. Start the UI (opens http://127.0.0.1:7860)
python app.py
```

In the UI:

1. Click **Load QuickDelivery example** (or type your own description and requirements).
2. Click **Generate**. Agent progress streams live (about 1–2 minutes).
3. Inspect the tabs: **Generated code**, **Generated tests**, **Test results**,
   **Plan**, **LLM usage**.
4. In **Run the app**, download the zip or click **Launch generated app**
   (opens the generated app at http://localhost:8502).

Command-line alternative (same pipeline, no UI):

```bash
python client.py                        # uses examples/quickdelivery.md
python client.py my_requirements.md     # any requirements file
```

Each run is saved to `generated/run_<timestamp>/`. To run a generated app
yourself, start Streamlit **from inside that folder** so its theme loads:

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
│ mcp_server.py  (MCP server, 9 tools)                                   │
│                                                                        │
│  Agent tools        plan ─────────► Planner Agent  ─┐                  │
│                     write_code ───► Coder Agent    ─┼─► llm.py ─► Gemini│
│                     write_tests ──► Tester Agent   ─┘   (retry + usage)│
│  Workspace tools    create_run, list_files, read_file                  │
│  Verification       run_tests (pytest), check_app (headless Streamlit) │
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
5. `run_tests` and `check_app` verify the result; failures are routed back to an agent.

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
| `get_usage(run_id)` | API calls and tokens per agent and in total |

### Collaboration pattern and repair

The client uses a **fixed pipeline** instead of letting an LLM choose tools.
This keeps the number of API calls small and predictable, which matters because
efficiency (tokens and API calls) is graded.

```
create_run → plan → write_code × N files → write_tests → run_tests + check_app
           → repair (only if needed) → get_usage
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

```
app.py                 Gradio UI (entry point)
client.py              MCP client: pipeline, repair, CLI
mcp_server.py          MCP server: agent, workspace, verification and usage tools
llm.py                 Gemini client: retries, JSON/text replies, usage counting
agents/
  planner.py           Planner Agent
  coder.py             Coder Agent (incl. UI guidelines for generated apps)
  tester.py            Tester Agent
  validation.py        Syntax and import checks shared by the agents
examples/
  quickdelivery.md     Our QuickDelivery requirements
  sample_output/       One generated QuickDelivery app with tests and usage
requirements.txt       Python dependencies
.env.example           Template for the API key
generated/             Output of each run (git-ignored)
```

---

## Security notes and limitations

- **Generated code is executed** (pytest, `check_app`, Launch button). It runs in
  its own process with a 60-second timeout (tests and app check) and with API
  keys and other secrets removed from its environment variables. It is **not
  sandboxed**: generated code could still read files on disk, such as `.env`.
  Use a container if you run untrusted requirements.
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
