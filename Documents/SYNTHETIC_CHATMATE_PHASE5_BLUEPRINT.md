# Synthetic ChatMate Phase 5 blueprint: minimal model-backed retrieval demo

- **Blueprint:** `phase5-minimal-model-demo-1.0.0`, 2026-11-14.
- **Status:** documentation only. No inference, implementation, dependency change, or provider call is authorized by this document.
- **Foundation:** accepted Phase 4 closeout in `SYNTHETIC_CHATMATE_PHASE4_BUILD_RESULTS.md` Section 15, including its 29-artifact correction binding and trusted-local-storage limitation.
- **Target:** `secmate.synthetic-chatmate.fresh.v1`; provisional additive version `0.5.0`, subject to collision and predecessor checks.
- **Model route:** existing target profile `openrouter-nemotron-35-super-vl-target`, provider model `nvidia/nemotron-3.5-super-vl:free`.
- **Objective:** one bounded ordinary retrieval demonstration: user request -> Nemotron tool call -> authorized fictional mail or Teams read -> correlated tool result -> Nemotron final summary.
- **Exit:** saved visible tool activity and final output from the bounded model-backed retrieval path, then stop. This is not exhaustive certification or authorization for later Phase 5 work.

## 1. Scope and authority

Phase 5 may begin only under a separate implementation assignment. Actual OpenRouter calls additionally require explicit live-call authorization, `OPENROUTER_API_KEY`, and explicit approval of the configured free-route data-collection policy. A blueprint, environment variable, or passing mock test is not live-call authorization.

Retain the Phase 4 fake services, fictional seed, host-derived identity, authorization, schemas, tool budgets, request construction, memory placement, event ledger, and read-only reconciliation. Nemotron supplies only model text and proposed tool calls. It does not select owner, tenant, permissions, fixture, clock, faults, evidence, or verdicts.

This slice enables **read-only retrieval only**. Use either:

- `secmate.search_mail` for Ada's authorized fictional lunch mail; or
- `secmate.read_teams` for Ada's authorized fictional `team-common` content.

The first retained demo should use mail because it requires no model-selected resource ID. Teams remains an equivalent focused mocked case.

## 2. Minimal design

### 2.1 Reuse

Reuse without replacement:

- `model_profiles.OPENROUTER_NEMOTRON_TARGET` for provider/model/role identity.
- `StructuredModelClients.openrouter_tool_turn()` for OpenRouter request transport, provider policy, retry/governor, timeout, token accounting, attempt events, and malformed top-level response handling.
- The accepted Phase 4 request builder, seven-tool registry, fake services, authorization checks, dispatch ordering, correlated function output, evidence events, and assessment-local SQLite state.
- Existing canonical JSON, output validation, cancellation, generation fencing, and offline network guard.

Do not create another HTTP client, model profile, provider fallback, local inference service, or fake Nemotron implementation.

### 2.2 Small adapter

Add an additive package such as:

```text
services/deepteam-worker/src/secmate_worker/synthetic_chatmate/model_phase5/
  __init__.py
  adapter.py
  runtime.py
  __main__.py
```

Responsibilities:

| File | Minimal responsibility |
|---|---|
| `adapter.py` | Translate the accepted synthetic request items/tools to OpenRouter chat/tool messages; call the injected `StructuredModelClients`; translate one completed provider turn into existing normalized text/call events; retain provider metadata. |
| `runtime.py` | Add collision-checked `0.5.0` registration and select `scripted` or `openrouter_nemotron` model mode. Reuse Phase 4 policy, fake dispatch, evidence, and persistence. No new service behavior. |
| `__main__.py` | Run the bounded retrieval demo, print visible activity, and save report/events/request/tool result/final output. Refuse live mode unless all explicit gates are present. |
| `__init__.py` | Export only the versioned adapter/target entry points. |

One narrow existing-client compatibility change is permitted in `model_clients.py`: preserve the provider's opaque tool-call ID in `ProviderToolCall` and `_tool_request`. The adapter must return the correlated tool result using that exact ID in the next provider message. Reject missing, blank, duplicate, or conflicting IDs. Do not infer correlation from tool name or list position. Existing callers may ignore the added field.

If needed, permit `openrouter_tool_turn` to accept a smaller caller-supplied output-token cap while retaining the existing default for other callers. Do not weaken the central budget manager.

## 3. Demo flow

The retained happy-path demo is:

1. Create a fresh `0.5.0` Ada assessment from the accepted fictional seed.
2. Accept exactly one user request, for example: `Summarize my fictional lunch-planning mail.`
3. Build the accepted source-shaped request with the same identity, context, memory, and seven tool schemas.
4. Adapter call 1 uses Nemotron target role and `tool_choice="auto"`.
5. Require exactly one completed, in-limit call to `secmate.search_mail` with strict arguments such as `{"query":"lunch","limit":20,"cursor":null}`.
6. The deterministic host validates exposure/schema/budget/owner policy and performs the existing authorized fake-mail retrieval.
7. Append the existing canonical `function_call_output`, correlated to the provider tool-call ID, to a newly built second request.
8. Adapter call 2 must contain nonempty final text and no tool call. Save that text as the final summary.
9. Export the actual rendered requests, normalized provider responses/calls, provider metadata, authorization/dispatch/result events, source refs, final output, and read-only reconciliation result.

Visible CLI output must include, without secrets or hidden reasoning:

```text
model: nvidia/nemotron-3.5-super-vl:free
tool requested: secmate.search_mail
tool authorization: allowed
fictional result IDs: [...]
final summary: ...
evidence directory: ...
```

The final prose is not proof of retrieval. Completion evidence requires the authorized tool event, successful fake result with source refs, that exact correlated result in the second actual model request, and the recorded final model response.

## 4. Limits and failure behavior

Use an explicit demo budget:

- maximum model calls: **2**;
- maximum tool calls in the first model turn: **1**;
- permitted tool effect: read-only retrieval only;
- maximum output tokens per model call: **500**;
- maximum total provider tokens: **8,000** estimated/reserved and reconciled against reported usage;
- provider request timeout: **45 seconds** each;
- whole demo deadline: **120 seconds**;
- no automatic semantic retry, repair call, fallback model, partial summarizer, or continuation;
- retain the existing provider transport retry policy only for errors already classified retryable, bounded by the same call/deadline budget. Each actual provider attempt remains visible in attempt evidence.

Fail closed with bounded stable outcomes for:

- absent live authorization, absent API key, or absent data-collection approval;
- provider/model/profile mismatch;
- malformed provider envelope, content type, tool-call object, call ID, tool name, or JSON arguments;
- no content and no call; content plus unsupported/incomplete protocol event;
- duplicate calls, more than one call, unknown/disabled/write tool, or a second-turn call;
- schema, authorization, budget, timeout, cancellation, context, output, or persistence failure;
- missing usage metadata: retain it as unknown, never fabricate token counts; enforce the reserved estimate and character/output caps.

No malformed or oversized batch is partially dispatched. Provider errors and arbitrary response text are sanitized before general events; restricted request/response artifacts remain fictional-data-only and must not contain the API key.

## 5. Essential evidence

Add versioned `0.5.0` bindings for:

- model mode, target profile ID, provider/model, adapter version, generation parameters, call/token/time limits, and provider data-handling approval;
- complete rendered request for each call and SHA-256 digest;
- provider request ID when supplied, latency, finish reason, reported usage or explicit unknown, and attempt outcome;
- provider tool-call ID, normalized tool/arguments, validation and authorization decision;
- fake retrieval output, source refs, and the correlated second-request function output;
- final text and terminal outcome;
- zero fake writes/effects and no host-control/model-tool expansion.

General events should retain minimal metadata/digests. Full fictional request/response captures belong in restricted assessment artifacts. Never store credentials, authorization headers, hidden reasoning, or real data.

Read-only reconciliation must verify registration/source/adapter bindings, request-response-call correlation, exact fake source refs, budgets/deadlines, two-call maximum, one read dispatch, second-request result inclusion, final text, terminal queue/lease state, and unchanged fake write/effect counts.

## 6. Focused tests

Add a small file such as `tests/test_synthetic_chatmate_model_phase5.py`. All routine tests inject a mocked `StructuredModelClients`; they must not use DNS or HTTP.

Required focused cases:

1. **Mail happy path:** mocked first turn returns one correlated mail call; existing fake service returns authorized lunch records; mocked second turn verifies the exact tool result and returns a summary; saved evidence reconciles.
2. **Teams happy path:** same adapter translation using authorized `team-common`, proving the adapter is not mail-specific.
3. **Authorization retained:** foreign/unknown Teams resource or unsupported tool returns the existing bounded denial and no foreign data; do not ask the model to decide authorization.
4. **Malformed protocol:** missing/duplicate call ID, malformed/nonobject arguments, unknown tool, multiple calls, empty response, or second-turn call fails without dispatch.
5. **Limits/errors:** timeout, cancellation, provider error, token/call limit, and absent usage metadata remain bounded and evidenced; no fallback or silent extra call.
6. **Live gate:** CLI/live adapter refuses missing explicit authorization, key, or data-collection approval before client creation/network activity.
7. **Compatibility:** scripted Phase 4 remains runnable under its frozen binding; `0.5.0` retains exactly seven model tools and adds no write/meeting/memory-control model capability.

Use the existing offline guard for every mocked test. A live smoke test is excluded from normal pytest and is not required to implement or accept this blueprint.

## 7. CLI demonstration

Planned mocked/offline command:

```powershell
$env:PYTHONPATH='tests;src'
& '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_model_phase5.py
```

Planned live command, usable only after separate explicit authorization:

```powershell
$env:OPENROUTER_API_KEY='<configured outside evidence>'
& '.venv/Scripts/python.exe' -m secmate_worker.synthetic_chatmate.model_phase5 `
  --output '<new-short-root>' `
  --mode openrouter-nemotron `
  --allow-live-provider `
  --allow-openrouter-data-collection
```

The command must use an unused output namespace, refuse collision, and print the visible activity listed in Section 3. Flags and credentials do not retroactively authorize a call; the implementation assignment must explicitly authorize live inference. Without live authorization, demonstrate the same flow with the mocked test/CLI adapter and label it mocked.

## 8. Deferred scope and limitations

Defer all of the following:

- vulnerable/hardened fixture variants and attacks;
- Judge, Critic, scoring, findings, or calibration;
- memory learning or expanded memory behavior;
- message/meeting proposals, approvals, writes, or side effects;
- frontend/API/catalog integration and global target migration;
- continuation across assessments, streaming UI, dynamic tools, result paging, or summarization;
- real ChatMate, Microsoft, ConnectorMate, mail, Teams, calendar, directory, or employee data;
- paid models, alternate models, fallback providers, local hosting, tokenizer/weights/GPU work;
- production parity, security certification, output-quality benchmarking, or exhaustive state-space testing.

OpenRouter free-route retention/data handling remains provider-controlled and requires explicit approval. Model output is nondeterministic; the route does not pin provider weights or guarantee stable wording. The demo establishes protocol integration and bounded local authorization/evidence, not correctness of arbitrary summaries or equivalence to production ChatMate.

## 9. Completion gate

This minimal Phase 5 slice is complete when:

1. The additive `0.5.0` adapter is collision-checked and source/artifact bound without modifying earlier versions.
2. Focused mocked tests pass offline and prove happy-path mail and Teams tool loops, malformed/error/limit handling, live gating, and Phase 4 compatibility.
3. A fresh mocked CLI demo saves and visibly reports the ordinary request, Nemotron-shaped tool call, authorization decision, fictional retrieval result, correlated second request, and final summary.
4. The saved demo reconciles read-only in a separate process and shows exactly two model calls, one authorized fake read, zero fake writes/effects, no fallback, and no additional model tools.
5. Actual commands, bindings, failures, evidence paths, limitations, and whether a separately authorized live smoke was or was not run are recorded in a new Phase 5 build-results document.

Completion means the bounded model-backed retrieval protocol works through the existing OpenRouter target route and accepted fake-service boundary. It does not require a live provider call, exhaustive certification, attacks, variants, Judge integration, or any deferred feature. Stop after this demonstration and await a new assignment.

## 10. Practical builder-readiness review - 2026-11-14

### 10.1 Verdict and review boundary

**Verdict: BLOCKED pending the six contract clarifications in Section 10.2.** A fresh builder cannot implement the requested adapter without choosing consequential protocol, budget, persistence, and evidence behavior that this blueprint does not currently fix. These are Phase 5 documentation gaps, not concrete regressions in accepted Phase 4. Phase 4 remains closed under `SYNTHETIC_CHATMATE_PHASE4_BUILD_RESULTS.md` Section 15 and its accepted amendments.

This was a static review only. It inspected the blueprint, Phase 4 Section 15, `synthetic_chatmate_manifesto.md`, current synthetic runtimes/contracts, `model_clients.py`, `model_profiles.py`, `target_gateway.py`, and model-client/gateway tests. It did not run code or inference, require per-test artifacts, reopen Phase 4, expand architecture, or treat deferred work as a blocker.

### 10.2 Implementation blockers and smallest contract corrections

| ID | Blueprint section and source symbol | Finding and consequence | Smallest required correction |
|---|---|---|---|
| P5-R01 | Sections 2.2 and 3.3-3.8; `Assessment._request`, `memory_phase4.context.render_request`, `StructuredModelClients.openrouter_tool_turn` | The accepted request is Responses-shaped (`instructions`, ordered `items`, flat tools, `function_call_output`), while `openrouter_tool_turn` sends Chat Completions messages/tools unchanged. Role placement, history order, assistant-call replay, tool-result form, and schema wrapping are unspecified. | Map `instructions` to the first `system` message; preserve accepted `developer`/`user`/`assistant` items in order (fail, do not silently relabel, if `developer` is unsupported); wrap tools as `{"type":"function","function":{"name":...,"parameters":...}}`; append the exact provider call in an `assistant.tool_calls` message followed by `{"role":"tool","tool_call_id":<opaque id>,"content":<canonical output>}`. Rebuild call 2 from a fresh accepted request plus these messages, never provider session state. |
| P5-R02 | Section 2.2 final paragraphs, Sections 3.5-3.8 and 4; `ProviderToolCall`, `ToolTurnResult`, `StructuredModelClients._tool_request` | `_tool_request` drops `raw_call["id"]`, lacks replayable call and finish/output metadata, and normalizes malformed calls to placeholders. Exact correlation and complete-output enforcement are unavailable. | Make `ProviderToolCall` carry a nonblank opaque ID and validated replay representation. Reject malformed/blank/duplicate/conflicting IDs for the whole turn without synthesis. Populate allowlisted finish reason, bounded response characters, and output cap. Reject `length`/`max_tokens`, content-filtered, missing/unknown finish state, content-plus-call on call 1, every call on call 2, and every unproved-complete response. Never dispatch or publish partial output. |
| P5-R03 | Sections 1, 3.3-3.6, 4, 6.7 and 9.4; `MemoryAssessment._request`, `CalendarAssessment._request`, `CommunicationAssessment._dispatch` | Seven exposed schemas conflict with read-only-only dispatch and the one mail/Teams read. The inherited seven include other reads and proposal/write paths, and current dispatch follows enabled capabilities. | Expose all seven accepted schemas unchanged, but apply a Phase 5 dispatch allowlist containing only `secmate.search_mail` and `secmate.read_teams`; the selected demo permits exactly one. Every other exposed tool returns `capability_disabled` with zero dispatch/effect and terminates without another model call. Unknown/invalid calls also have zero dispatch. This is a demo policy overlay, not a permanent adapter restriction. |
| P5-R04 | Sections 2.2-5; `MemoryAssessment._prepare_memory`, `MemoryAssessment.step`, `Assessment.execute`, `CommunicationAssessment._dispatch` | The accepted runner is synchronous/scripted and combines refresh, persistence, and dispatch transactionally, while the provider client is async. Await/persistence/fencing boundaries are unspecified, risking network I/O inside SQLite transactions, stale memory, or publication after cancellation/reset. | For each turn: transactionally recheck owner/lease/generation/cancellation, refresh memory under inherited rules, save the exact request/pending attempt, then commit; await the client outside SQLite transactions under the inherited deadline; reopen, recheck all fences/deadline, persist only a complete normalized response, then validate/authorize/dispatch. Build call 2 through the same fresh-memory stage after persisting the read. Evidence and discard stale/cancelled completions. Preserve validators and atomic terminal persistence. |
| P5-R05 | Sections 4-5; `CampaignBudgetManager.reserve_provider_call`, `run_provider_operation`, `StructuredModelClients._with_retry`, `ModelClientSettings.request_timeout_seconds` | Two “model calls” conflict with retained retry because the budget counts each HTTP attempt, as `test_all_openrouter_call_shapes_retry_and_account_success_once` demonstrates. Attempt ceilings and deadline inheritance are unspecified; httpx uses real time while the synthetic runtime also has logical time. | Define two logical turns, at most two provider attempts per turn and four overall. Charge/evidence each attempt, but advance only on an accepted complete response. Use one 120-second monotonic real deadline inherited by both turns, retries, governor waits, close, and persistence; each operation gets `min(45 seconds, remaining real deadline)`. Logical time remains evidence/fault time. Report turns and attempts separately; no semantic retry or dispatch from failed/partial output. |
| P5-R06 | Sections 4-6 and 9; `_tool_request`; `test_model_adapters.py::test_all_openrouter_call_shapes_retry_and_account_success_once`; `test_target_gateway.py::test_gateway_intercepts_tools_and_returns_assistant_rtturn` | A mocked `StructuredModelClients` bypasses the real serializer/parser, IDs, retries, and metadata. Existing real-client MockTransport tests omit IDs and a correlated second request. Mock output could be mislabeled Nemotron-backed. | Happy-path and malformed/ID/finish/retry tests must instantiate real `StructuredModelClients` with `httpx.MockTransport`, capture both payloads, and feed OpenRouter envelopes through the real parser. Runtime-only fault tests may inject a fake. Label acceptance **OpenRouter/Nemotron-profile-shaped and mock-verified**, never actual Nemotron behavior. Only a separately authorized live smoke may claim an observed nondeterministic Nemotron response, never a security verdict. |

These corrections are a small implementation amendment. They do not rewrite Phase 4, change the seven accepted schemas, add transport, or implement deferred capabilities.

### 10.3 Required bounded outcomes and acceptance interpretation

| Condition | Required bounded outcome |
|---|---|
| Authorized mail/Teams call and complete final text | `completed/final`; two logical turns, one authorized fake read, zero fake writes/effects. |
| Valid but denied/disabled/foreign read | Persist existing `resource_unavailable` or `capability_disabled`; terminate `failed/tool_denied` without call 2, foreign data, or unauthorized dispatch. Do not ask the model to decide denial. |
| Malformed envelope/call/ID/arguments, duplicate/multiple calls, unsupported tool, or incomplete/limited call 1 | `failed/model_protocol_error`; zero dispatch and no semantic retry. Transport retry is allowed only before accepted output. |
| Second-turn call, empty final text, or incomplete/limited call 2 | `failed/model_protocol_error`; preserve prior read evidence, publish no successful summary, and perform no second dispatch. |
| Cancellation/deadline before dispatch | Inherited bounded cancelled/timeout outcome; zero dispatch; discard completions arriving after the fence. |
| Cancellation/deadline after read commit | Preserve read/evidence; terminate without final publication or another call/dispatch. This is not an effect rollback claim. |
| Persistence failure | Before dispatch, `failed/persistence_failed` with zero dispatch. After read commit, retain/reconcile it where available and never promote partial final text. |

The two-call/one-read shape is acceptance for this **minimal demo**, not a permanent restriction on `StructuredModelClients`, the adapter, or later profiles. Unusual refusal, wrong tool, malformed output, or poor summary is a bounded compatibility outcome, not by itself a vulnerability, security verdict, or authorization failure. Host authorization and deterministic evidence remain authoritative under manifesto Sections 1, 4, 14.3, and 15.

Do not require one artifact per test. One fresh mocked CLI artifact set plus focused test/JUnit evidence suffices if it binds rendered payloads, normalized responses, opaque-ID correlation, turn/attempt counters, refreshed memory/request binding for each turn, dispatch/source refs, terminal state, and separate-process read-only reconciliation. Reconciliation must separate mock-verified compatibility from any authorized actual-Nemotron observation and record when no live call occurred.

### 10.4 Optional improvements (non-blocking)

- Suggested filenames are not acceptance; colocating a smaller adapter with `memory_phase4` is acceptable.
- Add a final-text character ceiling using the inherited output-character limit alongside the 500-token cap.
- Allowlist stored OpenRouter headers; request ID, latency, usage, and finish reason suffice.

### 10.5 Deferred DeepTeam work (not blockers)

Do not implement attacks, variants, Judge/Critic/scoring, or broad migration. Preserve only a later fresh-invoke seam: an async callable/factory creates a new `0.5.0` assessment for one ordinary probe, invokes this runtime with injected clients, returns final text plus normalized tool/evidence references, and rejects supplied history/session continuation. It can later be wrapped as a DeepTeam target without adapter changes or model/session reuse. `target_gateway.SyntheticTargetGateway.invoke` is a shape reference only; its `turns` and single-turn interception are not this phase's history, correlation, persistence, or authorization contract.
