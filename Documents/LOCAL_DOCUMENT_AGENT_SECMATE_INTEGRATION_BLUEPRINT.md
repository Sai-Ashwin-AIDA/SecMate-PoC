# Local Document Agent → SecMate integration blueprint

**Status:** Phase 1 implementation assignment; not an implemented connection.
**Source checkpoint reviewed:** `c1f6fb57d46a55b857ccfceb507766c93793022b` (`agent upgrade`).
**Planning date:** 2026-11-20.
**Operating model:** local internal PoC, one independently running target service.

> IMPLEMENT PHASE 1 ONLY. Produce its results record and STOP for human review.
> Do not add or implement Phase 2 until the user accepts Phase 1 and explicitly
> requests the next document amendment. Completion of tests is not permission to
> continue into SecMate onboarding or assessment execution.

## 1. Builder instructions: read first

1. Confirm the actual repository root, branch, working-tree state, and source
   checkpoint. Preserve existing changes. Do not reset or switch branches.
2. Read this document and the latest relevant sections of:
   - `local-document-agent/BUILD_STATUS.md`;
   - `local-document-agent/README.md` and `USER_MANUAL.md`;
   - `Documents/LOCAL_DOCUMENT_AGENT_BLUEPRINT.md` §§0, 5–7, 9, 13–16, 22;
   - the small source map in §3 below.
3. Ask the user about **every unresolved doubt, including minor ambiguities**,
   before choosing an interpretation or modifying the affected behavior. Do not
   silently invent defaults, broaden scope, change a contract, or select a
   replacement design. This applies to dependency compatibility, configuration,
   endpoint semantics, evidence exposure, testing and unexpected existing code.
4. Questions must state the precise uncertainty and recommended narrow choice.
   Batch independent questions when possible. Do not re-ask decisions explicitly
   settled here; do not request credentials in chat.
5. Work in the order in §9. Use focused source reads and tests. Do not rescan the
   LangChain checkout, redesign SecMate, or produce an exhaustive audit. If a
   documented API differs from the installed pin, inspect only that boundary and
   ask before changing the design.
6. Log actual results in the required Markdown file (§11), then stop. Never fill
   in passing counts or live claims before executing the corresponding checks.

This new assignment narrowly supersedes the original agent blueprint's deferred
HTTP-adapter prohibition **for Phase 1 only**. It does not authorize changes to
SecMate runtime, the agent's tools/prompt/model behavior, or later integration.
The original blueprint and historical build records must not be rewritten.

## 2. Goal and confirmed user decisions

The eventual product goal is a simple **Onboard target** button on SecMate's
Targets page leading to a short onboarding page, with the connected target
selectable in normal Assessments. Retain the existing DeepTeam catalogue and
existing synthetic targets. This paragraph is context, not implementation scope.

Confirmed decisions:

- The document agent may run on the same computer as SecMate, in a separate
  service/process and isolated Python environment.
- Use a reusable, versioned HTTP adapter contract, initially implemented for this
  agent only. Do not claim arbitrary existing APIs implement the contract.
- Authenticate with an **agent-local bearer token**, distinct from OpenRouter's
  provider key. Future SecMate registration will store a server-side connection
  credential/reference, not the agent's OpenRouter key.
- All three actual tools remain enabled: `search_documents`, `read_document`,
  `create_document`. Creation means a real local file, not a synthetic write or an
  approval-gated message proposal.
- HTTP input is **Harbor-only**: `local-document-agent/data/input/mock-workspace`.
  Output remains `local-document-agent/data/output`, with existing create-only
  behavior and no overwrites. Do not include `data/input/test.txt`.
- Allow a small exact-pinned app-local FastAPI/Uvicorn dependency addition.
- HTTP foundation comes first. There is **no SecMate UI in Phase 1**.
- The first eventual assessment milestone is direct-input, single-turn. Document
  injection and broader execution coverage are not part of this assignment.
- The user reports the CLI already responds using the real model. Treat this as
  **user-reported usability**, not a newly observed HTTP or SecMate demonstration.

### What qualifies as a genuine target

A same-machine service can be an independently assessed target: SecMate will
eventually send exact requests over HTTP to a separately executing agent using
its own model client and real tools. Do not import the document assistant into
SecMate or make a SecMate fixture imitate its responses.

Label this agent as a **connected agent** when product integration is later
authorized. Do not call it synthetic merely because its documents are fictional;
do not call it third-party-owned, independently certified, production-equivalent,
or secure. Endpoint metadata is self-reported, not cryptographic attestation.
Mocked tests prove wiring; a separately authorized live observation proves that
particular model-backed execution. Neither proves penetration-test coverage.

## 3. Verified starting point and source map

Commit `c1f6fb5` adds a user manual, build-status updates, and 18 reusable Harbor
documents: 10 Markdown, four text, four plain-text email files. It does not add
HTTP or SecMate integration. Runtime-installed copies under `data/` are ignored
and may be absent after a source-only transfer.

| Path | Reuse / inspect |
|---|---|
| `local-document-agent/src/local_document_agent/agent.py` | `DocumentAssistant`, `chat()`, `new_session()`, `TurnResult`, `ToolActivity` |
| `.../config.py` | Explicit app-local settings, provider-readiness and tracing gates |
| `.../provider.py` | `create_provider()`, exact route, SDK retry suppression, resource closing |
| `.../filesystem.py` | Validated non-overlapping roots, confinement and exclusive creation |
| `.../context.py` | Host-issued `Source` references and `ToolContext` observations |
| `.../contracts.py` | Strict tool results and `CreateData` |
| `.../tools.py` | The existing three real LangChain tool wrappers |
| `.../diagnostics.py` | Sanitized diagnostic logging |
| `local-document-agent/tests/` | Existing isolation fixtures and mocked SDK transport tests |
| `local-document-agent/examples/mock-workspace/` | Tracked reusable fictional sample collection |
| `local-document-agent/pyproject.toml`, `uv.lock` | Isolated package/dependency authority |

Actual orchestration is an explicit bounded LangChain loop. LangGraph is an
installed dependency, but this code is not a graph-backed `create_agent()` loop.
Do not migrate orchestration to LangGraph as part of HTTP integration.

The recorded environment uses Python 3.12.16, LangChain 1.5.2,
langchain-core 1.8.4, langgraph 1.2.16, langchain-openrouter 0.3.0,
openrouter 0.9.2, and Pydantic 2.12.5. Verify availability; preserve existing pins.
The recorded 142-pass/one-skip agent gate is historical until rerun.

## 4. Phase 1: exact deliverable and exclusions

Deliver a runnable **loopback HTTP service** wrapping the existing assistant,
with authenticated metadata, bounded asynchronous runs, polling, cancellation,
fresh-session isolation, explicit errors, and observed result serialization.
Prove it offline using real filesystem tools and a mocked provider boundary.

Allowed changes:

- New adapter/configuration/wire-contract modules within
  `local-document-agent/src/local_document_agent/`.
- App-local tests and an optional small offline/human-check helper.
- App-local package scripts, exact HTTP dependencies, lockfile, `.env.example`,
  README/manual startup instructions and a short BUILD_STATUS continuation.
- `Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE1_RESULTS.md`, created by the
  implementation builder, not pre-populated by this planning task.

Preserve the CLI and independently callable core. Prefer wrapping existing
results over changing core logic. If a core change appears necessary, ask the
user first and explain why the adapter cannot do it independently.

Do not implement:

- SecMate Targets UI, onboarding forms, target registry, API routes, worker
  gateways, attacks, Judge calls, reports, dashboard or notifications;
- changes under `apps/`, `services/deepteam-worker/`, or the framework checkout;
- document injection, payload generation, or adversarial live tests;
- session continuation between HTTP runs, durable target-run storage, SSE,
  WebSockets, webhooks, distributed jobs or more than one execution slot;
- email sending, approval execution, file downloads, arbitrary paths/URLs,
  deletion/cleanup endpoints, automatic output purging or provider fallback;
- automatic live calls, retry-until-success, scripted production responses,
  relaxed validation, extra tools or a different agent orchestration framework.

## 5. Service setup and dependency rules

### 5.1 Isolation and packages

Use the document agent's own Python/uv environment, not SecMate's API/worker
environment. Add FastAPI and base Uvicorn as app-local HTTP optional dependencies,
so ordinary CLI installs need not become dependent on a server stack. Avoid
`uvicorn[standard]` and unrelated packages unless the user approves a need.

Before installation, propose compatible **exact** FastAPI/Uvicorn pins and the
narrow lock changes to the user. Verify compatibility with the existing Python,
Pydantic and framework pins; do not guess versions or silently upgrade existing
packages. Record approved pins, resolution and installed versions in the results.
Missing installation privileges/network or resolution conflicts require a question.
Package installation is not authorization to perform inference.

### 5.2 Configuration

Provide a separate adapter entry point, for example
`local-document-agent-http = local_document_agent.http_cli:main`. Keep the
existing `local-document-agent` command unchanged. Its `--help` must work without
credentials, filesystem writes, a model or a provider connection.

Default bind: `127.0.0.1:7310`, one Uvicorn worker, no auto-reload. Make the port
an explicit server CLI option; do not bind `0.0.0.0`. Ask before changing this
default if it conflicts locally. Do not start or replace another process.

The adapter reads only explicitly selected app-local configuration and process
settings. Add `LOCAL_DOCUMENT_AGENT_ADAPTER_TOKEN=` to the example configuration;
never generate/populate a real secret in tracked files or read SecMate's `.env`.
The user enters the private token and provider settings themselves.

Use HTTP-specific validated root settings defaulting to app-root-relative:

```text
input:  data/input/mock-workspace
output: data/output
```

Do not rewrite the user's `.env` or change the CLI's existing DOCUMENT_INPUT_DIR
or DOCUMENT_OUTPUT_DIR. Treat HTTP roots as an explicit adapter configuration
overlay using the same `FilesystemRoots` validation. Never accept roots, an
app-root path, credentials, provider/model overrides, or policy changes in an
HTTP run request.

If Harbor inputs/output directories are missing, report precise setup steps and
ask before creating or copying anything. Use the existing tracked example set
only after permission; never merge over a nonempty runtime directory. Existing
inputs and outputs must remain untouched. Tests use fresh temporary roots.

### 5.3 Readiness versus inference

Imports, app factories, health/metadata reads and root checks must not construct a
provider or call a model. Readiness may validate settings, key presence, consent,
tracing state and roots without returning credential values or inspecting file
contents. Missing provider readiness is a reported state, not a fake successful
connection. A missing adapter token prevents real service startup.

Construct provider resources lazily only after an authenticated, fully validated
run is accepted and inference readiness passes. Close both provider HTTP clients
after each run using the existing provider lifecycle.

## 6. Version 1 HTTP contract: fix this boundary before coding

Use strict Pydantic wire contracts with unknown fields forbidden. Contract name:
`secmate-agent-http-v1`. These endpoints expose the agent, not SecMate run APIs.
Every endpoint below requires `Authorization: Bearer <adapter-token>`.

Bearer-token comparison must not log secrets. Disable request-body/header access
logging and provider debug/tracing. Do not enable browser CORS or cookie login;
future callers are the SecMate server/worker. Do not redirect authenticated calls.

### 6.1 `GET /v1/metadata`

Return a bounded metadata object containing:

- `contract_version`, fixed `agent_kind: local-document-agent`, display name,
  actual installed application version, adapter implementation version;
- `adapter_instance_id`: fresh opaque ID generated at each server startup;
- model/provider identity labeled **configured**, with observed identity unknown
  unless a real provider response actually supplies it;
- configured readiness and safe reasons when not ready;
- capability list: search/read/create, their actual read/create-only effects,
  supported file types, unsent-draft behavior, and input/output logical scope;
- fixed fresh-run/single-slot semantics and enforced effective limits;
- observation coverage: source/file provenance and sanitized tool summaries;
  explicitly state that full call arguments, all model-call usage, complete
  authorization traces and streaming events are not supplied by the current core.

Do not return absolute filesystem paths, tokens, environment values, document
content, system prompts or synthetic target labels. Metadata does not prove a
model request succeeded. Do not accept a SecMate-assigned target ID yet.

### 6.2 `POST /v1/runs`

Request shape:

```json
{
  "contract_version": "secmate-agent-http-v1",
  "adapter_instance_id": "<value from metadata>",
  "submission_id": "<caller-generated UUID>",
  "message": "Read projects/harbor/overview.md and briefly summarize it with references."
}
```

Require an exact UUID submission ID, exact current instance ID, and a nonblank
UTF-8 string message of 1–4,000 characters. Validate blankness without stripping
or changing accepted input. Hash exact UTF-8 message bytes using SHA-256.
Use a bounded body reader (32 KiB maximum) before JSON parsing; reject excess
content regardless of whether Content-Length was supplied. No argument coercion.

Accept one new run only when inference-ready and the single slot is free. Return
202 with server-generated `run_id`, submission/instance IDs, request SHA-256,
UTC acceptance time, current lifecycle state, and relative status/cancel paths.
Use opaque IDs; do not embed filenames, prompts or host paths in them.

After acknowledgement, execute exactly one `DocumentAssistant.chat(message)` in
a fresh assistant/session with the configured real provider and roots. Polling
and metadata must never start it again. Do not call the CLI through a shell.

### 6.3 Submission identity and bounded retention

Maintain an in-memory mapping from submission ID to exact request hash and run
record for the lifetime of one adapter instance. Under the same instance:

- Same ID and same input returns the existing acknowledgement/run; no second
  provider call, assistant instance or file effect.
- Same ID and different input returns 409 conflict.
- Check for an existing submission before rejecting a duplicate as busy.
- Different new submission while active returns 409 `TARGET_BUSY`; do not queue.
- Retain at most 32 accepted runs/submission receipts. When full, reject new
  submissions with 503 `RUN_CAPACITY_REACHED`; do not silently evict a receipt
  and make a retry executable again. Explain restart/collection limits in README.
- An old instance ID after a service restart returns 409
  `ADAPTER_INSTANCE_CHANGED`; never treat that request as a new intent.

No durable resume or automatic resubmission is supported. Callers must treat
missing old-instance records as unknown transport disposition, not proof that no
request ran or file was written. Record this limitation explicitly.

### 6.4 `GET /v1/runs/{run_id}`

Return the same identities/request hash and UTC lifecycle timestamps. Supported
states: `accepted`, `running`, `completed`, `failed`, `limited`, `cancelled`.
Running state may expose bounded sanitized `ToolActivity` summaries; final state
includes the serialized existing `TurnResult`:

- `session_id`, status, exact available answer and its UTF-8 SHA-256;
- observed successful source references and any retained references;
- observed `created_files`, `uncertain_outputs`, `unverified_source_ids`;
- bounded tool summaries and safe error code/message;
- timing and configured limits; unavailable observed model/usage fields are null
  or explicitly unavailable, never zero, guessed or provider-certified.

Reuse actual `Source` and `CreateData` field semantics. Source IDs are scoped to
this run/session, not globally unique evidence IDs. File references remain root-
relative. Never expose absolute host paths or reopen/download arbitrary files.

The HTTP wrapper must not claim a completed assistant turn is a passed security
test. Preserve partial answer/source/create observations on failed, limited or
cancelled turns according to the existing core. A successful write followed by a
model failure is still a real file effect; cancellation cannot undo it.

Final run responses are read-only snapshots. After terminal settlement, repeated
GETs return identical result bytes/hashes and cannot change output or issue model
calls. Do not read `data/output` automatically to fabricate observed provenance.

### 6.5 `POST /v1/runs/{run_id}/cancel`

Request cancellation of that run's existing task only. Return current state and
`cancel_requested` acknowledgement; do not claim cancellation completed before
the task actually settles. Repeated cancellation is safe and creates no new task.
Terminal cancellation requests return terminal state without changing it.

Do not release the execution slot until the running task settles and provider
resources close. On shutdown, cancel/await the active task with a bounded wait;
never restart or retry it. Do not cancel unrelated CLI sessions or processes.
Retain completed/uncertain file observations. Disconnected polling clients do not
automatically cancel a run; callers must use explicit cancellation.

### 6.6 Error handling

Use 401 for missing/wrong authentication, 404 for unknown run, 409 for identity or
busy conflicts, 413 for oversized bodies, 422 for malformed/invalid wire fields,
and 503 for configured readiness/capacity failures. Return safe structured codes,
not raw exceptions, submitted secrets, absolute paths or stack traces.

Pre-acceptance failures must create no assistant, provider invocation or output.
Post-acceptance provider/tool failures appear in the run's terminal result, not as
fabricated success or a generic missing HTTP response.

## 7. Agent behavior, budget and observation boundaries

Preserve existing model, prompt, tool schemas, no-retry SDK configuration,
filesystem constraints, context pruning and source lifecycle. Do not force tools
or adjust the agent to recognize SecMate/tests. HTTP runs use fresh sessions; no
prior run can contribute hidden conversation history or source IDs.

The adapter may expose existing effective model/tool/request/turn limits but may
not increase them. Do not equate the agent's conservative serialized-byte units
with SecMate's token reservation units. Exact shared campaign accounting across
an external target is not implemented here and must not be advertised.

Use only the existing observer for concise tool summaries in this phase. Do not
invent full tool arguments, call IDs or per-call usage from prose. An expanded
host-observation contract, if required for later security evaluation, needs its
own explicitly approved scope; it is not hidden work for this adapter phase.

Output is the existing shared create-only directory, as selected by the user.
Sessions are fresh, but output-directory state is **not automatically fresh**.
Existing filenames can cause `FILE_EXISTS`; report that honestly. Use unique new
filenames for human demonstrations. Do not clear outputs, alter source paths,
silently create per-run subdirectories, or retry a write with a guessed new name.
Offline tests use separate temporary input/output roots per test.

## 8. Expected implementation shape

Keep the wrapper small. Suggested modules (equivalent small naming is acceptable
only after asking if uncertain):

```text
local-document-agent/src/local_document_agent/
  http_contracts.py   # strict versioned request/result/metadata envelopes
  http_adapter.py     # injectable FastAPI app, bounded in-memory run ownership
  http_cli.py         # explicit local config and one-worker server entry point
```

Inject provider/assistant factories for tests; there must be no public production
request option selecting a fake provider. No construction or environment loading
on module import. Reuse the existing config/provider/filesystem modules and core.
Make accepted submission and single-slot acquisition atomic within the one server
event loop. Keep tasks strongly referenced through terminal settlement.

## 9. Execute Phase 1 in this order

1. **Preflight:** report branch/checkpoint and relevant local state. Ask remaining
   questions, including approval of HTTP pins. Do not inspect keys or documents
   outside the agreed fictional collection.
2. **Contract/configuration:** implement strict envelopes, explicit roots/token
   settings, no-inference metadata and import/`--help` behavior.
3. **Run wrapper:** connect the existing core, fresh session per run, bounded
   ownership/retention, duplicate-submission handling, polling and cancellation.
4. **Offline verification:** run the focused cases below, then the complete
   app-local regression suite. Fix reproduced Phase 1 defects only.
5. **Handover:** write exact startup/HTTP usage instructions and the results file.
   Give the user the human checklist. **STOP.**

If blocked, record `BLOCKED` and the specific question. Do not build later
components or claim a substitute/mock endpoint is a genuine live connection.

## 10. Focused verification requirements

Use the app's existing isolated pytest setup and temporary roots. Explicit mocks
must block outbound provider traffic and tracing. Do not introduce a test suite
that loads the real `.env` or relies on a live model.

Required checks, using parameterization where useful:

1. Import/CLI help works without secrets; metadata constructs no provider/model
   and reads no document bodies. Metadata reports configured/unverified identity.
2. Every endpoint rejects absent/wrong bearer tokens without effects. No secrets
   appear in JSON, headers, diagnostics or application/server logs.
3. Unknown fields, wrong types, invalid IDs, wrong instance, blank/oversized input
   and oversized/chunked bodies stop before acceptance. Exact accepted input bytes
   survive to the existing core and request hash.
4. ASGI HTTP -> real `DocumentAssistant` -> real three tools -> mocked provider
   produces a source-grounded summary and a real temporary report/unsent draft.
   Use the existing real SDK `httpx.MockTransport` boundary for at least one
   complete HTTP run, not only a fake assistant returning `TurnResult`.
5. Observed source/file hashes match temporary bytes. Discovery alone registers
   no read source; model claims alone register no operation. Unsent drafts remain
   marked not sent. Existing-file collision leaves bytes unchanged.
6. Duplicate same-input submission returns the original run with one actual
   provider sequence and one create effect. Conflicting reuse is rejected.
   A concurrent different submission is busy; metadata/polling stay usable.
7. Polling after acceptance and after completion never reinvokes the agent.
   Final result/hash is stable. Bad/unknown run IDs do not expose other records.
8. Provider refusal/error, missing readiness and existing agent limits retain
   truthful statuses. Cancellation is idempotent; cancellation/model failure after
   a create preserves successful/uncertain observations and does not retry it.
9. Separate HTTP runs have distinct sessions and no source/history carryover.
   A changed instance ID rejects replay after simulated restart. Capacity rejects
   the 33rd retained run without evicting old submission receipts.
10. CLI regression suite, filesystem/strict-tool tests and mocked SDK no-retry
    tests still pass. Preserve recorded Windows privilege-related skips honestly.

Use exact commands compatible with the actual app-local setup. Typical gate:

```powershell
# Working directory: local-document-agent
$env:UV_NO_ENV_FILE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
# Use the existing app-local uv executable and documented cache/Python settings.
.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-http-phase1
.\.tools\bin\uv.exe lock --check --offline
.\.tools\bin\uv.exe pip check --python .venv/Scripts/python.exe
```

The builder must verify/update the commands for approved HTTP extras before using
`--no-sync`. Do not invent passing outputs, reuse an uninstalled optional extra,
or regenerate the lock merely because a command is inconvenient.

## 11. Required results document and human acceptance

The builder must create:

`Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE1_RESULTS.md`

This planning assignment creates only the blueprint. The implementation builder
creates the results record after doing the work. If a results file already
exists, inspect it and ask before changing its disposition; append corrections,
do not replace prior evidence with a new success claim.

Required sections:

1. Source checkpoint, actual branch, initial changes and assigned scope.
2. User questions, answers and approved dependency pins.
3. Changed files and concise implementation decisions.
4. Actual wire-contract/configuration examples with no secrets or absolute
   personal paths; effective bounds and lifecycle semantics.
5. Commands, exit codes, test counts, skips/reasons and failed attempts/fixes.
6. Observed filesystem/provenance/idempotency/cancellation evidence from tests.
7. Separate dispositions: offline adapter, user-reported CLI usability, actual
   live HTTP demonstration, and SecMate integration. Unperformed checks say
   `NOT RUN`; SecMate integration says `NOT IMPLEMENTED IN PHASE 1`.
8. Remaining limitations and exact manual verification/startup steps.
9. Human review table, initially:

| Gate | Disposition |
|---|---|
| Builder offline checks | Actual result, not pre-filled |
| Human review of code/results | PENDING |
| Human manual HTTP check | PENDING / NOT RUN |
| Human permission to add Phase 2 | NOT GRANTED |

Maintain only a brief app-local BUILD_STATUS pointer to this integration result;
do not rewrite prior build history. No other integration blueprints/prompts or
Phase 2 instructions are to be created by this builder.

### Human checklist after builder handover

- Review the results file, changed paths, exact pins, remaining limitations and
  distinction between real tool tests and mocked model responses.
- Privately supply the adapter bearer token and retain the app's own provider
  configuration; no key is entered into chat or SecMate at this phase.
- Start the service manually with the documented one-worker entry point. Verify
  wrong-token rejection and authenticated metadata without model usage.
- If the user separately authorizes a bounded benign live HTTP check, submit one
  ordinary Harbor request, poll it, compare actual sources/created file hashes,
  and repeat the same submission ID to verify it does not execute twice. Use a
  unique output filename and preserve existing files. This blueprint does **not**
  authorize the builder to make that model call automatically.
- Record what was actually observed; an unavailable route can leave live
  usability unverified while offline correctness remains established.
- The human explicitly accepts Phase 1 or lists corrections. Only then may the
  planner be asked to append a separately scoped next phase to this document.

## 12. Phase 1 completion rule

Completion means the authenticated adapter is implemented, its focused and
app-local offline checks are recorded, the CLI remains intact, the results file
exists, and the builder has handed control back to the human. It does not mean
SecMate can onboard or assess the agent yet.

**STOP HERE. No Phase 2 implementation is included or authorized.**
