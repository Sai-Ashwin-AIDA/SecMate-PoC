# Local Document Agent — Slice 1

An independent Python package with **three real offline LangChain tools**. Slice 1
is implemented and tested; it is not yet a chat assistant.

There is **no model construction, agent loop, interactive CLI, console entry point,
HTTP adapter, or email sending**. Do not try `local-document-agent` or
`python -m local_document_agent`: those entry points belong to Slice 2.

Design authority: the blueprint on GitHub branch **Sai**, including Section 0.
The local `Documents/LOCAL_DOCUMENT_AGENT_BLUEPRINT.md` was older during this build
and was not replaced. See `BUILD_STATUS.md` for the exact revision and test results.

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

Latest result: **81 passed, 1 skipped**. The skip is the actual symlink fixture:
this Windows process lacks creation privileges/Developer Mode. Actual junction,
opened-handle boundary, hard-link, and exclusive-write checks passed.

## Direct local use — no inference

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

The source ledger stores metadata, not complete documents. Each `ToolContext` is
an explicit active-operation context, capped at 32 read references and 32 created
records. It also retains the returned read pages for observed-operation reporting.
Source IDs increase monotonically; discarding a reference makes it invalid for
future reports. Slice 2 owns conversation/history lifecycle and context pruning.
Use contexts sequentially; concurrent mutation is not supported.

## Configuration boundaries

No `.env` is created or read on import. `load_configuration(app_root)` reads only
that root's `.env`, with interpolation disabled and process settings taking
precedence. It never searches parents or mutates the process environment.
Pass `environment={}` for explicit isolated configuration in tests.

Offline operations require only valid local roots. The reserved
`Configuration.require_inference_ready()` gate rejects missing keys and false
transmission consent; it does not construct a model. Slice 2 must apply that gate,
root validation, and tracing restrictions at real assistant startup.

`.env.example` contains no secrets. Do not copy a parent `.env` or reuse its venv.
Do not enable tracing or add raw tool callbacks that log document contents.

Slice 1 transmits **no documents for inference**. In Slice 2/3, selected chat,
document excerpts, search snippets, and generated text will be sent to OpenRouter
and its serving provider. Provider privacy/retention policies still require review;
local storage does not make future inference private or offline.

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

Stop here for Slice 1. See `BUILD_STATUS.md` before beginning a separately assigned
Slice 2.
