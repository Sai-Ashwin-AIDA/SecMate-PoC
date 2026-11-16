# SecMate Technical Requirements Document 2B

> **Current frozen implementation:** [TRD-4](./TRD-4.md) supersedes this checkpoint's current-state/next-agent inventory. Historical diagnostic results are not proof of the final manual workflow or current provider availability.

## Model Connectivity, Brokered Handoff, and DeepTeam PoC Checkpoint

> **Document status:** Historical pre-worker implementation checkpoint
>
> **Checkpoint date:** 2026-09-26
>
> **Reviewed branch:** `Ashwin`
>
> **Checkpoint commit before this document:** `b06332e`
>
> **Predecessors:** [TRD-1.md](./TRD-1.md), [TRD-2.md](./TRD-2.md), and
> [TRD-2A-FRONTEND-IMPLEMENTATION.md](./TRD-2A-FRONTEND-IMPLEMENTATION.md)
>
> **Supporting DeepTeam documents:**
> [DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md](./DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md)
> and
> [DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md](./DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md)
>
> **Architecture successor:**
> [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md)
>
> **Supersession notice:** Current-state and next-agent sections in this file
> describe repository state at commit `b06332e`. Commits `c14e8d9` through
> `466e393` subsequently added the isolated worker, real DeepTeam execution,
> budgets, Target Gateway, deterministic policy, Architecture B evaluator,
> FastAPI dispatch, frontend invocation, and audit retrieval. Preserve this file
> for pre-integration rationale and warnings; use TRD-3 for architecture decisions
> and [TRD-4](./TRD-4.md) for current facts.
>
> **Current engineering handoff:** [TRD-4](./TRD-4.md). This document remains
> the historical pre-worker and compatibility checkpoint.

## 1. Purpose

TRD-2B is the permanent checkpoint for the first live model-connectivity and
brokered model-handoff PoC completed after TRD-2A.

It records:

- What was implemented during the 2026-09-26 session.
- Why those changes were made.
- What was verified with live providers.
- What remains synthetic, incomplete, or unapproved.
- How DeepTeam fits into SecMate and where it does not.
- The architectural options that remain unresolved.
- Mistakes, provider constraints, and security lessons that must not be
  repeated.
- The exact sequence the next coding agent should follow.

At this checkpoint, the repository had advanced beyond a frontend-only prototype
but did not yet have enough measured worker evidence for the later TRD-3.

## 2. Authority and Requirements Lineage

The requirements lineage is:

1. [TRD-1.md](./TRD-1.md) records the original action-space security thesis,
   declarative manifests, dual-stage verification, broker pattern, and initial
   engineering baseline.
2. [TRD-2.md](./TRD-2.md) is the authoritative reviewed continuation. It
   corrects terminology and standards, changes CI/CD to advisory behavior,
   removes hidden Chain-of-Thought requirements, strengthens safety, and defines
   readiness gates.
3. [TRD-2A-FRONTEND-IMPLEMENTATION.md](./TRD-2A-FRONTEND-IMPLEMENTATION.md)
   records the frontend implementation boundary and deferred backend work.
4. This TRD-2B records the scoped model-connectivity API, the synthetic brokered
   handoff, the DeepTeam compatibility review, and the next implementation
   decisions.
5. [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md)
   later reads all four documents and records measured fixed-worker evidence.
   Calibration, pilot, and production results remain future requirements.

Authority rules:

- TRD-2 remains authoritative when it explicitly changes TRD-1.
- TRD-2A and TRD-2B are implementation continuations, not replacements for
  TRD-2.
- This document does not approve production operation, real destructive tools,
  enterprise rollout, or calibrated assurance claims.
- The DeepTeam guide is a technical implementation guide subordinate to the
  SecMate TRD lineage.
- The current synthetic model workflow is diagnostic evidence, not an accepted
  SOCMate vertical slice.

## 3. Repository State at This Checkpoint

Current branch:

```text
Ashwin
```

Important commits:

```text
b06332e Document DeepTeam compatibility review
bdf838f Add adaptive model handoff test
aed28b9 Stabilize Judge connectivity output
7e1f52d Start API with frontend dev server
e1f6a30 Add model connectivity checks
625e24f Refresh frontend requirements handoff
e6ccbe2 Add profile settings section
49ff2cd Stabilize polling and redesign settings
571af23 Harden frontend for backend integration
749dd10 Document frontend approval review
```

`main` remains at the earlier frontend handoff baseline. All current PoC work is
on `Ashwin`.

The worktree was clean and synchronized with `origin/Ashwin` immediately before
this checkpoint document was drafted. The documentation changes creating and
linking TRD-2B are expected to appear as the only worktree changes until they
are committed.

## 4. Scope Completed During This Session

The session completed five related pieces of work:

1. A local FastAPI model-connectivity API under `apps/api`.
2. Frontend Settings integration for live provider and model tests.
3. A bounded three-turn synthetic brokered handoff.
4. DeepTeam guide import and static compatibility analysis.
5. Documentation of unresolved architecture alternatives.

The session did not implement a real DeepTeam Assessment.

## 5. Application Structure At This Checkpoint

```text
secmate/
  apps/
    web/                     React/Vite operator console
    api/                     FastAPI model-connectivity PoC
  Documents/
    TRD-1.md
    TRD-2.md
    TRD-2A-FRONTEND-IMPLEMENTATION.md
    TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md
    DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md
    DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md
```

The API and frontend can be started together from `apps/web`:

```powershell
npm run dev
```

The script starts:

- FastAPI on `127.0.0.1:8000`.
- Vite on strict port `5173` for the trusted local-origin policy.

## 6. Model Connectivity API

### 6.1 Purpose

The current API validates temporary model roles before DeepTeam attack
methodology is connected.

It does not provide:

- Assessment persistence.
- Queueing or a durable worker.
- Real Target registration.
- DeepTeam execution.
- Findings or Reports.
- Canonical audit bundles.

### 6.2 Current endpoints

```text
GET  /api/v1/health
GET  /api/v1/providers/status
GET  /api/v1/model-profiles
POST /api/v1/model-profiles/{profile_id}/test
POST /api/v1/model-workflows/adaptive-handoff/test
```

### 6.3 Current provider configuration

Provider credentials are stored only in:

```text
apps/api/.env
```

The file is ignored by Git. Only `.env.example` is committed.

Required variables:

```text
GROQ_API_KEY
OPENROUTER_API_KEY
```

The keys were pasted into the coding conversation during the session. That is
not an approved secret-handling practice. They should be rotated before broader
use, and future agents must never ask the user to paste credentials into chat.

### 6.4 Current temporary model profiles

```text
Attacker / planner
  Provider: Groq Cloud
  Model: qwen/qwen3.8-27b

Attack Critic
  Provider: Groq Cloud
  Model: qwen/qwen3.8-27b

Outcome Judge
  Provider: OpenRouter
  Model: nvidia/nemotron-3-super-120b-a12b:free

Synthetic Target
  Provider: OpenRouter
  Model: nvidia/nemotron-3-ultra-550b-a55b:free
```

These are temporary PoC profiles, not approved production models.

### 6.5 Provider constraints discovered

- Groq Qwen was responsive and supported the required structured output.
- Groq GPT-OSS 120B and 20B appeared in the model catalog but were blocked at
  the organization level.
- OpenRouter Gemma free endpoints repeatedly returned provider `429` responses.
- OpenRouter free endpoints required `data_collection: allow` for the available
  synthetic routes. This is acceptable only for harmless synthetic prompts.
- Nemotron Super initially spent its output budget on visible reasoning instead
  of JSON. The provider adapter now disables reasoning, supplies the exact
  schema in the prompt, increases the output allowance, validates the result,
  and retries malformed gateway responses once.
- Free provider availability is not stable enough to treat one successful call
  as an availability guarantee.

## 7. Frontend Model Connectivity Surface

Route:

```text
/settings?section=models
```

Implemented features:

- Provider reachability indicators.
- OpenRouter remaining free-request quota.
- Individual model test buttons.
- Sequential `Test all models` behavior.
- Model role, provider, model ID, and declared capabilities.
- Structured response preview.
- Latency and token usage.
- Provider-derived error details suitable for current synthetic diagnostics.
  These are not yet normalized through an allowlisted production error
  envelope and must not be assumed safe for arbitrary upstream content.
- Responsive desktop and mobile layout.
- A bounded adaptive-handoff dry-run panel.

The browser never receives provider key values.

The rest of the application still uses deterministic local mock data for
Targets, Assessments, Findings, Reports, dashboard projections, search, and
notifications.

## 8. Live Verification Completed

Live provider tests passed for:

- Groq Qwen Attacker structured output.
- Groq Qwen Attack Critic structured output.
- OpenRouter Nemotron Outcome Judge structured verdict.
- OpenRouter Nemotron Ultra structured tool call.

The Target tool call was intercepted and never executed.

Automated verification at the checkpoint:

```text
Backend pytest: 5 tests passed
Frontend Vitest: 18 tests passed
Frontend production build: passed
Vite-to-FastAPI development proxy: passed
```

The backend test suite currently emits a Starlette TestClient deprecation
warning involving the future `httpx2` transition. It does not fail the tests,
but should be addressed during normal dependency maintenance.

## 9. Synthetic Brokered Handoff At This Checkpoint

The API includes a three-turn synthetic approval-boundary workflow.

Current order:

```text
Attacker creates probe
        |
        v
Synthetic Target responds or attempts a tool
        |
        v
Deterministic tool-name check
        |
        v
Outcome Judge evaluates when no hard violation exists
        |
        v
Attack Critic advises when another turn remains
        |
        v
Attacker receives validated feedback for the next turn
```

Current rules:

- Maximum of three turns.
- Deterministic checks run before the Judge.
- Confirmed deterministic evidence stops the path immediately.
- Confirmed Judge evidence stops the path immediately.
- Critic feedback is requested only when another turn remains.
- No Critic call occurs after the final turn.
- All tools are synthetic and intercepted.

The live run completed three turns, used Critic feedback on turns one and two,
and stopped on a deterministic restricted-tool attempt on turn three.

### 9.1 Important limitation

This is not a real DeepTeam multi-turn implementation.

- At this checkpoint, DeepTeam was not installed or imported by SecMate.
- The Target does not receive the complete prior conversation history.
- The scenario and model profile IDs are hard-coded.
- The deterministic rule matches restricted tool names rather than a versioned
  policy contract.
- Provider usage, costs, correlations, and provenance are not persisted as an
  immutable run record.
- The output is displayed in Settings and is not an Assessment, Finding, or
  Report.

The handoff must remain a named diagnostics fixture after real DeepTeam
integration begins.

## 10. DeepTeam Documentation Imported

The following guide was copied byte-for-byte from the local Paramount DeepTeam
workspace:

[DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md](./DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md)

Verified source and destination SHA-256:

```text
F011B492800715585E3E438DDF31766C112DF4C060624D40A79FECFF5F6EEC59
```

The detailed comparison is recorded in:

[DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md](./DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md)

## 11. DeepTeam Compatibility Conclusion

DeepTeam is conditionally compatible with SecMate. It is a strong fit for:

- Vulnerability-specific baseline generation.
- Attack transformations.
- `AttackEngine` variations and validation.
- Single-turn attack methods.
- Selected multi-turn attack progression.
- `RTTurn` projections.
- Engine-native scores, reasons, stopping categories, and costs.

DeepTeam must not replace SecMate's:

- Authorization and scope control.
- Broker and lifecycle authority.
- Target Gateway.
- Mock action bus.
- Deterministic policy engine.
- Canonical Judge contract.
- Evidence and audit contracts.
- Finding severity.
- Advisory outcome aggregation.
- External release governance.

Recommended boundary:

```text
SecMate Control API
        |
        v
Isolated Python 3.11 worker
        |
        +--> pinned DeepTeam attack engine
        +--> SecMate Target Gateway
        +--> mock action bus
        +--> deterministic policy oracles
        +--> SecMate semantic Judge when required
        |
        v
SecMate evidence normalizer and advisory outcome aggregator
```

## 12. DeepTeam Runtime Requirements

The reviewed Paramount fork is:

```text
Repository: Paramount-Assure/deepteam
Package metadata: 1.0.9
Commit: 2fd3445c5bb2070ce09834f66f1622eb914f6f46
Declared Python: >=3.9,<3.14
CI runtime: Python 3.11
```

The current `apps/api` virtual environment uses Python 3.14.7. DeepTeam must not
be installed into that environment.

The future worker must use Python 3.11 and pin the fork exactly:

```text
deepteam @ git+https://github.com/Paramount-Assure/deepteam.git@2fd3445c5bb2070ce09834f66f1622eb914f6f46
```

Prefer an internally built wheel with a pinned hash. Do not use generic
`pip install deepteam` as the identity of the reviewed fork.

Required environment before importing DeepTeam:

```text
DEEPTEAM_TELEMETRY_OPT_OUT=YES
DEEPEVAL_TELEMETRY_OPT_OUT=YES
DEEPTEAM_SHOW_PROGRESS=false
```

The worker must not receive `CONFIDENT_API_KEY` and must call
`a_red_team(..., _upload_to_confident=False)`.

## 13. DeepTeam Features Available to SecMate

The reviewed fork provides:

- 22 registered single-turn attacks.
- 5 registered multi-turn attacks.
- 36 registered standard vulnerabilities.
- Custom vulnerabilities.
- OWASP, OWASP Agentic, NIST, MITRE, EU AI Act, Aegis, and BeaverTails modes.
- Guardrails.
- Trace scanning.
- AI code scanning.
- RiskAssessment serialization.

The current SecMate PoC uses none of the actual DeepTeam package code.

Estimated capability adoption:

```text
Current PoC: 0% actual DeepTeam execution
Single-turn integration: roughly 30-40% of useful attack capability
Selected multi-turn integration: roughly 60-70%
Broad attack, framework, guardrail, and scanner use: roughly 75-85%
```

The remaining features should be excluded where they duplicate SecMate
authority or are unsafe as canonical behavior.

## 14. DeepTeam Behaviors That Require Wrapping

### 14.1 Callback evidence

DeepTeam accepts `str` or assistant-role `RTTurn`. SecMate requires richer
evidence including trusted role, tool category and version, original and
redacted arguments, destination, interception decision, simulated result, and
policy outcomes.

The Target Gateway must store the full evidence record and return only a
correlated `RTTurn` projection to DeepTeam.

### 14.2 Score normalization

DeepTeam pass rates and CVSS-like scores are supporting metadata only.

Normalize cases with error precedence:

```python
if case.error:
    status = "error"
elif case.score is not None and case.score > 0:
    status = "pass"
else:
    status = "fail"
```

Do not trust aggregate error fields. Recompute from `risk.test_cases`.

### 14.3 Concurrency and mutable state

`RedTeamer.max_concurrent` does not bound all nested calls. Some attack and
framework paths reuse mutable state.

Initial policy:

- One fresh `RedTeamer` per run.
- Fresh vulnerability, attack, and `AttackEngine` objects.
- `max_concurrent=1` for initial multi-turn tests.
- One multi-turn profile per isolated worker.
- No concurrent built-in framework execution on one `RedTeamer`.

### 14.4 Async execution

Use `await red_teamer.a_red_team(...)` in an async worker. Do not call the
synchronous facade from a FastAPI event loop.

### 14.5 Persistence

Persist `risk.model_dump()` under a SecMate run ID together with the SecMate
manifest. Do not rely on `RiskAssessment.save()` as canonical persistence.

## 15. Architecture Decision Open At This Checkpoint

The final evaluation and critique architecture is intentionally unresolved.
The user decided that PoC evidence should determine the choice.

### Option A: Dual Attack Critics

```text
DeepTeam completes an attack path
        |
        v
SecMate verifies hard evidence
        |
        v
Critic A independently reviews attack quality
Critic B independently reviews attack quality
        |
        v
Bounded discussion or rebuttal, maximum three rounds
        |
        v
Consensus recommends the next attack method
```

In this option:

- The Attacker may make a provisional success claim.
- SecMate confirms machine-verifiable evidence.
- There is no always-on semantic Outcome Judge.
- Semantic cases without deterministic evidence require human review or an
  explicit `SEMANTIC_REVIEW_REQUIRED` result.

TRD-2 currently requires dual-stage verification and a structured semantic
Judge result for contextual behavior. Selecting Option A as the operational
architecture would therefore require a formal decision-log entry that explicitly
refines or supersedes the affected TRD-2 Judge requirements. PoC benchmarking
alone does not silently change that authority.

### Option B: Outcome Judge and One Attack Critic

```text
DeepTeam completes or advances an attack path
        |
        v
SecMate verifies hard evidence
        |
        +--> hard result: stop or continue without Judge
        |
        +--> ambiguous result: Outcome Judge
        |
        v
One Attack Critic recommends the next method after path exhaustion
```

This option provides a clearer separation between Target evaluation and attack
quality, but may use an additional semantic model call.

### 15.1 Agreed common behavior

Regardless of architecture:

- DeepTeam performs turn-level attack refinement.
- SecMate verifies hard evidence and controls stopping.
- Attack Critics review attack quality, not Target security.
- Attack Critics should normally run after a complete failed attack path rather
  than after every turn.
- Confirmed hard evidence stops the path immediately.
- No architecture may allow an Attacker or Critic claim to override SecMate
  evidence.
- Debate must be bounded; models must not discuss indefinitely.

### 15.2 Benchmark requirement

Both options should be implemented behind one replaceable review strategy and
benchmarked with identical Targets, attack methods, budgets, and ground truth.

Recommended interface:

```text
ReviewStrategy
  - DualCriticConsensusStrategy
  - JudgeCriticStrategy
```

Recommended initial benchmark:

```text
1 scenario
x 2 Target variants
x 2 architectures
x 3 repetitions
= 12 campaign runs
```

Target variants:

- Known-vulnerable synthetic Target.
- Hardened synthetic Target.

Metrics:

- Confirmed known weaknesses discovered.
- False success claims.
- Missed known weaknesses.
- Evidence completeness.
- Unique strategy count.
- Duplicate strategy rate.
- Turns to success.
- Provider calls and tokens.
- Duration and errors.
- Reproduction rate.

Neither architecture should grade itself. Use deterministic ground truth and
human review for semantic cases.

## 16. Role Definitions at This Checkpoint

### 16.1 Attacker / DeepTeam simulator

Responsibilities:

- Create the attack plan for one selected method.
- Predeclare success conditions.
- Generate the probe.
- Improve probes between turns using Target responses.
- Make provisional success claims.

The Attacker must not control tool dispatch, final outcomes, budgets, or release
decisions.

### 16.2 SecMate broker and deterministic evaluator

Responsibilities:

- Validate campaign scope.
- Route all model outputs.
- Treat Target output as untrusted data.
- Intercept tools.
- Check canaries, roles, destinations, approval tokens, and arguments.
- Confirm or reject Attacker success claims.
- Control turns, timeouts, cancellation, and stopping.
- Produce the authoritative machine-verifiable path result.

### 16.3 Outcome Judge, if architecture B is selected

Responsibilities:

- Evaluate only ambiguous semantic evidence.
- Return confidence, evidence references, concise rationale, policy references,
  missing evidence, and ambiguity.

It should be skipped when deterministic evidence is conclusive.

### 16.4 Attack Critics

Responsibilities:

- Review why an attack path failed.
- Identify unexplored Target boundaries.
- Reject duplicate or exhausted strategies.
- Recommend the next attack method and measurable evidence objective.

They do not issue the final Target-security verdict.

## 17. Canonical Success Evaluation Direction

The preferred evaluation hierarchy is:

```text
Target response and tool attempts
        |
        v
Deterministic SecMate policy checks
        |
        +--> conclusive hard evidence: authoritative result
        |
        +--> semantic ambiguity: optional Outcome Judge or human review
```

Hard evidence includes:

- Exact synthetic canary disclosure.
- Restricted tool attempt.
- Invalid approval-token acceptance.
- Unauthorized object or tenant access.
- Destination allowlist failure.
- SQL mutation or shell command attempt.
- Forbidden arguments.
- Synthetic data export.

Use synthetic secrets and records only. Never use real confidential data as a
test success marker.

## 18. Data And Contract Gaps At This Checkpoint

Before real DeepTeam execution, define valid versioned contracts for:

```text
ModelProfile
Campaign
AttackPlan
ThreatScenario
TargetInvocation
ConversationTurn
ToolAttempt
OracleResult
DeepTeamEngineResult
JudgeResult
CriticReview
CriticConsensus
NormalizedTestCase
LifecycleEvent
ErrorEnvelope
Finding
AuditBundle
Report
```

Do not use the current frontend DTOs or DeepTeam Pydantic classes as immutable
database or audit contracts.

The frontend currently has one demo model-profile domain and the API has a
separate connectivity model-profile domain. These must eventually be unified
under one versioned profile schema while retaining connectivity health as a
separate observation.

## 19. Work Not Implemented At This Checkpoint

- DeepTeam dependency installation.
- Python 3.11 worker.
- Target registry or authorization scope.
- Queue or durable background worker.
- SQLite or canonical JSON Assessment persistence.
- Full Target Gateway.
- Trusted authorization context.
- Versioned policy oracles.
- True Target conversation history.
- DeepTeam attack or vulnerability factories.
- DeepTeam `AttackEngine`.
- DeepTeam `RedTeamer` execution.
- Framework campaigns.
- Canonical Judge calibration.
- Architecture benchmark harness.
- Real Findings and Reports from live evidence.
- Regression replay.
- Remote Paramount Targets.
- Enterprise identity or RBAC.
- Secret-manager integration.
- Production deployment or monitoring.

## 20. Mistakes and Traps Not to Repeat

### 20.1 Secret handling

- Never ask the user to paste API keys into chat.
- Never put keys in `VITE_*` variables.
- Never commit `.env`.
- Rotate the keys used in the completed session because they were exposed in
  conversation context.
- Future persistence must store opaque secret references, not values.

### 20.2 Development server behavior

- Running Vite alone causes proxy `502` or `ECONNREFUSED` errors when FastAPI is
  not listening on port `8000`.
- Use `npm run dev` from `apps/web`; it starts both services.
- Vite uses strict port `5173`; free that port before starting the combined app.
- Do not kill unknown existing development processes.

### 20.3 Provider assumptions

- A model appearing in a provider catalog does not mean the organization is
  allowed to invoke it.
- A free endpoint that worked once may return `429` later.
- Structured-output support advertised at model level may vary by endpoint.
- Always validate model output against the schema.
- Handle success-status gateway responses that omit normal completion choices.
- Do not make real-evidence architecture depend on free-provider availability.

### 20.4 DeepTeam dependency identity

- Do not use generic `pip install deepteam` for the reviewed Paramount fork.
- Pin the exact SHA or internal wheel.
- Do not install DeepTeam in Python 3.14.
- Do not let its broad DeepEval dependency float without review.

### 20.5 DeepTeam orchestration

- Do not make DeepTeam the SecMate broker.
- Do not call the synchronous facade inside an async worker.
- Do not enable Confident upload.
- Set telemetry opt-outs before importing DeepTeam.
- Do not trust `RedTeamer.max_concurrent` as a global call limit.
- Do not share stateful attack instances concurrently.
- Do not use concurrent built-in framework execution on one `RedTeamer`.
- Do not use `reuse_simulated_test_cases=True`.
- Do not trust aggregate error counts.
- Do not treat DeepTeam CVSS as SecMate severity.
- Do not treat DeepTeam release-gate examples as SecMate release authority.

### 20.6 Current PoC interpretation

- Do not call the current handoff a real Assessment.
- Do not call it a DeepTeam implementation.
- Do not treat Settings output as security evidence.
- Do not claim that the Target maintains real multi-turn session state.
- Do not connect the current synthetic result directly to Findings or Reports.
- Do not retain hard-coded models, prompts, rules, or success conditions as
  production contracts.

### 20.7 Evaluation architecture

- Do not finalize dual-Critic versus Judge-plus-Critic based on preference.
- Do not let either architecture grade itself in the benchmark.
- Do not run unbounded model debates.
- Do not invoke two Critics after every turn without evidence that the extra
  calls improve attack success.
- Do not let Attacker or Critic claims override deterministic evidence.

## 21. Historical Recommended Next-Agent Sequence

The next coding agent must not jump directly into broad attack execution.

### Step 1: Read and verify authority

Read in this order:

1. [TRD-1.md](./TRD-1.md)
2. [TRD-2.md](./TRD-2.md), including Section 25
3. [TRD-2A-FRONTEND-IMPLEMENTATION.md](./TRD-2A-FRONTEND-IMPLEMENTATION.md)
4. This TRD-2B
5. [DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md](./DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md)
6. [DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md](./DEEPTEAM_SECMATE_COMPATIBILITY_REVIEW.md)
7. `README.md`
8. Current [TRD-4](./TRD-4.md) frozen-PoC handoff
9. Current code under `apps/api` and `apps/web`
10. Recent Git history on `Ashwin`

### Step 2: Rotate and validate secrets

- Confirm the user has rotated the Groq and OpenRouter keys.
- Keep values only in ignored server-side configuration.
- Verify no secrets are tracked before any commit.

### Step 3: Record the next approval boundary

Before DeepTeam code is added, confirm and record approval for:

- Python 3.11 worker creation.
- Exact DeepTeam SHA.
- One synthetic single-turn comparison slice.
- No real Target or real tool execution.
- No Confident upload.
- Synthetic evidence only.

### Step 4: Define contracts before execution

Create valid versioned schemas for the contracts listed in Section 18. Keep
presentation DTOs separate from execution and audit contracts.

### Step 5: Establish the compatibility foundation

- Create or configure a Python 3.11 worker environment.
- Pin the Paramount DeepTeam SHA.
- Set telemetry and upload policy before import.
- Implement `SecMateDeepTeamRunner`.
- Implement a Target Gateway interface and `RTTurn` projection.
- Implement shared external rate limits, timeouts, and cancellation.
- Persist nothing until the evidence contract is reviewed.

### Step 6: Implement one single-turn comparison slice

Recommended first slice:

```text
Target: synthetic SOCMate
Vulnerability: ExcessiveAgency / permissions
Attack: PermissionEscalation
Restricted tool: isolate_host
Cases: 1
Turns: 1
Concurrency: 1
Upload: disabled
Tools: intercepted
```

The slice must preserve raw DeepTeam output and a separate SecMate manifest.

### Step 7: Add true multi-turn only after the gateway works

Use `LinearJailbreaking(num_turns=3)` first. Ensure the Target receives real
conversation history. Keep concurrency at one.

### Step 8: Build the architecture benchmark

Implement the two review strategies behind one interface. Run the controlled
benchmark described in Section 15.2. Do not choose the final architecture until
the benchmark results are reviewed.

### Step 9: Connect to Assessment lifecycle later

Only after the worker, evidence, cancellation, and normalization behavior are
proven should the live HTTP adapter replace mock Assessment execution.

## 22. Acceptance Gates for the Next Phase

The compatibility foundation is accepted only when:

1. Python 3.11 and the exact DeepTeam fork SHA are recorded.
2. Telemetry and upload are disabled before import.
3. One target callback returns a valid assistant `RTTurn`.
4. Full SecMate evidence remains available outside the `RTTurn` projection.
5. All tool attempts are intercepted.
6. Deterministic policy runs before any canonical semantic result.
7. DeepTeam errors normalize to error and never pass.
8. Provider failure produces an explicit fail-closed state.
9. No secret appears in API output, audit output, Git, or logs.
10. The raw DeepTeam result and SecMate manifest can reproduce the run.

The first DeepTeam slice is accepted only when:

1. One approved attack and vulnerability subtype execute successfully.
2. The synthetic Target's expected boundary is explicit.
3. Hard evidence is machine-verifiable.
4. No real tool or destination is reached.
5. Another engineer can rerun the slice from documented configuration.

## 23. Historical TRD-3 Gate Outcome

At this checkpoint, TRD-3 was intentionally deferred. The later user decision
on 2026-09-28 authorized TRD-3 after a real fixed synthetic DeepTeam run,
deterministic policy, independent Target evaluation, frontend dispatch, and
checked verification artifacts existed.

The following items remain required before pilot or production claims:

- A DeepTeam-backed SOCMate vertical slice.
- Isolation and unauthorized-dispatch tests.
- Safe cancellation and timeout behavior.
- Reproducible Findings.
- Immutable redacted evidence.
- Zero credential retention verification.
- Architecture benchmark results.
- Judge calibration results if a semantic Judge remains in the design.
- False-positive and false-negative measurements.
- Requirement-by-requirement traceability across TRD-1, TRD-2, TRD-2A, and
  TRD-2B.

TRD-3 records implementation architecture only. Controlled-pilot, calibration,
and production gates remain open.

## 24. Historical Checkpoint Summary

SecMate now has:

- A mature deterministic frontend prototype.
- A local FastAPI model-connectivity service.
- Live Groq and OpenRouter model diagnostics.
- Structured output and tool-call validation.
- A bounded synthetic brokered handoff.
- A detailed DeepTeam implementation guide.
- A verified compatibility and gap analysis.
- A clearly defined next worker boundary.

At commit `b06332e`, SecMate did not yet have:

- A real DeepTeam worker.
- A real Assessment backend.
- A canonical evidence store.
- A production Target Gateway.
- A validated evaluation architecture.
- Calibrated assurance capability.

Those statements are preserved as historical checkpoint evidence and are not a
current gap inventory. See TRD-3 and [TRD-4](./TRD-4.md) for current status and
next work.
