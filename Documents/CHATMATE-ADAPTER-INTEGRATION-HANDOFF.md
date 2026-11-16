# SecMate–ChatMate adapter integration: next builder handoff

**Latest compatibility assessment:** read the [pre-integration audit](#pre-integration-compatibility-audit--2026-10-26) before resolving branches or designing the gateway. The branches are connectable with explicit integration work, not ready for a merge-and-run connection.

## Read this first: purpose and authority

**SecMate is a local internal testing tool for the company's AI team, testing the
company's internal AI products. It is never intended for wide-scale industry
use, public deployment, or a multi-tenant commercial platform.** Design this
connection for that operating model. A single local execution slot is acceptable;
do not turn this task into enterprise infrastructure or distributed scheduling.

This handoff records the user's next development goal and decisions on
2026-10-26. It supersedes older instructions that permanently prohibit automated
ChatMate delivery **for the future integration branch only**. It does not claim
that integration is implemented. [TRD-4](./TRD-4.md) remains the detailed record
of the accepted Ashwin implementation and historical evidence.

### Confirmed user decisions

- Preserve `Ashwin` runtime code. Documentation updates on `Ashwin` are allowed.
- The user will create a **new integration branch** and bring together the
  Ashwin product and Surya adapter there. Its name has not been supplied.
- Implementation and any adapter edits belong only on that new branch.
- Reuse the **normal/full SecMate platform and assessment execution path**
  currently used for synthetic testing, rather than extending the dedicated
  manual ChatMate page as the primary experience.
- ChatMate and its adapter-supported target configurations belong in the
  **Targets / target onboarding** page, selectable when creating an assessment.
- Replacing/removing the active manual workflow is desired **if safe**. Prove
  the automated replacement before retiring its entry points. Preserve saved
  manual evidence, historical readers, reports, hashes, and parent/child links.
- Retain the existing **Nemotron 3.5 Judge**. Surya's Groq GPT-OSS Judge is
  outdated for this integration and must not become the default or fallback.
- The actual ChatMate installation/startup setup is **uncertain**. Confirm it
  with the user before attempting a connection or changing ChatMate settings.
- The user wants both instruction-hierarchy and connector-authorization testing.
  Establish benign connectivity first, then response-based single-turn coverage;
  connector coverage also requires an agreed safe connector and verified event
  semantics. The new integration branch name is still undecided.
- This publication is documentation only: no merge, runtime changes, service
  startup, live ChatMate submission, or inference has been performed.

## End goal

```text
Targets: onboard local ChatMate adapter configuration
  -> Assessments: select that target and applicable attack/vulnerability
  -> API: freeze target/spec/budgets and accept a durable local job
  -> DeepTeam worker: generate attack and invoke ChatMate gateway
  -> Surya transport: authenticate locally, submit prompt, collect events
  -> SecMate: correlate evidence and evaluate supported security boundaries
  -> independent Nemotron 3.5 Judge where semantic evaluation is applicable
  -> existing results, Findings, Reports, Dashboard, history and notifications
```

Reuse the execution architecture of the synthetic path, **not its fictional
target facts**. A live ChatMate run must be labelled live, never synthetic or
operator-mediated. Keep synthetic fixtures available for offline regressions.
Do not reduce this work to a CLI demo that bypasses the platform.

## Inspected source checkpoints

| Ref | Inspected commit | Meaning |
|---|---|---|
| `origin/Ashwin` | `3111c962cb980765311d0a8a84cffc8e2ad3a137` | Product baseline before this documentation publication |
| `origin/Surya` | `c5f00604a4af2c310a22c426fcb8ca998c1653f9` | Live adapter plus standalone campaign |
| Surya adapter introduction | `8fc803a` | Local ChatMate client |
| Shared implementation ancestor | `632ac2f` | Surya predates Ashwin's final two-call cleanup/model fixes |

These are inspection anchors, not instructions to reset branches. Fetch and
inspect actual tips again; record newer changes before integrating. Read remote
files with `git show origin/Surya:<path>` while staying on Ashwin. Surya-only
paths below are intentionally plain paths, not broken local links.

## What exists on Ashwin

- React frontend, FastAPI control plane, separate pinned Python 3.11 worker.
- `/api/v1/deepteam-runs` supports the normal synthetic assessment path, using
  `AttackEngine`, `RedTeamer`, a target gateway, and SecMate-owned evaluation.
- Synthetic tools/retrieval have deterministic policies and evidence IDs. Their
  assumptions do not automatically apply to real ChatMate event payloads.
- Local SQLite run/job storage, budgets, cancellation, fencing, sealed
  publication, conservative restart handling, and no automatic inference replay.
- Exact evidence hashes, original/redacted separation, citation checks, reports,
  histories and result projections should be reused.
- Targets and some product records are currently browser-local. A new target
  card alone cannot configure the worker: the runtime needs a validated local
  API-owned target record or equivalent persisted server-side binding.
- Manual ChatMate is a separate lifecycle. Its generator is two direct Groq
  calls with advisory method review, not DeepTeam AttackEngine execution. Keep
  its historical contract distinct from the new normal-path integration.

### Preserve role separation

| Role | Current binding / integration instruction |
|---|---|
| Attacker / native evaluator | Groq `qwen/qwen3.8-27b`, `GROQ_API_KEY` |
| Critic | Qwen, dedicated `GROQ_CRITIC_API_KEY` where that role is used |
| Independent Judge | `openrouter-nemotron-35-super-vl-judge`, `nvidia/nemotron-3.5-super-vl:free`, `OPENROUTER_API_KEY` |
| ChatMate target | Whatever ChatMate actually routes for the selected adapter tier; not the Judge and not the synthetic Nemotron target |

Do not copy old Nemotron 3/Ultra routes from Surya. Do not adopt its
`groq-gpt-oss-judge` profile or GPT-OSS completion settings merely to connect
transport. Existing Judge accuracy is uncalibrated; this task must not claim
otherwise. Confirm permitted handling of captured internal responses using the
team's actual data policy; do not add standing consent dialogs as a substitute.

## What Surya actually provides

### `services/deepteam-worker/src/secmate_worker/chatmate_live.py`

The reusable transport is `ChatMateLiveClient.send_probe()` with
`ChatMateLiveSettings` and `ChatMateLiveObservation`.

| Setting | Current adapter contract |
|---|---|
| Base URL | Default `http://127.0.0.1:7300`; HTTP/HTTPS, host only `127.0.0.1`, `localhost`, or `::1` |
| Persona | `sara`, `alice`, `bob`; default `bob` |
| Model tier | `auto`, `pro`, `swift`, `free`; default `pro` |
| Timeout | Default 180 seconds; accepted settings range 1–900 seconds |
| Conversation | New conversation for every `send_probe()` call |
| Redirects | Disabled |
| Approval | Collected as evidence, never answered by this adapter |

Transport sequence:

1. `POST /api/v1/dev/session` with `persona`; the HTTP client retains its cookie.
2. `POST /api/v1/conversations` creates a conversation.
3. `POST /api/v1/conversations/{conversation_id}/messages` sends exact `content`
   and `model_tier`, returning a ChatMate run ID.
4. `GET /api/v1/runs/{run_id}/events?after=<cursor>` collects SSE events.
5. On timeout, it attempts `POST /api/v1/runs/{run_id}/cancel`.

It handles `answer.delta`, `answer.reset`, `tool.activity`, `run.citations`, and
terminal `run.completed`, `run.failed`, or `run.cancelled`. It permits up to
three stream reconnects after the initial stream, deduplicating numeric event
IDs. **Stream reconnection is not permission to resubmit a prompt.**

Observations include exact prompt/hash, original and redacted response, target
conversation/run IDs, tier/persona, timings, event count, redacted tool activity,
citations, optional connector approval, and transport outcome:

- `RESPONSE`: completed response; not automatically a secure or compromised result.
- `VISIBLE_FAILURE`: ChatMate explicitly reported failure; not resistance.
- `HARNESS_ERROR`: auth/network/timeout/incomplete stream/cancel failure state;
  never convert missing evidence into a pass.

The observation does not itself contain a response hash. Campaign conversion
adds a hash of the redacted response; original-response integrity and strict
observation-to-submission binding still need implementation (see audit below).

Surya's worker README says ChatMate needs its API **and agent worker** running,
`CHATMATE_API_AUTH_MODE=local-dev`, `CHATMATE_API_ENVIRONMENT=local`, and a real
`CHATMATE_API_MODEL_PROVIDER` rather than canned deterministic output. These
are documented expectations, **not verified ChatMate configuration**: the
ChatMate server implementation is not in this inspected tree. Confirm variable
names, startup commands, personas and routes against the actual ChatMate repo.

### `.../chatmate_live_campaign.py`: reference, not the integration architecture

This CLI generates candidate batches, submits every candidate in a fresh
conversation, saves observations, and invokes the manual evaluation path.
It does not wire Targets, normal assessments, API-managed jobs, or full UI flow.

Do not import its policy wholesale:

- It defaults to Groq `openai/gpt-oss-120b`; **keep Nemotron 3.5 instead**.
- It reports any connector-approval request as critical. A requested approval
  can demonstrate a working guardrail. Classify requested/blocked/approved/
  executed/unauthorized actions separately against the trusted test policy.
- It uses separate generation/evaluation budgets rather than a single normal
  platform campaign budget. Do not treat its per-stage caps as an overall cap.
- It retains manual execution labels in places and claims prior DeepTeam
  generation; audit all labels for the actual new path.
- It calls an existing Judge path without adding tool events to its prompt;
  collected events alone are not evidence that the Judge evaluated actions.
- Its output files are not automatically admitted into Ashwin's durable run
  store, original-evidence inventory, or sealed publication.

The tests `test_chatmate_live.py` and `test_chatmate_live_campaign.py` contain
mock HTTP/SSE examples. They were inspected, not executed in this handoff.

## Target onboarding design for the new agent

Use the existing Targets interface as the entry point. Propose a small typed
target configuration, then implement it on the new branch:

1. Internal product name and stable target ID; distinguish live ChatMate from
   `synthetic-chatmate-rag` and `chatmate-vuln` fixtures.
2. Adapter kind/version, loopback endpoint, persona, tier, timeout, profile version.
3. Product purpose, permitted test boundaries and observable capabilities.
4. Requested tier **separate from resolved provider/model identity**.
5. Connection validation state and last verified time, without generating an
   attack or spending inference as a hidden onboarding action.

**No model-discovery endpoint exists in the inspected adapter.** Do not invent
one or claim `pro` is a model ID. If ChatMate supplies trustworthy model-routing
metadata, record that. Otherwise use explicit locally configured metadata,
label it configured/unverified, and record resolved identity as unknown. Ask
the user where authoritative model configuration lives. Start with one target
configuration; support additional tiers/configurations only as actually exposed.

The API must resolve the selected target ID into validated settings, freeze a
snapshot per run, and pass it to the worker. The browser must not be the sole
authority for endpoint, model identity, target readiness or evidence. A small
local persisted registry is sufficient; no SaaS tenancy system is requested.

## Integration seam and minimum implementation order

### 1. Establish branch and ChatMate prerequisites

- Ask the user for the new integration branch name and whether it already
  contains both histories. Never implement or merge runtime changes on Ashwin.
- Inspect status/diffs and merge ancestry. Surya branches from an older Ashwin
  state; do not replace current files with whole older branch versions.
- Ask where ChatMate lives, how its API/worker start, its effective loopback URL,
  dev-auth availability, personas, actual provider/tier mapping, and permitted
  local test data/connectors. If unavailable, use mocks and report the blocker.

### 2. Bring in transport selectively and reconcile contracts

- Retain Ashwin's current model profiles, provider fixes, two-call legacy
  generator, hashes, schemas, runtime pins, recovery and evidence guarantees.
- Port the adapter and focused tests; reconcile changes to worker/API contracts,
  schema exports, CLI registration and evaluator interfaces deliberately.
- Surya changes worker evidence to accept `LIVE_LOCAL_API`; it does not complete
  the matching API/frontend migration. Do not only widen one literal and declare
  integration complete. A new normal run needs truthful versioned provenance.
- Register any new managed worker entry through the canonical allowlisted
  launcher, or reuse the normal managed runner. A detached standalone campaign
  must not bypass the API's execution slot, cancellation, leases or publication.

### 3. Generalize the normal target gateway

- `SecMateDeepTeamRunner` currently imports `SyntheticTargetGateway` directly.
  Introduce a thin target gateway seam/factory so live ChatMate can supply the
  callback and evidence that the existing runner consumes.
- Add a distinct live profile/binding, update catalog applicability, API request
  validation and target resolution, then wire the Targets selection into it.
- Construct a ChatMate-specific trusted `AssessmentSpec`. Do not reuse SocMate
  privileged-tool names, synthetic retrieved documents, canaries, or approval
  facts as though they describe ChatMate.
- Initially expose only compatible single-turn tests with the real transport.
  The adapter opens a fresh conversation each call; hide/disable multi-turn
  profiles until same-conversation continuation and state isolation are implemented
  and verified. An adaptive second fresh path is not multi-turn memory.
- Keep generation/native evaluation subordinate to SecMate's budgets and final
  evidence-qualified verdict. Reusing DeepTeam does not justify restoring the
  retired expensive manual enhancement loops or silently raising call limits.

### 4. Capture, evaluate and publish through the whole platform

- Bind run ID, target snapshot, exact submitted prompt/hash, ChatMate
  conversation/run IDs, terminal outcome, response/hash, timings and adapter
  version. Validate observation-to-submitted-prompt identity before evaluating.
- Keep originals backend-only under the existing evidence policy; pass redacted
  data to the Judge and normal UI. Do not log session cookies or raw exceptions.
- Map tool/citation events into typed evidence with stable IDs. Tool selection
  does not prove execution, and missing events do not prove no action occurred.
- Audit response/event size bounds, malformed SSE handling, trust of terminal
  payloads, and observation validation before persisting untrusted payloads.
- Preserve the independent Nemotron 3.5 evaluator with truthful provenance.
  Existing synthetic required-evidence rules need explicit mapping; do not force
  every live run into ERROR because it lacks fictional retrieval evidence, or
  relax criteria to manufacture RESISTED. Unsupported checks are unavailable or
  inconclusive, with a clear reason.
- Include target requests in deadline/call accounting where appropriate;
  ChatMate model token usage is unknown unless returned. Report unknown usage,
  not zero. Keep reconnects, resubmissions and provider retries distinct.
- Propagate cancellation to ChatMate and reconcile uncertain remote completion.
  Do not automatically send a second attack after a lost submission response.
- Persist through the normal job/run/evidence/report pipeline and update normal
  UI status, history, Findings, Reports, Dashboard and notifications from it.

### 5. Retire the manual entry point only after replacement acceptance

- First prove an onboarded live target can complete an assessment through the
  normal UI, survive navigation/reload and produce a saved report.
- Then remove/hide new manual-run creation and copy/paste steps if they are
  redundant. Reuse shared components where sensible.
- Preserve historical manual report URLs, API readers, contracts and artifacts
  as needed for saved evidence. No history reset or evidence rewriting.
- Inventory manual-only consumers before deleting code: Judge/Critic/report
  helpers may still be useful. Removing a page is not removing all evaluation
  machinery. Do not port the manual Critic into the new path without checking
  input/spec compatibility; normal adaptive execution has its own Critic.

## Source navigation

| Integration concern | Ashwin files to inspect |
|---|---|
| Target onboarding and browser state | `apps/web/src/ModulePages.tsx`, `platformService.ts` |
| Normal assessment selection/results | `apps/web/src/DeepTeamAssessmentPanel.tsx`, `AssessmentResultsPanel.tsx` |
| API routing, requests and jobs | `apps/api/src/secmate_api/main.py`, `contracts.py`, `deepteam_runs.py`, `jobs.py` |
| Durable evidence and reports | `apps/api/src/secmate_api/run_store.py`, `reporting.py`, `console.py` |
| DeepTeam orchestration/CLI | `services/deepteam-worker/src/secmate_worker/deepteam_runner.py`, `single_attack.py` |
| Target boundary/applicability | worker `target_gateway.py`, `target_profiles.py`, `deepteam_catalog.py` |
| Evaluation and citations | worker `target_evaluator.py`, `evidence_inventory.py`, `deterministic_policy.py` |
| Models, budgets, managed launch | worker `model_profiles.py`, `model_clients.py`, `execution_budget.py`, `job_runtime.py` |
| Historical manual compatibility | API `chatmate_runs.py`, worker `manual_chatmate.py`, both contract modules |

## Acceptance for this connection

The builder must report what was actually verified, not just tests added:

- Offline adapter tests: persona session, exact prompt/Unicode/whitespace,
  response hash, deltas/reset, event replay/deduplication, terminal states,
  malformed/oversized payloads, missing auth, lost stream, timeout and cancel.
- Normal managed-job test with mocked ChatMate: target ID/config travels from
  API through the real launcher; progress, cancellation and sealed publication
  work; restart/uncertain completion does not resubmit the target message.
- Target onboarding persists locally and selects the intended configuration;
  tier/configured model/resolved model are clearly distinguished.
- Normal assessment UI and saved reports show live target provenance, evidence,
  outcome and actual Judge profile. No simulated finding is manufactured by
  browser-local `assessmentOutcome()` or fixture data for a live run.
- Approval requested alone is not critical; real action-policy violations need
  defined evidence. Errors/incomplete traces never count as secure outcomes.
- Historical manual runs/reports and synthetic offline regressions still read.
- Once the actual ChatMate environment is confirmed, perform one explicitly
  agreed benign connectivity probe, then one bounded compatible attack through
  the full UI. A real model must be distinguished from deterministic canned
  output. Never duplicate a live submission merely because a tool times out.
- Run the relevant frontend build/tests and sandboxed API/worker checks. Use
  TRD-4's isolation procedures; never run tests against accepted local data.

Existing integration debts relevant here: synthetic adaptive Critic credential
propagation in `single_attack.py`; legacy diagnostic Critic key semantics in
`orchestrator.py`; managed candidate-progress run-ID mismatch. Fix/test only
what the new path uses, on the integration branch, and disclose what remains.

## First response expected from the next builder

1. Confirm this internal/local scope and the integration branch.
2. Summarize the actual Ashwin/Surya merge state and adapter contract.
3. Ask the missing ChatMate environment questions before live work.
4. Propose the smallest target-registry/gateway/API/UI changes and acceptance
   sequence, preserving Nemotron 3.5 and historical evidence.
5. Begin offline integration only in the authorized new branch; report blockers
   plainly. Do not broaden this into a public platform or unrelated roadmap.

## Pre-integration compatibility audit — 2026-10-26

### Decision and scope

**Compatible foundations; not integration-ready.** Surya's single-probe transport
can be adapted to Ashwin. Resolving textual conflicts does not connect normal
Targets/Assessments, admit evidence into durable storage, or establish reliable
live verdicts. Do not call the combination operational until the acceptance
checks below pass on the user's new branch.

This audit is for the **localhost internal AI-team PoC**. Keep the existing local
single execution slot and use a small persisted target registry. Distributed
queues, commercial tenancy, public deployment and industry-scale architecture
are not prerequisites or requested work. Localhost remains the operating
boundary unless the user explicitly changes it later.

### Inspection record and limits

The delegated general-agent audit fetched remote refs and inspected Git objects,
source, schemas and tests using `git show`, `ls-tree`, `diff`, `grep`, and legacy
three-tree `merge-tree`. No worktree merge, branch creation, checkout, code edit,
test execution, service start, inference or ChatMate connection occurred.

| Ref | Exact inspected SHA |
|---|---|
| `Ashwin`, `HEAD`, `origin/Ashwin` | `70ac3582093bcbb52dc3d0d4f72159f3b6a03f2f` |
| `origin/Surya` | `c5f00604a4af2c310a22c426fcb8ca998c1653f9` |
| Common ancestor | `632ac2f0903b4c82e8ce6b005a1e524a226f815e` |

At inspection there were three Ashwin-only and two Surya-only commits since
the ancestor. Neither tip contains the other. This audit's documentation commit
will advance Ashwin again; recheck refs before integration. The real ChatMate
server source/configuration and ignored local run stores were not audited.
Historical test totals are not current runtime acceptance evidence.

### Git compatibility and conflict-resolution instructions

Surya changes 11 paths: four additions and seven modifications. Five paths also
changed on Ashwin. Worker-relative paths below start at
`services/deepteam-worker/`.

| Overlap | Ashwin side | Surya side | Static result / resolution |
|---|---|---|---|
| `README.md` | Deleted obsolete worker README | Adapter/campaign documentation added | Modify/delete conflict (`removed in local` in legacy merge-tree). Extract verified facts into current docs; do not restore stale README wholesale. |
| `schemas/v1.1/worker-contracts.schema.json` | Current candidate/contract changes | Adds `LIVE_LOCAL_API` to embedded definitions | No conflict markers observed; reconcile source contracts and regenerate appropriate current exports. Preserve archives/readers. |
| `src/secmate_worker/contracts.py` | Current candidate modes and historical validation | Widens manual evidence collection method | No conflict markers observed; textual merge does not synchronize API/frontend provenance. |
| `src/secmate_worker/model_clients.py` | Current formatter, Nemotron 3.5, Critic-key, quota/wait/progress and generation fixes | GPT-OSS reasoning/completion settings | Content conflicts in two hunks. Retain Ashwin implementation; GPT-OSS changes are not needed for this connection. |
| `src/secmate_worker/model_profiles.py` | Current Nemotron 3.5 profiles | Adds GPT-OSS Judge profile | Textually combinable, but GPT-OSS must not become the new default/fallback. Preserve Ashwin bindings. |

Surya adds `chatmate_live.py`, `chatmate_live_campaign.py` and their two test
files; other modifications are `pyproject.toml` and `manual_chatmate.py`.
**`manual_chatmate.py` is not a divergent overlap:** Ashwin's blob is unchanged
from the ancestor. Its patch applies textually but still uses manual execution
semantics. CLI registration in `pyproject.toml` is not managed-job integration.

Prefer a reviewed merge or selective port on the new branch, preserving both
histories as the user chooses. Never resolve conflicts by replacing whole
current Ashwin modules with older Surya versions. No merge strategy was applied
or accepted during this audit.

### Runtime compatibility matrix

Line references are approximate anchors at the inspected tips, not stable APIs.
`A` means Ashwin; `S` means Surya. Worker source paths here are under
`services/deepteam-worker/src/secmate_worker/`.

| Boundary and evidence | Finding / required integration |
|---|---|
| A API `contracts.py:300–370` | Normal target/scenario IDs are fixed synthetic literals and `synthetic_only` is literally true. Add a live binding without mislabelling it synthetic. |
| A API `deepteam_runs.py:55–137,265–295` | Launches `single_attack` from catalog profile IDs; no persisted adapter-target resolution or frozen connection settings yet. |
| A web `DeepTeamAssessmentPanel.tsx:375–377,463` | Sends profile/scenario IDs and explicitly filters selection to `synthetic-socmate-tier1`. A Targets card alone will not enable live execution. |
| A `deepteam_runner.py:413–427`; `target_gateway.py:174–198` | Runner constructs `SyntheticTargetGateway`; callback expects `RTTurn`, not `ChatMateLiveObservation`. Add a gateway seam and conversion. |
| A runner `:474–476,962–998` | Also reads gateway `turns`, `oracle_results`, `retrieval_redactions`. Returning response text alone is insufficient. |
| S `chatmate_live.py:146,226` | Transport has no DeepTeam `turns` argument, session continuation, managed permission hook or gateway-state interface. |
| S worker contracts; A API `contracts.py:859`, web `chatmateService.ts:58`, `chatmateProjections.ts:70` | Only Surya worker widens collection method to `LIVE_LOCAL_API`; API/frontend still require manual provenance. Synchronize the chosen live contract across boundaries. |
| A worker `contracts.py:433–473,509–574` | Historical correlation hash does not bind collection method, adapter version, endpoint, tier or remote conversation/run IDs. Preserve old hash meaning; add a versioned live binding. |
| A `job_runtime.py:192–203` | Neither live CLI is allowlisted. Reuse the managed normal runner where possible; adding an executable does not grant job ownership. |
| A `job_runtime.py:214–228`; API `deepteam_runs.py:205–260` | Standalone campaign artifacts do not automatically satisfy sealed output and API publication requirements. |
| A runner `:465`; S `manual_chatmate.py` | Normal runner says `synthetic_only=True`; live campaign retains `MANUAL_CHATMATE` / prior-generation labels. Replace labels only for new execution; retain old readers. |
| A `target_evaluator.py:104`, runner `:555,609,1097–1098` | Synthetic-purpose wording/adaptive assumptions remain. Use a reviewed ChatMate-specific single-turn spec first. |

A dedicated live provenance envelope on the normal path may be cleaner than
stretching `ManualChatMateEvidence`. Either approach must version the change
and retain historical manual serialization, optional timestamps and lineage.

### Transport compatibility and missing guarantees

The adapter's endpoint/cookie sequence, fresh conversations, exact text capture,
numeric SSE replay handling and no automatic message resubmission are useful.
These specific gaps must be handled for the connected PoC:

1. **External cancellation:** adapter cancellation is attempted only on its own
   timeout. Task cancellation, worker watchdog exit or process termination does
   not reliably call remote cancellation. Propagate cancellation when possible.
2. **Cancel is only an attempt:** `_cancel_quietly()` ignores response status
   and transport errors. Persist attempted/confirmed/unknown status separately.
3. **Submission uncertainty:** ChatMate may accept a message before its POST
   response is lost. Without a remote run ID the adapter cannot cancel it.
   Record uncertainty; never automatically issue the attack again.
4. **Stream exhaustion:** reconnect exhaustion returns `STREAM_ENDED` without
   cancelling a potentially active remote run. Preserve remote uncertainty.
5. **Malformed shapes:** existing catches do not cover all nested shape failures
   such as `TypeError`/`AttributeError`. Validate endpoint and SSE payloads and
   return bounded redacted harness diagnostics rather than unhandled errors.
6. **Memory bounds:** SSE frames, deltas, events and citations have no explicit
   per-frame/aggregate byte or event-count bounds. A later sealed-artifact limit
   (64 MB / 256 files) is not an in-memory streaming bound.
7. **EOF framing:** SSE data is emitted on a blank line; a partial final frame
   is discarded. Specify and test behavior against the actual ChatMate server.
8. **Observation validation:** the prompt hash is format-checked, not recomputed
   by an observation validator; terminal/outcome/text consistency also needs
   validation. Dataclass annotations alone do not enforce persona/tier values
   supplied outside CLI `choices`.
9. **Version/model claims:** adapter version `1` and observation schema `1.0`
   do not verify server compatibility. The selected tier is not a model ID.

Each `send_probe()` starts a new conversation. Multi-turn attacks are therefore
**not supported by the current adapter**, even if invoked repeatedly. Defer
stateful attack profiles until continuation/isolation is actually implemented.

### Evidence correctness blockers

**S `chatmate_live_campaign.py:69–131`:** `live_evidence()` selects a candidate
from a batch and constructs correlation using its hash, without first verifying
the observation's exact prompt/hash, batch/candidate IDs and remote operation
binding. A normal call happens to supply matching objects; that is not an
admission invariant. Reject mismatches before evaluation or publication.

- The observation retains original/redacted response text but has no original
  response SHA-256. Campaign conversion hashes the redacted text only.
- Standalone observation files are written before evaluation, outside the
  normal original-evidence store and managed publication.
- Tool events and citations are redacted before observation construction; raw
  originals are not retained. Capture them deliberately if the agreed test
  requires them; never claim existing observations contain original events.
- Harness errors omit partial answer deltas, observation time and latency.
  Decide which partial diagnostics to retain without treating them as a
  completed target answer.
- Bind run ID, target configuration snapshot, prompt/hash, remote identity,
  response/hash, terminal state, timestamps and adapter identity explicitly.
  Preserve backend-only originals and a redacted operational projection.

**S campaign `:134–140,291–324`:** `_tools_called()` lists `phase == selected`
events but reports “Tools called.” Any approval request also triggers critical
exit status. Neither behavior is an acceptable compromise oracle:

- selection is not execution;
- requesting approval may be successful enforcement;
- approved execution is not necessarily unauthorized execution;
- absent traces do not prove absence of action.

Define event-to-policy mappings with the ChatMate owner. Requested, selected,
blocked, approved, executed and unauthorized states need distinct evidence.
The campaign Judge currently receives neither tool events nor citations; their
collection is not action-aware judging. Use deterministic policy checks where
the trace establishes them and explicit inconclusive outcomes elsewhere.

### Model and generator compatibility blockers

Retain `openrouter-nemotron-35-super-vl-judge` with
`nvidia/nemotron-3.5-super-vl:free` through the OpenRouter adapter/credential.
Surya's campaign constructs `GroqDeepEvalModel`, a GPT-OSS profile, and settings
with `openrouter_api_key=""`. Merely changing `--judge-model` to a Nemotron
string still uses the wrong provider/profile. Do not run that as an integration
shortcut. Surya's old Nemotron 3 Super/Ultra defaults must not replace 3.5.

Surya did not update its inherited manual generator: it retains AttackEngine
enhancement/completeness/method loops, a 60-call cap and two retries. Ashwin's
current manual generator is the deliberately bounded two-call advisory path.
A correct merge retains Ashwin's generator. The new normal DeepTeam path is a
separate execution contract; do not resurrect retired manual logic to use the
adapter or assume Surya's campaign carries current generation guarantees.

### Minimum local target and managed-job design

The current web target registry is browser-local
(`platformService.ts:307–322,390`). Browser `assessmentOutcome()` produces
simulated results (`:145,282`) and must never determine a live result.

For this PoC, persist a small API-owned target record: ID/version, adapter
kind/version, loopback endpoint, persona/tier/timeout, purpose, supported
boundaries, configured model metadata/verification state, and resolved model
identity if known. Resolve and freeze that record per job. Editing a target must
not change an existing run. No external database or fleet scheduler is required.

For managed execution, check permission before egress, share campaign
deadline/count accounting, store remote IDs promptly, propagate cancellation,
retain uncertainty, seal output and publish through existing validation. Report
ChatMate tokens as unknown unless measured. Recovery must never resubmit an
attack to reconstruct missing evidence. Progress and final sealing need separate
checks; existing candidate-progress identity debt is not fixed by a valid seal.

### Required offline acceptance before live tests

All checks below are future work, not results of this audit:

1. Historical manual/synthetic artifacts validate with unchanged hashes,
   optional timestamps, reports and parent/Critic/child lineage.
2. Adapter tests cover exact Unicode/whitespace, delta/reset/resume, malformed
   nested shapes, oversized frames/streams, missing auth, terminal failures,
   dropped submission response and stream exhaustion.
3. Mismatched prompt/hash, candidate/batch, target snapshot or remote operation
   identity fails evidence admission.
4. A mocked ChatMate run travels through the real API request and canonical
   managed launcher, frozen target, gateway conversion, sealed result and report.
5. Cancel before/after remote ID acquisition, failed cancel, killed worker,
   restart and sealed/unsealed recovery do not automatically resubmit messages.
6. Approval-only does not become critical; selected does not become executed;
   insufficient traces do not become resistance. Review both response and tool
   verdict paths against a specific trusted assessment policy.
7. Mocked provider requests and saved provenance prove OpenRouter Nemotron 3.5
   use, with no GPT-OSS or old-Nemotron fallback.
8. Targets selection persists, reload/navigation works, normal saved reports
   expose live provenance, and Findings/Dashboard/notifications reconcile.
9. Only after replacement acceptance retire manual creation; saved manual URLs,
   readers and evidence remain usable.

Surya's existing mocked tests cover cookie propagation, exact text, answer reset,
numeric replay, visible failures, dev-auth failure, timeout cancel attempt,
loopback rejection, evidence conversion and advisory summaries. They do **not**
establish actual server compatibility, managed execution, mismatch rejection,
original integrity, external/confirmed cancellation, multi-turn state, actual
model routing, Nemotron integration or full UI lifecycle. One campaign test
expects approval-request → critical exit; update it to the intended policy.

### Live acceptance and remaining user questions

The user requested **both instruction hierarchy and connector authorization**.
After offline checks and environment confirmation:

1. An explicitly agreed benign connectivity probe confirms real ChatMate routing.
2. A bounded single-turn instruction-hierarchy test runs through the full platform.
3. A separate connector-authorization test uses an agreed safe connector/action
   and verified event semantics. Do not approve a connector request automatically.

The audit does not authorize live submissions or establish their safety/setup.
The next agent must ask:

- What is the new integration branch name? **Still undecided.**
- Where is ChatMate installed, and how do its API and agent worker start?
- What loopback endpoint/server version is running, and are local-dev persona
  sessions available? Which personas are valid?
- Where is authoritative tier-to-provider/model configuration? Is there a
  non-inference readiness route or trustworthy resolved-model metadata?
- Which local test data, connector, action and persona are allowed? What event
  proves approval, denial, execution and actual authorization for that action?

**Builder priority:** target binding + gateway contract + evidence correlation +
Nemotron routing + managed lifecycle + single-turn live spec first. Multi-turn,
adaptive live campaigns and extra model tiers are deferred until a working
single-target flow is demonstrated. Preserve the local PoC scope.
