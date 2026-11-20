# Local document agent — build status

**Current state:** Slice 1 audit fixes and Slice 2 offline gate passed. CLI and
sanitized diagnostics are implemented. The user now reports the CLI responding;
the three builder-run live workflow demonstrations remain unrecorded. An
18-document fictional input workspace and full usage manual have been added and
verified offline. Earlier credential-gate sections are historical records, not
claims that the user's current CLI is blocked. No live inference was performed
for the mock-data/manual assignment.

## Authority and preserved work

- Followed GitHub branch `Sai`, revision `41fdd4a3a40a3e476db151ebad501f763890d5cd`,
  including Section 0 of `Documents/LOCAL_DOCUMENT_AGENT_BLUEPRINT.md`.
- The local blueprint is older and was deliberately not overwritten or pulled.
- Initial Git status: existing untracked `LangChain/`; preserved untouched.
- Only `local-document-agent/` files have been added. Nothing staged, committed,
  pushed, cleaned or reset.
- User explicitly chose to record the host symlink-privilege skip rather than
  change Windows privileges/Developer Mode.

## Environment and resolution actually performed

- Application-local `uv` 0.13.9, installed using the existing Python 3.11:
  `python -m pip install --disable-pip-version-check --target .tools uv` — exit 0.
- `uv python install 3.12 --no-install-bin` — exit 1; this uv version does not
  recognize that option. No dependency pins were changed.
- `uv python install 3.12` with app-local install/bin/cache settings — exit 0;
  installed CPython 3.12.16 under `.python/`.
- `uv lock` — exit 0; resolved 50 packages, including the application.
- `uv sync --frozen --group dev` — exit 0; installed 49 packages in `.venv/`.
- All eight declared runtime/development dependency pins and
  `hatchling==1.27.0` are unchanged. No Git/editable framework dependency.

Installed versions read from distribution metadata:

| Package/runtime | Actual version |
|---|---|
| CPython | 3.12.16 (Windows x86-64) |
| uv | 0.13.9 |
| local-document-agent | 0.1.0 |
| langchain | 1.5.2 |
| langchain-core | 1.8.4 |
| langgraph | 1.2.16 |
| langchain-openrouter | 0.3.0 |
| openrouter | 0.9.2 |
| pydantic | 2.12.5 |
| python-dotenv | 1.2.1 |
| pytest | 9.0.2 |

Lock format: **version 1, revision 5**, 50 package records. Registry sources use
`https://pypi.org/simple`; the application is the sole local editable package.
Build-system hatchling is pinned separately in `pyproject.toml` and used in the
isolated packaging build; it is not claimed to be a runtime installation.

`uv.lock` SHA-256:

```text
4434b4a502034626b21fd5ce9be9660f426450ce5d0b8817fcdec1d09784dc48
```

## Actual files delivered

All paths below are relative to `local-document-agent/`:

```text
pyproject.toml
uv.lock
.python-version
.gitignore
.env.example
README.md
BUILD_STATUS.md
src/local_document_agent/__init__.py
src/local_document_agent/config.py
src/local_document_agent/contracts.py
src/local_document_agent/context.py
src/local_document_agent/filesystem.py
src/local_document_agent/text.py
src/local_document_agent/tools.py
tests/conftest.py
tests/test_contracts_config.py
tests/test_filesystem.py
tests/test_text.py
tests/test_tools.py
```

Ignored local setup artifacts: `.tools/`, `.python/`, `.cache/`, `.venv/`, Python
bytecode, and pytest cache. No private `.env` or personal document collection was
created. Harmless test data is confined to dedicated application-local temporary
directories.

No `provider.py`, `agent.py`, `prompts.py`, `cli.py`, `__main__.py`, console script,
API module, or model mock/loop was added. The full blueprint's future package tree
is not a claim that those later-slice files exist.

## Verification commands and actual results

From the application directory, setup used:

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
$env:UV_PYTHON_BIN_DIR = "$PWD\.tools\bin"
```

Offline test/check commands used:

```powershell
$env:UV_NO_ENV_FILE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-slice1-complete
.\.tools\bin\uv.exe lock --check --offline
.\.tools\bin\uv.exe pip check --python .venv/Scripts/python.exe
```

Final completed suite: **81 passed, 1 skipped**, exit 0, 10.50 seconds.
Lock consistency check: exit 0, 50 packages, no lock regeneration.
Installed dependency compatibility check: exit 0, 49 packages compatible.
Final `uv sync --frozen --offline --group dev`: exit 0, 49 packages checked;
no lock regeneration or version changes.
Source/documentation whitespace check: exit 0, 18 files, no trailing whitespace.
Final parent `git diff --name-only`: empty; only this new application and the
pre-existing untracked `LangChain/` remain untracked. No staging/commits/pushes.

Tests use application-local temporary roots and block socket connections/DNS
before application-module imports. Tracing is disabled and inherited
provider/tracing credentials are removed in the test process.

Earlier execution history (preserved rather than relabelled as passing):

1. Initial full run: **69 passed, 2 failed, 1 skipped**, exit 1.
   - Provider-facing subset schema dropped `additionalProperties: false`.
     Fixed by exposing each original strict Pydantic argument schema.
   - Windows asyncio self-pipe attempted a loopback socket blocked by the
     network guard. The synchronous async-wrapper test now drives its
     non-suspending coroutine without creating an event loop.
   - Symlink fixture skipped: host lacks creation privileges/developer mode.
     The actual junction fixture and opened-handle boundary checks passed.
2. Focused rerun of those two failures: **2 passed**, exit 0.
3. Full run after bounded-I/O and valid-UTF-8 adjustments:
   **72 passed, 1 skipped**, exit 0.
4. Final suite above additionally proves direct search/read/create for all three
   input formats, inventory count bounds, exclusive-open collision preservation,
   failed-write provenance, source-ledger bounds, and sanitized permission errors.

An early installed-API signature inspection exceeded a 10-second command timeout;
rerunning it with a 120-second allowance succeeded. This was an import inspection,
not a provider request.

## What the passing tests establish

- Exact three LangChain tools, simple strict provider-compatible schemas with
  `additionalProperties: false`, and host rejection without argument coercion.
- Direct real-file search/read/create sequences for `.txt`, `.md`, and `.eml`.
- Stable literal search ordering/pagination/snippets, partial results, aggregate
  byte bounds, and no source registrations from discovery alone.
- Actual page content, raw hashes, completeness, normalized/extracted line
  references, changing-version warnings, and bounded source ID allocation.
- Real reports and explicitly unsent drafts with validated source references,
  UTF-8/LF bytes, actual write hashes/counts, and original-file preservation.
- Traversal/drive/UNC/device/ADS/reserved-path rejection, root separation, actual
  Windows junction rejection, opened-handle boundaries, and hard-link rejection.
- Exclusive creation preserves an existing file even after a racing creator wins
  between preflight and exclusive open. Failed fsync never registers success.
- Strict decoding, malformed/HTML-only email failures, attachment/HTML omission,
  oversized raw/extracted/output handling, and no fabricated content on errors.
- Tool-call IDs and success/error `ToolMessage` status are preserved. This is
  direct tool invocation, not a mocked agent loop.
- Fresh-process import requires no API key, transmission consent, `.env`, network,
  or `langchain_openrouter` module import. Package has no fake CLI entry point.

## Skipped checks and reasons

- **1 actual symlink fixture:** insufficient Windows symlink creation privilege/
  Developer Mode. User approved recording the skip. No host policy or privilege
  changes were attempted. Junction and reparse restrictions were exercised with
  a real Windows junction; do not claim the actual symlink fixture passed.
- **All model/provider/agent/CLI checks:** intentionally out of Slice 1. No
  authenticated inference, provider construction, agent fake, SDK retry transport
  test, conversational summary, or model-generated draft was run.
- **Other operating systems and adversarial filesystem races:** not certified.
  Filesystem checks are not an OS sandbox.

## Limitations and remaining issues

- No known failing Slice 1 test. Actual symlink creation remains host-unverified.
- Conservative email rejection can reject imperfect exports. HTML-only content,
  attachments, unsupported formats, and oversized/overlong pages remain unavailable.
- Output access preflight is advisory on Windows; real file operations can still
  fail. A failed write may leave a partial new file; no successful record is
  emitted, no deletion is guessed, and no automatic retry occurs.
- Local calls use bounded synchronous filesystem I/O; cooperative deadlines cannot
  interrupt a hung OS call. Hostile concurrent path replacement is outside the
  documented threat model.
- `ToolContext` is an active sequential host context, not a session manager. It
  holds at most 32 registered read ranges and 32 successful create records.
  Slice 2 must manage turn/retained-source lifecycle and prune observed page data.
- No assistant/model behavior, semantic factual accuracy, prompt-injection
  immunity, provider availability, or live usability has been established.
- GitHub Sai's Section 0 is newer than the local blueprint. The next builder must
  read the cited approved revision (or a confirmed newer Sai revision) and this
  status before editing; do not infer authorization to alter parent documentation.

## Original Slice 1 → Slice 2 handoff (historical; now implemented)

Only after a separate Slice 2 assignment:

1. Preserve these tool contracts, confinement checks, and passing real-file tests.
2. Add `provider.py`, `prompts.py`, `agent.py`, and callable CLI/module entry points.
3. Apply the real inference readiness gate and explicit app-local environment
   loading. Never use dummy production keys or load SecMate configuration.
4. Implement the explicit bounded LangChain message/tool loop, ordinary assistant
   role instructions, sequential dispatch, history/source lifecycle, deadlines,
   budgets, observed activity, `/new`, cancellation, and write-failure reporting.
5. Add offline mocked provider/agent/CLI tests. At the actual integration transport
   boundary, verify `retries=None` disables the SDK retry default, request timeout
   units, exact route, and proper tool-result serialization/correlation.
6. Add no real inference, server, adapter, UI, or SecMate changes.

Slice 2 exit: installed usable CLI works with explicitly mocked providers in tests
and documented real startup is ready for a user-supplied private key. Stop before
Slice 3. Live demonstrations require separate explicit authorization and harmless
sample content; the key must be entered privately.

## Independent Slice 1 audit — 2026-11-20

**Verdict:** substantial, correctly isolated Slice 1 integration, but not an
unqualified clean handoff. Fix blockers A1–A2 and rerun focused regressions before
relying on the tools in Slice 2. A3–A4 are nonblocking integration corrections.
This audit does not certify absence of other defects or future provider issues.
Earlier completion statements above are the builder's record, not this verdict.

### Scope and verification

- Read the README, existing status, all application modules and tests, dependency
  declaration, example configuration and ignores. Design authority was the
  read-only GitHub blueprint at `41fdd4a3a40a3e476db151ebad501f763890d5cd`,
  Section 0 and applicable Sections 4–12/19, not the older local blueprint.
- Initial `git status --short` from the parent repository returned only
  `?? LangChain/` and `?? local-document-agent/`. Neither was staged or changed
  outside this authorized status append. No installation, model construction,
  inference, private environment loading, or SecMate/framework edits.
- Exact test command, from `local-document-agent/`:

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.cache\uv"
  $env:UV_PYTHON_INSTALL_DIR="$PWD\.python"
  $env:UV_NO_ENV_FILE="1"
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
  .\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-audit
  ```

  **Exit 0: 81 passed, 1 skipped in 7.00s**, CPython 3.12.16, pytest 9.0.2.
  Skip: `tests/test_filesystem.py:93`, host lacks symlink privileges/Developer
  Mode. Actual junction, hard-link, opened-handle and exclusive-open tests passed.
  No dependency resolution or installation was repeated.
- One additional stdin probe used the same environment and exact runner
  `@' ... '@ | .\.tools\bin\uv.exe run --frozen --no-sync python -` (exit 0).
  Before application imports it removed inherited `OPENROUTER_*`, `LANGSMITH_*`
  and `LANGCHAIN_*` settings, set all three known tracing flags false, and
  blocked socket connect/connect_ex/sendto, connection helpers and DNS helpers.
  It also used `tracing_context(enabled=False)` throughout. Only fictional
  files under an ignored `.cache/audit-probe-*` TemporaryDirectory were used;
  that directory was removed by its context manager. Reproduction inputs and
  actual outputs are recorded below; these were probes, not added pytest tests.

### Blockers — builder fixes required

**A1 — High: ambiguous MIME headers bypass conservative email extraction.**

- Path: `src/local_document_agent/text.py:54–90`. Checking parser/header defects
  is insufficient: the standard parser accepts duplicate singleton MIME headers
  without defects, and `get_content_type()` / `get()` silently choose the first.
- Reproduction: `extract(raw, ".eml")` with raw bytes
  `b"Content-Type: text/plain\r\nContent-Type: text/html\r\n\r\n<p>html secret</p>"`
  **succeeds**, returning `'\n\n<p>html secret</p>'`. Conflicting duplicate
  `Content-Transfer-Encoding: 7bit` then `base64`, body `Ym9keQ==`, likewise
  succeeds and returns the encoded text as complete body content.
- Expected: reject ambiguous/malformed MIME with `MALFORMED_EMAIL`, rather than
  silently choosing an interpretation and making potentially HTML content
  available to text search/read. This is not a request for HTML conversion or
  more permissive MIME repair.
- Fix: explicitly reject duplicate/conflicting singleton MIME headers on relevant
  parts before choosing content type, disposition, charset or transfer encoding.
  Audit malformed declared charset handling as part of that check: the probe
  `Subject: =?not-a-codec?b?YWJj?=` plus a valid plain body also succeeded as
  `Subject: abc`; header decoding can silently fall back despite the declared
  unknown charset. Reject unsupported encoded-word charsets rather than repairing.
- Regression: conflicting Content-Type/transfer headers at root and nested inline
  parts; invalid encoded-word charset; valid multipart alternative and attachment
  omission must remain unchanged. Through real tools, assert failed reads register
  no source and failed text extraction yields no snippet.

**A2 — Medium: failures after output creation omit uncertain-file reporting.**

- Paths: `filesystem.py:21–31,274–303`, `tools.py:194–221,238–241`.
  Exclusive opening creates a file before the second deadline check. Exceptions
  then lose the distinction between pre-open failure and an output already made.
- Reproduction 1: replace `context.check_deadline` with a check that raises
  `DocumentError("LIMIT_EXCEEDED", "The operation deadline has expired.")` when
  `output/deadline.md` exists; invoke create with ordinary report text. Actual:
  `LIMIT_EXCEEDED`, `data:null`, `warnings:[]`, deadline-only error, **zero-byte
  deadline.md remains**.
- Reproduction 2: patch `os.fsync` to raise
  `PermissionError("private diagnostic")`; create `permission.md`. Actual:
  `PERMISSION_DENIED`, message `Access to the local path was denied.`,
  `warnings:[]`, **file containing b"ordinary" remains**. Neither failure adds
  a successful create record (correct); neither reports the possible output.
- Expected per Sections 7.3/16: failed operations remain failures, but explicitly
  identify the possible partial/new file by safe relative basename. Permission
  errors after creation and post-open deadline failures need the same warning
  discipline as ordinary fsync failures. No blind cleanup or automatic retry.
- Fix: track whether exclusive creation succeeded and preserve sanitized
  uncertain-output metadata/message on every subsequent failure, including
  `DocumentError`, permission, flush/close and verification failures. Ensure
  Slice 2 can render this without inventing a successful created-file event.
- Regression: both probes above, close failure, and pre-open permission/deadline
  failures; assert possible-file notice only where appropriate, no raw exception
  text/absolute path, no success record, and existing-file preservation.

### Nonblocking corrections and Slice 2 interface cautions

**A3 — Medium: Windows case aliases suppress changed-version warnings.**

- Paths: `tools.py:177–184`, `context.py:44`. Ledger identity uses the caller's
  exact string, not Windows path identity. Read `notes.txt` containing `old`,
  replace its bytes with `new`, then read `NOTES.TXT` on this Windows host.
  Actual: R1/R2 have different correct hashes, but the second read has
  `warnings:[]`. Both calls opened the same file; expected changed-version warning.
- Fix: maintain a platform-aware validated canonical path identity for comparison
  while preserving readable relative paths and distinct hash/range entries.
  Do not globally casefold paths on case-sensitive platforms.
- Regression: Windows mixed-case same-file reads with changed and unchanged bytes;
  retain the existing ordinary changed-path test.

**A4 — Medium: tracing rejection is invocation-path dependent.**

- Path: `tools.py:45–73,224–242`. `.invoke()` checks tracing, but inherited
  `.run()` enters LangChain callback handling and executes the tool without that
  check. Build tools with tracing disabled, set `LANGSMITH_TRACING=true`, then
  call `read_tool.run(valid_arguments)`: actual successful read and source event;
  `.invoke()` would reject the same environment.
- The probe kept an explicit disabled tracing context and blocked network, so
  this proves the missing guard, **not an actual disclosure**. README documents
  invoke/ainvoke as the supported boundary; do not accidentally use run/arun in
  Slice 2. Factory/startup checks alone do not make all inherited paths equivalent.
- Fix: guard public execution paths before callback setup, or explicitly constrain
  the controller to the guarded boundary and test that invariant. Regression:
  run/arun and invoke/ainvoke with enabled tracing must not read, write or register
  events; preserve strict argument errors and ToolMessage correlation.

**Deferred, not Slice 1 defects:** provider/agent/CLI absence is correct under
Section 0. Source/history eviction, failed-turn rollback and `/new` belong to
Slice 2. The current ledger is globally capped at 32 and `reads` retains full pages
even after `ledger.discard()`; a naive long-lived shared ToolContext will either
hit that cap or accumulate pages if only ledger entries are pruned. Design a
separate bounded active-turn event lifecycle and retained-source ownership with
monotonic IDs, whole-turn pruning and failed-turn cleanup. Preserve successful
write observations across provider failure, including A2's uncertain outputs.

Other reviewed boundaries match the intended Slice 1 design: strict flat argument
schemas, direct ToolMessage success/error correlation, bounded raw reads/search/
output framing, no discovery-only citations, exclusive writes, local configuration
precedence without parent search/interpolation, and final Windows handle checks
before reading/writing bytes. Hostile concurrent path replacement, advisory Windows
ACL preflight, synchronous bounded I/O and possible partial failed writes are
documented limitations, not demands for a new sandbox or automatic deletion.

**Next gate:** fix A1–A2, preferably A3–A4 as well, add their focused tests and rerun
the offline suite. Then proceed only under a separate Slice 2 assignment, retaining
the existing SDK transport/retry, timeout, history and cancellation gates. No live
usability or future error-free behavior has been established by this audit.

## Builder response to audit — A1–A4 fixed

- **A1:** reject duplicate singleton MIME headers on root/nested parts before
  choosing type/encoding/disposition; validate encoded-word charsets explicitly.
  Regression tests prove no read sources or search snippets from ambiguous MIME.
- **A2:** track successful exclusive-open creation. Every subsequent filesystem/
  document failure includes a safe possible-output basename and warning. The
  context records uncertainty separately from successful creates. Pre-open failures
  have no such notice. Tested deadline, permission, close and verification failures.
- **A3:** compare validated platform-normalized path identities while preserving
  caller-readable relative paths. Windows aliases now warn for changed hashes.
- **A4:** guard invoke/ainvoke/run/arun before LangChain callback execution.
  All four paths reject enabled tracing without reads or source registration.
- Gate command: `uv run --frozen --no-sync pytest --basetemp=.cache/pytest-audit-fixes`
  with the documented isolated/offline environment — **99 passed, 1 skipped**,
  exit 0, 7.77 seconds. Same user-approved symlink privilege skip.

At that gate, the user authorized Slice 2 only; live inference was not yet
authorized. The user also approved a tightly scoped
test-only exception for Windows asyncio's internal socketpair construction.
External connections and DNS remain blocked during tests. No global Windows
privileges or Developer Mode settings were changed.

## Slice 2 offline completion and Slice 3 preparation

### Authority, concurrency and authorization

- Continued on **Sai only**, following the approved Section 0 staged contract.
  The user subsequently authorized Slice 3, real fictional-content tests, and
  bounded app-local sanitized error logs. This explicitly requested logging
  supersedes the blueprint's earlier default of no persistent application log;
  keys, personal document/chat content and raw provider payloads remain excluded.
- During work, repository activity outside this agent advanced HEAD to `eba1b29`
  (merge on Sai, following `a2eed4e` / `41fdd4a`). The application is now tracked
  in that baseline and the local blueprint now includes Section 0. Preserved that
  work. This agent did not stage, commit, merge, pull, push, clean or reset.
- No SecMate component, parent dependency file, or LangChain reference file was
  edited. All new work and notes remain inside `local-document-agent/`.

### Implemented application files and interfaces

- `agent.py`: explicit bounded model → validated tool → ToolMessage loop;
  sequential execution, exact call-ID validation, ordinary error feedback,
  repeated-failure stopping, no semantic repair loop, no retry/fallback.
- `provider.py`: real `ChatOpenRouter` using exact pinned SDK/integration; explicit
  SDK `retry_config=None` **and** `retries=None` per invocation; millisecond
  request timeouts; fixed requested free route and no provider fallback. SDK
  payload debug logging is disabled even with inherited `OPENROUTER_DEBUG`.
- `prompts.py`: normal document-assistance instructions and honest transmission
  disclosure; no evaluation objectives. Retrieved content is data, not authority.
- `context.py` / `agent.py`: fresh per-turn observed-operation contexts with
  bounded retained source metadata; whole-turn history pruning, monotonic source
  IDs, failed-turn reference removal, `/new`, and no accumulating read-page event
  log. Successful writes survive conversation failure/cancellation. Earlier
  references exposed to the model are reported separately from new reads.
- `cli.py`, `__main__.py`, `pyproject.toml`: actual installed console and module
  entry points; chat, tool activity, observed source/output footers, uncertain
  output warnings, reset/help/exit, EOF/cancellation, and configuration gates.
  No fake or alternate-provider CLI mode.
- `diagnostics.py`: ignored `.logs/errors.log`; 1 MiB current file and three
  backups. Allowlisted timestamp/version/phase/code/session/tool metadata and up
  to eight safe code-location frames. No exception prose, source lines, locals,
  credentials, prompts, snippets, documents, draft bodies, raw responses or
  document filenames enter the log API. Logging degradation is explicit, not
  silently reported as durable success.
- `examples/input/`: three fictional launch/budget/email samples.
  `examples/live_smoke.py`: guarded real-model demonstrations with ordinary
  prompts, actual tools and CLI renderer; no forced tools or scripted replies.
  New isolated fictional roots per invocation, no personal input directory read.
  Three turns, configured bounds, no automatic retries; a failed turn stops later
  tasks. Actual outputs and metadata-only `outcomes.json` remain under ignored
  `.cache/live-demo-<id>/`.
- Updated `README.md`, local ignores and tests. The package version remains
  `0.1.0`; Python 3.12.16, uv 0.13.9 and every dependency pin remain unchanged.

### Commands and observed results

All uv commands were run from the application directory using app-local uv/Python/
cache settings, `UV_NO_ENV_FILE=1`, and offline test isolation. Tests never load
the real application `.env` or construct a real network-connected provider.
User-approved Windows internal socketpair creation is the only test networking
exception; provider connections, direct outbound sockets and DNS are blocked.

1. `uv lock --offline` — exit 0, 50 packages; no pin changes.
2. `uv sync --frozen --offline --group dev --reinstall-package local-document-agent`
   — exit 0, rebuilt/reinstalled **only** this application to install the real
   console entry point.
3. First Slice 2 focused run — **31 passed, 2 failed**, exit 1.
   - The context-pruning fixture did not exceed its chosen budget; adjusted the
     fixture to actually exercise whole-turn eviction.
   - The real SDK correctly rejected a mock response missing its required
     `system_fingerprint` field. Corrected that fixture and added a regression
     asserting malformed success responses produce a sanitized protocol error.
     No production coercion or framework patch was introduced.
4. Focused rerun of those two cases — **2 passed**, exit 0.
5. First complete Slice 2 suite:
   `uv run --frozen --no-sync pytest --basetemp=.cache/pytest-slice2-full`
   — **134 passed, 1 skipped**, exit 0, 20.32 seconds.
6. Pre-live gate with cancellation/diagnostic regressions:
   `uv run --frozen --no-sync pytest --basetemp=.cache/pytest-prelive-gate`
   — **141 passed, 1 skipped**, exit 0, 22.46 seconds.
7. Latest complete suite:
   `uv run --frozen --no-sync pytest --basetemp=.cache/pytest-cli-final`
   — **142 passed, 1 skipped**, exit 0, 21.91 seconds.
8. `uv lock --check --offline` — exit 0, 50 packages.
   `uv pip check --python .venv/Scripts/python.exe` — exit 0, 49 packages compatible.
9. `git check-ignore` confirms `.env`, `.logs/errors.log`, `.venv` and `data/input`
   are ignored. No secrets or generated personal data are staged.
10. Final `uv sync --frozen --offline --group dev` — exit 0, 49 packages checked.
    `git diff --check` — exit 0. Explicit source/documentation/fictional-sample
    whitespace check — 33 files, zero findings; excluded the real `.env`.
    Tracked changes are application-local only.

Lock format remains version 1 / revision 5, with unchanged SHA-256:

```text
4434b4a502034626b21fd5ce9be9660f426450ce5d0b8817fcdec1d09784dc48
```

### What the offline gate now establishes

- All original tool/audit regressions still pass.
- Mocked agent and CLI sequences cover document summary, unsent reply draft and
  report creation with actual local tools, not fabricated filesystem outcomes.
- Real pinned LangChain → OpenRouter SDK → `httpx.MockTransport` tests prove
  provider-compatible schemas, serialized calls/results, timeout units, exact
  route, no inherited session/broadcast metadata, and no payload logging.
- Mocked 401/402/429/500/400 and timeout responses make one transport attempt each;
  no SDK retry/fallback occurs. A full real-SDK mocked-transport agent sequence
  reads a file, creates a report, and returns genuine host provenance.
- Invalid/missing/duplicate call IDs and malformed/truncated responses cannot
  trigger filesystem effects. Unknown tools and bad arguments receive ordinary
  correlated errors; repeated identical failed calls stop.
- Tests cover model/tool/token/context limits, real request timeout, accelerated
  real asyncio outer timeout, whole-turn eviction, 40 sequential bounded turns,
  `/new`, cancellation, provider failure after a write, and cancellation after a
  write. Successful/uncertain files remain distinct and visible.
- Console and module `--help` work without credentials. Startup missing-key and
  missing-consent errors do not construct a provider. Real startup/shutdown
  boundaries are also exercised using an explicit injected test provider.
- Rotating diagnostics exclude marker keys, user prompts, document/body text,
  private filenames, exception prose and full machine paths. Disk write failure
  marks diagnostics unavailable rather than disrupting a completed file write.
- The explicit live-runner flag is checked before reading private configuration.

### Actual Slice 3 credential gate — blocked, not run

- The user said credentials were already app-local. A readiness-only check found
  **no `local-document-agent/.env`**; it did not inspect parent environments or
  print values and performed no inference.
- At the user's request, created a private `.env` **exclusively**, from the blank
  `.env.example`, with key empty and transmission consent false. Existing files
  would not have been overwritten. Created/preserved app-local `data/input` and
  `data/output`; no document collection was read.
- Asked the user to add the key privately and set consent true, then confirm
  readiness. Do not poll or repeatedly read the file while it is being edited.
- **No authenticated live model request or live demonstration has run.**
  Do not relabel mocked checks as Nemotron usability or claim final Slice 3
  completion. No retries or fallback have been attempted.

### Remaining limitations and next action

- One approved skip remains: actual Windows symlink fixture creation privilege.
  Actual junction, opened-handle and hard-link restrictions passed.
- The pinned SDK expects particular response fields (including
  `system_fingerprint`); catalog availability alone does not establish that the
  live route returns a compatible shape. Unsupported responses are surfaced
  safely, not repaired silently.
- Model interpretation/source accuracy, live capacity, free quotas, provider
  privacy policy, and live CLI usability remain unverified. No application can
  promise zero provider/model errors or durable logging when storage is broken.
- After the user confirms private key setup, check readiness without displaying
  values, then run once:

  ```powershell
  $env:UV_NO_ENV_FILE="1"
  .\.tools\bin\uv.exe run --frozen --no-sync python examples/live_smoke.py --run-live
  ```

  Use only fictional example roots. Record the actual summary/reply/report
  outcomes, output paths, safe error codes and any not-run tasks here. If a defect
  is reproduced, fix narrowly, rerun affected offline checks, and discuss any
  consequential change before another live attempt. Do not retry until success,
  force tools, swap models, or broaden scope.
- Normal CLI is ready after private setup:
  `uv run --frozen --no-sync local-document-agent` (or the module entry point).
  See README for app-local uv path and configuration. No API adapter, onboarding
  UI, SecMate changes, production infrastructure, commit or push is authorized.

## Mock input workspace and user manual

### Scope and installation

- User requested populated mock `.txt`, `.md`, and `.eml` inputs and a full usage
  manual. Started on Sai with a clean working tree; existing work was preserved.
- Resolved the actual configured roots without printing credentials:
  `local-document-agent/data/input` and `local-document-agent/data/output`.
- Existing `data/input/test.txt` was not opened or written. The configured output
  files were not read or modified.
- Added **18 fictional files**, totaling **16,960 bytes**:
  **10 Markdown, 4 text, 4 plain-text emails**.
- Reusable source collection: `examples/mock-workspace/`.
  Installed input collection: `data/input/mock-workspace/`.
  Runtime copies are ignored by Git; reusable examples and the manual are normal
  source artifacts. Used exclusive target-directory and file creation, not
  overwrite/merge copying.
- Content covers one coherent Harbor project: current/historical budgets and
  meeting dates, actions, risks, people, approvals, onboarding, a report template,
  and related emails. All identities and `example.invalid` addresses are fictional.
  This is retrieval material, not training, permanent learning or a model change.
- Added `USER_MANUAL.md` with startup, exact paths, discovery, cited summaries,
  version comparison, task extraction, saved reports, unsent replies/new drafts,
  output inspection, memory/limits, privacy and troubleshooting. README links it.

### Actual verification

- An initial long inline shell probe was rejected by the tool's portable command
  scanner before execution. Moved the probe into ignored
  `.cache/validate_mock_workspace.py`; this was not an application failure.
- Ran:

  ```powershell
  .\.venv\Scripts\python.exe .cache/validate_mock_workspace.py
  ```

  **Exit 0.** The probe blocked network, disabled tracing, loaded no key/private
  configuration, constructed no provider, and used only the fictional subfolder
  plus a new temporary output directory.
- All 18 installed files match the reusable copies by SHA-256.
- Actual LangChain tools successfully read every file completely with source IDs
  and correct raw hashes. All four `.eml` files extracted successfully.
- Repeated text searches returned identical results; filename search found four
  emails. Discovery alone registered no sources.
- Actual report and email-draft writes succeeded in temporary output.
  Reports included observed source references; drafts had the NOT SENT heading.
  Attempted reuse of the report filename returned FILE_EXISTS without changing
  its bytes.
- Every input hash was unchanged afterward. Temporary validation outputs were
  removed by their owning TemporaryDirectory context. Normal output was untouched.
- All 14 unique explicit sample-file paths in the manual resolve to installed
  inputs. `git diff --check` passed; runtime copies and the probe are Git-ignored.
- No runtime/dependency/integration changes were needed, so the full application
  suite was not rerun for this data/documentation-only addition. Previous full-suite
  results above remain historical, not new live/model evidence.
- No staging, commits, pushes, SecMate changes, parent dependency edits, reference
  checkout edits, or live inference were performed for this assignment.
