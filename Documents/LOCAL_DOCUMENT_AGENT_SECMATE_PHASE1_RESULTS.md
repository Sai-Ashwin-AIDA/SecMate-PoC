# Local Document Agent → SecMate: Phase 1 results

**Disposition:** offline HTTP foundation implemented; human acceptance **PENDING**.
**Date:** 2026-11-20. **Phase 2: NOT IMPLEMENTED / NOT AUTHORIZED.**

## 1. Authority, checkpoint and preserved work

- Controlling assignment: `Documents/LOCAL_DOCUMENT_AGENT_SECMATE_INTEGRATION_BLUEPRINT.md`,
  Phase 1 only, including its fixed HTTP contract and human acceptance gate.
- Repository root confirmed as the `SecMate-PoC` checkout, branch **Sai**.
  Initial checkpoint was `c1f6fb5`; the controlling integration blueprint was
  missing, so implementation stopped and asked for it rather than substituting
  the older agent blueprint.
- After the user said to continue, checkpoint was **`630fbde`**, with the
  integration blueprint present, one primary worktree and a clean working tree.
  That concurrent checkpoint was preserved; HEAD remained `630fbde` at verification.
- Read the latest `local-document-agent/BUILD_STATUS.md`, including its final
  mock-workspace/manual verification, mapped app contracts and relevant blueprint
  sections. Historical live/CLI claims were not relabeled as new evidence.
- Changes are restricted to the independent application and this results file.
  No SecMate frontend/API/worker, framework checkout, core agent behavior, existing
  dependency pin, private `.env`, runtime input or existing output was changed.
- Runtime Harbor/output directory existence was checked without opening their
  documents or enumerating outputs. Both existed; no setup copying was needed.
  All write/provenance tests used isolated temporary roots.
- No staging, commit, push, branch switch, reset, live model call or actual server
  launch was performed.

## 2. User questions and approvals

| Question | User-approved decision |
|---|---|
| Missing controlling assignment | Wait; user subsequently supplied it in the newer checkpoint and requested continuation. |
| Exact HTTP pins/installation | Optional app-local `http` extra only: FastAPI `0.121.3`, base Uvicorn `0.38.0`; preserve all existing locked versions; review transitive additions before installing. |
| HTTP-specific root settings | Fix production roots beneath the explicit app root to `data/input/mock-workspace` and `data/output`; trusted temporary-root injection for tests only. |
| Exact UUID spelling | Canonical lowercase hyphenated UUID strings; no normalization/coercion. Malformed run-path IDs return safe 404. |
| Bounded shutdown | One total **10-second** deadline covering active cancellation and provider cleanup; stop new acceptance immediately; no retries; report timeout as incomplete/unknown. |
| Cleanup failure and core outcome | Lifecycle `failed` plus separate safe adapter error/cleanup status; preserve the original core result, answer and file observations unchanged. |
| Reusing a slot after close failure | Keep the slot unavailable for that instance; operator review and deliberate restart, no cleanup retry. |
| Existing one-script regression | Narrowly update the packaging assertion to require exactly the original CLI and the approved separate HTTP entry point, both real callables. |

No credentials were requested in chat or printed. No private configuration was
loaded during builder verification.

### Dependency evidence

PyPI metadata verified the approved direct pins support Python 3.12 and the
existing Pydantic 2.12.5. The selected minimal FastAPI release avoids the latest
release's mandatory OpenTelemetry dependency. This is a narrowly approved PoC
dependency choice, not a vulnerability certification or claim of newest releases.

| Added package | Locked and installed version |
|---|---|
| fastapi | 0.121.3 |
| uvicorn | 0.38.0 |
| starlette | 0.50.0 |
| annotated-doc | 0.0.7 |
| click | 8.5.1 |

Lock resolution: **55 package records** (previously 50). The reviewed diff adds
only these five records and application optional-extra metadata. A subsequent
TOML comparison against `HEAD:local-document-agent/uv.lock` confirmed **zero
changes/removals to existing locked package versions**. Installed application
version remains `0.1.0`; Pydantic remains `2.12.5`; Python remains `3.12.16`.
No `uvicorn[standard]`, telemetry or unrelated dependency was installed.

Current lock SHA-256:

```text
ecd158bbb2261c482450bcacaf1a3b0db23f90a2f7d6cb5373562d27ca73b101
```

## 3. Changed files and implementation

Paths below are relative to `local-document-agent/`, except this results file:

| Path | Change |
|---|---|
| `src/local_document_agent/http_contracts.py` | Strict versioned request/metadata/result/error envelopes, UUID/message validation, effective bounds. |
| `src/local_document_agent/http_config.py` | Explicit app-local configuration overlay, distinct secret token, fixed production roots, no-inference readiness. |
| `src/local_document_agent/http_adapter.py` | Authenticated injectable ASGI app; atomic receipt/slot ownership, fresh core sessions, lazy providers, deduplication, immutable terminal snapshots, cancellation and shutdown. |
| `src/local_document_agent/http_cli.py` | Separate loopback-only, one-worker entry point; no-reload/no-access-log startup; side-effect-free help. |
| `tests/test_http.py` | 48 isolated HTTP/core/tool/SDK boundary and lifecycle cases. |
| `tests/test_contracts_config.py` | User-approved packaging assertion for exactly two actual entry points. |
| `pyproject.toml`, `uv.lock` | Optional exact HTTP dependencies and separate command; no original CLI target/pin changes. |
| `.env.example` | Blank adapter-token setting only; no real secret generated. |
| `README.md` | Exact setup/authenticated HTTP examples, limits, failure/cleanup/retention semantics and offline commands. |
| `USER_MANUAL.md` | Brief separate HTTP startup link and Harbor-relative-path clarification. |
| `BUILD_STATUS.md` | Brief pointer to this result, preserving historical sections. |
| `../Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE1_RESULTS.md` | This actual outcome and pending human-review record. |

The existing `DocumentAssistant`, provider lifecycle, configuration parsing,
`FilesystemRoots`, `Source`, `CreateData`, three tool wrappers, prompts, route,
budgets, SDK retry suppression and diagnostic format are reused unchanged.
Factories are trusted Python test injection points, never public request knobs.
No SecMate target ID, registry, UI, worker gateway or assessment logic was added.

## 4. Actual contract and configuration

Installed command: `local-document-agent-http`, default **127.0.0.1:7310**,
one Uvicorn worker, no reload. Explicit `--port` and `--app-root` options exist;
there is no public bind-host or worker-count override. No service was started by
the builder. `--help` imports no HTTP stack/configuration/provider and writes nothing.

Private configuration uses the explicit application `.env` plus process overlay,
with no parent search/interpolation. Add privately:

```dotenv
LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN=
```

The actual token must be nonblank ASCII without whitespace and distinct from the
provider key. The tracked example stays empty. Existing CLI input/output settings
and the private `.env` were not rewritten. Provider readiness still requires the
original fixed route, key and explicit document-transmission consent.

Every endpoint requires the adapter bearer token, compared without logging it:

| Endpoint | Behavior |
|---|---|
| `GET /v1/metadata` | Bounded configured/unverified identity, readiness, read/create-only capabilities, effective limits and observation gaps; no provider construction/body reads. |
| `POST /v1/runs` | Strict body below; 202 receipt for accepted or identical deduplicated submission. |
| `GET /v1/runs/{run_id}` | Read-only lifecycle/result snapshot; no new inference or output scan. |
| `POST /v1/runs/{run_id}/cancel` | Idempotent cancellation acknowledgement; never claims settlement before task completion. |

Example request (placeholder IDs are illustrative; callers use metadata and a
new canonical UUID, not literal placeholders):

```json
{
  "contract_version": "secmate-agent-http-v1",
  "adapter_instance_id": "<current metadata UUID>",
  "submission_id": "<caller-generated lowercase hyphenated UUID>",
  "message": "Read projects/harbor/overview.md and briefly summarize it with references."
}
```

Unknown fields/coercion, invalid IDs, blank messages, invalid UTF-8 and more than
4000 characters fail before acceptance. The streaming reader enforces **32 KiB**
before JSON parsing, including chunked bodies. Accepted message whitespace and
UTF-8 bytes are unchanged; `request_sha256` hashes message bytes, not JSON.

Acknowledgement fields: `contract_version`, `adapter_instance_id`, `run_id`,
`submission_id`, `request_sha256`, `accepted_at`, `state`, `status_path`,
`cancel_path`. IDs are opaque UUIDs; paths are service-relative.

Snapshots additionally contain UTC `started_at`/`finished_at`,
`elapsed_seconds`, `cancel_requested`, `cleanup_status`, `disposition`,
`tool_events`, `result`, `adapter_error`, `limits`. Core `result` retains
session/status/answer and its UTF-8 hash, actual source/create records, retained
sources, uncertain outputs, unverified citations, bounded summaries and safe
errors. `observed_model`, `observed_provider`, `model_call_usage` are **null**:
the existing core does not expose complete observations of those fields.
Source IDs are run/session-local; file paths remain root-relative.

### Enforced ownership and bounds

- One event-loop-owned execution slot, acquired atomically with the receipt.
  No queue; a new competing intent gets 409 `TARGET_BUSY`.
- Fresh assistant/session per accepted execution; no cross-run history/source
  ledger reuse. Production tools remain search/read/create with original behavior.
- Same-instance identical submission/hash returns its original run before
  busy/capacity checks. Conflicting message bytes get 409 `SUBMISSION_CONFLICT`.
- At most **32** retained runs/receipts, no eviction. The 33rd new intent gets
  503 `RUN_CAPACITY_REACHED`. Restart changes instance ID; stale replay gets
  409 `ADAPTER_INSTANCE_CHANGED`.
- Configured core defaults remain eight model calls, twelve tool calls,
  30-second request / 120-second turn timeout, 2048 output tokens/call,
  32768 conservative context units, 80000 cumulative turn budget units and four
  retained history turns (HTTP never continues that history). Existing validated
  bounds cannot be raised through HTTP.
- Original tool bounds are exposed too: 256 KiB raw/extracted input, read pages
  200 lines/12000 characters, search 1000 entries/eight levels/five seconds/16 MiB
  aggregate reads/20 hits, create 24000 content characters/64 KiB framed bytes.
- Result snapshots become byte-stable at terminal settlement. Terminal polls or
  cancellation cannot mutate them or issue another provider/file operation.
- Cancellation targets only the owned chat task, never unrelated CLI work.
  Repeated cancellation does not cancel provider closure. The owner stays strongly
  referenced through settlement. Successful/uncertain writes remain visible.
- A close failure preserves the core result, marks adapter lifecycle/cleanup
  failed and keeps the slot unavailable. A timeout leaves nonterminal state and
  disposition/cleanup unknown, retaining ownership; no fabricated cancellation.
- Shutdown stops new acceptance and applies one total 10-second cooperative wait
  to cancellation plus cleanup. It logs sanitized `SHUTDOWN_TIMEOUT` on expiry.
  No repeated close, automatic retry, output rollback or resubmission occurs.
- Unauthorized requests return 401 before body handling; malformed/unknown runs
  404; invalid bodies 422; oversized bodies 413; identity/busy conflicts 409;
  readiness/capacity failures 503. Errors do not echo rejected values/exceptions.
  Docs/schema routes, redirects, CORS/cookie auth and access logs are disabled.

## 5. Commands and actual verification

Working directory for application commands: `local-document-agent/`.
Environment used for uv/test gates:

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
$env:UV_PYTHON_BIN_DIR = "$PWD\.tools\bin"
$env:UV_NO_ENV_FILE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
```

| Actual command/check | Exit | Observed result |
|---|---:|---|
| `.\.tools\bin\uv.exe lock` after direct-pin approval | 0 | 55 records; exactly five expected additions. Reviewed lock diff before installation. |
| `.\.tools\bin\uv.exe sync --frozen --extra http --group dev` | 0 | Installed five new packages; rebuilt/reinstalled only the local application for its new entry point. |
| `.\.tools\bin\uv.exe run --frozen --no-sync pytest tests/test_http.py --basetemp=.cache/pytest-http-phase1-focused` | 0 | **41 passed**, 8.25 seconds. |
| `.\.tools\bin\uv.exe run --frozen --no-sync pytest tests/test_http.py --basetemp=.cache/pytest-http-phase1-focused-expanded` | 0 | **48 passed**, 7.86 seconds. |
| `.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-http-phase1` | 1 | **189 passed, 1 failed, 1 skipped**, 31.29 seconds. Existing packaging test assumed one script. |
| User-approved exact-entry-point assertion fix | — | Now asserts original CLI target plus HTTP target and real callability; no runtime/core change. |
| `.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-http-phase1-final` | 0 | **190 passed, 1 skipped**, 25.97 seconds, including all 48 HTTP cases. |
| `.\.tools\bin\uv.exe lock --check --offline` | 0 | 55 packages; lock consistent. |
| `.\.tools\bin\uv.exe pip check --python .venv/Scripts/python.exe` | 0 | 54 installed packages compatible. |
| Python TOML/installed-distribution comparison against HEAD lock | 0 | Existing locked-version changes `{}`; installed additions match approved lock; lock hash recorded above. |
| `git diff --check` | 0 | No whitespace errors; Git emits ordinary LF→CRLF conversion warnings for this Windows checkout. |
| Explicit changed-file whitespace check, including untracked new files | 0 | 13 files, zero findings; private `.env` excluded. Final status remains on `Sai` / `630fbde`, with only the listed authorized changes. |

**One skip:** `tests/test_filesystem.py:93`, actual symlink fixture requires
Windows privileges/Developer Mode unavailable on this host. The prior approved
skip was preserved; no host policy/privilege changes. Actual junction,
opened-handle, hard-link, confinement and exclusive-write regressions passed.

An early informational installed-version probe requested Click before it was
installed and raised `PackageNotFoundError`; it was replaced by an
availability-aware metadata probe. This was not a test/provider failure and made
no dependency change. No failing attempts have been relabeled as passing.

The existing collection-time network/DNS blocks, tracing suppression and
credential removal remain in use. The approved Windows internal asyncio
socketpair exception is unchanged. New HTTP tests remove the inherited adapter
token, use explicit fake settings/temporary `.env` files only and in-process ASGI.
No TCP service was started, private `.env` read, real provider traffic made or
live model usage consumed.

## 6. Observed offline evidence

- Both report and email-draft scenarios traverse **ASGI HTTP → real
  DocumentAssistant → real search/read/create tools → real pinned SDK →
  httpx.MockTransport**. Each uses four mocked completion responses.
  Raw input hashes and created-file hashes/counts match actual temporary bytes.
  Draft bytes retain `EMAIL DRAFT — NOT SENT`; inputs are unchanged.
- Duplicate same-ID/same-message submissions retain one run, one provider
  sequence and one created file. Conflicting reuse fails. Polls and terminal
  cancellation return identical final snapshot bytes without another operation.
- Accepted surrounding whitespace/non-ASCII input reaches the core unchanged and
  has the expected exact UTF-8 request hash; available answer/hash is unchanged.
- Discovery alone yields no source. Model claims of reads/saves do not create
  provenance; an invented `R99` is explicitly unverified. Existing-file collision
  returns `FILE_EXISTS`, with existing bytes unchanged.
- Failure, model-call limit and cancellation **after an actual create** preserve
  the file and successful record. Injected fsync permission failure leaves a
  possible output and reports it separately, without a successful create record.
- Separate runs have different sessions and no message/source carryover.
  Referencing prior-run `R1` fails `UNKNOWN_SOURCE` without creating an output.
- Mock SDK 401/429/503 responses become truthful failed run results with safe
  codes and one attempt each. Original SDK retry/timeout/privacy regressions pass.
- Metadata/app construction uses no provider or document-body read. Import/help
  succeeds in a fresh subprocess with configuration/provider access blocked.
  Startup tests replace Uvicorn; they verify loopback/one-worker/logging arguments
  without opening a port. Missing adapter token fails without filesystem writes.
- Normal shutdown cancels the active task, preserves a pre-cancellation write
  and closes its owned provider. Deadline tests accelerate the wait to 0.01
  seconds while holding closure: no terminal-cancelled claim, slot retained,
  `SHUTDOWN_TIMEOUT` recorded; repeated cancellation does not interrupt closure.
  Tests release the fake closure afterward to finish cleanly.
- Separate close-failure tests preserve completed/cancelled core results and
  mark lifecycle failed, retaining the unavailable slot. No cleanup retry occurs.
- The 33rd new retained run is rejected; retrying the first still returns its
  original receipt. A simulated restart rejects the old instance and cannot
  retrieve its old in-memory run.
- Authentication/validation errors, mocked provider errors, diagnostic capture
  and server startup options do not expose tested token/key/private-error markers.
  No raw submitted body/header/stack trace is returned by adapter error handlers.

## 7. Separate dispositions

| Area | Actual disposition |
|---|---|
| Offline adapter/core/tool wiring | **PASS:** 190 passed, one documented Windows privilege skip. |
| Existing CLI live usability | **USER-REPORTED**, not newly demonstrated by builder. Offline CLI regressions pass. |
| Actual live HTTP demonstration | **NOT RUN**; requires separate explicit authorization and private settings. |
| Actual listening-server/manual HTTP check | **NOT RUN**; tests use ASGI and mocked server startup only. |
| SecMate onboarding / assessment integration | **NOT IMPLEMENTED IN PHASE 1**. |
| Human acceptance / Phase 2 permission | **PENDING / NOT GRANTED**. |

## 8. Limitations and exact human startup/manual checks

No current offline test blocker remains. Human acceptance and live usability are
not established. Source references prove what was returned, not model factual
accuracy or successful security testing. Full arguments/call IDs/authorization
traces/streaming and complete usage/observed model identity are not available
from the current core, and were not invented.

This is an in-memory local PoC, not durable jobs or an OS sandbox. Same-machine
malicious filesystem replacement, blocked synchronous OS calls, other platforms,
concurrent output changes and real listening-server behavior are not certified.
The ten-second shutdown test proves cooperative ownership behavior with an
accelerated test wait; it does not prove hard preemption or real-network cleanup.
Provider construction failures expose only a safe adapter error, not speculative
file/model success. Model-authored answer text remains untrusted exact content,
not a security verdict. Dependency compatibility tests are not a dependency
security audit.

Shared output is not automatically fresh. Existing names can collide, partial
new files can remain after failures and cancellation cannot undo successful
writes. No file is downloaded/reopened to manufacture provenance. At restart
the old receipt/result set is lost; absence is **unknown disposition**, never
proof no model request or file effect occurred. Collect results before a
deliberate restart and do not automatically resubmit.

From `local-document-agent/`, after reviewing this record:

```powershell
$env:UV_CACHE_DIR = "$PWD\.cache\uv"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
$env:UV_PYTHON_BIN_DIR = "$PWD\.tools\bin"
$env:UV_NO_ENV_FILE = "1"
.\.tools\bin\uv.exe sync --frozen --extra http --group dev
.\.tools\bin\uv.exe run --frozen --no-sync local-document-agent-http --help
```

1. Review all changed paths, five exact added package versions, failed-attempt
   record, offline/mock distinction and retained limitations.
2. Privately supply the distinct adapter bearer token and keep the application's
   own provider key/route/consent. Never paste keys in chat or copy SecMate's `.env`.
   Do not overwrite the private `.env` from the example.
3. Confirm existing Harbor input and separate output roots. If absent, ask before
   copying tracked examples or creating anything; never merge over existing data.
4. Manually start:
   `.\.tools\bin\uv.exe run --frozen --no-sync local-document-agent-http`.
   If port 7310 conflicts, do not replace another process; decide explicitly on
   a different loopback `--port`.
5. Verify missing/wrong token gives 401 and authenticated `/v1/metadata` works
   without a model call. Full private-token PowerShell examples are in the README.
6. **Only if separately authorized**, submit one benign Harbor request using
   metadata's instance UUID and a fresh submission UUID. Poll the relative status
   path; if creating a report/draft, use one unique new output filename. Compare
   actual source/output hashes manually without changing existing files.
7. Replay the exact same submission/message under the same instance and verify
   the original receipt and no repeated effect. Do not treat new-instance replay
   or a missing receipt as permission to retry.
8. Record actual human observations, including unavailable-route failures.
   Explicitly accept Phase 1 or request corrections. No Phase 2 work follows
   without separate approval and a separately scoped blueprint amendment.

## 9. Human acceptance gate

| Gate | Disposition |
|---|---|
| Builder offline checks | **PASS: 190 passed, 1 skipped**; lock/installed compatibility checks pass. |
| Human review of code/results | **PENDING** |
| Human manual HTTP check | **PENDING / NOT RUN** |
| Human permission to add Phase 2 | **NOT GRANTED** |

**STOP: handed back for explicit human review and acceptance.**
