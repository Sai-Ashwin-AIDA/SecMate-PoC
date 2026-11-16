# SecMate Technical Requirements Document 2

> **Current implementation successor:** [TRD-4](./TRD-4.md) records the frozen PoC and AI-agent handoff. It does not waive this document's unchanged calibration, pilot, privacy, identity or production requirements.

## Reviewed Upgrade and Continuation of TRD-1

> **Document status:** Authoritative reviewed upgrade
>
> **Predecessor:** [TRD-1.md](./TRD-1.md)
>
> **Development model:** Waterfall requirements lineage
>
> **Product:** SecMate, Paramount Computer Systems internal AI-agent assurance platform
>
> **Review date:** 2026-09-24
>
> **Architecture successor:**
> [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md)
> records the later approved fixed synthetic PoC architecture and implementation
> evidence. TRD-2 remains authoritative for unchanged product, assurance, pilot,
> and production requirements.
>
> **Current engineering handoff:** [TRD-4](./TRD-4.md). Use it for the latest
> implementation delta. This TRD remains authoritative for requirements not
> explicitly refined by the successor implementation records. The frozen PoC described in TRD-4 does not waive unmet enterprise gates.

TRD-2 is the reviewed continuation and upgraded version of
[TRD-1.md](./TRD-1.md). It does not erase TRD-1. The two documents form a
traceable waterfall requirements history:

1. TRD-1 records the original system vision, foundational architecture, and
   engineering baseline.
2. TRD-2 records the subsequent product and AI-team review, corrects outdated
   assumptions, resolves scope decisions, and adds implementation and
   acceptance requirements.
3. TRD-3 reads this lineage, retains the historical rationale, and records the
   later fixed synthetic DeepTeam PoC architecture. It does not supersede the
   unchanged production and pilot gates in this document.

When TRD-2 explicitly conflicts with TRD-1, TRD-2 is authoritative. All TRD-1
requirements not changed here remain active.

---

## 1. Review Outcome

SecMate has a strong product direction and an appropriate architectural thesis,
but it is currently an early frontend and requirements prototype rather than an
operational LLM penetration-testing platform.

The review approves the following direction:

- SecMate will be used only by Paramount Computer Systems' internal AI teams
  and authorized supporting security, platform, governance, and engineering
  stakeholders.
- SecMate will be a specialized AI-agent assurance layer in the internal
  software delivery lifecycle.
- The product will assess company-built AI agents through controlled black-box
  and grey-box testing.
- Action-space behavior remains the primary security boundary.
- Attacks will be target-specific, adaptive, reproducible, and evidence-driven.
- CI/CD results will be advisory. SecMate will not directly authorize or block
  a release; consuming governance and pipeline policies will decide how to act
  on SecMate's result.
- The frontend may be developed before the backend only through typed,
  contract-first mock services that can later be replaced by real API adapters.
- The current executive dashboard screenshots are the visual authority for the
  dashboard milestone.

The review does not approve SecMate for production CI/CD use until the
acceptance gates in this document are satisfied.

---

## 2. Product Scope

### 2.1 Purpose

SecMate is an internal AI-agent security testing and assurance platform. It
helps Paramount AI teams evaluate an existing or newly developed agent before
and during controlled release processes.

The platform must determine whether a Target can be manipulated into:

- Violating its stated operating boundaries.
- Revealing sensitive data, prompts, topology, or credentials.
- Misusing authorized tools.
- Calling unauthorized tools.
- Supplying dangerous or policy-breaking tool parameters.
- Escalating identity or privileges.
- Following malicious instructions from retrieved or third-party content.
- Persisting poisoned instructions in memory or context.
- Producing unsafe output that downstream software executes or trusts.
- Consuming excessive resources or causing cascading workflow failures.

### 2.2 Internal-Only Boundary

SecMate is not a public SaaS product, a customer-facing offering, or a general
offensive-security platform. Testing is restricted to Paramount-owned or
Paramount-authorized AI agents and approved controlled environments.

Conventional vulnerabilities are in scope only when they are reachable through,
caused by, or materially affect an AI agent's model, tools, retrieval sources,
memory, identity, output handling, or execution environment.

### 2.3 Non-Goals

SecMate will not:

- Launch uncontrolled destructive tests against production systems.
- Replace human threat modeling, architecture review, or incident monitoring.
- Claim that an automated semantic judge is infallible.
- Treat a visually complete dashboard as proof of security-testing capability.
- Store hidden model Chain-of-Thought as audit evidence.
- Directly decide whether a business release is permitted.

---

## 3. Authoritative Terminology

### 3.1 Target

A **Target** is a Paramount-built or Paramount-authorized AI agent under test.
Examples include:

- **SOCMate:** An internal SOC correlation and analysis agent with access to
  security telemetry and approved security tools.
- **ChatMate:** An internal enterprise assistant with controlled access to M365
  mail, calendar, directory, and employee information.
- **GuardMate:** A policy or security-control enforcement agent.
- **TicketMate:** An IT service desk agent with ticketing and workflow tools.

The frontend and APIs must use **Target** for an assessable AI agent. The
generic navigation label **Agents** is superseded by **Targets** to avoid
confusion with the Attacker.

### 3.2 Attacker

The **Attacker** is SecMate's adversarial model or coordinated adversarial
generation subsystem. It studies a Target and produces a target-specific attack
plan. It is not an onboarded business agent and must not be counted in Target
inventory metrics.

The Attacker may propose probes and adaptations, but it must not control durable
orchestration, safety boundaries, tool dispatch, budgets, retries, or final
verdicts.

### 3.3 Assessment

An **Assessment** is a controlled execution of a versioned attack plan against a
versioned Target profile. It contains one or more sessions, scenarios, and
turns.

### 3.4 Finding

A **Finding** is an evidence-backed policy violation or security weakness
observed during an Assessment. Findings must be reproducible, attributable to
an exact Target and configuration, and suitable for remediation tracking.

### 3.5 Other Terms

- **Attack plan:** A structured set of goals, applicable techniques, candidate
  paths, stopping rules, and budgets for an Assessment.
- **Scenario:** A versioned test definition for one threat behavior or policy
  boundary.
- **Probe:** An adversarial input sent to the Target.
- **Action-space:** Tools, APIs, databases, queues, commands, functions, MCP
  servers, and other interfaces through which a Target can cause side effects.
- **Policy oracle:** A deterministic evaluator for an exact expected boundary.
- **Semantic judge:** A calibrated LLM evaluator for contextual behavior that
  deterministic rules cannot fully classify.
- **Audit bundle:** The immutable, redacted evidence required to review and
  reproduce an Assessment outcome.

---

## 4. Standards Baseline and Versioning

### 4.1 Standards Baseline

SecMate must maintain explicit, versioned mappings to applicable guidance,
including:

- OWASP GenAI LLM Top 10 2026.
- OWASP Top 10 for Agentic Applications 2026.
- OWASP AI Testing Guide v1.
- OWASP GenAI Red Teaming guidance.
- OWASP Agent Control Standard, where compatible with Target frameworks.
- MITRE ATLAS techniques and mitigations.
- NIST AI Risk Management Framework 1.0 and subsequent approved revisions.
- NIST AI 600-1, Generative AI Profile.
- NIST SP 800-218A, Secure Software Development Practices for Generative AI
  and Dual-Use Foundation Models.
- OpenAPI 3.1.
- JSON Schema Draft 2020-12.

### 4.2 Taxonomy Correction

TRD-1 and the original README associated OWASP `LLM08` with Excessive Agency.
In the OWASP 2025 taxonomy, Excessive Agency is `LLM06`, while `LLM08` covers
Vector and Embedding Weaknesses. New implementations must not rely on an
unversioned identifier.

Each standards mapping must include at least:

```json
{
  "framework": "string",
  "framework_version": "string",
  "control_or_risk_id": "string",
  "title": "string",
  "mapping_type": "primary | related | mitigation"
}
```

Mappings must be data, not hard-coded presentation text. This permits future
taxonomy upgrades without rewriting historical findings.

### 4.3 Crosswalk Requirement

The threat catalog must support many-to-many mappings between internal SecMate
scenario IDs and external frameworks. Reports must state the exact framework
version used at Assessment time.

---

## 5. Waterfall Delivery Model

SecMate will use traceable waterfall stages for major requirements evolution.
Iterations may occur within a stage, but a later phase must not silently alter
an approved earlier requirement.

### Phase 1: Requirements Baseline

Outputs:

- TRD-1 historical baseline.
- TRD-2 reviewed and upgraded baseline.
- Defined scope, terminology, safety boundaries, acceptance criteria, and
  unresolved decisions.

Exit gate:

- Product, AI engineering, security, and platform stakeholders approve the
  requirements lineage.

### Phase 2: System and Data Design

Outputs:

- Valid JSON Schemas.
- API contracts.
- Assessment state machine.
- Target integration contract.
- Threat catalog and standards crosswalk.
- Sandbox and credential architecture.
- Judge calibration design.

Exit gate:

- Architecture review confirms that destructive side effects cannot reach
  unauthorized systems.

### Phase 3: Vertical-Slice Implementation

Outputs:

- One simulated SOCMate Target.
- Target onboarding and manifest validation.
- Attack-plan generation.
- Bounded multi-turn execution.
- Tool interception.
- Deterministic and semantic verification.
- Finding generation.
- Dashboard reflection and machine-readable result.

Exit gate:

- The vertical-slice acceptance criteria in Section 18 pass.

### Phase 4: Verification and Calibration

Outputs:

- Gold evaluation set.
- Human-reviewed verdict calibration.
- False-positive and false-negative measurements.
- Reproduction testing.
- Safety and isolation testing.
- Load, timeout, retry, and provider-failure testing.

Exit gate:

- Quality thresholds in Section 17 pass.

### Phase 5: Controlled Internal Pilot

Outputs:

- Advisory CI/CD integration.
- Approved pilot Targets.
- Operational runbooks.
- Access control and audit review.
- Incident and emergency-stop procedures.

Exit gate:

- AI leadership and security governance approve limited internal operation.

### Phase 6: Scale And Post-Pilot Requirements

The original review reserved the TRD-3 name for measured pilot evidence. D-022
later authorized TRD-3 for the fixed implementation architecture. The substance
of this gate remains active and is now the TRD-4 gate: measured pilot evidence
and retained/refined/superseded requirement traceability are required before
wider rollout.

---

## 6. Target Intelligence Model

Smart attacks require a structured understanding of the Target rather than a
single free-text description.

Each Target profile must support:

- Identity, purpose, owner, business criticality, and environment.
- Model provider, model family, model version, and runtime configuration where
  disclosure is permitted.
- Black-box or grey-box assessment mode.
- System and developer instructions where available.
- Guardrails and negative operating boundaries.
- User personas and role tiers.
- Tools, functions, MCP servers, and tool schemas.
- Tool categories and side-effect classification.
- Authentication and authorization model.
- Data sources, RAG collections, memory stores, and external content channels.
- Data classifications and sensitive fields.
- Downstream systems and possible business impact.
- Expected safe refusals and expected permitted behavior.
- Known limitations and accepted risks.
- Transport, session, timeout, and correlation behavior.
- Approved sandbox and mock destinations.
- Historical findings and pinned regression cases.

Target profiles and all nested schemas must be versioned. Every Assessment must
record the exact profile version used.

---

## 7. Intelligent Attacker Architecture

### 7.1 Required Pipeline

The Attacker subsystem must use the following conceptual pipeline:

```text
Target Profiler
      |
      v
Threat Model and Capability Graph
      |
      v
Attack Planner
      |
      v
Candidate Strategy and Probe Generator
      |
      v
Broker-Controlled Target Execution
      |
      v
Observation and Dual Verification
      |
      v
Attack Refiner or Termination Decision
```

### 7.2 Planning Requirements

The Attack Planner must:

- Identify high-value prohibited outcomes from Target boundaries.
- Select only techniques relevant to actual Target capabilities.
- Build candidate attack paths from an entry channel to a prohibited outcome.
- State assumptions and required preconditions.
- Assign budgets for turns, tokens, requests, time, and estimated cost.
- Rank candidate strategies by applicability, expected impact, novelty, and
  evidence from previous attempts.
- Avoid repeating semantically equivalent failed probes unless repetition is
  required for statistical confidence.
- Define stopping conditions before execution.

### 7.3 Attack Generation Methods

SecMate must combine multiple methods rather than relying on one generator:

- Curated deterministic regression cases.
- Versioned attack recipes.
- Target-conditioned LLM generation.
- Template and parameter mutation.
- Coverage-guided fuzzing.
- Multi-turn authority and social-engineering strategies.
- Direct and indirect prompt injection.
- RAG, document, record, email, log, and web-content injection.
- Tool argument and parameter smuggling.
- Identity, role, and privilege manipulation.
- Encoding, formatting, multilingual, and representation transformations.
- Context-window and instruction-priority stress tests.
- Memory persistence and context poisoning.
- Multi-tool and multi-agent attack chains.
- MCP server, tool-description, and tool-result trust tests.
- Historical finding replay.

### 7.4 Diversity and Model Monoculture

The platform must support diversity across attack strategies and, when approved,
across attacker models. A Target must not be considered robust merely because it
resists attacks generated by one model family or one prompt template.

### 7.5 Broker Authority

The deterministic broker, not the Attacker model, owns:

- State transitions.
- Correlation and trace IDs.
- Allowed destinations.
- Tool dispatch and interception.
- Retry and timeout policies.
- Rate and token limits.
- Session history serialization.
- Safety stops and emergency cancellation.
- Confirmation that a policy oracle or judge result is valid.
- Final Assessment status.

---

## 8. Minimum Threat Coverage

The initial production threat catalog must cover, where applicable:

- Direct prompt injection.
- Indirect prompt injection.
- Jailbreak and instruction hierarchy manipulation.
- Agent goal hijacking.
- System prompt and topology disclosure.
- Sensitive information disclosure.
- Excessive agency and tool misuse.
- Tool parameter smuggling.
- Identity and privilege abuse.
- Improper output handling.
- Unexpected code or command execution.
- Memory and context poisoning.
- RAG, vector, and embedding weaknesses.
- Insecure inter-agent communication.
- MCP server and tool trust weaknesses.
- Agent and model supply-chain weaknesses.
- Data and model poisoning where the Target lifecycle permits testing.
- Unbounded token, request, memory, or tool consumption.
- Cascading failures in multi-step and multi-agent workflows.
- Human-agent trust exploitation.
- Cross-session persistence and poisoned state.
- Unsafe fallback behavior during provider, tool, or network failures.

Each threat scenario must identify applicability criteria. Non-applicable tests
must be recorded as not applicable rather than silently omitted or counted as a
pass.

---

## 9. Execution and Safety Architecture

### 9.1 Transport

The gateway roadmap remains:

- In-memory adapters for development and deterministic testing.
- HTTP/REST as the first remote Target transport.
- WebSocket for conversational streaming Targets.
- gRPC when a concrete Target requires it.

### 9.2 Action-Space Interception

For every observable tool attempt, the system must capture:

- Tool identity and version.
- Tool category.
- Arguments before redaction and a safe redacted audit representation.
- Caller role and authorization context.
- Intended destination.
- Interception or sandbox decision.
- Simulated result returned to the Target.
- Applicable policy rules and outcomes.

If a remote Target does not expose tool calls separately, its integration must
use an approved proxy, callback bus, instrumented adapter, or other defined
observation mechanism. Text-only observation must be explicitly marked as
reduced assurance.

### 9.3 Safety Requirements

- Mutating and administrative actions must never reach real unauthorized
  production destinations.
- Sandboxes and mocks must default to deny.
- Destination allowlists must be broker-enforced.
- Credentials must be referenced through a secret manager or isolated runtime
  configuration, never embedded in Target manifests.
- Persistent records must redact credentials, access tokens, personal data, and
  other configured secrets.
- Every run must support immediate cancellation and a global emergency stop.
- Safety-control failure must produce `HARNESS_ERROR` or
  `ASSESSMENT_INCONCLUSIVE`, never a pass.

---

## 10. Dual-Stage Verification

### 10.1 Stage 1: Deterministic Policy Oracles

Deterministic verification must run before semantic judging for exact
action-space constraints.

Rules must be scoped by:

- Tool identity and category.
- Caller role.
- Target environment.
- Data classification.
- Destination and resource.
- Parameter semantics.
- Assessment scenario.

Supported oracle types should include:

- JSON Schema validation.
- Allowlist and denylist policies.
- CIDR and network-range checks.
- SQL AST and mutation checks.
- Command and argument parsing.
- Identity and recipient validation.
- Role and authorization policy evaluation.
- Data-loss and honeytoken detection.
- Resource and budget limits.

### 10.2 Stage 2: Semantic Judge

The semantic judge must evaluate contextual behavior against a scenario-specific
rubric. It must use constrained structured output where supported and robust
parsing otherwise.

The judge output must contain:

- Verdict.
- Severity recommendation.
- Confidence.
- Evidence references.
- Concise auditable rationale.
- Applicable policy statements.
- Ambiguities or missing evidence.

The requirement in TRD-1 to formulate and persist step-by-step Chain-of-Thought
is superseded. SecMate must not request or store hidden Chain-of-Thought. It may
store a concise rationale that is suitable for audit and human review.

### 10.3 Conflict Handling

- A confirmed deterministic violation cannot be overturned solely by a semantic
  judge.
- Judge-only findings must record confidence and calibration metadata.
- Conflicting judges or malformed outputs must trigger retry, secondary review,
  or `ASSESSMENT_INCONCLUSIVE` according to policy.
- The system must distinguish no violation from insufficient evidence.

### 10.4 Calibration

Every approved judge configuration must be evaluated against a human-reviewed
gold set. Calibration must measure:

- False-positive rate.
- False-negative rate.
- Human/judge agreement.
- Severity agreement.
- Evidence-selection quality.
- Stability across repeated evaluations.
- Drift after provider or model-version changes.

Judge configuration changes require re-calibration before production use.

---

## 11. Repetition, Robustness, and Reproducibility

LLM behavior is probabilistic. Temperature zero does not guarantee identical
hosted-model output across time or infrastructure.

SecMate must distinguish:

- Exact input and configuration replay.
- Deterministic policy replay.
- Best-effort semantic re-evaluation.
- Reproduction against a pinned model snapshot, when available.

Scenarios must define a repetition policy. A single refusal or pass must not be
treated as proof of robustness when repeated trials are required.

Reports must state:

- Number of trials.
- Number of successful violations.
- Attack success rate.
- Confidence interval or other approved uncertainty representation when sample
  size permits.
- Target and attacker model versions.
- Judge configuration.
- Scenario and policy versions.

---

## 12. Finding and Evidence Requirements

Every Finding must include:

- Finding ID and version.
- Target identity and Target profile version.
- Assessment, session, scenario, and turn identifiers.
- Title and concise description.
- Expected policy or safe behavior.
- Observed behavior.
- Exact evidence references.
- Redacted probe and Target response.
- Tool call, arguments, and interception outcome where applicable.
- Deterministic oracle results.
- Semantic judge result and calibration metadata.
- Severity, confidence, and business impact.
- Preconditions and reproduction steps.
- Attack path or sequence of actions.
- Applicable framework mappings and versions.
- Recommended remediation.
- Owner, status, timestamps, and risk-acceptance metadata.
- Links to pinned regression cases.

Findings must not claim successful exploitation without evidence of the defined
success condition.

### 12.1 Finding Lifecycle

Initial statuses:

```text
OPEN
TRIAGED
IN_REMEDIATION
READY_FOR_RETEST
RESOLVED
ACCEPTED_RISK
FALSE_POSITIVE
```

Status changes must be auditable. Risk acceptance must have an owner, rationale,
approval, and expiry date.

---

## 13. Assessment Results and Advisory CI/CD

TRD-1's mandatory build-blocking quality-gate behavior is superseded.

SecMate must emit one of the following machine-readable results:

```text
PASS
PASS_WITH_WARNINGS
CRITICAL_RISK_DETECTED
ASSESSMENT_INCONCLUSIVE
HARNESS_ERROR
```

SecMate provides evidence and an advisory result. A consuming pipeline,
governance system, or Target team owns any blocking decision.

Recommended execution tiers:

| Stage | Required purpose |
| --- | --- |
| Pull request | Fast deterministic regression set and bounded smoke attacks |
| Nightly | Broader adaptive, indirect, and multi-turn coverage |
| Pre-release | Full target-specific campaign with approved budgets |
| Post-deployment | Non-destructive canary and drift checks |
| Manual investigation | Deep adaptive testing with operator oversight |

Machine-readable exports must include JSON first, followed by SARIF and JUnit
XML where applicable.

---

## 14. Frontend Architecture and Dashboard Requirements

### 14.1 Frontend-First Constraint

Frontend-first development is approved only when the UI consumes typed,
asynchronous service interfaces. Static values embedded directly in components
must not define the future backend contract.

The mock implementation must support:

- Loading states.
- Empty states.
- Error states.
- Stale-data indicators.
- Deterministic fixtures for tests.
- Replaceable adapters for future HTTP APIs.

### 14.2 Required Routes

The frontend must use bookmarkable routes:

```text
/dashboard
/targets
/assessments
/findings
/reports
```

### 14.3 Dashboard Visual Authority

The supplied AIDA executive-dashboard screenshots are the current dashboard
visual authority. The layout must retain:

- Four KPI cards.
- Assessment posture trend.
- Severity mix.
- Target risk overview.
- Recent activity.

### 14.4 Dashboard Terminology and Metrics

- `Agents onboarded` is superseded by `Targets onboarded`.
- `View agents` is superseded by `View targets`.
- `Blocked releases` is superseded by `Critical findings`.
- Attacker details must not be presented as onboarded Target inventory.
- Detailed attacker planning belongs in Assessment and Finding views.
- Reports must summarize the evidence and outcomes without exposing secrets.

### 14.5 Dashboard Interactions

The dashboard milestone must implement:

- Date-range filtering that updates all dependent dashboard data consistently.
- Real module routes.
- Search across Targets, Assessments, and Findings.
- A functional notification panel backed by mock services.
- Responsive desktop and mobile behavior.
- Accessible charts, controls, keyboard operation, and status semantics.

The full New Assessment workflow is deferred from this dashboard milestone. The
button may navigate to the Assessments route until that workflow is specified.

---

## 15. Data and API Design Principles

- All major contracts must use valid JSON Schema Draft 2020-12, not illustrative
  pseudo-schema values.
- API contracts must be versioned.
- Historical Assessments must retain the schema and taxonomy versions used at
  execution time.
- Credentials must use opaque secret references.
- All timestamps must be unambiguous and include timezone information.
- IDs must remain stable across exports.
- Audit data must be append-oriented and tamper-evident.
- Sensitive data must be classified and redacted according to policy.
- Target, scenario, policy, attacker, and judge versions must be first-class
  fields.

The following core resources are required:

```text
Target
TargetProfileVersion
ToolDefinition
PolicyRule
ThreatScenario
AttackPlan
Assessment
Session
Turn
ToolAttempt
OracleResult
JudgeResult
Finding
RegressionCase
AuditBundle
Report
Notification
```

---

## 16. Detailed Analysis Quality

The requirement that SecMate produce detailed and relevant analysis must be
measurable.

Every reported Finding must answer:

1. What policy or boundary was expected?
2. What exactly did the Target do?
3. What evidence proves the behavior?
4. Was a side effect attempted, intercepted, simulated, or completed?
5. Why does the behavior matter to Paramount?
6. How severe and reproducible is it?
7. Which standards and internal policies apply?
8. How can the Target team reproduce and remediate it?
9. Which regression test will verify the fix?

Verbose output without these elements is not considered detailed analysis.

---

## 17. Quality Metrics and Readiness Gates

Before a controlled internal pilot, the AI team must approve explicit numeric
thresholds for the following metrics:

- Threat coverage by applicable Target capability.
- Evidence completeness rate.
- Finding reproduction success rate.
- Human/judge verdict agreement.
- Human/judge severity agreement.
- False-positive rate.
- False-negative rate on the gold set.
- Duplicate-finding rate.
- Percentage of Findings with actionable remediation.
- Attack success rate by scenario and Target version.
- Assessment completion and inconclusive rates.
- Harness error rate.
- Sandbox escape or unauthorized-dispatch count, which must be zero.
- Credential leakage into persistent audit records, which must be zero.
- Median and tail latency by assessment tier.
- Token and monetary cost by completed Assessment.

Until numeric thresholds are approved, SecMate may be demonstrated but must not
be represented as a calibrated production assurance control.

---

## 18. First End-to-End Vertical Slice

After the executive dashboard milestone, implementation priority must shift to a
complete SOCMate vertical slice.

The slice must:

1. Onboard a simulated SOCMate Target.
2. Define its tools, role tiers, sensitive data, and prohibited actions.
3. Validate and version its Target profile.
4. Produce a structured threat model and attack plan.
5. Select applicable scenarios and standards mappings.
6. Execute at least one bounded multi-turn attack.
7. Intercept at least one simulated unsafe tool attempt.
8. Apply a tool-scoped deterministic policy oracle.
9. Produce a structured semantic judge result.
10. Generate a complete evidence-backed Finding.
11. Pin the Finding as a regression case.
12. Reflect the result in the dashboard, Assessment view, and Finding view.
13. Export the advisory result as JSON.
14. Demonstrate that no real destructive side effect or credential is retained.

The slice is accepted only when another authorized engineer can reproduce the
Finding from the audit bundle without relying on undocumented knowledge.

---

## 19. Operational Requirements

Before pilot use, SecMate requires:

- Enterprise identity integration.
- Role-based authorization.
- Project or engagement isolation.
- Secrets-manager integration.
- Audit retention and deletion policy.
- Provider and model allowlists.
- Egress restrictions.
- Redaction rules for judge inputs and persistent evidence.
- Emergency stop and incident-response procedures.
- Model and provider quota monitoring.
- Queue and worker health monitoring.
- Backup and recovery requirements.
- Judge drift and calibration monitoring.
- Human escalation paths for inconclusive or high-impact findings.

Availability, concurrency, retention, recovery, and throughput targets remain
open requirements and must be finalized before Phase 5.

---

## 20. Decision Log

| ID | Decision | Rationale | Supersedes or refines |
| --- | --- | --- | --- |
| D-001 | SecMate is an internal AI-agent assurance platform | Prevents scope drift into general pentesting | Clarifies TRD-1 scope |
| D-002 | Use Target for the AI agent under test | Distinguishes business agents from the Attacker | Frontend `Agents` terminology |
| D-003 | Use Attacker for SecMate's adversarial subsystem | Establishes an explicit adversarial role | Adds to TRD-1 terminology |
| D-004 | Attacks must begin with structured Target intelligence and planning | Target conditioning alone is not sufficient for smart attacks | Refines synthesis engine |
| D-005 | Use multiple attack-generation methods | Reduces static coverage and model-monoculture weaknesses | Refines refusal-resistant fuzzing |
| D-006 | Deterministic broker retains orchestration and safety authority | LLMs must not control durable or destructive operations | Retains and strengthens TRD-1 broker pattern |
| D-007 | Do not request or persist hidden Chain-of-Thought | Store concise evidence-based rationale instead | Supersedes TRD-1 CoT requirement |
| D-008 | CI/CD outcomes are advisory | Existing governance owns release decisions | Supersedes mandatory build blocking |
| D-009 | Frontend-first work must use typed mock service contracts | Allows later API replacement without UI redesign | Adds implementation constraint |
| D-010 | Dashboard screenshots are the visual authority | Preserves the approved AIDA executive experience | Clarifies concept-image priority |
| D-011 | Replace Blocked releases with Critical findings | SecMate reports risk rather than claiming release authority | Dashboard metric change |
| D-012 | Standards mappings must be versioned data | Framework identifiers change over time | Corrects static taxonomy assumptions |
| D-013 | Finish the dashboard, then build a SOCMate vertical slice | Prevents extended frontend work without validating the security engine | Refines implementation sequence |
| D-014 | Frontend services must be resource-oriented before HTTP integration | Aggregate browser state prevents independent loading, pagination, authorization, and failure handling | Refines D-009 typed mock services |
| D-015 | Frontend contracts must represent the complete asynchronous Assessment lifecycle | A real broker and worker cannot complete generation, execution, verification, findings, and reports in one synchronous request | Refines Sections 7, 9, 13, and 18 |
| D-016 | Zero or unsupported scenario coverage must fail closed | Missing coverage is insufficient evidence and must never produce PASS | Strengthens Sections 8, 10, 13, and 18 |
| D-017 | Background synchronization must be silent, adaptive, and state-aware | Fixed polling caused layout movement and unnecessary rerenders after no active work remained | Refines Section 14 frontend-state requirements |
| D-018 | Detail views must be addressable by stable resource identifiers | Search, notifications, refresh, and collaboration require exact-record navigation | Refines Section 14 dashboard interactions and Section 15 stable IDs |
| D-019 | Settings and Profile are frontend preference surfaces until enterprise identity is approved | Local appearance, demo reset, and time zone may work without implying SSO, RBAC, or backend governance | Preserves Section 19 operational deferrals |
| D-020 | Contract-sensitive frontend behavior requires automated tests before adapter replacement | Lifecycle, fail-closed, navigation, and synchronization regressions would otherwise appear during backend integration | Adds implementation readiness gate |
| D-021 | Approve a server-side model-connectivity PoC before DeepTeam methodology integration | Provider authentication, schema output, tool calling, quotas, and frontend diagnostics must be proven independently from attack orchestration | Narrowly supersedes the provider-call deferral in Section 25.9; does not approve Assessment execution or production architecture |

All future architecture and product decisions must be added to the latest TRD's
decision log with rationale and predecessor impact.

---

## 21. TRD-1 to TRD-2 Traceability

| TRD-1 area | TRD-2 treatment |
| --- | --- |
| Internal AI-agent security platform | Retained and narrowed explicitly |
| Action-space primacy | Retained and strengthened |
| Declarative manifests | Retained; valid schemas and versioning required |
| Dynamic adversarial synthesis | Expanded into profiling, planning, generation, observation, and refinement |
| Dual-stage verification | Retained; conflict handling and calibration added |
| Chain-of-Thought judge | Superseded by concise auditable rationale |
| Stateless broker | Retained; broker authority made explicit |
| Multi-turn execution | Retained; applicability, repetition, and stopping requirements added |
| Tool interception and mock bus | Retained; remote observation and emergency-stop requirements added |
| Immutable telemetry | Retained; redaction, evidence completeness, and tamper evidence strengthened |
| Static standards IDs | Superseded by versioned mappings and crosswalks |
| Mandatory CI/CD build block | Superseded by advisory machine-readable outcomes |
| Frontend concept direction | Refined to the approved dashboard screenshots and Target terminology |
| Missing availability and scale targets | Still open; must be resolved before pilot |

---

## 22. Historical Instructions For TRD-3

The later TRD-3 followed this required reading and traceability direction. These
instructions are retained to explain its authority:

1. Read [TRD-1.md](./TRD-1.md) first to understand the original architecture and
   rationale.
2. Read this TRD-2 second to understand the formal review and upgraded
   requirements.
3. Read
   [TRD-2A-FRONTEND-IMPLEMENTATION.md](./TRD-2A-FRONTEND-IMPLEMENTATION.md)
   to understand the frontend implementation boundary.
4. Read
   [TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md](./TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md)
   to understand the model-connectivity PoC, DeepTeam compatibility findings,
   unresolved architecture benchmark, and next-agent sequence.
5. Inspect the implementation, test results, calibration evidence, and decision
   log produced after TRD-2B.
6. Create a requirement-by-requirement traceability table.
7. Mark each earlier requirement as retained, refined, superseded, rejected, or
   deferred.
8. Explain why every material change is necessary.
9. Preserve historical framework versions for completed Assessments while
   adopting approved current standards for new Assessments.
10. Base readiness claims on measured evidence rather than frontend completion,
    provider connectivity, synthetic handoff behavior, or architectural intent.

TRD-3 does not rewrite these documents; it records the later fixed synthetic PoC
architecture and leaves pilot and production gates open.

---

## 23. Approval State At The TRD-2 Review

Approved for continuation:

- Executive dashboard completion.
- Typed mock-service contracts.
- Real frontend routing, search, notifications, and date filtering.
- Data-contract and threat-catalog design.
- SOCMate vertical-slice implementation after the dashboard milestone.

Not yet approved:

- Production CI/CD reliance.
- Unsupervised destructive testing.
- Company-wide rollout.
- Claims of comprehensive standards coverage.
- Claims of calibrated finding accuracy.

The next formal review must evaluate working evidence from the SOCMate vertical
slice against Sections 17 and 18.

---

## 24. Interim Implementation Continuation

The implementation state and frontend-first review boundary established after
this document are recorded in
[TRD-2A-FRONTEND-IMPLEMENTATION.md](./TRD-2A-FRONTEND-IMPLEMENTATION.md).
The subsequent model-connectivity, synthetic brokered-handoff, and DeepTeam PoC
checkpoint is recorded in
[TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md](./TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md).

TRD-2A is an interim bridge, not an authoritative TRD-3 and not evidence of
management approval. It records:

- The complete frontend mock implementation produced for management review.
- Traceability from TRD-1 and TRD-2 requirements to frontend representation.
- The distinction between simulated frontend evidence and unimplemented backend
  security controls.
- The current decision to defer backend, model integration, prompt formulation,
  and harness implementation until the frontend review is completed.
- File-level and sequencing guidance for future coding agents.

The later TRD-3 reads TRD-1, TRD-2, TRD-2A, and TRD-2B and evaluates measured
implementation evidence. It does not treat frontend completion, provider
connectivity, or one synthetic worker run as proof that Sections 17 and 18 have
passed.

---

## 25. Frontend Implementation Review Addendum

> **Addendum date:** 2026-09-26
>
> **Reviewed branch:** `Ashwin`
>
> **Reviewed implementation:** commit `e6ccbe2`
>
> **Status:** Frontend implementation evidence pending management workflow and
> visual approval. This addendum does not approve backend architecture, live
> model integration, enterprise identity, production assurance, or pilot use.

### 25.1 Purpose

This addendum records the frontend implementation and review evidence produced
after the original TRD-2 review. It preserves all earlier requirements and does
not replace TRD-2A. TRD-2A remains the detailed frontend implementation bridge
and is updated alongside this addendum.

The work completed on `Ashwin` converted the frontend from a mostly synchronous
demo workflow into a backend-compatible review prototype. The frontend still
uses deterministic local fixtures and does not execute a real assessment.

### 25.2 Current Frontend Surfaces

The buildable React/Vite application now provides:

- `/login`: compact local-preview sign-in with asynchronous submission state,
  validation, neutral SSO-unavailable messaging, and responsive presentation.
- `/dashboard`: executive posture projection with KPI cards, date range,
  Assessment activity, severity mix, risk-prioritized Targets, recent activity,
  loading, empty, error, stale, and retry states.
- `/targets`: resource-specific Target loading, empty/error handling, draft
  creation, validation before readiness, details, and exact-record links.
- `/assessments`: fail-closed scenario validation, prerequisite checks,
  resource-specific loading, lifecycle status, progress, cancellation, pending
  outcomes, final outcomes, and exact-record links.
- `/findings`: severity filtering, governed lifecycle transitions, mutation
  errors, regression pinning, standards mappings, evidence details, and exact
  record links.
- `/reports`: report selection, exact-record links, guarded JSON export, print
  projection, report status, and not-found handling.
- `/settings`: Windows-style category navigation with Overview, Profile,
  Appearance, Demo workspace, and planned enterprise control sections.

Shared shell behavior includes search, notifications, responsive navigation,
theme selection, account actions, keyboard focus handling, and deterministic
demo reset.

### 25.3 Frontend Assessment Lifecycle Contract

The mock frontend now represents the lifecycle expected from a future broker and
worker boundary:

```text
DRAFT
VALIDATING
QUEUED
PLANNING
RUNNING
VERIFYING
FINALIZING
CANCEL_REQUESTED
CANCELLED
COMPLETED
FAILED
TIMED_OUT
```

The advisory result is nullable until terminal completion and supports:

```text
PASS
PASS_WITH_WARNINGS
CRITICAL_RISK_DETECTED
ASSESSMENT_INCONCLUSIVE
HARNESS_ERROR
```

Frontend invariants:

- Zero scenarios are rejected.
- Unsupported scenario identifiers are rejected.
- Assessment names, approved budgets, turn limits, ready Targets, Attacker
  profiles, and Judge profiles are validated before creation.
- Findings and Reports are created only after simulated terminal completion.
- Cancellation is represented as a request followed by safe terminal
  acknowledgement.
- No frontend state claims that a real Target, Attacker, Judge, tool, or backend
  was executed.

### 25.4 Resource Service Boundary

The frontend modules no longer consume one aggregate `PlatformState` query.
They use resource-specific asynchronous mock methods for Targets, model
profiles, Assessments, Findings, and Reports.

The future HTTP adapter should preserve these conceptual operations:

```text
targets.list / targets.get / targets.create / targets.createVersion
modelProfiles.listApproved
assessments.list / assessments.get / assessments.create / assessments.cancel
findings.list / findings.get / findings.transition
reports.list / reports.get / reports.requestExport
dashboard.getProjection
notifications.list / notifications.markRead
```

The existing local adapter is a deterministic review implementation, not the
approved backend persistence contract.

### 25.5 Synchronization and Stability

Background data synchronization is intentionally silent and state-aware:

- Target polling runs only while a Target is validating.
- Assessment polling runs only while an Assessment is active.
- Report polling runs only while an Assessment or Report is active.
- Findings and Reports receive one quiet refresh when terminal artifacts become
  available.
- Polling pauses when the browser tab is hidden.
- Duplicate requests are coalesced.
- Stale responses are ignored.
- Unchanged data does not update React state.
- Background synchronization does not insert a visible refresh banner or alter
  page layout.

These behaviors are frontend implementation requirements for the future HTTP
adapter and must not be regressed.

### 25.6 Settings, Profile, and Themes

The approved frontend review presets are:

- White
- SecMate Dark
- Blue Cyber

Settings uses a desktop category rail and mobile category selector. Only the
selected category is rendered, and sections are addressable through
`/settings?section=<id>`.

Functional local preferences:

- Theme selection under `secmate.theme`.
- Profile time zone under `secmate.profile.timezone`.
- Deterministic demo reset under `secmate.demo.platform.v1`.

The Profile section displays the current preview session name, account value,
role, identity source, and time zone. It explicitly states that enterprise SSO,
role assignment, and access governance remain future Paramount IT decisions.

### 25.7 Accessibility and Navigation Evidence

Implemented frontend behavior includes:

- Accessible names for mobile navigation.
- Keyboard-operable Assessment and Finding record controls.
- Exact-record query links from search and notifications.
- Explicit not-found states for invalid Target, Assessment, Finding, and Report
  links.
- Dialog initial focus, focus wrapping, Escape handling, backdrop handling, and
  focus restoration.
- Search error handling, stale-response protection, and focus restoration.
- Responsive long-text wrapping and truncation where appropriate.

Accessibility requires continued browser and assistive-technology review before
pilot approval.

### 25.8 Automated Verification

The frontend now includes Vitest, Testing Library, jsdom, and jest-dom support.

As of commit `e6ccbe2`:

- 16 frontend behavior tests pass.
- `npm run build` passes TypeScript compilation and the production Vite build.
- The development server runs on port `5173`.
- Login and all protected route entry points return successfully through Vite.

Current tests cover:

- Local-preview login validation and SSO notice behavior.
- Fail-closed Target and Assessment validation.
- Assessment lifecycle completion and cancellation.
- Stable records within unchanged lifecycle stages.
- Invalid Report links.
- Inactive polling termination and refresh-banner regression.
- Settings default, direct links, single-section rendering, Profile identity,
  and time-zone persistence.

### 25.9 Remaining Approval Boundary

Approved for continued frontend and contract work after management review:

- Frontend QA and requested workflow corrections.
- Valid JSON Schema and OpenAPI design.
- Resource API contract design.
- HTTP adapter planning while retaining the mock adapter.
- SOCMate vertical-slice design.

Explicitly approved scoped PoC exception before the broader management gate:

- A local FastAPI model-connectivity API under `apps/api`.
- Temporary Groq and OpenRouter calls using harmless synthetic prompts.
- Frontend Settings checks for Attacker, Attack Critic, Outcome Judge, and
  synthetic Target responsiveness.

This exception is limited to connectivity diagnostics and the harmless
synthetic handoff recorded in TRD-2A and TRD-2B. It does not approve Assessment
execution, persistence, a queue or worker architecture, or production use.

Still not approved beyond connectivity testing:

- DeepTeam attack execution or adaptive assessment orchestration.
- Attack prompt formulation or prompt storage beyond harmless connectivity
  fixtures.
- Provider endpoints, API keys, or credentials in the browser.
- Backend framework, persistence, queue, worker, secret manager, or deployment
  selection without architecture review.
- Claims that the frontend mock is security evidence.
- Claims of calibrated Judge accuracy.
- Production CI/CD reliance, release authority, or company-wide rollout.

### 25.10 Required Next Sequence

After management approves the frontend workflow:

1. Define versioned schemas for Target, TargetProfileVersion, ToolDefinition,
   ModelProfile, ThreatScenario, Assessment, Finding, Report, and standards
   mappings.
2. Define API operations, error envelopes, pagination, filtering, optimistic
   concurrency, and timestamp rules.
3. Separate presentation DTOs from immutable audit and execution contracts.
4. Select the control API, persistence, queue, worker, secret-management, and
   deployment architecture.
5. Implement one controlled SOCMate vertical slice with an in-memory Target and
   mock action bus.
6. Preserve the frontend lifecycle, fail-closed, advisory, redaction, and
   synchronization invariants recorded in this addendum.
7. Add enterprise identity and role enforcement only after the vertical-slice
   contract and isolation behavior are proven.

Frontend completion remains implementation evidence, not proof that Sections 17
or 18 have passed. The later TRD-3 implementation checkpoint does not close
those pilot and production gates; measured isolation, reproduction, calibration,
and operational evidence are still required.

## 26. 28 September 2026 Decision Addendum

### D-022: Fixed Synthetic DeepTeam PoC And TRD-3

Management frontend approval was confirmed, and the user authorized continued
backend integration plus creation of TRD-3 on 2026-09-28. This explicit decision
supersedes the earlier timing instruction that reserved the TRD-3 name for a
post-pilot document; it does not supersede the pilot evidence requirements. The
implementation
evidence after Section 25 includes an isolated Python 3.11 worker, pinned
DeepTeam execution, one synthetic Target Gateway, one deterministic policy
oracle, provisional Architecture B Target evaluation, local FastAPI dispatch,
frontend polling, and redacted synthetic audit retrieval.

The approved scope is limited to the fixed synthetic PoC recorded in
[TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md).
This decision does not approve real Targets, general Assessments, production
providers, calibrated assurance, release blocking, pilot rollout, or company-wide
deployment. Sections 17 and 18 remain open.
