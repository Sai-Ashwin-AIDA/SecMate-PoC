# Local Document Agent — CLI and local tools

An independent Python package with **three real LangChain tools**, a bounded
message/tool controller, and a working terminal interface. Tools, agent wiring,
SDK transport, and CLI behavior are verified offline with explicit mocks.

**Getting started:** [User manual and example prompts](USER_MANUAL.md). A fictional
18-document Harbor workspace is available under `data/input/mock-workspace/` in
this workspace, with reusable source files in `examples/mock-workspace/`.

**The user reports live CLI responses, but the three builder-run live workflow
demonstrations remain unrecorded.** See `BUILD_STATUS.md` for actual outcomes.
Normal CLI use requires your OpenRouter key and explicit transmission consent.
There is no fake-success CLI mode, email sending, alternate model, paid fallback,
or SecMate integration. An optional authenticated loopback HTTP foundation is
documented below; it is not SecMate onboarding or assessment execution.

Design authority: the blueprint on GitHub branch **Sai**, including Section 0.
The local blueprint was initially older; concurrent repository updates have now
brought in Section 0. This agent did not overwrite or pull parent documentation.
See `BUILD_STATUS.md` for the exact authority and observed results.

## Setup — Windows PowerShell

Run these commands from `local-document-agent/`, not a SecMate or LangChain package.
Python, uv, caches, and the environment can all stay under this application.
The verified environment uses **CPython 3.12.16** and **uv 0.13.9**.

This workspace already has `.tools/bin/uv.exe`, `.python/`, and `.venv/`.
For a fresh copy with Python 3.11+ available, bootstrap uv locally:

```powershell
python -m pip install --disable-pip-version-check --target .tools uv==0.13.9
```

Then:

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
$env:UV_PYTHON_BIN_DIR = "$PWD\.tools\bin"
$env:UV_NO_ENV_FILE = "1"

.\.tools\bin\uv.exe python install 3.12
.\.tools\bin\uv.exe sync --frozen --group dev
.\.tools\bin\uv.exe lock --check --offline
.\.tools\bin\uv.exe pip check --python .venv/Scripts/python.exe
```

Retain `uv.lock`; do not regenerate it during routine setup. All declared pins are
unchanged from the blueprint:

| Package | Version |
|---|---|
| langchain | 1.5.2 |
| langchain-core | 1.8.4 |
| langgraph | 1.2.16 |
| langchain-openrouter | 0.3.0 |
| openrouter | 0.9.2 |
| pydantic | 2.12.5 |
| python-dotenv | 1.2.1 |
| pytest (development) | 9.0.2 |

The build backend is `hatchling==1.27.0`. All framework dependencies are released
PyPI packages, not the reference checkout. Only this application is installed
editable in its own environment.

## Run the focused offline tests

```powershell
$env:UV_NO_ENV_FILE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-local
```

Use that dedicated test directory only: pytest owns and may replace it.
The suite creates harmless temporary files, blocks outbound sockets and DNS
during collection, removes inherited provider/tracing credentials in its process,
and disables LangSmith tracing. No key, consent setting, `.env`, personal files,
provider client, or model fake is needed.

Latest pre-live gate: **142 passed, 1 skipped**. The suite includes the independent
audit fixes, mocked agent/CLI tasks, and real SDK calls over `httpx.MockTransport`.
No inference takes place in tests. The skip is the actual symlink fixture:
this Windows process lacks creation privileges/Developer Mode. Actual junction,
opened-handle boundary, hard-link, and exclusive-write checks passed.

## Normal CLI setup and startup

Only app-local `.env` is loaded. Never copy SecMate credentials or use its venv.
Create dedicated document roots, preserving existing configuration:

```powershell
New-Item -ItemType Directory -Force ".\data\input"
New-Item -ItemType Directory -Force ".\data\output"
if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
}
notepad ".\.env"
```

Set `ALLOW_OPENROUTER_DOCUMENT_TRANSMISSION=true` only after reviewing the
disclosure below. Supply `OPENROUTER_API_KEY` privately in that file or only in the
current process, without putting the key in a command:

```powershell
$secret = Read-Host "OpenRouter API key" -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

Leave the exact model/base URL and tracing disabled. Then run:

```powershell
$env:UV_NO_ENV_FILE = "1"
.\.tools\bin\uv.exe run --frozen --no-sync local-document-agent
# Equivalent:
.\.tools\bin\uv.exe run --frozen --no-sync python -m local_document_agent
```

`--help` works without a key. `--app-root PATH` selects an explicit application
configuration directory. Default configuration is anchored to this editable source
installation, not the caller's current directory; use `--app-root` if installing
the wheel elsewhere.

Commands: `/help`, `/new`, `/exit`. EOF exits. Ctrl+C cancels active inference;
already-written files remain and are still reported. Ctrl+C at the input prompt
or a second Ctrl+C exits. Observed tool activity, actual read references, and
created paths are shown. No successful read/write is inferred from model prose.

Missing key/consent/root errors stop startup. Provider rate limits, capacity,
timeouts, malformed responses, file failures and argument errors are reported
without automatic retry, argument repair, or fallback.

## Direct local tools — no inference

The supported programming boundary is:

```python
from local_document_agent.context import ToolContext
from local_document_agent.filesystem import FilesystemRoots
from local_document_agent.tools import build_tools
```

Construct roots from **existing, separate, non-overlapping local directories**.
No directory is created implicitly by imports, configuration, or tool factories.
Invoke tools with explicit dictionary arguments, or LangChain tool-call objects.
Dictionary invocation returns a JSON string. A LangChain tool-call invocation
returns a `ToolMessage` with the original call ID and success/error status.

This example exercises actual tools on fictional files without accessing personal
documents. Run it as Python code using this application's environment:

```python
import json
import os
import tempfile
from pathlib import Path

for variable in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ[variable] = "false"

from local_document_agent.context import ToolContext
from local_document_agent.filesystem import FilesystemRoots
from local_document_agent.tools import build_tools

Path(".cache").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=".cache") as temporary:
    root = Path(temporary).resolve()
    source, output = root / "input", root / "output"
    source.mkdir()
    output.mkdir()
    (source / "notes.md").write_text("# Review\nTuesday review.\n", encoding="utf-8")
    context = ToolContext()
    tools = {
        item.name: item
        for item in build_tools(FilesystemRoots(source, output), context)
    }
    found = json.loads(tools["search_documents"].invoke({
        "query": "Tuesday", "scope": "text", "offset": 0, "limit": 5,
    }))
    assert found["ok"]
    read = json.loads(tools["read_document"].invoke({
        "path": found["data"]["results"][0]["path"],
        "start_line": 1, "max_lines": 20,
    }))
    assert read["ok"]
    created = json.loads(tools["create_document"].invoke({
        "filename": "review.md",
        "kind": "report",
        "content": "# Review\nTuesday review.",  # Caller-supplied text, not an AI answer.
        "source_ids": [read["data"]["source_id"]],
    }))
    assert created["ok"] and (output / "review.md").is_file()
    print(context.ledger.snapshot()[0].reference())
    print(created["data"]["path"])
```

That example's files are deleted by `TemporaryDirectory` on exit. To use persistent
local roots later, explicitly create `data/input` and `data/output` and pass their
paths. Never select a home/repository directory or a folder containing secrets.

## What each tool does

- **`search_documents`**: literal case-insensitive relative-path and/or extracted
  text search; deterministic ordering and pagination; bounded snippets and explicit
  partial/skipped indicators. It does not register read sources.
- **`read_document`**: actual bounded `.txt`, `.md`, or plain-text `.eml` reading.
  Returns normalized line ranges, raw-byte SHA-256, pagination, completeness, and
  a host-issued source ID such as `R1`.
- **`create_document`**: exclusive new `.txt`/`.md` output creation. Validates source
  IDs, appends observed source references, and reports only successful writes.
  `kind="email_draft"` always prepends `EMAIL DRAFT — NOT SENT`; nothing sends mail.

All argument fields are required. Pydantic strict models reject extra fields,
string integers, booleans as integers, invalid enums, and duplicate source IDs.
Paths and filenames are validated without rewriting them. A write collision never
overwrites the existing file, even when another creator wins the exclusive-open
race after the preflight check.

The source ledger stores metadata, not complete documents. A standalone
`ToolContext` defaults to 32 read references and caps successful creates at 32.
The controller uses fresh per-turn event contexts and a bounded shared metadata
ledger sized for retained turns (maximum 180 references). Source IDs increase
monotonically within a session. Whole-turn eviction removes owned IDs; failed
turns drop newly introduced references, not successful files. Returned pages live
only in bounded turn/message history, not an accumulating event log.
Use contexts sequentially; concurrent turns are rejected.

The independently callable core is `DocumentAssistant(configuration, model,
roots=...)`, `await assistant.chat(text)`, and `assistant.new_session()`.
The model is explicitly injected; the normal CLI constructs the real configured
provider. `TurnResult` exposes observed reads, earlier observed sources referenced,
successful files, uncertain outputs, activity and safe errors.

## Configuration boundaries

No `.env` is created or read on import. `load_configuration(app_root)` reads only
that root's `.env`, with interpolation disabled and process settings taking
precedence. It never searches parents or mutates the process environment.
Pass `environment={}` for explicit isolated configuration in tests.

Offline operations require only valid local roots.
`Configuration.require_inference_ready()` rejects missing keys and false consent.
The real CLI applies that gate, root validation, and tracing restrictions before
provider construction. Tool imports still require no client, key, or consent.

`.env.example` contains no secrets. Do not copy a parent `.env` or reuse its venv.
Do not enable tracing or add raw tool callbacks that log document contents.

**Normal CLI use sends chat, selected document excerpts, search snippets, and
generated text to OpenRouter and its serving provider.** Review their retention/
training policies; local storage does not make inference private or offline.
Keep account-level broadcast/observability destinations disabled. SDK payload
logging is explicitly disabled even when `OPENROUTER_DEBUG` is inherited. No trace
metadata is sent and LangSmith tracing is disabled around model/tool execution.

## Conversation controls

Defaults: four previous complete turns, eight model calls and twelve tool calls
per turn, 2048 output tokens/call, 30-second request timeout, 120-second turn
deadline. Context and cumulative token budgets are configurable within fixed
bounds. Context uses conservative serialized-byte units plus per-message overhead,
not an exact Nemotron tokenizer.

Old whole turns are pruned without orphaning call/result pairs. An over-budget
active turn stops rather than silently losing its tool results. Failed, limited
or cancelled turns are not retained; successful files and possible partial
outputs are still reported. `/new` clears conversation/source memory and changes
the session ID, not local files. No autonomous or durable memory exists.

## Safe error diagnostics

At the user's request, normal CLI errors are recorded in **`.logs/errors.log`**
inside the application. Rotation retains a 1 MiB current file and at most three
backups. `.logs/`, `.env`, data, environments, and caches are ignored by Git.

Records contain UTC timestamps, app/Python versions, phase, stable error code,
session ID, known tool name, exception class and up to eight code-location frames.
They never include prompts, document/snippet/draft bodies, keys, raw provider
responses, exception prose, source lines, or local-variable dumps. Document
filenames are not logged; the terminal shows needed paths locally.

To inspect recent diagnostics:

```powershell
Get-Content ".\.logs\errors.log" -Tail 20
```

Startup, tool, provider, budget, cancellation and shutdown errors have distinct
codes. For debugging, share a sanitized record's code/session/timestamp and code
frames—not your `.env` or personal documents. If logging storage becomes
unavailable, the CLI warns that the error may not have been saved; disk/permission
failures cannot guarantee durable logging.

## Limits and limitations

- Raw/extracted text: 256 KiB; read page: 200 lines and 12,000 characters maximum.
- Search: 1000 entries, eight directory levels, five seconds, 16 MiB aggregate
  raw reads, and at most 20 returned hits with 160-character snippets.
- Create: at most 24,000 content characters and 64 KiB framed UTF-8 output.
- `.txt`/`.md` use strict UTF-8/BOM decoding and LF normalization; no guessing or
  silent replacement. NUL-containing binary-like text is unsupported.
- Email uses standard-library MIME parsing and declared charsets; parser/decoding
  defects fail conservatively. Only inline plain text and selected headers are
  returned. HTML and attachment payloads are never decoded into tool results.
  Raw `.eml` bytes necessarily include those MIME parts during bounded parsing.
- Email references identify extracted representation lines, not raw MIME lines.
- Symlinks, junctions, reparse points, hard-linked inputs, UNC/device paths,
  traversal, Windows device basenames, and overlapping roots are rejected.
- Output is flat and separate; tools cannot reopen outputs or modify originals.
- Windows handle resolution verifies actual opened-file boundaries. These checks
  are not an OS sandbox against hostile concurrent same-privilege path replacement.
- Root write-access preflight is advisory; Windows ACLs may reject the actual
  write. Write errors are ordinary tool failures.
- A failed write may leave a newly created partial file. It is never registered
  as a successful create, never retried, and never silently overwritten/deleted.
- The async tool wrapper performs bounded synchronous local I/O without spawning
  threads. Cooperative deadline checks are not a hard interrupt of a stuck OS call.
- Search is literal and linear, not semantic. No attachments/PDF/Office/OCR,
  mailbox/calendar, vector database, shell, arbitrary web access, or persistent
  memory exists.
- Source references establish what was read, not factual accuracy of supplied
  report prose. No model behavior or complete assistant usability is verified.

See `BUILD_STATUS.md` for the completed offline gates and the live-test gate.
No live success, provider availability, or immunity to future errors is claimed
without an actual observed demonstration.

## Explicit live sample demonstrations

`examples/input/` contains only fictional launch notes, a budget and a plain-text
email. After private app-local `.env` setup and consent, the explicitly guarded
demonstration command is:

```powershell
.\.tools\bin\uv.exe run --frozen --no-sync python examples/live_smoke.py --run-live
```

It uses the real model and tools, ordinary task prompts, and the CLI result
renderer. It does not force tools, fabricate responses, retry, or fall back.
Only fictional copies in a new `.cache/live-demo-<id>/input` are available to the
model's tools; no configured personal document directory is read. Each of the
three tasks starts a fresh conversation. Configured call/token/deadline limits
apply. A failed turn stops the remaining tasks instead of retrying until success.

Actual reports/drafts remain in that run's `output/`. `outcomes.json` records only
statuses, observed source/output names and error codes, not response prose or
credentials. Exit 0 means the observed workflow checks passed, not independent
semantic certification of the model's answer. Exit 1 indicates an unsuccessful
workflow; exit 2 indicates private configuration/consent is not ready. This sample
runner reads only the app-local `.env`, deliberately ignoring ambient provider keys.

## Optional Phase 1 HTTP service — human review required

Authority: `Documents/LOCAL_DOCUMENT_AGENT_SECMATE_INTEGRATION_BLUEPRINT.md`.
Actual checks/limitations and the pending human acceptance gate:
[`LOCAL_DOCUMENT_AGENT_SECMATE_PHASE1_RESULTS.md`](../Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE1_RESULTS.md).
The CLI is unchanged. HTTP is a separate process/environment entry point, not a
SecMate route. No live HTTP inference is implied by the offline checks.

Install the optional stack in this application's environment only:

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
$env:UV_PYTHON_BIN_DIR = "$PWD\.tools\bin"
$env:UV_NO_ENV_FILE = "1"
.\.tools\bin\uv.exe sync --frozen --extra http --group dev
.\.tools\bin\uv.exe run --frozen --no-sync local-document-agent-http --help
```

Direct HTTP pins: FastAPI **0.121.3**, base Uvicorn **0.38.0**, not standard
extras. Ordinary installs without `--extra http` need no HTTP stack.

Privately set `LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN` in the app-local `.env` or
process environment, distinct from the provider key. Use a high-entropy ASCII
token without whitespace. No token is generated for you or exposed in metadata.
Retain the app's own provider key, route and explicit transmission consent.
Never use SecMate's configuration. Settings are loaded once at startup with
process values taking precedence, without parent search or interpolation.

HTTP roots are **fixed relative to the selected app root**:

- Input: `data/input/mock-workspace` only; **not** `data/input/test.txt`.
- Output: existing shared `data/output`, exclusively new flat `.txt`/`.md` files.
- HTTP ignores the CLI's `DOCUMENT_INPUT_DIR`/`DOCUMENT_OUTPUT_DIR` values.
- Roots must already exist and pass the existing confinement validation. If
  absent, inspect authenticated readiness and ask the operator before creating
  directories/copying `examples/mock-workspace`; never merge a nonempty target.
  Startup/metadata do not create roots or read document bodies.

Start manually from this application:

```powershell
.\.tools\bin\uv.exe run --frozen --no-sync local-document-agent-http
# Explicit alternate loopback port, only after resolving a local conflict:
# .\.tools\bin\uv.exe run --frozen --no-sync local-document-agent-http --port 7311
```

Default is `127.0.0.1:7310`, one worker, no reload, no CORS/cookies, no redirects,
no access/body/header logs. `--app-root PATH` selects explicit app-local settings;
HTTP roots remain fixed beneath it. Missing adapter token prevents startup.
Missing key/consent/roots is reported as not-ready, without a provider connection.
`--help` needs neither settings nor credentials and performs no writes.

### Authenticated contract

Every endpoint requires `Authorization: Bearer <adapter-token>`, including
metadata. Documentation/schema endpoints are disabled. Fetch metadata without
inference; enter your token privately, not as a literal shell command:

```powershell
$secret = Read-Host "Adapter bearer token" -AsSecureString
$headers = @{ Authorization = "Bearer " + [System.Net.NetworkCredential]::new("", $secret).Password }
Remove-Variable secret
$metadata = Invoke-RestMethod -Uri "http://127.0.0.1:7310/v1/metadata" -Headers $headers
$metadata
```

Metadata declares configured, **unverified** model/provider identity, readiness,
logical scopes, effective bounds and observation gaps. It proves neither a
successful model call nor security-test coverage. Missing/wrong tokens return
401, unknown runs 404, strict validation failures 422, oversized bodies 413,
instance/submission/busy conflicts 409, readiness/capacity failures 503.

**Only after separately authorizing a benign live model call**, submit one exact
message, then poll the returned relative status path:

```powershell
$body = @{
    contract_version = "secmate-agent-http-v1"
    adapter_instance_id = $metadata.adapter_instance_id
    submission_id = [guid]::NewGuid().ToString()
    message = "Read projects/harbor/overview.md and briefly summarize it with references."
} | ConvertTo-Json -Compress
$ack = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:7310/v1/runs" -Headers $headers `
    -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
$run = Invoke-RestMethod -Uri ("http://127.0.0.1:7310" + $ack.status_path) -Headers $headers
# Explicit cancellation of this run only:
# Invoke-RestMethod -Method Post -Uri ("http://127.0.0.1:7310" + $ack.cancel_path) -Headers $headers
```

Request has exactly four required fields above, with no unknown fields/coercion.
IDs are canonical lowercase hyphenated UUIDs. Message is nonblank valid UTF-8,
1–4000 characters, preserved exactly (including accepted surrounding whitespace).
Actual streamed body is bounded to 32 KiB before JSON parsing. Request SHA-256
hashes exact message UTF-8 bytes, not the JSON envelope.

202 acknowledgements contain contract/instance/submission/run IDs, request hash,
UTC acceptance time, current state and relative status/cancel paths. Lifecycle:
`accepted`, `running`, `completed`, `failed`, `limited`, `cancelled`.
One fresh assistant/session per accepted run; no continuation, queue or fallback.
Only accepted runs construct providers, lazily; polling/metadata never do.

Same-instance same-submission same-message retry returns the existing run,
**without another model/file operation**, even when busy or capacity is full.
Reusing that ID for different message bytes returns `SUBMISSION_CONFLICT`.
A different submission while occupied gets `TARGET_BUSY`. At **32 retained
runs**, new submissions get `RUN_CAPACITY_REACHED`; receipts are never evicted.
Collect results before a deliberate restart. Storage is in-memory only: restart
changes the instance UUID and old IDs return `ADAPTER_INSTANCE_CHANGED`. Loss of
an old record means **unknown transport disposition**, not proof nothing ran or
was written. Never automatically resubmit under a new instance/submission ID.

Polling includes lifecycle times, timing/limits and bounded tool summaries.
Final `result` wraps the existing `TurnResult`: exact answer and UTF-8 SHA-256,
session/status, observed source ranges/raw hashes, created-file bytes/hashes,
uncertain outputs, retained references, unverified citation IDs and safe errors.
Source IDs are run/session-local; file references are root-relative. Observed
model/provider and complete model-call usage are unavailable/null, not guessed
from configuration or prose. No file download or output-directory scan exists.
Terminal snapshot bytes are stable across polling and terminal cancellations.

Cancellation is idempotent and does not mean settlement until the task finishes.
Disconnecting a poll does not cancel a run. Already-written/possibly partial files
remain reported; nothing rolls them back. The slot remains occupied through both
provider-client closures. Closure failure gives lifecycle `failed` with separate
`adapter_error`/`cleanup_status`, preserving the core result/status unchanged;
the slot then stays unavailable until operator review and deliberate restart.

Shutdown stops accepting new runs and uses **one total 10-second cooperative
deadline** for active cancellation plus cleanup. Timeout logs sanitized
`SHUTDOWN_TIMEOUT`, leaves unsettled state/disposition unknown and retains the
slot; it does not claim cancellation, resource closure or file rollback.
Cooperative deadlines cannot preempt a hung synchronous filesystem operation.
No run/cleanup retry, durable resume, output cleanup or automatic restart exists.
Errors use the existing bounded sanitized diagnostic log; no payloads are logged.

### Offline gate (no live service or inference)

After installing the `http` extra, use the isolated app-local test environment:

```powershell
$env:UV_NO_ENV_FILE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.\.tools\bin\uv.exe run --frozen --no-sync pytest tests/test_http.py --basetemp=.cache/pytest-http-focused
.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-http-phase1
.\.tools\bin\uv.exe lock --check --offline
.\.tools\bin\uv.exe pip check --python .venv/Scripts/python.exe
```

All HTTP tests use in-process ASGI, temporary roots and explicit mocked provider
boundaries; at least one sequence traverses the real pinned SDK MockTransport.
Outbound traffic/tracing remain blocked by the existing test isolation. These
tests establish adapter/tool wiring, not real-model interpretation or live
service usability. Human review/manual HTTP checks are pending; **stop before
Phase 2**, which is neither implemented nor authorized.
