# SecMate Technical Requirements Document 2A

> **Current frozen implementation:** [TRD-4](./TRD-4.md). Preserve this dated frontend rationale; do not reapply its pre-backend restrictions or old UI controls as current instructions.

## Frontend Implementation Continuation and Agent Handoff

> **Document status:** Historical frontend implementation snapshot; management
> review is complete. Architecture continuation is recorded in TRD-3 and current
> implementation status is recorded in [TRD-4](./TRD-4.md).
>
> **Predecessors:** [TRD-1.md](./TRD-1.md) and [TRD-2.md](./TRD-2.md)
>
> **Successor implementation checkpoint:**
> [TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md](./TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md)
>
> **Architecture successor:**
> [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md)
>
> **Development stage represented here:** Frontend review prototype before
> DeepTeam worker integration
>
> This document is retained for frontend rationale and traceability. Its
> deferred-work lists are not a current capability inventory. Do not use it to
> infer that worker, gateway, policy, or Judge code is still absent.
>
> **Current engineering handoff:** [TRD-4](./TRD-4.md). This document remains
> a historical frontend implementation snapshot.

## 1. Lineage, Status, and Authority

TRD-2A is the implementation bridge between the approved requirements history
and the current frontend prototype:

1. [TRD-1.md](./TRD-1.md) records the original architecture, action-space
   security thesis, declarative manifests, dual-stage verification, and broker
   pattern.
2. [TRD-2.md](./TRD-2.md) reviews and refines TRD-1, establishes authoritative
   terminology, corrects earlier assumptions, defines frontend requirements,
   and sets future implementation gates.
3. This TRD-2A records how those requirements are represented in the frontend
   review prototype and what must remain deferred until management approval.
4. [TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md](./TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md)
   records the later live model-connectivity PoC, synthetic brokered handoff,
   DeepTeam compatibility review, unresolved evaluation architecture, and
   next-agent implementation sequence.
5. [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md)
   later reads all four documents and records measured worker evidence. Neither
   TRD-2A nor TRD-2B substitutes for pilot, calibration, or production evidence.

This document does not supersede TRD-1 or TRD-2 and must not be cited as
management approval. If it conflicts with TRD-2, TRD-2 remains authoritative.
Requirements not discussed here retain their TRD-1/TRD-2 status.

Development boundary at this frontend snapshot:

- Build the complete frontend with typed asynchronous mock services.
- Use locally persisted deterministic demo data for manager review.
- Show model-selection concepts as clearly labeled demo configuration only.
- Keep the same visible capabilities for the three prototype user roles until a
  role and authorization matrix is reviewed.
- Do not implement live model calls, prompts, credentials, Target connections,
  orchestration, test-harness execution, or backend persistence before frontend
  approval.

## 2. Product Boundary

SecMate has three model roles and three human user roles. They are separate
concepts and must not be combined in authorization or audit records.

Model roles:

- **Target model:** The model used by the AI-agent product under assessment.
- **Attacker model:** A model used to propose target-specific attack strategies
  and probes under broker-controlled budgets and safety constraints.
- **Judge model:** A calibrated model used only for contextual evaluation after
  deterministic policy oracles have run.

Potential future human-role boundaries, pending management and identity review:

- **Security Lead:** Configures assessments and selects approved Attacker and
  Judge profiles within policy limits.
- **AI Product Owner:** Onboards owned Targets, maintains Target profiles, and
  requests or reviews assessments.
- **Executive Viewer:** Reads posture, findings, and reports without changing
  execution or model configuration.

The orchestration broker, safety controls, policy oracles, budgets, retries,
tool dispatch, and final Assessment state are deterministic application
services. They are not a fourth model role and must never be controlled by an
LLM.

The current frontend does not enforce these role differences.

## 3. Non-Binding Backend Repository Proposal

The only current decision is that a future test harness must not run in the
browser or inside React components. The following repository shape is a
non-binding discussion proposal for the post-frontend architecture review:

```text
apps/
  web/                    React operator console
  cli/                    Headless advisory assessment runner
services/
  control-api/            Authentication, resources, workflow, and query API
  harness-worker/         Isolated assessment execution workers
packages/
  contracts/              JSON Schemas, API types, status enums, fixtures
  harness-core/           Broker state machine and execution interfaces
  policy-oracles/         Deterministic tool-scoped verification
  provider-adapters/      Attacker, Judge, and Target transport adapters
  report-serializers/     JSON, SARIF, JUnit, and report projections
infra/
  local/                  Local queue, database, mock bus, and sandbox setup
  deployment/             Controlled internal deployment definitions
```

The backend language, framework, service boundaries, database, queue, and
deployment model remain unapproved. Python may be evaluated after frontend
approval, but this draft does not select it. Contracts should remain
language-neutral JSON Schema so backend evaluation does not require redesigning
the approved frontend domain model.

## 4. Draft Model Registry and Selection Concept

### Approved Model Profiles

For frontend review, model profiles are deterministic mock records. Azure
OpenAI model and deployment names are realistic examples only and do not imply
provider, security, architecture, procurement, or production approval.

If this approach is later approved, users should not enter arbitrary provider
URLs, API keys, prompts, or model names when launching an Assessment.
Administrators would maintain an approved model registry, and Assessments would
reference immutable profile versions.

Each model profile should contain:

```text
profile ID and version
role: attacker | judge | target_simulator
provider and model identifier
deployment or region reference
capability flags
approved data classifications
structured-output support
context and output limits
rate and cost limits
default and permitted runtime parameters
secret reference, never a credential value
calibration status for Judge profiles
approval status and expiry
```

### Attacker Model

Selection location:

- Primary selection in the New Assessment workflow under an Advanced section.
- Defaults from an organization or Target-specific assessment policy.
- Full profile management in a future Governance and Model Registry area.

Customization:

- Operators may select an approved Attacker profile and strategy mix.
- Operators may adjust turn, token, request, time, and cost budgets within
  broker-enforced limits.
- Operators may select attack diversity and repetition policies.
- Raw system-prompt editing, unapproved providers, and unrestricted endpoints
  are not normal per-run controls.
- Security Leads may create draft strategy templates, but approval and
  versioning are required before shared use.

### Target Model

Selection location:

- Target runtime and disclosed model metadata belong in the Target profile.
- A real black-box or grey-box Target is connected through its transport; SecMate
  does not replace its production model for an Assessment.
- Model selection is available only for simulated Targets such as the first
  SOCMate vertical slice.

Customization:

- Product Owners maintain disclosed provider, family, version, runtime, tools,
  roles, and guardrails as versioned Target metadata.
- Secrets are opaque references managed outside the Target manifest.
- Assessment operators may select a Target profile version and approved
  environment, not silently rewrite the Target's model configuration.

### Judge Model

Selection location:

- Judge profile selection appears in New Assessment after scenario selection.
- The UI displays calibration status, supported data classification, last
  calibration date, and profile version.
- Judge registry administration belongs in Governance and Model Registry, not
  on the dashboard.

Customization:

- Only calibrated, approved Judge profiles may produce an operational verdict.
- Temperature and structured-output behavior are profile-controlled rather than
  freely editable per run.
- Scenario rubrics and concise-rationale schemas are versioned contracts.
- Security Leads may choose among approved Judge profiles.
- Product Owners may view the selected profile and request review, but should
  not tune a Judge to alter an active finding.
- Executive Viewers may see provenance and calibration status only.

## 5. Delivery Sequence

### Milestone 1: Complete Frontend Review Prototype

Complete all five TRD-2 routes before backend implementation:

- `/dashboard`: posture, filtering, search, notifications, and frontend states.
- `/targets`: multiple AI-agent Targets, profile details, and onboarding.
- `/assessments`: Target, scenario, budget, Attacker, and Judge selection.
- `/findings`: evidence, severity, lifecycle, remediation, and regression pinning.
- `/reports`: executive evidence projection and demo JSON export.

All workflows use typed asynchronous mock services and locally persisted,
versioned demo fixtures. The model profiles and assessment outcomes are
simulations and must be labeled accordingly.

### Milestone 2: Management Frontend Approval Gate

Review the connected frontend with product, AI engineering, security, platform,
and management stakeholders. Record:

- Approved navigation, terminology, workflows, information hierarchy, and
  responsive behavior.
- Changes requested for Target onboarding, model-selection presentation,
  findings, reports, and executive posture.
- Whether and how human roles should differ.
- Which backend concepts are approved, rejected, or still unresolved.

No backend implementation starts until the frontend review outcome is recorded.
Section 11 later records an explicit narrow exception for the `apps/api`
model-connectivity diagnostics service. That exception does not approve an
Assessment backend, persistence, queue, worker, or production architecture.

### Milestone 3: Post-Approval Contracts and Architecture

After frontend approval, define valid versioned schemas for Target profiles,
tools, policies, scenarios, model profiles, attack plans, Assessments, evidence,
Findings, audit bundles, notifications, and reports. Then review API boundaries,
authorization, redaction, state transitions, backend language, persistence,
queueing, secrets, and deployment choices.

Replace frontend mocks only after the contracts and adapter boundaries are
approved.

### Milestone 4: SOCMate Harness Vertical Slice

After architecture approval, implement one controlled SOCMate flow:

1. Load immutable Target, scenario, model, and policy versions.
2. Produce a structured threat model and attack plan.
3. Generate a bounded adversarial probe.
4. Send it through an in-memory Target adapter.
5. Intercept an unsafe simulated tool attempt in the mock action bus.
6. Run the applicable deterministic policy oracle.
7. Run the selected calibrated Judge profile.
8. Resolve conflicts according to TRD-2.
9. Persist a redacted audit bundle and advisory result.
10. Support cancellation, timeout, inconclusive, and harness-error states.

Do not add remote destructive transports until this slice proves isolation,
reproduction, and zero credential retention.

### Milestone 5: Backend-Connected Findings, Reports, and Regression

Replace simulated frontend evidence with persisted harness evidence. Add finding
reproduction, risk acceptance, regression replay, canonical JSON, then SARIF and
JUnit where meaningful. SecMate remains advisory; external governance decides
whether to block a release.

### Milestone 6: Remote Targets and Controlled Pilot

Add HTTP/REST first, then WebSocket only when required. Add queues, scheduling,
concurrency controls, secrets-manager integration, enterprise identity, audit
retention, emergency stop, provider monitoring, and calibration monitoring
before a controlled internal pilot.

## 6. Customization Guardrails

SecMate should be customizable through versioned data, not arbitrary code or
per-run prompt editing.

Highly customizable:

- Target profiles, tools, roles, data boundaries, and approved environments.
- Threat scenarios, applicability rules, standards mappings, and attack recipes.
- Deterministic policy rules and expected safe behavior.
- Assessment strategy mix, repetition policy, and budgets within hard limits.
- Report audience and redacted presentation templates.

Restricted customization:

- Provider endpoints and credentials.
- Broker state transitions and safety decisions.
- Destination allowlists and sandbox routing.
- Judge output schema and calibrated runtime parameters.
- Global maximum budgets and emergency controls.
- Audit redaction and credential-handling rules.

Every executable configuration must be versioned, attributable, reviewable, and
recorded in the Assessment audit bundle.

## 7. Near-Term Decisions Required Before Harness Work

- Backend language and framework.
- Database, queue, and object/audit storage.
- Enterprise identity provider and concrete role matrix.
- Secret manager and provider credential ownership.
- Initial approved Attacker and Judge providers.
- Judge gold set and calibration thresholds.
- SOCMate tool schemas, role tiers, prohibited outcomes, and mock responses.
- Audit retention, sensitive-data classification, and redaction policy.
- Maximum per-run budgets and emergency-stop ownership.
- Local sandbox and mock action bus isolation design.

## 8. TRD-1 and TRD-2 Implementation Traceability

This table describes the implementation state at commit `e6ccbe2`. `Frontend represented`
means the workflow or information is visible through deterministic mock data; it
does not mean the underlying security control exists.

| Requirement lineage | TRD-2A treatment | Current state |
| --- | --- | --- |
| TRD-1 action-space primacy | Preserve tool attempts, interception outcomes, and policy evidence as first-class frontend concepts | Frontend represented; harness deferred |
| TRD-1 declarative manifests | Represent Targets through structured, versioned profile data rather than page-specific values | Mock Target profiles implemented; valid JSON Schemas deferred |
| TRD-1 refusal-resistant adversarial synthesis | Expose scenario and Attacker-profile selection without implementing prompt generation | Frontend represented; prompts and live generation deferred |
| TRD-1 dual-stage verification | Show deterministic oracle evidence separately from semantic Judge rationale | Mock evidence implemented; real oracles and Judge calls deferred |
| TRD-1 stateless broker pattern | Keep durable orchestration out of React and reserve it for a deterministic backend service | Architectural boundary retained; broker deferred |
| TRD-1 bounded multi-turn execution | Expose a one-to-five-turn Assessment budget | Frontend configuration implemented; execution deferred |
| TRD-1 immutable telemetry | Show Assessment IDs, Target versions, model profiles, evidence, and report provenance | Locally persisted demo records implemented; tamper-evident audit deferred |
| TRD-1 zero credential retention | Do not collect provider endpoints, API keys, Target credentials, or live secrets in the frontend | Retained in current frontend |
| TRD-2 Target terminology | Use `Target` for assessable AI agents and separate it from the Attacker | Implemented |
| TRD-2 advisory CI/CD | Use advisory result labels and avoid claiming that SecMate blocks releases | Implemented in frontend copy and statuses |
| TRD-2 typed frontend mocks | Consume typed asynchronous resource interfaces with deterministic fixtures and replaceable adapters | Implemented in `dashboardService.ts` and resource-specific `platformService.ts` methods; HTTP adapter deferred |
| TRD-2 required routes | Provide `/dashboard`, `/targets`, `/assessments`, `/findings`, and `/reports` | Implemented |
| TRD-2 dashboard interactions | Provide date filtering, exact-record search and notification links, responsive behavior, and frontend states | Implemented with record-derived dashboard projection and stale/error handling |
| TRD-2 Target intelligence | Represent ownership, criticality, environment, model metadata, tools, guardrails, and data classifications | Frontend represented; full schema deferred |
| TRD-2 model provenance | Display Attacker and Judge profile identity with explicit demo status | Implemented as Azure OpenAI demo fixtures; approval and integration deferred |
| TRD-2 Finding evidence | Present expected behavior, observed behavior, tool attempt, oracle result, Judge rationale, standards, remediation, governed status transitions, and regression pinning | Implemented with mock evidence; typed audit resources deferred |
| TRD-2 reports | Present advisory summaries, report status, guarded demo JSON export, and print projection | Frontend implemented; canonical backend audit, SARIF, and JUnit deferred |
| TRD-2 role-aware operation | Preserve identity and role provenance without claiming authorization enforcement | Local preview session implemented; enterprise identity and differentiated permissions deferred |
| TRD-2 SOCMate vertical slice | Do not claim frontend simulation as the accepted vertical slice | Not implemented; requires post-approval backend evidence |
| TRD-2 Assessment execution states | Represent asynchronous broker and worker progress without claiming live execution | Implemented as deterministic mock lifecycle with progress, cancellation, terminal outcomes, and fail-closed validation |
| TRD-2 fail-closed outcomes | Reject missing or unsupported coverage and represent inconclusive or harness-error outcomes | Implemented in frontend contracts and mock service validation |
| TRD-2 loading and stale behavior | Support independent resource loading, empty, error, retry, background update, and stale-data states | Implemented; background polling is silent and state-aware |
| TRD-2 settings and governance concepts | Present approved local preferences separately from future enterprise controls | `/settings` implemented with Overview, Profile, Appearance, Demo workspace, and planned control categories |
| Frontend verification | Protect contract-sensitive behavior before HTTP adapter replacement | Vitest and Testing Library implemented with 16 passing tests as of `e6ccbe2` |

## 9. Frontend Implementation Record At `e6ccbe2`

As of commit `e6ccbe2` on branch `Ashwin`, the review prototype contains a
backend-compatible frontend simulation while remaining entirely local and
deterministic.

### 9.1 File Map

- `apps/web/src/App.tsx`: authentication routing, protected application shell,
  dashboard, global search, exact-record notifications, account menu, responsive
  navigation, theme state, and Settings routing.
- `apps/web/src/LoginPage.tsx`: compact login, asynchronous submission state,
  validation, password visibility, support links, and neutral SSO preview state.
- `apps/web/src/ModulePages.tsx`: independent Target, Assessment, Finding, and
  Report resource loading; dialogs; exact-record query links; lifecycle progress;
  cancellation; evidence; transitions; export; and retry/error handling.
- `apps/web/src/SettingsPage.tsx`: Windows-style Settings category navigation,
  Overview, Profile, Appearance, Demo workspace, and clearly labeled planned
  enterprise categories.
- `apps/web/src/dashboardService.ts`: record-derived dashboard projection, date
  filtering, search index, exact-record links, notifications, and mock error,
  stale, and empty modes.
- `apps/web/src/platformService.ts`: deterministic local resource adapter,
  Target validation, Assessment lifecycle reconciliation, fail-closed input
  validation, cancellation, terminal artifact generation, Finding transitions,
  Reports, and demo reset.
- `apps/web/src/theme.ts`: approved White, SecMate Dark, and Blue Cyber presets,
  persistence, and migration from earlier light/dark values.
- `apps/web/src/styles.css`: complete responsive design system, print projection,
  accessibility states, Windows-style Settings layout, and Profile layout.
- `apps/web/src/*.test.ts(x)`: login, lifecycle, validation, polling, deep-link,
  Settings, Profile, and time-zone regression coverage.

### 9.2 Routes

Protected review routes:

```text
/dashboard
/targets
/assessments
/findings
/reports
/settings
```

Detail state is addressable through query parameters:

```text
/targets?id=<target-id>
/assessments?id=<assessment-id>
/assessments?create=1
/findings?id=<finding-id>
/reports?id=<report-id>
/settings?section=<settings-section>
```

### 9.3 Local Persistence

Browser-local keys:

```text
secmate.demo.session
secmate.demo.platform.v1
secmate.theme
secmate.profile.timezone
```

These keys support frontend review only. They are not approved backend schemas,
database models, authentication sessions, or enterprise preferences.

### 9.4 Assessment Simulation

The mock adapter exposes realistic intermediate states so the frontend can be
reviewed against future backend behavior:

```text
VALIDATING -> QUEUED -> PLANNING -> RUNNING -> VERIFYING -> FINALIZING
           -> COMPLETED
           -> CANCEL_REQUESTED -> CANCELLED
           -> FAILED / TIMED_OUT
```

The adapter validates coverage, supported scenarios, Target readiness, model
roles, turn limits, token budgets, and Assessment name. It does not call a model,
Target, tool, or backend.

### 9.5 Synchronization Contract

Resource updates follow these rules:

- Background polling is silent and does not insert a refresh banner.
- Targets poll only while validating.
- Assessments poll only while active.
- Reports poll only while execution or generation is active.
- Terminal changes broadcast one dependent-resource refresh.
- Duplicate requests are coalesced.
- Stale responses are ignored.
- Unchanged records retain stable timestamps and do not rerender.
- Polling pauses in hidden browser tabs.

Future HTTP adapters must preserve these user-experience invariants.

### 9.6 Test and Build Evidence

As of `e6ccbe2`:

- `npm test` passes 16 tests.
- `npm run build` passes TypeScript and Vite production compilation.
- Vite development routes run on port `5173`.
- The self-hosted Google Sans Flex font is emitted as a fingerprinted build
  asset with its SIL Open Font License.

### 9.7 Explicitly Deferred

- Backend API, database, queue, worker, scheduler, or deployment environment.
- Live centrally reachable Attacker model integration.
- Live Judge model integration or calibration.
- Attacker prompts, Target prompts, Judge rubrics, or prompt formulation.
- Provider endpoints, API keys, credentials, or secret-manager integration.
- Target transport, tool interception, sandbox, or mock action bus execution.
- Deterministic policy engine or semantic Judge calls.
- Canonical immutable audit bundles, SARIF, or JUnit backend serialization.
- Enterprise identity, differentiated authorization, ownership enforcement, or
  access review.
- Production monitoring, production CI/CD reliance, or rollout claims.

## 10. Historical Instructions For Coding Agents

Every coding agent continuing SecMate must use this reading order:

1. Read [TRD-1.md](./TRD-1.md).
2. Read [TRD-2.md](./TRD-2.md), including Section 25.
3. Read this TRD-2A.
4. Read
   [TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md](./TRD-2B-MODEL-CONNECTIVITY-AND-DEEPTEAM-POC.md).
5. Read [TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md](./TRD-3-DEEPTEAM-ARCHITECTURE-B-POC.md).
6. Read [TRD-4](./TRD-4.md) for the current frozen implementation and safe build-agent procedures; the former root README/handoff files were removed during approved cleanup.
7. Inspect branch `Ashwin`, Git history, tests, and the implementation before
    proposing changes.

Until management frontend approval is recorded, future agents must:

- Keep all changes on `Ashwin` unless explicitly instructed otherwise.
- Continue frontend corrections through resource-oriented mock adapters.
- Preserve Target, Attacker, Judge, Assessment, Finding, Report, and advisory
  result terminology.
- Preserve fail-closed validation and all five advisory outcomes.
- Preserve exact-record links and accessible keyboard behavior.
- Preserve silent adaptive synchronization; do not reintroduce visible periodic
  refresh banners or fixed polling after terminal states.
- Preserve demo labeling and never treat local records as security evidence.
- Avoid live providers, prompts, credentials, backend services, transports,
  tools, or production-readiness claims before approval.
- Add tests for contract-sensitive changes.
- Record material decisions in the latest requirements lineage rather than
  silently altering historical rationale.

The next approved technical activity after management frontend approval was
versioned JSON Schema and worker architecture, followed by the controlled
synthetic slice now recorded in TRD-3. Pilot and production readiness still
require broader isolation, reproduction, and calibration evidence.

## 11. Model Connectivity PoC Approval

On 2026-09-26, the user explicitly approved a narrow model-connectivity phase
before DeepTeam attack methodology is implemented. This approval adds a local
FastAPI application under `apps/api` and a functional Model connectivity
section in the frontend Settings page.

Approved scope:

- Server-side Groq and OpenRouter credentials loaded from an ignored `.env`.
- Temporary model profiles for Attacker, Attack Critic, Outcome Judge, and a
  synthetic Target.
- Harmless schema-output and tool-calling checks initiated from the frontend.
- Provider health, latency, usage, and quota presentation without exposing
  credential values.
- Interception of synthetic tool calls without execution.
- A bounded three-turn brokered handoff dry run where deterministic checks run
  before judging, Critic feedback is requested only when another turn remains,
  and confirmed evidence stops the path early.

Still deferred:

- DeepTeam attack generation or execution.
- DeepTeam-defined adaptive multi-turn attack methodology.
- Real Assessment, Finding, Report, or audit-bundle persistence.
- Remote Targets, real tools, production credentials, calibrated judging, or
  production-readiness claims.

This scoped approval supersedes both the earlier provider-call deferral and the
blanket no-backend-before-review rule only for the `apps/api` connectivity
diagnostics service and its harmless synthetic handoff. It does not approve an
Assessment backend, persistence, queue, worker, production architecture,
TRD-3, or vertical-slice acceptance evidence.
