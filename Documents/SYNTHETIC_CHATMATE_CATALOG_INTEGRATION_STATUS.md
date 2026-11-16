# Synthetic ChatMate DeepTeam Catalog Integration Status

Date: 2026-11-15

## 1. Disposition

Synthetic ChatMate now exposes the full existing pinned DeepTeam catalog through the normal SecMate assessment workflow without changing catalog IDs or adding attack methods. Catalog visibility and experimental admission are separate from established target applicability and runtime capability.

- Catalog schema: `2.3`.
- Target: `secmate.synthetic-chatmate.fresh.v1`, version `0.5.0`.
- Scenario: `chatmate-direct-user-prompt-injection`.
- Existing attack methods visible/admitted: 27.
- Existing vulnerability/risk profiles visible/admitted: 125 in the current pinned catalog.
- Execution modes: `SINGLE/1` and `ADAPTIVE/2` where structural and provider prerequisites are met.
- Standard means one path; it may use a single-turn or compatible linear multi-turn method.
- Expanded means two fresh, isolated paths with the existing automatic Critic and shared campaign budget.

This is experimental catalog access, not a claim that every risk is meaningful or executable for this target. Existing applicability, capability level, and compatibility reasons remain visible and are not rewritten as verified support.

## 2. Existing Attack Methods

The target exposes the existing IDs and descriptions for:

- `permission-escalation-v1`
- `authority-escalation-v1`
- `prompt-injection-v1`
- `prompt-probing-v1`
- `system-override-v1`
- `roleplay-v1`
- `emotional-manipulation-v1`
- `gray-box-v1`
- `math-problem-v1`
- `multilingual-v1`
- `linguistic-confusion-v1`
- `input-bypass-v1`
- `context-poisoning-v1`
- `goal-redirection-v1`
- `synthetic-context-injection-v1`
- `adversarial-poetry-v1`
- `base64-v1`
- `character-stream-v1`
- `context-flooding-v1`
- `embedded-json-v1`
- `leetspeak-v1`
- `rot13-v1`
- `crescendo-v1`
- `linear-jailbreaking-v1`
- `tree-jailbreaking-v1`
- `sequential-jailbreak-v1`
- `bad-likert-judge-v1`

All methods are selectable for experimental submission. `tree-jailbreaking-v1` is not executable because its speculative sibling callbacks conflict with one authoritative linear conversation per path; it produces the explicit scoreless code `FRESH_TREE_SPECULATIVE_HISTORY_UNSUPPORTED` rather than a fabricated test.

## 3. Risk Selection And Rubrics

Every risk area/category and every risk exported by the pinned catalog is visible for Synthetic ChatMate. Unknown IDs still fail before lock or dispatch.

For an executable selection, the worker builds a fresh-target assessment specification from the selected vulnerability profile. The specification binds the selected risk ID, name, category, definition, compromise/resistance/inconclusive criteria, expected evidence, generation guidance, and target-specific policy. The attacker, native evaluator, and independent Judge therefore receive the selected risk rather than the direct-prompt-injection policy or a SOCMate rubric.

The additive `fresh-selection-capability-v1` object records in all four artifacts and each path:

- exact target, method ID/name/turn mode, and risk ID/name/category;
- established versus experimental admission;
- established target applicability;
- `EXECUTABLE` or `UNSUPPORTED` capability;
- stable capability code and sanitized reason.

## 4. Honest Unsupported Outcomes

Selections requiring a protocol or channel absent from fresh Synthetic ChatMate are accepted as experimental requests but stop before provider calls. They publish a sealed `FAILED` / `ERROR` diagnostic audit with zero calls, zero turns, no native score, no Judge result, and no security conclusion.

Current unsupported capability families include:

- speculative tree histories;
- privileged function, write, destructive, or autonomous action protocols;
- object, role, tenant, or delegated-agent identity boundaries;
- debug or administrative interfaces;
- outbound network, external integration, or internal-service access;
- controlled malicious document, RAG, tool-output, or cross-context injection delivery;
- recursive/shared-state tool orchestration and attacker-controlled tool metadata;
- code, shell, or dynamic-evaluation execution;
- inter-agent messaging, collusion, and autonomous reward state;
- authoritative system, file, database, or retrieval-configuration metadata;
- API/database PII access and cross-session leakage.

Stable codes include `FRESH_PRIVILEGED_PROTOCOL_UNAVAILABLE`, `FRESH_IDENTITY_PROTOCOL_UNAVAILABLE`, `FRESH_ADMIN_PROTOCOL_UNAVAILABLE`, `FRESH_NETWORK_PROTOCOL_UNAVAILABLE`, `FRESH_INJECTION_CHANNEL_UNAVAILABLE`, `FRESH_TOOL_PROTOCOL_UNAVAILABLE`, `FRESH_INTER_AGENT_PROTOCOL_UNAVAILABLE`, `FRESH_TOOL_METADATA_CHANNEL_UNAVAILABLE`, `FRESH_CODE_EXECUTION_PROTOCOL_UNAVAILABLE`, `FRESH_AUTONOMY_PROTOCOL_UNAVAILABLE`, `FRESH_WRITE_PROTOCOL_UNAVAILABLE`, `FRESH_OUTBOUND_PROTOCOL_UNAVAILABLE`, `FRESH_SYSTEM_METADATA_CHANNEL_UNAVAILABLE`, `FRESH_DATA_PROTOCOL_UNAVAILABLE`, and `FRESH_SESSION_PROTOCOL_UNAVAILABLE`.

The remaining risk profiles can execute through bounded text conversation and the available synthetic read-only mail and Teams tools. Execution does not guarantee a conclusive result; missing required evidence remains inconclusive or error according to the selected specification.

## 5. Baseline And Transformed Execution

The verified unenhanced baseline remains limited to this exact binding:

- Synthetic ChatMate;
- `DirectPromptInjection:direct_user_instruction`;
- `prompt-injection-v1`;
- `SINGLE/1`.

It records `baseline-execution-v1`, `BASELINE_UNENHANCED`, and `enhancement_applied=false`, and the UI labels it **Baseline / unenhanced**.

Every other executable selection retains its actual DeepTeam attack transformation and is labeled **DeepTeam transformed**. The system does not silently fall back to baseline after transformation failure. Unsupported selections are labeled **Not executed / unsupported**.

Linear multi-turn methods use the existing authoritative path-local conversation. User and assistant turns remain ordered, target/tool evidence remains correlated, caller history is checked against recorded state, and duplicate/current-probe or cross-path/session injection is rejected. Each independent path receives fresh state. No cross-assessment continuation is implemented.

## 6. API, Evidence, And Reports

The API admits exact catalog IDs independently of established applicability while retaining structural checks for target/scenario/version, gateway, execution profile, mode/path shape, budgets, configured providers, and adaptive Critic readiness.

Sealed publication validates `fresh-selection-capability-v1` across `manifest.json`, `evidence.json`, `deepteam-risk.json`, `summary.json`, and each path. It preserves selected method/risk/spec identity, baseline/transformed provenance, path ordering, Phase 5 path/turn bindings, adaptive Critic-to-path-two selection, and failure-without-score behavior.

Typed unsupported audits and operational failures remain available to Results and Reports without becoming `RESISTED`, `COMPROMISED`, or a numeric score. Reload/export is read-only and does not replay inference. Historical catalog `2.1`/`2.2` records and existing SocMate/legacy ChatMate readers remain supported.

## 7. Frontend Behavior

For Synthetic ChatMate:

1. Open **Assessments** and select **Synthetic ChatMate**.
2. Select any existing **Risk area** and exact **Security risk**.
3. Select **Single-turn** or **Multi-turn**, then choose any existing method shown for that turn shape.
4. Review the compatibility note. `NOT_APPLICABLE` means the combination lacks established target applicability; it does not hide the entry or alone disable Start.
5. Choose **Standard** for one fresh path or **Expanded** for two fresh paths when operational prerequisites are available.
6. Select **Start assessment**. The request uses the exact visible target, scenario, risk, method, mode, path count, and token limit.
7. Results identify execution as **Baseline / unenhanced**, **DeepTeam transformed**, or **Not executed / unsupported**. Unsupported results show the stable reason and `Not evaluated` / `Not recorded`, with no policy-success claim.

Start remains disabled for genuine operational problems: unknown or missing selected IDs, unavailable worker/providers, insufficient budget, invalid mode/path shape, unresolved recovery, an active run, or a duplicate in-flight launch. SocMate retains its existing strict applicability filtering and defaults.

## 8. Implementation Paths

Worker:

- `services/deepteam-worker/src/secmate_worker/{contracts.py,deepteam_catalog.py,deepteam_runner.py,target_evaluator.py}`
- `services/deepteam-worker/src/secmate_worker/synthetic_chatmate/model_phase5/onboarding.py`
- focused catalog/fresh/runner/evaluator/gateway tests.

API:

- `apps/api/src/secmate_api/{contracts.py,deepteam_catalog.py,deepteam_runs.py,standard_reviews.py}`
- `apps/api/tests/test_fresh_deepteam_api.py` and focused lifecycle/review/report regressions.

Frontend:

- `apps/web/src/{modelConnectivityService.ts,DeepTeamAssessmentPanel.tsx,AssessmentResultsPanel.tsx,managementReport.ts,ManagementReportPanel.tsx}`
- corresponding focused component/service/report tests.

## 9. Verification

Worker focused gate:

```powershell
$env:PYTHONPATH='tests;src'
& '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_deepteam_catalog.py tests/test_deepteam_chatmate_fresh.py tests/test_deepteam_runner.py tests/test_target_evaluator.py tests/test_evidence_inventory.py tests/test_target_gateway.py tests/test_synthetic_chatmate_model_phase5.py
```

Result: **289 passed in 186.69s**.

API focused gate, with test storage isolated before execution-module imports:

```powershell
& '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider tests/test_fresh_deepteam_api.py tests/test_deepteam_runs.py tests/test_standard_reviews.py tests/test_job_lifecycle.py tests/test_lifecycle_checkpoint.py tests/test_management_report_data.py
```

Result: **298 passed in 238.72s**, with one existing Starlette/httpx deprecation warning.

Frontend focused gate and build:

```powershell
npm test -- --run src/DeepTeamAssessmentPanel.test.tsx src/modelConnectivityService.test.ts src/AssessmentResultsPanel.test.tsx src/ManagementReport.test.tsx src/ModulePages.test.tsx
npm run build
```

Result: **66 passed**; TypeScript/Vite production build passed. Responsive/accessibility assertions used the existing jsdom environment; no actual browser runner is installed or was added.

`git diff --check` passed with working-copy line-ending warnings only. All provider transports were mocked/offline. No live assessment, dependency change, staging, commit, or push occurred.

## 10. Remaining Limitations

- Full catalog visibility is experimental access, not calibration or live verification of every combination.
- Runtime capability is decided from the current target's bounded text/read-only protocol. Unsupported selections intentionally produce error evidence rather than simulated coverage.
- Provider/model behavior, generated wording, target responses, Judge outputs, route availability, and verdicts remain nondeterministic.
- Tree branching, unavailable delivery channels, privileged/write protocols, real Microsoft effects, and cross-assessment conversation continuation are not implemented.
- The target exposes only fictional local data and bounded synthetic mail/Teams reads; no real tenant, ChatMate, Microsoft, network, write, meeting, or administrative effect is reachable.
- No automatic full-catalog live run was performed or authorized.

## 11. Read-Only Targets Presentation - 2026-11-15

### 11.1 Implemented presentation

The Targets page now uses one versioned, server-owned projection and one shared card/detail-dialog presentation for the two current product targets:

- `synthetic-socmate-tier1` / **SocMate**;
- `secmate.synthetic-chatmate.fresh.v1` / **Synthetic ChatMate**.

Both targets appear once in the existing target grid with matching dimensions, typography, spacing, borders, and interaction. Cards show the authoritative purpose, synthetic environment, profile version, and total inventory tool count. Search and visible/total counts operate on the same server response.

Both cards and direct links such as `/targets?id=secmate.synthetic-chatmate.fresh.v1` open the same `DialogFrame`-based modal. The shared dialog retains modal semantics, labelled heading, initial Close focus, Escape dismissal, Tab trapping, backdrop dismissal, URL state, and focus restoration.

The dialog contains:

- **Identity**: actual provider/model, environment, server ownership, owner only when known, and target/profile versions;
- **Tools and actions**: read/write classification, synthetic effect scope, model exposure, implementation status, current executability, and collapsed canonical/native details;
- **Guardrails and access**: trusted application/runtime/assessment enforcement facts;
- **Data and memory**: fictional data sources, production-data exclusion, seeded-memory policy, natural-learning status, cross-run behavior, and assessment isolation;
- collapsed **Execution support and limitations** with distinct smoke, DeepTeam-profile, and target-runtime limits;
- collapsed **Technical details** with IDs, schema/profile/scenario/binding versions, and repository-relative sources/design references.

The dialog is limited to approximately 1,000 pixels and 90 viewport-height units with internal scrolling, long-value wrapping, responsive one-column sections, and viewport-safe mobile sizing.

### 11.2 Removed Targets-only smoke presentation

Targets no longer renders:

- the duplicate standalone ChatMate card;
- **Select Synthetic ChatMate**;
- the embedded smoke runner or its start/cancel/progress/result controls;
- Phase 5 implementation labels;
- `MOCKED ONLY` or `UNFINISHED` banners;
- target onboarding actions.

The existing `SyntheticChatMateTarget`, `syntheticChatMateService`, API smoke endpoints, smoke tests, and historical evidence remain unchanged and available to their existing owners. Assessments continue to run from Assessments, not Targets.

### 11.3 Server-owned target projection

The API now provides deterministic, read-only endpoints:

- `GET /api/v1/targets`;
- `GET /api/v1/targets/{target_id}`.

The strict `target-projection-v1` contract returns only controlled target metadata. It does not read assessment/smoke history or run storage, launch workers/jobs, construct provider clients, or perform inference. Unknown target IDs return 404, and mutation methods are unavailable.

Synthetic ChatMate accurately reports seven model-exposed tool schemas while identifying only mail search and Teams reads as executable in the current Phase 5 assessment dispatch. History, directory, message proposal, calendar, and meeting proposal capabilities remain implemented/exposed or deferred as applicable and are not presented as usable assessment actions. SocMate distinguishes simulated alert reads from approval-gated containment and administrative simulations.

Responses exclude credentials, environment-variable names, prompts, hidden reasoning, private fixture truth, raw schemas, provider request IDs, canaries, production data, and absolute local paths.

### 11.4 Changed files

API:

- `apps/api/src/secmate_api/target_projection.py`
- `apps/api/src/secmate_api/main.py`
- `apps/api/tests/test_target_projection.py`

Frontend:

- `apps/web/src/ModulePages.tsx`
- `apps/web/src/styles.css`
- `apps/web/src/targetProjectionService.ts`
- `apps/web/src/targetProjectionService.test.ts`
- `apps/web/src/TargetsPage.test.tsx`
- `apps/web/src/ModulePages.test.tsx`

### 11.5 Verification results

API focused command:

```powershell
& '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider tests/test_target_projection.py tests/test_synthetic_chatmate_smoke.py tests/test_api.py
```

Result: **27 passed**, with one existing Starlette/httpx deprecation warning. Coverage includes exact two-target ordering, list/detail consistency, strict contracts, accurate tool states and memory/limit facts, sensitive-data exclusions, 404/405 behavior, repeated stable reads, isolated-storage immutability, and explicit no-dispatch/no-provider/no-smoke access.

Frontend focused command:

```powershell
npm test -- --run src/TargetsPage.test.tsx src/targetProjectionService.test.ts src/ModulePages.test.tsx src/SyntheticChatMateTarget.test.tsx
npm run build
```

Result: **21 passed**; TypeScript/Vite production build passed with 68 modules transformed. Coverage includes one card per target, search/count consistency, authoritative details, direct links, unknown IDs, shared dialog semantics, Close/Escape, focus trap/restoration, no obsolete smoke presentation, no smoke-service request, and responsive structural safeguards.

`git diff --check` passed with existing working-copy line-ending warnings only. No provider call, assessment execution, dependency change, staging, commit, or push occurred.

### 11.6 Browser disposition

An isolated API, Vite server, and headless Edge session were prepared on alternate localhost ports without using historical storage. The browser assertions were not completed because the user asked to stop the long-running command and continue with the remaining work. The isolated processes were terminated.

At that checkpoint, desktop and 390-pixel behavior was covered only by component/CSS tests and production compilation. Section 11.7 records the later completed browser verification for the corrected layout.

### 11.7 Targets dialog layout correction - 2026-11-15

The shared target dialog was tightened without changing assessment, catalog, model, authorization, or ownership enforcement behavior:

- Synthetic ChatMate's server-owned target projection now displays owner **AIDA**; SocMate remains unspecified.
- Identity, Guardrails and access, and Data and memory are compact, independently sized, and top-aligned.
- Tools and actions is full width with seven compact cards in two columns on desktop and one column on narrow screens.
- The rendered **Execution support and limitations** and **Technical details** disclosures were removed; their backend metadata and report data remain unchanged.
- The modal uses an approximately 1,000-pixel maximum width, 16-pixel viewport clearance, a fixed visible header/Close action, and one internally scrolling content body. The tool grid has no nested scrollbar.

Focused verification:

- API projection: **5 passed**, one existing Starlette/httpx warning.
- Targets frontend: **18 passed**.
- TypeScript/Vite production build: passed.

Real Chrome layout checks against the current isolated API code passed:

- `1440x768`: dialog bounds `220,16` to `1220,752`; owner AIDA visible; three summary panels top-aligned with independent heights; seven tools in two columns; body overflow `auto`; tool overflow `visible`; Close visible; no horizontal overflow; removed disclosures absent.
- `390x844`: dialog bounds `16,16` to `374,828`; summary and tool grids one column; all seven tools present; body overflow `auto`; tool overflow `visible`; Close visible; no horizontal overflow.

The same shared dialog class and actual Nemotron model value were also verified for SocMate. Temporary browser/API/web processes were terminated after the checks.

## 12. Targets dialog screenshot regression correction - 2026-11-15

The user-supplied approximately `1920x966` screenshot disproved the current-state layout claim in section 11.7: the header rendered across the left of the modal while the summary and tool content collapsed into narrow, overlapping strips at the far right. The prior jsdom checks asserted markup and inline-width absence but could not perform browser layout. The browser evidence recorded in section 11.7 therefore did not represent the checked-in stylesheet state reproduced by the screenshot.

The exact root cause was the target-specific rule in `apps/web/src/styles.css`: `.target-detail-dialog` set `display: flex` without setting `flex-direction`. Its initial value is `row`, so the direct-child header and `.target-detail-body` became horizontal flex items. The header's intrinsic content consumed most of the dialog width and the body, including `.target-summary-grid`, `.target-tools-section`, and `.target-tools`, was flex-shrunk into the remaining right-hand sliver. The generic `.detail-dialog` width/overflow rules and the target grid `minmax(0, 1fr)` columns were not the source; they exposed the failure because those otherwise-correct grids resolved inside the compressed body. Later generic `.detail-dialog` rules changed only border radius/shadow or `.detail-columns` descendants and did not restore the missing main axis.

Files changed for this correction:

- `apps/web/src/styles.css`
- `apps/web/src/TargetsPage.test.tsx`
- `Documents/SYNTHETIC_CHATMATE_CATALOG_INTEGRATION_STATUS.md`

The fix adds `flex-direction: column` to `.target-detail-dialog`. This places the fixed header above `.target-detail-body`, lets the body use the full dialog width, and preserves the existing single body scrollbar, desktop three-column summary/two-column tools layout, mobile stacking, visible Close action, and all projection/runtime semantics. The focused regression test reads the actual production stylesheet and requires the dialog's flex-column/overflow contract and the body's vertical-scroll/horizontal-containment contract; this directly fails if the omitted-axis compression returns. Existing component assertions continue to cover the three summary sections, full-width tools section, seven tool cards, 2 executable/5 deferred labels, AIDA ownership, direct links, search/count behavior, Close/Escape, focus trap/restoration, SocMate, and absence of Targets smoke/onboarding controls.

Verification completed against the current working tree without provider or live calls:

```powershell
npm test -- --run src/TargetsPage.test.tsx src/targetProjectionService.test.ts src/ModulePages.test.tsx src/SyntheticChatMateTarget.test.tsx
npm run build
git diff --check
```

- Focused frontend gate: **22 passed** across four files.
- TypeScript/Vite production build: passed with 68 modules transformed.
- Real headless Chrome against the current Vite page and local projection API, desktop browser window `1920x966` / measured CSS viewport `1902x870`: dialog `x=451..1451`, `y=16..854`, width `1000`; computed direction `column`; body width `998`, client/scroll width `983/983`, overflow `hidden auto`, client/scroll height `694/1439`; summary columns `301/301/301`; tool columns `440.5/440.5`; seven equal-width tools; 2 executable and 5 deferred labels; Close visible; no document horizontal overflow.
- Separate narrow headless Chrome check, measured CSS viewport `500x748`: dialog `x=16..469`, `y=16..732`; computed direction `column`; body client/scroll width `436/436`, overflow `hidden auto`; summary sections stack at `408` pixels and tools stack at `374` pixels; all seven tools and correct status labels are present; Close is visible; no document horizontal overflow. Chrome enforced a 500-pixel minimum CSS viewport for this headless window, so this is not claimed as a 390-pixel browser run; the `max-width: 700px` mobile layout was active.

## 13. Targets summary content reduction - 2026-11-15

The Guardrails and access and Data and memory cards contained projection diagnostics rather than the minimum information needed for a PoC. Enforcement-source badges, Phase5 terminology, repeated boolean facts, the separate assessment-state field, and three bullets duplicated the same safety and isolation claims and made the summary disproportionately tall.

This correction is presentation-only. `apps/web/src/ModulePages.tsx` still receives the complete `target-projection-v1` payload, but now exposes concise user-facing facts:

- Synthetic ChatMate Guardrails and access: `Trust boundary - User instructions are untrusted` and `Access - Read-only mail search and Teams read`.
- Synthetic ChatMate Data and memory: `Data - Synthetic only; no production data`, shortened source names, and `Memory - Seeded facts only; reset each assessment`.
- SocMate uses the same compact structure for trusted approval, simulated effects, its synthetic source, and its no-persistent-memory claim.
- The fresh-path guardrail remains in projection metadata but is not repeated in the guardrail card because the memory row already communicates the reset boundary.

`apps/web/src/styles.css` adds a shared compact definition-row layout with an 88-pixel label column and a flexible content column. It uses the existing panel borders, typography, spacing, and responsive stack rather than nested cards, preventing the condensed content from distorting either the desktop grid or mobile dialog. `apps/web/src/TargetsPage.test.tsx` verifies the five Synthetic ChatMate essentials, the absence of repeated summary text, equivalent SocMate summaries, and the production CSS contract.

Verification against the current working tree:

- Focused frontend gate: **19 passed** across `TargetsPage.test.tsx`, `targetProjectionService.test.ts`, and `ModulePages.test.tsx`.
- TypeScript/Vite production build: passed with 68 modules transformed.
- Real Chrome at `1440x768`: three top-aligned 301-pixel summary columns; Identity, Guardrails, and Data/Memory heights `224/174/235`; five compact facts present; repeated summary text absent; seven tools in two columns; one body scrollbar; Close visible; no horizontal overflow.
- Real Chrome at `390x844`: summary and tools stack to one column; both compact fact groups are 294 pixels wide; all seven tools remain present; Close remains visible; no horizontal overflow.

No API contract, projection metadata, target behavior, assessment/runtime path, dependency, provider, or live-call behavior changed.

## 14. Model-backed capability enablement and user-facing projection - 2026-11-15

This increment replaces the historical mail/Teams-only execution overlay recorded in earlier sections. The target ID and target version remain `secmate.synthetic-chatmate.fresh.v1` / `0.5.0`; the expanded behavior is bound by additive execution profile `deepteam-conversation-v1` version `2.0.0`. Historical saved records and artifacts retain their recorded execution-profile version and are not rewritten.

### 14.1 Worker execution profile

`services/deepteam-worker/src/secmate_worker/synthetic_chatmate/model_phase5/execution_profile.json` is now the strictly validated worker-owned effective profile. Runtime registration, onboarding evidence, budgets, tool partitions, and the Targets projection consume this policy rather than maintaining separate availability claims.

The current model-backed assessment runtime supports:

- available read-only capabilities: conversation history, mail search, Teams read, directory search, and calendar read;
- approval-gated staged proposals: message and meeting proposals;
- up to four logical model turns, two transport attempts per turn, four cumulative provider attempts, 8,000 provider tokens, 500 output tokens per request, a 45-second provider-operation cap, and a 120-second target deadline.

The existing corrected handlers remain authoritative for accepted schemas, ownership, same-tenant authorization, validation, state, evidence, immutable review, approval binding, execution settlement, and exactly-once synthetic effects. No handler was rebuilt and `secmate.action.decide` was not added to the model tool inventory. Memory is refreshed under the existing host rules; no autonomous learning, model-callable memory control, or cross-assessment persistence was introduced.

Read results are replayed to the model with the exact opaque provider call ID. The bounded loop supports multiple ordered read calls before a final response or proposal. Proposal staging is also replayed with the exact call ID on the next model turn; that turn must be final and cannot dispatch another tool. Regardless of model wording, the public result is host-authored `Awaiting approval`, with terminal reason `pending_approval`, one immutable pending review, and zero effect before trusted host approval. Model text cannot approve a proposal.

The worker gateway retains trusted assessment state and has host-only copied review/decision methods that reuse the existing approval path. The current Assessments API/UI does not expose an approval interaction, so an assessment proposal remains accurately reported as `Awaiting approval`; it is not auto-approved, presented as delivered, or converted into a target execution error. Approval-required tool attempts are classified as mutations intercepted without execution until a trusted host decision exists.

### 14.2 Read-only target projection and UI

`apps/api/src/secmate_api/target_projection.py` reads and validates the static worker execution profile without importing or launching the worker and fails closed if the policy is missing or malformed. Targets remains GET-only and does not access jobs, run storage, providers, smoke execution, or model dispatch.

The normal target dialog now displays five `Available` read capabilities and two `Requires approval` proposals with clear names, purposes, and `Read-only` / `Proposes an action` labels. Phase5, dispatch-allowlist, fixture, schema-exposure, canonical/native, binding, EXPOSED, and IMPLEMENTED terminology is absent from the normal UI. Canonical names, native mappings, provenance, IDs, limits, references, and implementation fields remain available in the backend projection and sealed evidence/export contracts.

New assessments bind execution profile `2.0.0`. The API catalog language now describes the bounded linear read/proposal loop and synthetic staged delivery accurately. Historical artifacts continue to validate against their own recorded profile metadata.

### 14.3 Verification and limits

All provider-facing worker checks used mocked transports and the offline network guard:

- Worker Phase 5 model suite: **46 passed**.
- Worker gateway/fresh-target/historical base selection: **92 passed**.
- Corrected communication/calendar compatibility selection: **9 passed**; the larger handler run reached 73 percent without a failure before the command timeout, so no full-suite pass is claimed.
- Independent rerun of `test_synthetic_chatmate_model_phase5.py` and `test_deepteam_chatmate_fresh.py`: **67 passed**.
- API target projection, fresh DeepTeam API, and DeepTeam run gate: **232 passed**, with one existing Starlette/httpx warning.
- Complete frontend suite: **515 passed** across 37 files; TypeScript/Vite production build passed with 68 modules transformed.

Real Chrome verification against isolated current API/Vite processes:

- `1440x768`: 1,000-pixel dialog; three top-aligned 301-pixel summary cards; all seven capability names; five Available and two Requires approval badges; two capability columns; no developer terms, technical disclosures, nested tool scrollbar, or horizontal overflow; Close visible.
- `390x844`: summary and capability grids stack to one column; compact fact groups remain 294 pixels wide; all seven capabilities remain present; one body scrollbar; no horizontal overflow; Close visible.

No live assessment or provider call was made. Real outbound mail, chat delivery, invitations, Microsoft effects, autonomous approval, and cross-assessment memory remain unavailable.

## 15. Capability-card compatibility and limitations removal - 2026-11-15

The reported blank capability headings came from an updated frontend rendering an older target payload that did not contain `display_name` and still used `EXECUTABLE` / `DEFERRED` statuses. The same payload carried the obsolete three-item Limitations copy.

The frontend now uses projected display names when present and falls back to clean names for every known SocMate and Synthetic ChatMate capability, with a readable canonical-name fallback for future tools. Current and prior status enums map to honest user labels. Each card consistently renders name and access on the left, availability on the right, and purpose below. The Limitations block and its contents are no longer rendered; backend limitation and technical fields remain unchanged.

Focused frontend verification: **20 passed** across Targets, target-service, and shared module tests; the production build passed. A regression reproduces the older payload shape and proves all seven names render, two legacy executable tools remain Available, five deferred tools are identified as not enabled, and obsolete limitation text is absent.

Real Chrome verification passed at `1440x768` and `390x844`: all seven cards have nonblank names, the current profile shows five Available and two Requires approval badges, the Limitations section is absent, desktop uses two capability columns, mobile uses one, Close remains visible, and neither viewport has horizontal overflow.

## 16. Fresh selection provenance parity repair - 2026-11-15

Run `api-run-bdfb9481a95e` exposed a deterministic API/worker contract drift. The API accepted execution-profile-2.0 provenance stating that the selection could use synthetic reads and approval-gated proposals, while the worker sealed the older mail/Teams-only reason. All four worker artifacts were present and internally consistent, but strict API publication correctly rejected their non-identical `fresh-selection-capability-v1` object. The historical failed run and its unaccepted artifacts were not changed or republished.

The worker catalog now uses the same execution-profile-2.0 executable and unsupported capability reasons as the API. Its direct and experimental assessment specifications no longer claim a one-read or mail/Teams-only boundary; they describe bounded reads, approval-gated proposals, exact tool correlation, and the requirement that no proposal take effect without trusted approval. Strict artifact equality and tamper rejection remain unchanged.

New regressions prevent recurrence:

- every worker-authored attack/risk selection object is compared byte-for-structure with the API projection across the complete fresh catalog;
- the exact Emotional Manipulation / Blind SQL Injection worker-authored provenance now passes sealed API publication validation;
- representative unsupported risk classes verify the same profile-2.0 capability reasons;
- assessment specifications reject stale mail/Teams-only and read-only-allowlist wording.

The results UI no longer renders a result hero for `FAILED` / `ERROR` runs because no accepted result exists. It retains the header `Assessment incomplete` status, detailed operational error, no-audit state, and any explicit retained `Not evaluated` score evidence. It does not expose the worker's unaccepted `RESISTED` result or manufacture a conclusion.

Verification:

- worker focused catalog gate: **164 passed**;
- API fresh DeepTeam gate: **208 passed**, one existing Starlette/httpx warning;
- broader worker catalog/fresh/runner/evaluator/evidence/model gate: **283 passed**;
- broader API fresh/run/lifecycle/report gate: **283 passed**, one existing warning;
- focused frontend report/management/service gate: **33 passed**; production build passed with 68 modules transformed;
- real Chrome on `/reports?live=api-run-bdfb9481a95e`: zero result heroes, status and exact provenance error visible, no-audit state visible, duplicate hero explanation absent, and no horizontal overflow.

No provider or live assessment call occurred. Future runs use the corrected worker source, but unrelated provider, network, budget, cancellation, or validation failures remain possible and continue to fail scorelessly. A deployed long-running API should be restarted once with no active assessment so imported code and its catalog cache are coordinated with the corrected worker.

## 17. Linked Attack Critic draft hash compatibility - 2026-11-15

The saved Attack Critic draft was valid on the API but falsely rejected by the browser. Python canonical JSON retained the Judge confidence value as `1.0`; after JSON parsing, JavaScript represented the same numeric value as `1`. The frontend therefore hashed different lexical JSON bytes and displayed `Linked draft parent evidence hash does not match its frozen context`, even though the stored backend digest matched exactly.

The unreliable duplicate browser hash recomputation was removed from linked-draft and management-report presentation. Integrity remains enforced by the strict API `LinkedAssessmentContext` contract when the context is created/loaded and again by `validate_linked_source()` before a linked assessment can start. Frontend scope, target, scenario, risk, method, review, and parent bindings remain checked.

Verification:

- frontend Standard Review, management-report, and chain tests: **47 passed**; production build passed;
- API Standard Review suite: **18 passed**, one existing Starlette/httpx warning;
- durable draft `api-run-f715249f7e5c` passed backend source validation without launching work;
- real Chrome loaded that exact draft with no alert, a visible parent-evidence link, an enabled Start linked assessment button, and no horizontal overflow.

No linked assessment, provider call, historical-record rewrite, or automatic retry occurred.

## 18. Executive Dashboard canonical activity aggregation - 2026-11-15

The Executive Dashboard previously mixed three identities: DeepTeam report family, target identity, and browser-local seeded targets. `console.py` labeled every DeepTeam record as source `SocMate`, rewrote `synthetic-socmate-tier1` to `socmate`, omitted drafts and smoke runs, inferred critical severity from report family, returned only three activities, and built proportional UTC intervals rather than calendar-date buckets. The frontend then merged those records with the browser-local `socmate` seed, creating duplicate/misnamed rows and fabricated Low/Critical risk and severity values.

`console-summary-v2` now normalizes retained DeepTeam assessments/drafts, legacy ChatMate assessments/drafts, and Synthetic ChatMate smoke runs without invoking reconciliation or persistence. It keeps report family separate from target identity, uses exact canonical IDs, resolves authoritative target names/owners from the target projection, and preserves legacy manual ChatMate as a separate non-projected scope. The endpoint returns distinct lifecycle counts, nullable backend-authoritative pass rate, UTC calendar-day range/buckets, global and in-range active flags, up to 20 namespaced activities, and an honest unavailable finding-severity state. Failed, cancelled, rejected, abandoned, draft, smoke, inconclusive, and unevaluated records do not enter the conclusive pass-rate denominator.

The current retained store was observed through the v2 endpoint as 20 activities: 19 assessments, one draft, zero smoke rows, and exactly the canonical `synthetic-socmate-tier1` and `secmate.synthetic-chatmate.fresh.v1` target keys. Historical 2.1/2.2/2.3 records remain read through existing loaders; no runtime record was rewritten.

The frontend now loads authoritative `/targets` metadata instead of `platformService` target seeds. Dashboard metrics report assessments, active work, conclusive pass rate, and lifecycle exceptions. Empty conclusive sets display `No evaluated results`. Finding severity displays `Severity unavailable` unless actual severity counts are supplied. Target rows are canonical, deduplicated, owner-correct, unrated without evidence, keyboard navigable, and linked to valid destinations. Activity uses target names rather than report family and links DeepTeam reports, linked drafts, legacy ChatMate, and smoke entries appropriately.

The dashboard header no longer exposes server-snapshot or generation-time metadata. Zero smoke-test text is omitted, and the lifecycle-exception card displays only failed and cancelled counts. Assessment Activity now keeps pass rate as a summary only; the graph plots assessment counts with a separately positioned blue dashed `Assessments run` legend, UTC date labels on the x-axis, and count labels in five-test increments on the y-axis. Drafts and smoke tests do not inflate the plotted assessment count.

Recent activity is capped at the latest three normalized records before rendering, followed immediately by the assessment-history action. Target activity overview now uses four aligned columns (Target, Evaluated outcomes, Latest activity, Status); target descriptions and the Owner/Risk columns are not rendered. Desktop target/activity cards retain equal row height, while mobile stacks the cards without horizontal page overflow.

Dashboard requests are abortable and range-specific. Focus, visibility, online, run-change, and data-change events queue one refresh if another request is in flight; stale/out-of-order responses cannot replace the selected range. Active work, including awaiting ChatMate phases and running Standard Critic reviews, enables fast polling. Notifications retain canonical target labels, valid browser links, and cached running Critic events during source outages.

Verification:

- backend console contract: **7 passed**, one existing Starlette/httpx warning;
- adjacent backend/store/restart/deletion selection: **127 passed** before final edge additions;
- complete frontend suite: **525 passed** across 38 files;
- dashboard/notification/target focused gate: **62 passed** before the presentation-only chart follow-up;
- final dashboard metric/chart gate: **35 passed**;
- final activity/table gate: **37 passed**; production build passed;
- intercepted real-Chrome layout check at `1440x900`: three activity rows, history action visible, four target columns, descriptions absent, equal 364-pixel operation-card heights, and no horizontal overflow;
- intercepted real-Chrome layout check at `390x844`: three activity rows, four-column table contained by its existing horizontal table scroller, one-column metric layout, and no horizontal page overflow;
- TypeScript/Vite production build passed with 68 modules transformed;
- `git diff --check` passed with existing line-ending warnings only.

No model/provider call, inference launch, runtime-data rewrite, dependency change, staging, commit, or push occurred. A real desktop/mobile browser result is not claimed: the existing localhost frontend was not running, and no server was started in accordance with the user's instruction. Browser rendering should be checked when the user next starts the application manually.
