# DeepTeam and SecMate Compatibility Review

> **Dated pre-integration review:** This analysis was completed before the
> worker implementation. Its ownership boundaries and cautions remain relevant,
> but future-tense and not-implemented statements are not a current gap list.
> Read
> [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md)
> for the implemented architecture and live evidence.
>
> **Requirements context:** [TRD-2B](./TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md)
>
> **Current engineering handoff:** [TRD-4](./TRD-4.md). This review retains framework rationale; current manual generation deliberately bypasses the retired AttackEngine/enhancement path.

## Review Status

- Review date: 2026-09-26
- Review type: documentation and static-code comparison only
- Application code changed during this review: no
- Guide reviewed: [DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md](./DEEPTEAM_INHOUSE_IMPLEMENTATION_GUIDE.md)
- SecMate branch reviewed: `Ashwin`
- DeepTeam fork reviewed: `Paramount-Assure/deepteam`
- DeepTeam commit reviewed:
  `2fd3445c5bb2070ce09834f66f1622eb914f6f46`
- DeepTeam package metadata version: `1.0.9`
- DeepTeam declared Python range: `>=3.9,<3.14`
- DeepTeam CI runtime: Python 3.11

The copied implementation guide is an accurate technical guide to the reviewed
DeepTeam fork. It does not supersede TRD-1, TRD-2, or TRD-2A. Where its proposed
release gates, orchestration ownership, evidence model, or lifecycle conflict
with TRD-2, the SecMate requirements lineage remains authoritative.

## Executive Finding

**Overall compatibility: conditionally compatible, approximately 50%.**

DeepTeam is a strong fit for SecMate's adversarial case generation, attack
transformation, vulnerability catalog, and selected multi-turn progression.
It is not a drop-in SecMate backend and must not own:

- Target authorization or allowed destinations.
- Assessment lifecycle or final status.
- Provider and Target budgets.
- Tool dispatch or interception.
- Deterministic policy decisions.
- Canonical evidence and audit contracts.
- Finding severity or business impact.
- Advisory Assessment outcomes.
- Release blocking decisions.

The correct boundary is:

```text
SecMate broker and worker controls
        |
        +--> DeepTeam attack engine
        +--> SecMate Target Gateway and mock action bus
        +--> SecMate deterministic policy oracles
        +--> approved SecMate Judge adapter
        |
        v
SecMate evidence normalizer and advisory outcome aggregator
```

DeepTeam should be consumed as an isolated worker dependency behind a strict
anti-corruption layer.

## Strong Alignment

### Authorized internal testing

Both systems require named ownership, explicit scope, controlled environments,
approved endpoints, synthetic data, and production authorization.

- DeepTeam guide: Sections 2.1 through 2.3.
- SecMate: TRD-2 Sections 2 and 9.

### Action-space evidence

DeepTeam can preserve response text, retrieval context, turns, and tool calls
through `RTTurn`. SecMate also treats action-space behavior as the primary
security boundary.

`RTTurn` is useful as an execution projection, but it is not sufficient as the
canonical SecMate audit record.

### Tool isolation

The guide's mock-tool, read-only credential, disposable tenant, egress, and
budget controls align closely with SecMate's mock action bus and fail-closed
safety requirements.

### Adaptive and multi-turn attacks

DeepTeam provides:

- 22 registered single-turn attacks.
- 5 registered multi-turn attacks.
- 36 registered standard vulnerabilities.
- Baseline case generation.
- `AttackEngine` transformations and variations.
- Weighted attack selection and Cartesian execution.
- Linear, tree, crescendo, sequential, and Bad Likert progressions.
- Multi-turn stopping categories and per-turn evidence.

This is a strong match for SecMate's required attack-generation layer.

### Reproducibility warnings

The guide correctly identifies that DeepTeam's native metadata propagation,
aggregate error counts, DataFrame views, and timestamp-based save names are not
sufficient for canonical evidence. This reinforces the need for a SecMate-owned
immutable run manifest.

### Error handling

The guide correctly warns that DeepTeam errors are excluded from pass-rate
denominators. This aligns with SecMate's rule that errors and insufficient
evidence must never become PASS.

## Critical Compatibility Gaps

### 1. Python runtime mismatch

The current `apps/api` virtual environment uses Python 3.14.7. DeepTeam 1.0.9
declares Python `<3.14`, and repository CI exercises Python 3.11.

DeepTeam must not be installed into the current Python 3.14 environment.

Required treatment:

- Run the future DeepTeam worker on Python 3.11.
- Set the worker project's Python range to `>=3.11,<3.14`.
- Keep the control API and worker separable even if both remain under
  `apps/api` during the PoC.

### 2. Generic package installation does not identify the Paramount fork

The guide currently includes:

```text
pip install deepteam
```

That can install the upstream package rather than the reviewed Paramount fork.
The package metadata version `1.0.9` is not a unique fork revision, and the fork
has no Git tags.

Required treatment:

```text
deepteam @ git+https://github.com/Paramount-Assure/deepteam.git@2fd3445c5bb2070ce09834f66f1622eb914f6f46
```

An internally built wheel pinned by hash is preferable. The resolved DeepEval
version should also be pinned rather than allowed to float.

### 3. DeepTeam cannot replace the SecMate broker

DeepTeam internally owns case generation, attack transformation, target calls,
multi-turn progression, metric evaluation, and result aggregation.

SecMate requires its deterministic broker to retain authority over:

- State transitions.
- Correlation IDs.
- Allowed destinations.
- Tool interception.
- Retry and timeout policy.
- Rate and token budgets.
- Cancellation and emergency stops.
- Final Assessment status.

DeepTeam must therefore execute inside a SecMate-controlled worker step rather
than become the top-level orchestrator.

### 4. DeepTeam callback evidence is narrower than SecMate evidence

DeepTeam accepts callbacks returning `str` or assistant-role `RTTurn`. SecMate
must additionally retain:

- Tool identity and version.
- Tool category.
- Original and redacted arguments.
- Trusted caller role and authorization context.
- Destination.
- Interception or sandbox decision.
- Simulated result returned to the Target.
- Applied policy rules and outcomes.

Required treatment:

- Every DeepTeam callback must invoke the SecMate Target Gateway.
- The gateway stores the complete evidence envelope.
- The callback returns a correlated `RTTurn` projection to DeepTeam.
- No direct provider or Target callback may bypass the SecMate gateway.

### 5. DeepTeam scores cannot become SecMate outcomes

DeepTeam uses positive scores for pass, zero for vulnerable, and normally
`None` for error. Its CVSS-like calculation cannot currently reach Critical.

SecMate requires:

```text
PASS
PASS_WITH_WARNINGS
CRITICAL_RISK_DETECTED
ASSESSMENT_INCONCLUSIVE
HARNESS_ERROR
```

Required treatment:

- Preserve DeepTeam score, reason, cost, and CVSS as engine-native metadata.
- Give `case.error` precedence over any score.
- Recompute pass, fail, and error counts from raw cases.
- Derive SecMate severity and advisory results independently from normalized
  evidence, deterministic policy, business impact, confidence, and coverage.

### 6. DeepTeam release-gate examples conflict with SecMate advisory authority

The guide contains `must_block` release-gate examples. TRD-2 explicitly states
that SecMate provides advisory results and external governance owns any release
decision.

Required treatment:

- Rename DeepTeam blocking examples to policy recommendations when used by
  SecMate.
- Never claim that SecMate itself authorizes or blocks a release.

## High-Risk Integration Issues

### Stateful attack instances are not safe merely because they are per-run

DeepTeam reuses configured attack objects across cases inside a run. Some attack
classes maintain mutable state, including Crescendo, Tree Jailbreaking, and
Emotional Manipulation.

Instantiating attacks once per Assessment is not sufficient when cases run
concurrently.

Safe initial treatment:

- Construct fresh vulnerabilities, attacks, and `AttackEngine` instances.
- Use `max_concurrent=1` for initial multi-turn campaigns.
- Run one multi-turn profile per isolated worker.
- Do not share stateful attacks across cases.

A fork patch is required only if high-throughput concurrent multi-turn execution
becomes a concrete requirement.

### Built-in asynchronous framework execution races shared state

DeepTeam can assess framework categories concurrently on one `RedTeamer` while
mutating shared evaluator, simulator, attack simulator, test-case, and result
state.

Required treatment:

- Do not use concurrent built-in framework orchestration.
- Expand framework categories in SecMate.
- Create a new `RedTeamer` for each category.
- Aggregate results under SecMate-controlled concurrency.

### The synchronous API should not run inside FastAPI event loops

The guide's example uses an async callback with synchronous
`red_teamer.red_team()`. The synchronous facade uses event-loop bridging.

Required treatment:

- Use `await red_teamer.a_red_team(...)` inside async workers.
- Reserve `red_team()` for synchronous process entry points.

### Error state must override stale scores

The guide states that errors use `score=None`, but mutable reused test cases can
retain a stale score when a later execution errors.

Required normalization:

```python
if case.error:
    status = "error"
elif case.score is not None and case.score > 0:
    status = "pass"
else:
    status = "fail"
```

Do not use `reuse_simulated_test_cases=True`.

### DeepTeam concurrency controls are incomplete

`RedTeamer.max_concurrent` does not bound every nested call. Baseline cases,
AttackEngine refinement and validation, tree branches, and dataset frameworks
can create additional fan-out.

SecMate must apply shared external controls around:

- Simulator calls.
- Evaluator calls.
- Target calls.
- Tree branches.
- Dataset framework execution.

### Automatic telemetry and Confident upload require process policy

Required worker environment before importing DeepTeam:

```text
DEEPTEAM_TELEMETRY_OPT_OUT=YES
DEEPEVAL_TELEMETRY_OPT_OUT=YES
DEEPTEAM_SHOW_PROGRESS=false
```

Workers must not receive `CONFIDENT_API_KEY` and must always pass
`_upload_to_confident=False`.

### Current OpenRouter collection settings are synthetic-only

The current SecMate PoC uses `data_collection: allow` because free OpenRouter
endpoints otherwise had no compatible routes. This is acceptable only for the
declared harmless synthetic connectivity tests.

It must not become the default for real Target prompts, internal context,
source code, or Assessment evidence.

## Recommended SecMate Treatment At The Review Date

### Retain

- FastAPI server-side provider boundary.
- Backend-only credential loading.
- Structured-output validation.
- Provider health and quota diagnostics.
- Synthetic Target and intercepted mock tools.
- Deterministic checks before semantic judging.
- Model Connectivity Settings surface.
- Current frontend polling, cancellation, routing, and fail-closed invariants.
- The synthetic three-turn handoff as a diagnostics fixture.

### Adapt

- Split connectivity DTOs from execution and audit contracts.
- Expand tool evidence beyond name and arguments.
- Add run IDs, timestamps, versions, usage, cost, errors, and correlations.
- Complete the Judge contract with severity, policy references, missing
  evidence, ambiguity, and calibration metadata.
- Replace hard-coded tool-name checks with versioned policy oracles.
- Add provider-wide semaphores, rate limiting, cancellation, and total budgets.
- Unify frontend demo model profiles with backend connectivity profiles.
- Add a canonical error envelope with stable codes and retryability.

### Replace for DeepTeam-backed execution

- Replace `run_adaptive_handoff()` as the operational attack engine.
- Replace hard-coded scenario, profile IDs, and prompts with an approved
  versioned campaign.
- Replace direct synthetic Target requests with the Target Gateway.
- Replace simple Judge-string stopping with policy-controlled conflict and
  confidence handling.

The current handoff should remain available as a named connectivity fixture. It
must not be treated as a real DeepTeam multi-turn Assessment because the Target
does not currently receive full prior conversation history.

### Retire only after backend equivalence exists

- Retire duplicate operational Attacker/Critic logic after DeepTeam worker
  progression is proven.
- Retire local mock Assessment outcomes only after the HTTP lifecycle matches
  cancellation, polling, fail-closed, and artifact-generation behavior.
- Retain the mock frontend adapter for deterministic UI regression tests.

## Catalog Compatibility

DeepTeam provides broad but not complete one-to-one coverage of the SecMate
threat catalog.

Strong coverage includes:

- Prompt injection and prompt probing.
- System prompt leakage.
- BOLA, BFLA, RBAC, debug access, SQL injection, shell injection, and SSRF.
- Excessive agency and tool misuse.
- Indirect instructions and context poisoning.
- Tool metadata poisoning.
- Identity and inter-agent trust abuse.
- Encoding, obfuscation, multilingual, roleplay, and authority attacks.
- Multi-turn linear, tree, crescendo, sequential, and rating-based attacks.

SecMate must retain its own scenario catalog for areas that are broader than or
not canonically represented by DeepTeam, including:

- Improper output handling as an application boundary.
- Vector and embedding weaknesses.
- Model and agent supply-chain weaknesses.
- Data and model poisoning.
- Cascading multi-agent workflow failures.
- Cross-session persistence.
- Unsafe provider, network, tool, and fallback behavior.
- Human-agent trust exploitation as a measurable business scenario.

Framework mappings must remain versioned SecMate data. DeepTeam framework mode
is an execution option, not the canonical standards crosswalk.

## Recommended Integration Boundary

```text
React operator console
        |
        v
SecMate Control API
  resources, approvals, lifecycle, cancellation, advisory outcomes
        |
        v
Queue or isolated Python 3.11 worker
  immutable run manifest, budgets, telemetry policy, rate limits
        |
        +--> SecMate Target Gateway
        |      trusted identity, session history, tool interception,
        |      complete evidence, deterministic policy
        |
        +--> DeepTeam 1.0.9 at pinned Paramount SHA
        |      case generation, AttackEngine, selected attack progression,
        |      optional vulnerability metric signal
        |
        +--> SecMate Judge adapter
               calibrated structured verdict and evidence references
        |
        v
SecMate Evidence Normalizer
  Findings, AuditBundle, Report, advisory Assessment result
```

## Guide Corrections Before Treating It as an Implementation Specification

The copied guide is intentionally preserved unchanged. The following items
should be corrected in a future reviewed revision:

1. Replace generic `pip install deepteam` with the pinned Paramount commit or
   internal wheel.
2. Identify the reviewed revision by package version and Git SHA.
3. Say that the Python range is declared support while CI currently verifies
   Python 3.11.
4. Prefer `a_red_team()` in async services.
5. Clarify that stateful attacks need per-case isolation or serialized
   execution, not merely per-run construction.
6. Document the shared-state race in concurrent framework execution.
7. State that `case.error` must override any retained score.
8. Expand the YAML warning beyond catalog counts to include unsupported
   parameters, frameworks, upload control, and path behavior.
9. Clarify that automatic upload exports sensitive evidence but not the entire
   `RiskAssessment` object.
10. Repeat telemetry opt-out requirements in the offline test instructions.

## Historical Recommended Next Sequence

No DeepTeam code should be added until the following comparison decisions are
approved:

1. Confirm that DeepTeam is a worker engine, not the SecMate broker.
2. Approve Python 3.11 for the worker.
3. Approve the exact Paramount DeepTeam SHA or internal wheel.
4. Define canonical versioned contracts for campaign, Target invocation, tool
   attempt, oracle result, Judge result, normalized test case, lifecycle event,
   error, and audit manifest.
5. Define the Target Gateway and `RTTurn` projection boundary.
6. Define external provider data-handling rules for non-synthetic evidence.
7. Decide whether initial multi-turn work will be serialized or whether the
   fork will be patched for safe concurrent attack instances.
8. Select one low-cost comparison slice before any frontend Assessment
   integration.

Recommended first comparison slice after those decisions:

```text
One synthetic SOCMate Target
One explicit vulnerability subtype
One deterministic transformation or PromptInjection attack
One case
max_concurrent=1
no Confident upload
all tools intercepted
raw DeepTeam model_dump plus SecMate manifest
```

Linear Jailbreaking with three turns should follow only after the SecMate Target
Gateway preserves true Target conversation history.

## Final Determination

The guide is technically strong and the majority of its attack counts, API
descriptions, callback rules, lifecycle, telemetry warnings, stopping
categories, result caveats, and known repository defects match the reviewed
fork.

DeepTeam is suitable for SecMate's adversarial generation and selected
multi-turn attack layer. It is unsuitable as SecMate's canonical broker,
policy engine, evidence store, scoring system, or release authority.

The safest path is to retain the current connectivity diagnostics, introduce a
Python 3.11 isolated worker, wrap the pinned DeepTeam fork behind SecMate
contracts, and preserve SecMate ownership of deterministic safety, lifecycle,
audit, findings, and advisory outcomes.
