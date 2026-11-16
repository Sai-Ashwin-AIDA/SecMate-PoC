# Synthetic ChatMate Phase 3 build results

Date: 2026-11-12. Target: `secmate.synthetic-chatmate.fresh.v1`; new version `0.3.0`.

**Current disposition: Phase 3 implemented and offline-verified following the explicit user-approved invitation-commit amendment.** Final gate: **628 passed**, including **204 Phase 3 cases**; separate guarded CLI and read-only reconciliation passed for **20 assessments**. Section 10 records the current completion, bindings and evidence. Stop before Phase 4.

**Historical stopped disposition (Sections 1–9):** the initial attempt stopped at a material public-evidence contract conflict, before its final combined gate and retained CLI demonstration. Those records, failures and provisional digests below retain their historical meaning and are superseded for the final amended implementation by Section 10. No earlier evidence was rewritten.

## 1. Stop condition and decision required

Blueprint §§14.3, 17.3/A05 and 21/F04 require public observers to reject inconsistent invitation identities. The exact closed schema and stage population rules in §§7/14.1 expose `invitation_ids` only in the `MeetingReceipt` at `action.completed`. `action.simulated` carries effect/event/execution identities but no independently observed invitation identities. The public event schemas provide no other committed invitation-ID binding. Invitation IDs are opaque host-assigned IDs; no deterministic allocation rule is specified.

Replacing only `receipt.invitation_ids` with a different, unique, schema-valid opaque ID preserves every other public observation. Count/shape/uniqueness checks cannot distinguish that replacement from the actual committed invitation. The current preliminary observer initially returned `expected_behavior_observed`; an executed negative test exposed that insufficiency. SQLite can establish the actual ID, but the blueprint explicitly prohibits using restricted state to upgrade this public assertion. An expected ID derived from an undocumented allocator would not establish an actual committed-row observation either.

The observer now fails closed with missing prerequisite `independent_public_invitation_identity_binding`. Its full meeting-correspondence result is **inconclusive**, including on an ordinary successful trace. The positive acceptance expectation remains failing; it was not weakened to call this Phase 3 acceptance. The selected missing-binding profile still has its separately scoped purpose. No actual invitation-ID contradiction is being hidden when an independent observation exists: the problem is that the pinned public contract supplies no such independent observation.

**Requested decision:** authorize a version-bound, closed public invitation-commit observation, emitted atomically with the event/effect/invitation rows, containing the approval/execution/effect/event identities and ordered invitation-ID/attendee/calendar/record-digest bindings. Then bind the observer to that observation and update the scoped blueprint binding before continuing. No accepted document was edited to introduce this change without approval.

This invokes blueprint §22's missing/inconsistent evidence-contract stop condition. It is not a timezone prerequisite failure, historical regression, production finding, or claim that the preliminary implementation otherwise meets every acceptance case.

## 2. Read-only preflight and preservation

Read the build status (including all of §19), complete Phase 3 blueprint, complete manifesto and mapper, and expansion Part A through the separator before Appendix B. Inspected the corrected runtime/contracts/artifacts/evidence/reconciler, inherited runtime/store/contracts/services, all three existing synthetic test files and the network-denial guard. No repository `AGENTS.md` was found by the workspace search.

Git initially contained the existing modified expansion document and untracked synthetic documents, Phase 1, historical communication, corrected communication, tests and guard. These were preserved. No tracked application source, prior synthetic implementation/test/definition, accepted document or historical verdict was edited. All changes made by this attempt are new Phase 3 package/test files and this new report. No staging, commit, push, dependency/configuration change, installation, real ChatMate access or global ownership change occurred.

Read-only `git hash-object` results matched before implementation and again at the stop:

| Input | Git blob SHA-1 |
|---|---|
| `Documents/chatmate_mapper.md` | `559bf61ace74094996df9a871dd276569a7a7aa9` |
| `Documents/synthetic_chatmate_manifesto.md` | `518b848480a43f8e7d17838c6f7136cd1d903765` |
| `Documents/REDTEAM_EXPANSION.md` | `1549398da71cc0142b6e50cced3c7aa7bd9f9cb8` |
| `Documents/SYNTHETIC_CHATMATE_BUILD_STATUS.md` | `6899f5c6df6bce98f4118bc2adc984d8a1c282f3` |
| `Documents/SYNTHETIC_CHATMATE_PHASE3_BLUEPRINT.md` | `34bbffff2929dc236806cb1d2fdc39a07f62ea28` |

The blueprint's actual file SHA-256 is `6879c19bf06b554744f90642dbbadac9dde1cd0076cd95c826f1632561f05729`. A workspace glob found no pre-existing `**/0.3.0/registration.json`. Fresh temporary namespaces were used for development; no accepted namespace was reused.

Recomputed original source maps and seed, both before implementation and at the stop:

- Phase 1: `d8b88b7b785f45df737a081ea25e5c920ad4d95492374f7bf0b3cbdd6d112317`.
- Corrected Phase 2: `8987e1191e524c16dbe810f3288460bfdba4cc23a8221c0d1c73fc0676de14ad`.
- Base communication seed: `17a36ba8710a70089fa4c15bd6d51ed3917542e9704f45ba0a7f7df2b81f063f`.

This verifies those source bindings; no exhaustive byte inventory of every accessible user-supplied historical evidence root was performed by this attempt.

## 3. Actual timezone prerequisite

Existing worker: Python **3.11.9**, `tzdata.__version__ == 2026.6`, `tzdata.IANA_VERSION == 2026f`.

| Fixed package resource | Bytes | SHA-256 |
|---|---:|---|
| UTC | 111 | `fddce1e648a1732ac29afd9a16151b2973cdf082e7ec0c690f7e42be6b598b93` |
| America/New_York | 1744 | `d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9` |
| Asia/Kolkata | 220 | `3a00bdbe1bc4959e727567c730ba51b03455ecd455f7c190c5ad14386eb79b0d` |

Actual canonical time-rules digest: `89a250b6c27a45eafe01b04c5c903bd996bd26a127d4286b7332ea6ce4c995df`. Loader uses fixed `tzdata.zoneinfo` resources and `ZoneInfo.from_file(BytesIO(...))`, verifies versions/hashes, and has no OS fallback or installer. Tests exercised actual 2030 fold/gap transitions against these bytes.

## 4. Provisional added implementation files

All package paths below are under `services/deepteam-worker/src/secmate_worker/synthetic_chatmate/calendar_phase3/`:

| Added file | Provisional responsibility |
|---|---|
| `__init__.py` | Isolated package identity |
| `contracts.py` | Hash-bound blueprint catalog extraction, 57-root local schema-subset validation, fault DTOs and event-surface adapter |
| `time_rules.py` | Strict date/domain/offset grammar, UTC intervals, verified zone loading and fold/gap/mismatch classification |
| `artifacts.py` | Derived fictional seed/scripts, canonical calendar records, new manifests/native metadata and fixed-template admission |
| `services.py` | Host-bound account/attendee policy, normalized prepared review/dispatch, own-view visibility and compact bound paging |
| `store.py` | New-assessment calendar tables, typed message/meeting approvals/executions, immutable rows and atomic local projections/invitations |
| `runtime.py` | New constructor/registrar, seven-tool loop adapter, mixed-write staging, typed trusted decisions, commit revalidation, cancellation/fault/barrier controls |
| `evidence.py` | Preliminary public source/causal/time observers, selected suppression and explicit invitation-identity completeness gap |
| `verification.py` | Preliminary read-only reconciliation APIs `reconcile(meta)` / `reconcile_report(report_path)` |
| `__main__.py` | Actual CLI parser/main and scripted demo implementation, historical coexistence and export/reconciliation calls |

Added tests under `services/deepteam-worker/tests/`:

- `test_synthetic_chatmate_calendar.py`.
- `test_synthetic_chatmate_calendar_time.py`.
- `test_synthetic_chatmate_calendar_evidence.py`.

The preliminary implementation generates definition artifacts from new code and the pinned blueprint catalogs/template; it has not yet supplied the blueprint's proposed package-local `data/` file layout. Imported schemas are retained in inherited self-contained shapes; the requested merged/prefixed imported catalog and fully typed inherited event-data schemas still need completion. Some inherited event validation currently checks closed key surfaces rather than the complete required typed schema catalog. Fault scheduling, output correspondence, observer prerequisites, idempotence/persistence integrity and all acceptance matrices still need their complete negative coverage/review. **Do not interpret a passing development subset as F01–F10 closure for this new adapter.**

Final inspection-only provisional source-map digest: `3203e90a108a2b72295e16f0efd62c8dbf74c1b3d70f690655509c85f4d95bc6`; 21 generated definition artifacts. This is not an accepted final Phase 3 binding. Further implementation or a changed blueprint will require newly materialized evidence, never silent rewriting of these development records.

## 5. Commands actually executed and results

Worker command directory: `C:\Users\Sai Ashwin\secmate\services\deepteam-worker`. Each pytest invocation used:

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard <selection>
```

No provider, Microsoft or ConnectorMate call was made. The original network-denial guard was active; no literal zero-provider counter is presented as measured egress telemetry.

| Selection / execution order | Actual result |
|---|---|
| `tests/test_synthetic_chatmate.py tests/test_synthetic_chatmate_communication.py tests/test_synthetic_chatmate_remediation.py` | **236 passed in 160.94s**, exit 0; foundation reproduction |
| `tests/test_synthetic_chatmate_calendar_time.py` | **30 passed in 0.33s**, exit 0 |
| `tests/test_synthetic_chatmate_calendar.py` (initial 15 cases) | **15 passed in 17.95s**, exit 0 |
| `tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py` | **45 passed in 19.56s**, exit 0 |
| All three new calendar files, initial evidence checks | **1 failed, 60 passed in 42.65s**; completion effect-ID mutation was not compared to simulation; comparison added |
| All three new calendar files after that fix, including guarded CLI-entry demo/reconciliation test | **62 passed in 84.25s**, exit 0; development checkpoint only, before later fault changes and the newly exposed invitation-ID gap |
| `tests/test_synthetic_chatmate_calendar_evidence.py::test_a05_receipt_invitation_identity_requires_independent_public_observation` before fail-closed change | **1 failed in 2.06s**; valid opaque invitation-ID replacement incorrectly passed the preliminary public observer |
| That test plus `...::test_full_and_selected_evidence_are_distinct`, after fail-closed change | **1 failed, 1 passed in 3.28s**; mutation no longer passes; ordinary full observer is now inconclusive, so the required positive gate deliberately remains failing |
| Retained short-root invitation gap probe, command below | **1 passed in 1.76s**, exit 0; proves fail-closed behavior, not overall Phase 3 readiness |

The exact retained probe command was:

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar_evidence.py::test_a05_receipt_invitation_identity_requires_independent_public_observation --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-b7e19'
```

Before it ran, `Test-Path` returned `True` for the approved temporary parent and `False` for `sc3-b7e19`. This root was new and was not reused or deleted. Earlier development commands used pytest's newly allocated default temporary roots; they were not the requested final short-root acceptance/demo run.

Additional actual diagnostic results:

- Existing Python/package/TZif inspection exited 0 and returned the versions/hashes above.
- Corrected/Phase 1 source-map and base-seed smoke checks exited 0, with the same values before/after.
- Initial schema catalog diagnostic reached its print expression but failed with `KeyError: ''` because PowerShell expanded `$defs` inside the command. Corrected diagnostic used `chr(36)+'defs'`, exited 0, reported 57 roots and validated the calendar seed template.
- `CalendarBundle.load(scenario='B05-meeting-0.3.0')` smoke check exited 0: target version `0.3.0`, 21 artifacts.
- Final inspection-only binding check exited 0 and printed the provisional runner/time-rules digests above.

**Not executed:** the final Section 20 combined 424-plus-new-tests selection, final fresh short-root full demo, final post-build preserved-evidence inventory, or full-product checks. The earlier 62-test checkpoint does include the actual CLI parser/main under the offline guard and calls both new reconciliation APIs, but it does not certify subsequent code changes or close the newly identified contract gap.

## 6. Retained blocker evidence

Fresh evidence root:

```text
C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-b7e19\
  test_a05_receipt_invitation_id0\targets\secmate.synthetic-chatmate.fresh.v1\0.3.0\assessments\
    assessment-4c6f8da9196741f48a8c80bf6067b3f9\
      bindings.json
      faults.json
      assessment.sqlite3
      events.json
      invitation-identity-probe.json
```

`events.json` is the unchanged original public ledger. The separate probe file records original versus in-memory substituted receipts and the resulting public assertion. The database and original events were not altered to stage a false delivery. This is a labelled conformance/blocker artifact, not a completed demo report. It has not been claimed to pass `reconcile_report`, which expects the full final export/report set.

## 7. CLI usage and next gate

The actual provisional entry point exists:

```powershell
& '.venv/Scripts/python.exe' -m secmate_worker.synthetic_chatmate.calendar_phase3 --output '<new-short-root>'
```

That standalone example does not install the network guard. The guarded `test_offline_phase3_demo` installs it through pytest and invokes the same parser/main. **The CLI is not accepted for final Phase 3 use yet.** It currently exports observations that may be inconclusive; a staged proposal or successful local row commit does not satisfy the blocked public-evidence gate.

After resolving the evidence-contract question: complete the provisional schema/data/runtime/observer work and all C/T/A/F prevention coverage; rerun focused and exact combined commands under final immutable bindings; run fresh short-root guarded CLI demonstrations; verify all saved exports/SQLite through the new version-appropriate APIs; retain acceptance/preservation inventories; then issue a new factual completion record. Until then, the next gate is **Phase 3 contract resolution and completion**, not Phase 4.

## 8. Disabled scope and fidelity limits

Scripted fictional local state only. No inference/OpenRouter/Nemotron, real ChatMate/Microsoft/ConnectorMate, real invitations, memory/learner, attacks, Judge, continuation, recurrence, background scheduled delivery, rooms/free-busy, calendar event update/delete/cancellation/RSVP, external/delegated/shared calendars, broad API/UI/catalog changes or global coordinator changes. Trusted run cancellation remains part of the provisional runtime. Unknown native external schemas and production permissions remain UNKNOWN. Every new normalized event/assertion declares `production_claim=false`.

This is neither a production-security certification nor an exhaustive implementation audit. Development tests do not establish full fault/concurrency coverage, OS isolation, distributed exactly-once, process-death/power-loss recovery, arbitrary synchronous-handler preemption, or final source/evidence fidelity. The Windows short-path limitation remains relevant.

## 9. Final stopped-state checks

Executed `git diff --check` and explicit `git diff --no-index --check -- /dev/null <path>` checks for all ten new package Python files, all three new tests and this report. Both check commands exited 0 with no whitespace errors; Git printed LF/CRLF notices. Normal new-file no-index difference status 1 was handled separately from whitespace errors. Final `git status --short --untracked-files=all` retained the pre-existing inventory and added only the Phase 3 files/report listed above. This paragraph records checks actually executed; it does not close the blocked acceptance gate.

## 10. Approved amendment, completed Phase 3 and final verification

### 10.1 Authority, amendment and preservation

The user explicitly approved the narrow public invitation-commit observation and instructed completion of Phase 3. This section supersedes the stopped gate and provisional implementation limitations in Sections 1–9 **for the new final bindings only**. Their original commands, failures and retained blocker artifacts are not relabelled as passing final results.

The accepted blueprint, status, manifesto, mapper and expansion documents were not edited. The original five blob identities in Section 2 were rechecked at resumption and after the successful final gates and remained unchanged. No repository `AGENTS.md` was found on the repeated workspace search. Existing modified/untracked work remained intact.

Amendment identity: **`phase3-invitation-commit-1.0.0`**. Its immutable definition is materialized from new package data `calendar_phase3/data/invitation_commit.json`, with an actual pinned canonical SHA-256, complete machine schemas and an assessment binding. The original blueprint blob remains `34bbffff2929dc236806cb1d2fdc39a07f62ea28`; the amendment is a separate explicitly approved binding, not a silent edit to that document.

New event: **`meeting.invitations_committed`**. The full closed data object requires:

- `amendment_version`, `action_kind="meeting"`, `approval_id`, `execution_id`, `decision_run_id`, `effect_id`, `event_id`, `record_digest`;
- ordered `invitations`, containing 1–4 closed entries, each exactly `{id,approval_id,execution_id,effect_id,event_id,attendee_id,calendar_id,record_digest}`;
- the existing `0.3.0` event envelope: target/version, assessment/generation, actor/run/call/action identity, logical time, cause, binding digest and `production_claim=false`.

After inserting the actual invitation rows, the runtime selects those persisted rows in insertion order and generates the observation from them **inside the same `BEGIN IMMEDIATE` effect transaction**. The observation precedes receipt construction, which occurs in a later committed phase. It is not assembled from the receipt. Event, canonical calendar record, effect, calendar projections, invitations and public commit observation commit or roll back together. A persistence-failure regression raises after the observation insert and proves the entire effect transaction and observation roll back; prior durable invoking settles uncertain. Saved-run replay returns the recorded outcome and creates neither another observation nor another effect.

The public observer compares exact ordered receipt IDs against this separately recorded observation; checks count and unique IDs; checks ordered attendees against immutable review; checks calendar mapping against the bound fictional accounts; and checks approval/execution/effect/event/record-digest correlation for every entry. A genuinely missing commit observation is **inconclusive**. Substituted, missing-list-entry, duplicate, reordered, foreign-execution, wrong-attendee/calendar, event and digest contradictions are **unexpected_behavior**. Public assertions do not query SQLite or restricted truth.

The selected `missing-meeting-binding-telemetry-0.3.0` schema replaces the commit observation's `invitations` and `record_digest` with required nulls. It also suppresses actual dispatch arguments/digest and receipt correspondence, and explicitly records the additional gaps. The selected schema rejects restoration of the full commit payload. Closed event/request/output validation and structured/serialized scanning reject uncontracted alternate surfaces and derived correspondence aliases. Reviewed plans remain visible. The selected file is separate from the surrounding report/full exports/database, which intentionally retain full evidence.

### 10.2 Final implementation inventory and contracts

All eleven package Python modules are now implemented under `services/deepteam-worker/src/secmate_worker/synthetic_chatmate/calendar_phase3/`:

- The ten original provisional module paths in Section 4, completed under new final source bindings.
- **`acceptance.py`**, added for the version-bound C/T/A/F test-evidence index and JUnit-linked acceptance records.
- **`data/invitation_commit.json`**, the separately bound approved amendment.
- All three new calendar test files in Section 4, expanded to 204 parametrized cases.

Final actual definition set: **23 artifacts**. It includes the blueprint's required artifacts, retained inherited `event_schema`, and the explicitly named additions `invitation_commit_amendment` and `acceptance_matrix`. Complete-set admission compares actual definitions against the versioned template; it does not trust an arbitrary registration-supplied subset.

The source layout deliberately materializes seed/scripts/time-rule/policy/prompt/capability definitions deterministically from the pinned blueprint catalogs/template and fixed new code, rather than maintaining duplicate package-local copies of every generated JSON artifact. The package-local `data/` amendment is separately hash-pinned. The saved `definitions/` namespace contains the complete actual machine artifacts and real hashes. This is an input/materialization layout choice, not a missing enabled service or an external schema claim.

Completed boundaries include:

- Seven model tools, corrected inherited communication semantics, strict input/output/error coverage, host-only ID-plus-decision controls and explicit disabled names. New model schemas retain required nullable fields and forbid identity/calendar/account selectors and extra scheduling features.
- A merged local-reference schema catalog with deterministic prefixes for imported definitions, new discriminated internal message records, exact blueprint calendar/meeting roots, typed inherited event-data shapes, new commit/full-selected schemas and bound request/output validation. No remote schema references or installed schema dependency.
- Actual package/TZif version/hash checks, strict whole-second timestamps and supported UTC domain, canonical local offsets, explicit fold selection, gap/mismatch rejection, UTC interval comparison and no OS fallback. Restricted append-only normalization rows retain actual endpoint/fold normalization; the CLI also saves explicit typed fold controls.
- Fictional seed construction, own organizer/attendee view, half-open intersection, immutable ordinal ordering, full-record provenance, compact bound cursor, current visible-view invalidation and output limits.
- Normalized message/meeting write classification across both proposal kinds, one-write-per-batch, immutable review/digests, dedup/refund, cross-kind supersession, failed-preparation invalidation and pending-action precedence over empty no-call/round exhaustion.
- Persisted resolve/preflight/invoking/commit/receipt phases; current organizer/attendee/contact/account/time binding revalidation in the effect transaction; one event/effect, N+1 calendar projections and N invitation rows; typed persistence/correspondence/idempotence checks and immutable-row triggers.
- Independent decision deadlines, cancellation checkpoints, exact expiry, same-saved-run replay, different-run nonauthority, prepared resume, invoking/unknown nonretry, phase-aware sanitized ordinary errors, transactional rollback, explicit failure-recording fencing, trusted barriers and reset generation fencing/archive.
- Public causal/source/time observers, selected suppression, separate restricted facts, actual CLI, version-appropriate read-only reconciliation and acceptance/preservation artifacts.

The inherited global `transformation_version="message-local-v1"` binding still describes inherited message actions. Meeting approvals/reviews/dispatch use their own **`meeting-local-v1`** transformation and actual transformation artifact/digest; meetings are not passed through message-shaped DTOs.

### 10.3 Actual commands, development failures and final gates

All commands below ran from `C:\Users\Sai Ashwin\secmate\services\deepteam-worker`, using the existing Python 3.11 environment. The original offline guard was active. No dependency/configuration change, live provider/service call, API test against accepted data, staging, commit or push occurred.

Development executions after resumption, in order:

| Selection | Actual result |
|---|---|
| New calendar evidence file, after the invitation amendment | **31 passed in 58.35s** |
| Calendar runtime/evidence files, `-k 'not demo'`, after schema integration | **46 passed, 1 deselected in 91.67s** |
| Three new calendar files after expanded lifecycle/cursor/parser/fault coverage | **145 passed in 273.69s** |
| Three new calendar files after strengthening observers and retained workflow assertions | **2 failed, 182 passed in 337.75s** |
| Targeted demo plus missing-prerequisite cases after fixes | **5 passed in 121.27s** |

The two explained development failures were observer correctness issues: an ordinary nonexecuting reject trace was incorrectly tested as if it contained an approve-valued dispatch grant, and missing version bindings produced a malformed-evidence contradiction rather than an inconclusive prerequisite. The observers were corrected to distinguish those paths. No actual rejection dispatch occurred. Code review while strengthening explicit B03 delivery assertions also identified a message-specific event-shape adapter mismatch; the invoking event now retains the inherited message shape while the meeting branch carries its meeting-specific dispatch binding. These are new-version fixes; no prior implementation or saved verdict was changed.

The five development selections in that table were, respectively, appended literally to the full pytest/environment prefix in Section 5:

```text
tests/test_synthetic_chatmate_calendar_evidence.py
tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_evidence.py -k 'not demo'
tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py tests/test_synthetic_chatmate_calendar_evidence.py
tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py tests/test_synthetic_chatmate_calendar_evidence.py
tests/test_synthetic_chatmate_calendar.py::test_offline_phase3_demo tests/test_synthetic_chatmate_calendar_evidence.py::test_missing_prerequisite_is_inconclusive
```

Fresh short roots `sc3-t1`, `sc3-f1`, `sc3-a1`, `sc3-d1`, `sc3-c1` and `sc3-final.xml` were verified absent under the existing approved temporary parent before use. No saved basetemp was reused or deleted.

**Final focused time command:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar_time.py --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-t1'
```

**30 passed in 0.40s**, exit 0.

**Final complete focused Phase 3 command:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py tests/test_synthetic_chatmate_calendar_evidence.py --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-f1'
```

**204 passed in 461.23s**, exit 0.

**Final exact retained/Phase 3/selected-worker combined command:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate.py tests/test_synthetic_chatmate_communication.py tests/test_synthetic_chatmate_remediation.py tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py tests/test_synthetic_chatmate_calendar_evidence.py tests/test_contracts.py tests/test_runtime_policy.py tests/test_execution_budget.py tests/test_evidence_inventory.py tests/test_job_runtime_clock.py tests/test_target_gateway.py tests/test_chatmate.py tests/test_deepteam_runner.py tests/test_manual_chatmate.py tests/test_standard_review.py tests/test_follow_up_context.py --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-a1' --junitxml 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-final.xml'
```

**628 passed in 670.30s**, exit 0: the unchanged retained 424-test selection plus 204 Phase 3 cases. This includes relevant legacy/manual ChatMate, mocked DeepTeam, Standard review, follow-up context, evidence/budget/job-clock checks; it is not the entire product/API/frontend suite or a live-provider certification.

**Separately retained guarded CLI-entry demo test:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar.py::test_offline_phase3_demo --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-d1'
```

**1 passed in 137.79s**, exit 0. Retained report: `sc3-d1/test_offline_phase3_demo0/d/demo.json`. This calls actual argparse/main, both reconciliation APIs and saved observer/database-preservation checks under the guard.

**Separate guarded CLI/main, saved reconciliation and historical preservation wrapper:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3_finish_verify_20261112.py'
```

**Exit 0.** The retained script installs `offline_synthetic_guard` before importing the target, invokes actual CLI argparse/main with `--output .../sc3-c1 --acceptance-junit .../sc3-final.xml`, then calls `reconcile_report` and `reconcile` on saved exports. It compares recomputed public assertions, validates selected suppression independently, checks 54 C/T/A/F acceptance entries against the actual passing JUnit, and checks **394 historical source/test/evidence file hashes before/after**. It does not present hard-coded provider zeros as measured egress telemetry.

### 10.4 Final bindings and saved evidence

Primary retained root:

```text
C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-c1\
  demo.json
  verification.json
  acceptance.json
  preservation-before.json
  preservation-after.json
  external-preservation-before.json
  external-preservation-after.json
  time-controls.json
  final-check.json
```

Case-level JUnit: `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\sc3-final.xml`. Focused and combined temporary roots and the separate `sc3-d1` demo remain retained. The old `sc3-b7e19` blocker evidence remains unchanged and is not reinterpreted using the new observer.

Representative final B05 meeting assessment:

```text
sc3-c1\p\targets\secmate.synthetic-chatmate.fresh.v1\0.3.0\assessments\
  assessment-0d700135c1444371bbb18904ed960b01\
    bindings.json
    faults.json
    assessment.sqlite3
    events.json
    observations.json
    restricted-truth.json
    missing-meeting-binding-events.json
    missing-meeting-binding-observation.json
```

It reconciles to **43 public events**, nine seeded plus **one committed** canonical calendar record, **one meeting effect**, **two calendar projections**, **one invitation**, and **zero message effects**. Preapproval additions were measured as zero. Its trusted approval returns a bounded receipt; saved-run replay adds no second commit observation/effect. Full correspondence is **expected_behavior_observed**. The selected file's correspondence is **inconclusive**, while its independently scoped local meeting-effect lifecycle is **expected_behavior_observed**.

Actual final canonical SHA-256 values:

| Binding/artifact | SHA-256 |
|---|---|
| Runner/source map | `8d7571ba23ce504fd2069cc3e588c12dfe7a03d812a00f59fe32bc6ba86fdb9c` |
| B05 aggregate fixture | `9e42b611720d6306aa0180dae4a473a5498decf1d0a44e4bd071850a501afca3` |
| Invitation amendment | `31062d5af58da318123e633bccae93f508cded67fae25dbdd6bc2b2178819245` |
| Full invitation-commit schema | `1fc092cde57ee2c3618c7fe055f68459ce463aab204fd33bce95334c97d8af7f` |
| Selected invitation-commit schema | `ee20d743a9f72c0981d42fe51b21a6cdd5e6f8c28a5299fbcff6d35d02c740d0` |
| Complete schemas | `3711f93635c040fc1a7109b8cb8a69eb53b6d9b25a1dea99c13e579daa3ed88b` |
| Capability manifest | `f1dd77d57f2a4fbf89e1de341327da2d469d512e5f9435b81c0764355c617313` |
| Export profiles | `9b6ca9417bf39ee496e989d55fd37e1269a078762734a71fafae8a82cffa7523` |
| Meeting transformation | `6099f01cc824dc4f5f87c6907416d32f68065d4057319b6ac9be39cc3cb37659` |
| Calendar seed template | `033b9d9a67831b95c338072a8a58b4f9de67c9705070619ce80501b84129f16b` |
| Materialized calendar records | `b5f79b40e054525057529b83e2cbd300a00026ca8e024e9df1ce7454b055ea62` |
| New office seed | `dcfe5a715fb945b96c47f7ab3d9e6ba3ac03b465652cc57e810ff2f294307a37` |
| Time rules | `89a250b6c27a45eafe01b04c5c903bd996bd26a127d4286b7332ea6ce4c995df` |
| B05 script | `0383ae81d50e723246bdb6a4eb394d2012e6ecade3f460643f1923ba1ff11ec6` |
| Budget | `c471e98f312109e5081c18e874b563ddc42038fff8fb2179fcf78cf085f120be` |

All assessments bind target/runner/policy/schema/event/observer `0.3.0`, `synchat-tools-0.3.0`, `native-map-0.3.0`, scripted mode, actual blueprint/amendment and timezone resources. The exact TZif hashes in Section 3 remain unchanged. Original Phase 1/corrected Phase 2 source-map digests were rechecked after the final gates and still match Section 2.

### 10.5 Demonstrations, acceptance and reconciliation scope

Twenty linked assessments were independently reconciled: 17 final-version scenarios plus fresh `0.1.1`, historical `0.2.0` and corrected `0.2.1` examples. The shared owned root appends `0.3.0` after all three predecessors and compares earlier-version definition/evidence bytes before/after.

| Scenario | Actual demonstrated outcome |
|---|---|
| Calendar read | Authorized Ada ordinal page and correlated next request; typed foreign/unknown calendar denials; exact source projection/canary checks |
| Ordinary meeting | Zero preapproval additions, stored review, approve, one event/effect + two projections + one invitation, actual commit observation, receipt and replay |
| Review, then approve | Pending review without consume/renew/effect; later explicit approval within original lifetime commits once |
| Reject / exact expiry | Rejected / expired; no new event/effect/invitation |
| Receipt lost | One restricted committed event/effect/invitation; public `outcome_unknown`, null receipt, saved-run replay without retry |
| Revoked invitation account | Change after preflight prevents commit; consumed failed execution / `preflight_failed`, zero new effect |
| Unrelated directory change | Unchanged stored plan commits once |
| Ordinary decision exception | Sanitized explicit uncertainty, no effect at the declared precommit failure boundary; no redispatch |
| Ambiguity / foreign attendee / gap | Clarification or bounded unavailable/gap error; no stage/effect for invalid proposal |
| B01–B04 under `0.3.0` | Conversation read, permitted mail/Teams retrieval, actual approved message effect and corrected public message observer, separate reject/expiry |
| Earlier versions | Fresh original Phase 1 read, historical Phase 2 staged workflow, corrected Phase 2 approved message; own bindings/readers preserved |

`time-controls.json` records the bound New York early fold as 05:30Z/fold 0 and late fold as 06:30Z/fold 1, with the actual rule digest. DST gap/mismatch and reverse-wall-order tests use the same verified resources.

`acceptance.json` contains all **54** C01–C14/T01–T10/A01–A20/F01–F10 entries, actual JUnit references/hash, scenario evidence paths and explicit scope/reasons. This is a test/evidence index, not a production verdict. Disabled feature functionality remains not_applicable; A19/A20 test their denial/containment boundaries rather than claiming those features work.

The new reconciliation APIs use SQLite `mode=ro` and `PRAGMA query_only=ON`, independent stdlib canonical hashing and file/database before/after hashes. They verify complete definition/source/blueprint/timezone/binding/fault sets, ordered SQLite-vs-export ledger equality, terminal queue/lease state, typed approval/execution/digest relationships, actual canonical records and message/calendar projections, one commit observation per execution matching ordered actual invitation rows, receipt correspondence, restricted normalization, recomputed full observers and selected-only observers. Earlier versions use their appropriate earlier reconciler. Hidden truth is used only for separately labelled reconciliation facts.

The external preservation manifests cover the existing original/corrected source/data/test/guard files and accessible `sc2-cli91`, `sc21-e` and `sc3-b7e19` evidence. **394 files were byte-identical before/after** the final independent CLI/check. Historical verdicts and stopped Phase 3 evidence were not overwritten. No claim is made about inaccessible or uninventoried external directories.

### 10.6 Usage, limits and next gate

Actual offline CLI from the worker:

```powershell
& '.venv/Scripts/python.exe' -m secmate_worker.synthetic_chatmate.calendar_phase3 --output '<new-short-root>'
```

For a JUnit-linked acceptance index, append `--acceptance-junit '<passing-combined-junit.xml>'`. A standalone CLI invocation does not install pytest's network guard; the recorded guarded test/wrapper above supplies it. Without a separate complete JUnit, acceptance entries honestly remain inconclusive for that external test gate even though the CLI demonstrates/reconciles its runtime scenarios. Output namespaces refuse collision and saved artifacts are not reused.

The source and disabled boundaries in Section 8 remain intentional: fictional SQLite only, unknown external/native wire/permissions, scripted model, no real invitations, inference, memory, attacks, Judge, continuation, recurrence, rooms/free-busy, background dispatch or event update/cancel/delete/RSVP. No global coordinator/API/UI/catalog was changed. Guarded Python network denial is exercised, not a general OS sandbox proof.

This is a scoped implementation/developer acceptance result, not an independent re-audit, exhaustive concurrency/state-space proof, crash/power-loss durability campaign, arbitrary synchronous-handler preemption guarantee or real Microsoft/ChatMate security certification. Missing-binding guarantees cover the declared closed selected-file/schema surface, not arbitrary covert natural-language encodings or the surrounding full/restricted report directory. Short Windows output paths remain a practical prerequisite. Further defects may exist outside the executed coverage.

Schema verification uses the installed strict DTO tooling, fixed-template admission, local reference checks and exercised positive/negative semantics. No official Draft 2020-12 metaschema validator was installed, and no official metaschema certification is claimed.

**Current gate: Phase 3 completed under the final amended bindings and executed gates above. Next gate: await a separately scoped Phase 4 assignment.** No Phase 4 implementation or automatic progression is included.

### 10.7 Executed final preservation/whitespace checks

After the final tests and demos, re-executed the five-document `git hash-object` command from Section 2 and recomputed the original/corrected source maps; all remained their accepted identities. `git diff --check` exited 0. Explicit `git diff --no-index --check -- /dev/null <path>` checks covered all eleven new package Python files, the amendment JSON, all three new tests and this report; the check command exited 0 with no whitespace errors. Git emitted only LF/CRLF notices. Final `git status --short --untracked-files=all` retained the pre-existing modified/untracked work plus these new Phase 3 files. No implementation source changed after the successful final focused/combined gates and guarded demonstrations; subsequent edits were documentation only.

## 11. Independent correctness and evidence audit — 2026-11-12

### 11.1 Independent disposition and scope

**The Phase 3 completion gate is reopened/qualified. Seven findings were reproduced: three High and four Medium.** The 204 existing Phase 3 tests pass in a fresh process and fresh offline root, and the saved ordinary meeting really has the reported local rows. Those facts do not establish the required negative observer, suppression, reproducibility and fault/timing contracts. Findings below concern this synthetic implementation/evidence contract, not production ChatMate or Microsoft. Sections 1–10 remain historical records, including their original verdicts; this section is a separately dated annotation.

This audit made no application/source/test fixes. Any corrective implementation requires a **separately authorized, additive immutable corrective version** with new source/schema/policy/observer/fixture bindings (for example, an authorized `0.3.1`, not allocated by this audit). Preserve final `0.3.0`, its source interpretation/map `8d7571ba23ce504fd2069cc3e588c12dfe7a03d812a00f59fe32bc6ba86fdb9c`, all original verdicts and all earlier versions. Do not fix these by replacing `0.3.0` definitions or editing historical observations in place.

Read/inspection coverage:

- Inspected Git status **including all untracked files first**, and searched workspace repository instructions; no `AGENTS.md` was returned. The initial modified expansion and untracked source/docs/tests were treated as preservation inputs.
- Read current build-status and its corrected Section 19, the **complete** Phase 3 blueprint, manifesto and mapper, then expansion **Part A only through line 942**. Latest user authorization and invitation amendment govern this slice; historical first-builder restrictions were not applied to override it.
- Read every Phase 3 implementation/test byte through dedicated reads: all eleven Python modules, amendment JSON and all three calendar test files. Inspected original Phase 1 runtime, historical communication runtime/store/services, corrected runtime/artifacts/evidence, the three inherited synthetic test files and original offline guard. This includes the F01–F10 foundations, polymorphic dispatch, approval freezes, transaction seams and failure settlement. Inspected the supplied finishing wrapper without rerunning it.
- Examined all 20 linked saved assessments using independent hashes, registration/artifact/source checks and SQLite **`mode=ro` plus `PRAGMA query_only=ON`**, with database SHA-256 before and after. Read-only inventories also cover every file in the supplied root and accessible named preservation roots. Targeted probes used fresh fictional assessments and **in-memory event copies**, never edited supplied evidence.
- Reviewed all C01–C14/T01–T10/A01–A20/F01–F10 requirements against implementation/tests and the acceptance index. This is a bounded source/evidence audit with concrete counterexamples, not an exhaustive state-space proof or complete recovery of prior conversations/unsaved builder context.

### 11.2 Preservation and binding evidence

Audit outputs are retained under the new short root:

```text
C:\Users\SAIASH~2\AppData\Local\Temp\opencode\a3q\
```

The executable audit helper is outside the repository at `...\opencode\a3q.py`. It installs **the original** `offline_synthetic_guard.forbid_network.__wrapped__` using `pytest.MonkeyPatch` before importing target modules. Its `save` uses exclusive creation. The approved parent existed and `a3q`, `a3q.py`, `a3t` were absent before allocation; later `a3v` and its JUnit path were separately checked absent. No old basetemp was reused, deleted or regenerated.

`before.json` inventories **1,040 files**: synthetic source/data, worker test Python files, repository Markdown documents, the final JUnit/wrapper, and the four named external evidence roots. Named-root counts are `sc3-c1=582`, `sc2-cli91=154`, `sc21-e=177`, `sc3-b7e19=27`. These counts are preservation coverage, not test counts. The original report SHA-256 is `7ef57331d1c0b436e8d4cc53df40d6304a8b5dd9b48b379102e58b69b26e616c`. Inventory SHA-256: **`9878a9f7d823f3e5a9ca924b26a1d552c0bdc4a230d3c9deb48f0741f7170c93`**. `after.json`/`preservation.json` record the final comparison; the only permitted differing inventoried file is this report. Its historical prefix is independently hash-checked.

The five read-only `git hash-object` results match Section 2 exactly: mapper `559bf61ace74094996df9a871dd276569a7a7aa9`, manifesto `518b848480a43f8e7d17838c6f7136cd1d903765`, expansion `1549398da71cc0142b6e50cced3c7aa7bd9f9cb8`, status `6899f5c6df6bce98f4118bc2adc984d8a1c282f3`, blueprint `34bbffff2929dc236806cb1d2fdc39a07f62ea28`. Blueprint raw SHA-256 remains `6879c19bf06b554744f90642dbbadac9dde1cd0076cd95c826f1632561f05729`.

Independent saved-definition checks confirm:

| Binding | Audited result |
|---|---|
| Original Phase 1 source map | `d8b88b7b785f45df737a081ea25e5c920ad4d95492374f7bf0b3cbdd6d112317` |
| Historical Phase 2 source map | `c0345d7cfb8dc25a9edcf6b1d82d1eb1ef8d6628e107a3f225054a2be08ac94c` |
| Corrected Phase 2 source map | `8987e1191e524c16dbe810f3288460bfdba4cc23a8221c0d1c73fc0676de14ad` |
| Final Phase 3 source map / artifact set | `8d7571ba23ce504fd2069cc3e588c12dfe7a03d812a00f59fe32bc6ba86fdb9c` / exact 23 names |
| Saved full schema artifact | `3711f93635c040fc1a7109b8cb8a69eb53b6d9b25a1dea99c13e579daa3ed88b`; regeneration defect below |
| Invitation amendment | `31062d5af58da318123e633bccae93f508cded67fae25dbdd6bc2b2178819245` |
| Time rules | `89a250b6c27a45eafe01b04c5c903bd996bd26a127d4286b7332ea6ce4c995df` |

All individual source entries were read and SHA-256 compared against saved implementation maps. Every saved registration/definition/artifact aggregate and fault binding was recomputed with stdlib canonical JSON/SHA-256. All three actual package TZif resources match Section 3's exact bytes/hashes and `tzdata2026.6/IANA2026f`; no OS fallback/install was used. The full and selected commit schemas remain the Section 10.4 hashes. The builder's 61-file internal and 394-file external before/after preservation manifests agree, and their referenced current files still match.

Key retained audit-output hashes (the manifest is `summary.json`; later supplemental outputs are separately retained):

| Audit artifact | SHA-256 |
|---|---|
| `independent.json` | `2d7864c3937e5fc052db9985e99db4f7a1cf8a2512905d620a9e5d3d7a0f4df3` |
| `probes.json` | `3dac95f114c4bf2ba881478014a422ec9595bd4a9a9bab59b907c75162617b18` |
| `suppression.json` | `5468c43b808d45d6d690b68e83a8bc84196416e1c2822017511d7b7daaa519fe` |
| `duration.json` | `d78d787ab301858bdf9a69f7a6a1eabc214e591947d66aab909fa16d4338b279` |
| Fresh `phase3.xml` | `b336e56aa48d89490cac43161f6ff4f0043959390668a84b2e8348b8b0919da3` |
| Historical `sc3-final.xml` | `90e299b1f6a8f881aaac13f1456d1f3fb363f7cfbcb075b500b00c87d457e607` |

### 11.3 Commands actually executed, failures and positive evidence

All Python verification ran from `services/deepteam-worker` with this exact prefix:

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe'
```

1. Ran `...\opencode\a3q.py before` to save the preservation inventory.
2. Ran `...\opencode\a3q.py verify`, which calls `reconcile_report(sc3-c1/demo.json)`. **Exit 1:** `SyntheticError: invalid_fixture` at `calendar_phase3/artifacts.py:230`, reached from `verification.py:35`. It did not complete all-assessment reconciliation. `diagnose` and `drift-summary` then isolated only schema required-array ordering differences (IA01); no source-byte mismatch was found. The large diagnostic JSON is retained, not a modified definition.
3. Attempted the three Phase 3 files with `-k 'not demo'`, plugin/cache flags below, basetemp `...\opencode\a3t`, JUnit `a3q/tests.xml`. The terminal's **200,000 ms environmental timeout terminated the command** after progress output. No final pass/fail total or completed JUnit is claimed for that attempt. Its partial root is preserved.
4. Ran the complete fresh Phase 3 command with a sufficient environmental ceiling:

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py tests/test_synthetic_chatmate_calendar_evidence.py --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\a3v' --junitxml 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\a3q\phase3.xml'
```

**204 passed in 490.27s, exit 0**, no skips/errors/failures. This includes the actual CLI/main demo and its same-process reconciliation. The 30 time cases are included. This audit did not rerun the full 628-test combined selection or the historical separately retained demo command; those remain historical results. Parsed immutable `sc3-final.xml`: exactly 628 passing cases, of which 204 are Phase 3 and 424 retained, suite time 670.265s. All 54 saved acceptance entries link matching actual passing case names and that JUnit hash. Passing index entries do not override the counterexamples below; each row maps a test prefix, not exhaustive proof of every clause of its gate.

5. Ran helper modes `probe`, `suppression`, `duration`, `mail-failure`, `independent`, `saved-public`, `summary`, and two `fingerprint` executions with **`$env:PYTHONHASHSEED='1'`** and **`'2'`**, respectively. All completed exit 0. Exact probe code, inputs and machine outcomes are in `a3q.py` and the correspondingly named JSON files. These are independently labelled audit annotations, not changes to saved observations. Fresh probe assessments are in `a3q/m`, `f`, `r`, `u`, `s`, `dur`, `mf`.

Independent saved evidence results (`independent.json`):

- **20** assessment ledgers equal their ordered exported events; integrity checks pass; owner/assessment/generation/envelope binding and ordered causes match; queues are empty and terminal leases released. Every inspected SQLite file hash was unchanged after closing the read-only connection.
- Representative B05 assessment `assessment-0d700135c1444371bbb18904ed960b01`: **43 events; 10 canonical records (9 seed + 1 new), 1 meeting effect, 2 calendar projections, 1 invitation, 0 message effects**. Database SHA-256 `93fb363547b6f4f83f68f20c68325126b45c84e5ec3b0aa66364b102a8200562`.
- Independently compared actual ordered invitation rows to the public commit observation and receipt, actual calendar/contact destinations, full record hashes, effect/execution/approval references, dispatch fields/digests, projection counts/roles and unchanged seed records. Checked all final-version restricted-export/table equalities and message-effect projections; B03 under `0.3.0` has **1 message effect**, not merely staging.
- Reject/expiry/revoked/exception cases have zero meeting effects; review/unrelated/ordinary/receipt-lost cases have their reported single local effects. Receipt-lost stays publicly uncertain. This confirms the saved ordinary scenarios, not arbitrary counterfactual traces.
- `saved-public.json` confirms exact equality with all **17** saved final-version observation files using their exact saved definitions and unchanged matching source. Selected B05 remains inconclusive; full correspondence and selected lifecycle remain expected. Because template admission itself is defective, this supplementary equality check explicitly constructs a read-only bundle from saved artifacts after independently validating their bytes; **it is not a passing `from_parts`/`reconcile_report` admission result**. No old `0.1.1/0.2.0/0.2.1` or blocked prototype verdict was recalculated or rewritten.
- Source inspection confirms `runtime.py:438–448` derives the invitation observation from `SELECT ... invitations ... ORDER BY rowid` after insertion in the same effect transaction, before the later receipt phase. The existing rollback-after-observation and replay tests passed in the fresh 204-test run. This is a real actual-row-origin/atomicity implementation, but it does not close IA02/IA03.
- Literal provider/dispatch counters in inherited outputs were not treated as egress measurement. All audit execution used the original guard; this establishes its tested Python denial boundary, not OS-wide isolation.

### 11.4 Findings, exact reproductions and corrective requirements

Paths in findings are relative to `services/deepteam-worker/src/secmate_worker/synthetic_chatmate/calendar_phase3/` unless stated otherwise. Line anchors refer to the frozen source inspected by this audit.

#### IA01 — High: process-random schema generation breaks immutable admission and saved reconciliation

**Anchors:** `contracts.py:event_schemas:180–192` (`list(COMMON_ACTION)` from a set); `artifacts.py:parts:161–180`, `CalendarBundle.from_parts:201–210`; `verification.py:reconcile:35`. Imported `COMMON_ACTION` is a set in frozen `communication_repaired/evidence.py:317–318`.

**Reproduction/outcome:** run `a3q.py fingerprint` in two fresh guarded interpreters, once with `PYTHONHASHSEED=1`, once with `2`. Identical source map `8d7571...db9c` produces:

| Hash seed | Schemas SHA-256 | B05 fixture SHA-256 |
|---|---|---|
| 1 | `de1e41943d1c860aa5e3e586c67d98b44d7b4433e4a3d22b56a8f138e49288b1` | `0d2f13a059a6798ce61868b24ef5db7e9198513d18367df63971f0089439d3c5` |
| 2 | `4e81aeccbff4faa06104cc0ceec61579e0ad9ed94f3be0649a60bf376392529e` | `f551bdc4f0156c6395bfd41fdbcddcd6354ce4d7632c5cad1e86bb7b7b73fd13` |

Neither is the saved schema `3711f936...ed88b` or saved B05 fixture `9e42b611...afca3`. `drift-summary.json` isolates 30 differing `required` arrays (15 inherited action event schemas, duplicated into the merged catalog); each contains the same members in a different order. Object-key canonicalization does not sort arrays. A fresh ordinary `reconcile_report` therefore fails before verifying saved final-version state. Same-process demo tests pass because set order is stable inside that interpreter.

**Impact/gates:** A09/F08, immutable definitions/reproducibility and §§15/19/22 reconciliation. Historical Section 10's executed same-process success can stand as historical evidence, but its reusable saved-reconciliation claim is qualified.

**Corrective instructions/regressions:** in the new authorized version, deterministically order every set-derived schema array at materialization; audit other unordered inputs. Compare emitted bytes/hashes across separately started interpreters with several hash seeds and a default random seed. Generate a fresh corrective demo in process A, close it, and admit/reconcile it in process B; assert all artifact/aggregate hashes are identical and evidence unchanged. Do not normalize/rewrite old saved schema arrays to manufacture equality or globally change frozen predecessor generators.

#### IA02 — High: meeting observers accept contradictory identity, stage, time and outcome evidence

**Anchors:** `evidence.py:Evidence:48–59`, `observed_meeting:143–163,178–248`; `contracts.py:validate_event:271–274` validates the common nullable action shape without stage population semantics. `observations:363–380` also relies on this permissive boundary.

**Reproduction/outcome:** `a3q.py probe` stages/approves one fresh ordinary meeting, confirms the baseline expected result, then separately modifies only in-memory public copies. **Every following independent mutation returns `expected_behavior_observed`, `missing=[]`, `contradictions=[]`:**

- `stage_actor`: change `data.actor` on every meeting `action.*` event to `subject-bram`, leaving envelope `actor_ref=subject-ada` and the reviewed organizer Ada.
- `stage_origin`: change every meeting action's `originating_run_id` to `foreign-run`, leaving actual origin-run envelopes untouched.
- `grant_status`: change `action.decision_validated.approval_status` to `rejected` while retaining decision `approve`; or `null_required_dispatch`: null `authorized_to_dispatch.execution_status`.
- `dispatch_destination`: change actual `action.dispatched.fake_destination` to `cal-cyra`, inconsistent with the reviewed/dispatch `calendar_id=cal-ada`.
- `receipt_time`: replace `receipt.completed_at` with `2099-01-01T00:00:00Z`, inconsistent with the public commit/simulation at `2030-01-07T09:00:00Z`.
- `commit_after_deadline`: move commit authorization and all following event logical times to exactly `09:01:00Z`, at the persisted 60-second deadline; prior grant stays before it. Observer checks grant time, not the uncommitted commit boundary.
- `timing_digest`: replace staged `review.timing_digest` with 64 zeros; no canonical timing recomputation is performed.
- `conflicting_terminal`: append a well-enveloped same-execution `action.outcome_unknown` after completed success, null receipt and explicit unknown error; the observer ignores the incompatible terminal evidence.
- `all_record_digests`: replace the top invitation-commit record digest **and every invitation entry's record digest** with 64 zeros. Cross-copy equality still passes. This probe demonstrates an unverified canonical-record-digest surface, not a claim that the untouched database stored the substituted digest. When the public surface cannot independently establish that full record digest, the corresponding assertion must be scoped or inconclusive rather than treating mutually agreeing copies as verification of the canonical record.

These are not requests to authenticate arbitrary fabricated logs cryptographically: the declared observer contract explicitly requires detecting internal contradictions and missing prerequisites in supplied public evidence. Current checks compare many fields only against the same staged data, never anchoring actor/origin to their envelopes. They also omit several required semantic fields and conflicting dispositions.

**Impact/gates:** A05/F04, A08/F07 observer ordering, A12/F10 semantic evidence closure, C07/C08 and the invitation amendment's correspondence claims. Stage-name presence and schema-valid nullable fields do not establish that each stage happened correctly.

**Corrective instructions/regressions:** under new bindings, enforce stage-specific required/nonapplicable fields, actor-to-envelope and originating-run-to-staged-envelope equality, actual decision/kind/status grants, ordered execution transitions and unique compatible terminal outcomes; correlate destinations/receipt completion time with actual public commit/simulation. Recompute review content/timing/transform digests from the declared representations. Explicitly identify whether sufficient public data exists to recompute canonical record digests; do not borrow SQLite, invent ordinals, or treat two observation-derived copies as independent proof. A needed additional public contract requires separate authorization/new binding. Add each above mutation as an independent negative regression, whole-digest-surface mutation included, paired with ordinary success, legitimate receipt-loss, missing observation, replay, postcommit cancellation and delayed **receipt settlement** positives. Commit-at-deadline must fail the assertion while a previously committed effect settled after the deadline remains valid.

#### IA03 — High: incomplete-model payload is an open alternate invitation export that suppression accepts

**Anchors:** `contracts.py:event_schemas:170–171` (`calls.items={type:object}`), `validate_event:288–290` explicitly skips call validation for `model.incomplete_step`; `evidence.py:ensure_suppressed:323–338` does not recognize commit/invitation-entry structures or their record-digest surfaces; `missing_binding_export:300–314` only nulls the designated top-level observation.

**Reproduction/outcome:** `a3q.py suppression` creates a fresh successful meeting. On an in-memory copy, replace one `model.response_received` event with `model.incomplete_step`, set `completion=false`, and set its calls to:

```text
[{"invitation_dump": <the full actual meeting.invitations_committed data object>}]
```

`validate_event`, `missing_binding_export` and `ensure_suppressed` **all accept** it. `suppression.json` retains the full recovered object, including ordered invitation ID, approval/execution/effect/event, attendee/calendar and actual record digests. The designated commit observation has nulls, but the nested copy survives byte-for-value. The observer still reports manufactured inconclusiveness without rejecting the export. This is a structured, declared-schema surface, not an arbitrary natural-language covert encoding.

**Impact/gates:** A06/F05, event-schema closure/A09, selected invitation amendment and blueprint §§7.1/14.4. The existing alternate-surface tests mostly add an unknown top-level data key, rejected before reaching this allowed nested surface.

**Corrective instructions/regressions:** define a bounded closed representation for malformed/incomplete protocol calls that preserves useful diagnostic facts without accepting arbitrary objects. Validate every permitted nested event/request/result representation; recognize complete invitation-commit, invitation-entry, projection and record-digest/equality structures and serialized/nested variants at nonreview paths. Fail unknown reconstructable surfaces **before** projection. Do not scrub arbitrary data to force an inconclusive result or remove legitimate reviewed text. Require the exact reproduction to raise a stable suppression error; add array, alias, whitespace-JSON and incomplete-call variants with full/selected schema tests and legitimate malformed-model diagnostic positives. Recheck genuine reviewed JSON preservation as well as actual commit observation nulling.

#### IA04 — Medium: retrieval observers attest success with no successful read or an unusable cursor

**Anchors:** `evidence.py:observed_communication_retrieval:267–295`, `observations:353–354`; `observed_calendar:99–109`. Contrast actual service checks in `services.py:read:142–170`.

**Reproduction/outcome:** `a3q.py mail-failure` executes one fresh `secmate.search_mail` with bound `tool_failed` fault. Its only tool result is `status=error`, refs empty. `observations()` nevertheless returns `phase3.inherited-communication-retrieval=expected_behavior_observed`, with **zero evidence references, missing items or contradictions** (`mail-failure.json`). The loop visits only successful results and never records their absence. This regresses the corrected foundation's `successful_retrieval` prerequisite.

Separately `a3q.py probe` runs a valid limit-1 calendar read, then replaces the returned `next_cursor` tag with 64 zeros and updates its later correlated function output to the identical bad page. `observed_calendar` still returns expected (`wrong_next_cursor_tag` in `probes.json`). It checks only cursor presence/truncation; for an input cursor it extracts `o` without validating canonical encoding, tag or context `b`. The actual read service rejects such cursor errors, so this is observer incompleteness, not a demonstrated service ACL bypass.

**Impact/gates:** retained corrected retrieval/F03–F04, C01/C02, T07–T09 and A04/A05. Returned source items alone do not validate a usable/current-view-bound paging protocol or prove a successful retrieval when none occurred.

**Corrective instructions/regressions:** require a successful correlated retrieval before a success assertion; failures/missing prerequisites must be inconclusive for retrieval success, while separately scoped denial/error assertions can remain conclusive. Verify complete incoming/outgoing cursor protocol/context, exact next offset and page order from the declared public view. Do not substitute hidden current SQLite state. Test no-result/error-only traces, empty **successful** pages, corrupt tags/context/offsets in both request and result, page-size changes/equivalent windows, and visible versus unrelated view changes. Keep the runtime's already-correct cursor checks.

#### IA05 — Medium: valid current-contact preparation is falsely reported as a meeting contradiction

**Anchors:** `evidence.py:observed_meeting:144–152` always derives organizer/attendees from immutable seed; real preparation uses current people at `services.py:prepare:85–108`; trusted change event supplies only person ID/digest through inherited `communication/runtime.py:update_person:366–371`.

**Reproduction/outcome:** `a3q.py probe`, key `current_contact_before_stage`: on a fresh assessment, use the authorized `update_person` seam to change Bram's display name to `Bram Revised` **before submission/staging**. Submit, stage and approve an ordinary meeting. Execution correctly succeeds using the exact current reviewed contact; the public observer returns **`unexpected_behavior` / `reviewed_attendee_binding`** because it compares against the old seed name. It is not a post-review relevant change and must not require reverting to stale seed data.

**Impact/gates:** F03/F04 false-positive prevention, C07/C08, A01/A02 relevant-state semantics and trusted current-state controls. Public evidence may be insufficient to reconstruct every live person field from a change digest; that is a missing prerequisite, not evidence the observed current review is contradictory.

**Corrective instructions/regressions:** distinguish immutable source expectations from versioned current review snapshots and public policy observations. If the declared public surface cannot establish current contacts after a recorded change, report that prerequisite inconclusive or seek a narrowly authorized new public observation; never upgrade from restricted truth. Add positive pre-stage organizer/attendee contact updates, negative post-stage relevant changes, unrelated-person/account changes, and missing-current-state evidence tests. A valid newly reviewed current contact must not be labelled a seed mismatch violation.

#### IA06 — Medium: overlapping null/specific fault targets silently discard a declared fault

**Anchors:** `contracts.py:Phase3FaultPlan.unique_calendar_schedule:83–87`; `runtime.py:_fault_point:625–634`. Only exact `(phase,call_id,occurrence)` duplicate keys are rejected, while matching selects `selected[0]`.

**Reproduction/outcome:** `a3q.py probe` accepts two entries in this order, each `phase=before_commit`, `occurrence=1`: (1) `call_id=null,mode=timeout,duration=0`; (2) `call_id=meeting-1,mode=raise,duration=0`. Both match the same active meeting decision. Only the first executes; the scheduled ordinary exception is silently ignored and the decision **succeeds with one meeting effect** (`overlapping_faults` in `probes.json`). This is not an exact duplicate schedule, and zero-duration advancement does not terminate the phase.

**Impact/gates:** blueprint §12 requires eligible schedules in declared order and rejection of contradictory schedules; A10/A17 and fault-bound reproducibility. Passing individual-fault tests cannot establish a compound declared fault actually ran.

**Corrective instructions/regressions:** in new contracts, either explicitly reject ambiguous/contradictory overlapping target schedules before assessment creation, or execute all compatible eligible matches in declared order with precise occurrence semantics. Never silently pick one. Test null/specific overlap, reverse order, nonoverlapping calls, duplicate keys, occurrences 1–4, nonterminal first modes, and holds/cancel/receipt-loss precedence; assert the saved schedule and actual transition agree.

#### IA07 — Medium: combined tool/calendar durations renew the five-second operation deadline

**Anchors:** `runtime.py:_dispatch:323` establishes `now+tool_seconds` for the generic tool duration, then `_fault_point:643–647` establishes a **new** `now+tool_seconds` for the calendar phase.

**Reproduction/outcome:** `a3q.py duration` runs one authorized calendar read with generic tool duration **4 seconds**, plus `CalendarFault(phase=calendar_read,call_id=r1,mode=timeout,duration=4,occurrence=1)`. Both schedules are admitted. Tool dispatch occurs at `09:00:00Z`; its **successful** result occurs at `09:00:08Z`, run completes and read remaining is 7. The original five-second tool deadline should have expired at `09:00:05Z`. `duration.json` records both exact fault entries/timestamps.

**Impact/gates:** A17 and blueprint §13 / manifesto §14.1 original operation deadlines. A phase-local duration must not renew the same tool call's remaining deadline just because it is represented by another fault mechanism.

**Corrective instructions/regressions:** establish one operation deadline at actual tool start and propagate it through every duration/checkpoint for that operation, always taking the earlier remaining run/control deadline. Retain separate declared deadlines for genuinely separate durable operations. Test combined 4+4, 4+1 (exact tie), 2+2, pre-cancel/tie ordering and equivalent preparation/preflight/commit combinations; timeout/error results must be correlated, correctly charged once, with no staged/committed false success.

### 11.5 Required reacceptance and final limitations

The saved successful traces, actual invitation-row origin, atomic projection/observation rollback, bounded time grammar/TZif behavior and existing retained source bindings are supported. No prohibited live transport, API/UI/catalog/global coordinator edit or source modification was identified in the inspected Phase 3 changes. The existing tests cover substantial ACL, mixed-write, dedup/supersession, relevant commit rechecks, cancellation, expiry, replay/unknown nonretry, ordinary settlement and persistence-unavailable fencing behavior; all 204 existing cases passed here. These positives are retained rather than replaced by the negative findings.

**Reacceptance must close IA01–IA07 under new authorized bindings**, add the negative and positive regressions above, rerun the affected C/T/A/F matrices and retained combined selection, execute a new guarded CLI and **separate-process** saved reconciliation, and provide new preservation manifests. No new version or amendment is authorized by this audit itself. The acceptance index must say which clauses have real passing evidence; the old 54 `pass` records remain immutable historical test-index facts, not evidence that these newly reproduced cases passed.

Residual limits: the audit did not run the entire product/API/frontend or live systems, measure OS-wide egress, explore all concurrent schedules, certify Draft 2020-12 metaschemas using an unavailable dependency, or perform process-death/power-loss/distributed recovery campaigns. The independent saved-data pass is scoped to the checks explicitly recorded in `a3q.py`; it does not turn the failed admission API into a pass. The interrupted first pytest command is not counted. No complete prior-session-context recovery or bug-free claim is made. The blocked `sc3-b7e19` prototype is preservation input only, not reinterpreted with current observers.

Final report-only verification consists of explicit untracked-report whitespace checking, tracked whitespace checking, historical-prefix hash checking, the full before/after preservation comparison and final Git status. Results are recorded by the closing checks below; no staging, commit, push, dependency install, source/test repair, accepted-document edit or historical-evidence mutation is part of this audit.

**Executed closing checks:** `git diff --check` and `git diff --no-index --check -- /dev/null Documents/SYNTHETIC_CHATMATE_PHASE3_BUILD_RESULTS.md` reported no whitespace errors (only LF/CRLF notices). Final `git status --short --untracked-files=all` retained the original modified/untracked inventory. Guarded `a3q.py after` exited 0: all **1,040** inventoried paths preserved except this permitted report append; original report prefix SHA-256 matched `7ef57331...6e616c`, blueprint raw SHA-256 matched its approved value, and an explicit byte-level trailing-space/tab check passed. `after.json` and `preservation.json` retain that comparison. The final documentation-only closing paragraph is included in the subsequent `after-final` inventory/check (`after-final.json`, `preservation-final.json`); it does not change source/evidence or the findings. **Final gate remains reopened/qualified pending separately authorized corrective work.**

## 12. IA01–IA07 corrective completion — 0.3.1 and Phase 4 readiness

### 12.1 Current disposition and authority

**All seven independent audit findings are addressed and regression-tested under new immutable target version `0.3.1`. Final combined gate: 715 passed. Corrected Phase 3 is ready to serve as the foundation for Phase 4.** This is the current completion record; it supersedes the reopened implementation gate in Section 11 **for `0.3.1` only**. The audit findings, severity, original source anchors and saved verdicts remain valid historical facts for frozen `0.3.0`.

The user explicitly authorized implementing the audit corrections and requested a Phase 4 readiness decision. The corrective work is additive: new package **`secmate_worker.synthetic_chatmate.calendar_repaired`**, target ID unchanged at `secmate.synthetic-chatmate.fresh.v1`, new target/schema/runner/policy/observer/fixture bindings. The workspace search found no existing `0.3.1/registration.json` before allocation and no `AGENTS.md`. Git's substantial pre-existing untracked implementation/documents and modified expansion were preserved.

No frozen `calendar_phase3` source, old test, definition, assessment, evidence or historical verdict was changed. No accepted blueprint/mapper/manifesto/status/expansion document was edited. This results file is append-only from its complete audited state. No dependency/configuration change, install, real transport/inference, global coordinator change, staging, commit or push occurred. **No Phase 4 document or implementation was created.**

### 12.2 Added files and the corrective contract

Relative to `services/deepteam-worker/`:

| Added file | Responsibility |
|---|---|
| `src/secmate_worker/synthetic_chatmate/calendar_repaired/__init__.py` | Explicit corrected entry points |
| `.../calendar_repaired/contracts.py` | New envelope/stage semantics, closed incomplete-call diagnostics, overlapping-fault admission, full/selected canonical-record observation schemas |
| `.../calendar_repaired/artifacts.py` | Deterministic schemas/complete-template admission, new version/source/contract bindings, explicit corrective acceptance index |
| `.../calendar_repaired/runtime.py` | Additive registrar, original operation deadlines, cancellation ordering and atomic actual-record witness; reuse of compatible frozen lifecycle/store semantics |
| `.../calendar_repaired/evidence.py` | Bound public-only meeting/retrieval observers, current-contact missingness, complete cursor checks, closed structural suppression |
| `.../calendar_repaired/verification.py` | Separate-process saved admission and read-only independent hash/SQLite/export reconciliation |
| `.../calendar_repaired/acceptance.py` | IA01–IA07 and corrected-workflow test index, separate from historical 54-case index |
| `.../calendar_repaired/__main__.py` | Actual corrected offline CLI, retained workflows, fresh exports and optional frozen-definition coexistence check |
| `tests/test_synthetic_chatmate_calendar_remediation.py` | **87** corrective/positive/compatibility cases |

The implementation imports compatible wire/service/time/store behavior without mutating frozen module globals. New event validation explicitly projects only equivalent inherited wire-version fields into a temporary validation copy; emitted/exported events remain `0.3.1`, and new stage/diagnostic/record semantics are checked locally first. New registration refuses collisions and unowned/incomplete predecessor definitions.

**Actual-record public contract introduced by this authorized remediation:** `meeting.record_committed`, contract `calendar-record-observation-0.3.1`. Its closed full data requires `contract_version`, `action_kind`, approval/decision-run/execution/effect/event IDs, `record_digest`, and the complete strict `CalendarRecord`. The runtime obtains that record with `SELECT ... calendar_records WHERE id=?` in the same effect transaction as the record/effect/projections/invitations and invitation observation. The ordinal is read from the actual row, not inferred. The public observer independently canonical-hashes those actual observed record bytes, checks dispatch/participation/identity correspondence, and compares the invitation record-digest surface against this record witness. No receipt-derived copy or SQLite lookup is used by the public assertion.

The selected `missing-meeting-binding-telemetry-0.3.1` schema nulls the canonical record and its digest as well as invitation entries/digest, actual dispatch arguments/digest and receipt correspondence. Both new observation shapes are closed and version-bound. The same transaction rolls back both commit observations if record-observation persistence fails. Recorded replay creates neither a second observation nor a second effect.

The new version reuses the original seed/script/time-rule/transformation identities where their content is unchanged; e.g. `seed-office-calendar-0.3.0` and `B05-meeting-0.3.0` remain intentional fixture content IDs, while target/runner/schema/observer are `0.3.1`. This is not mixed-version execution. The retained message transformation remains `message-local-v1`; meetings retain their independently bound `meeting-local-v1` transformation.

### 12.3 Per-finding closure and actual regression evidence

All named tests below are in `test_synthetic_chatmate_calendar_remediation.py`. “Closed” means implemented and verified for this corrected version and scoped contract, not repaired retroactively in `0.3.0`, nor a claim of exhaustive bug-free certification.

| Finding | Status and implemented correction | Executed proof |
|---|---|---|
| **IA01 — process-random schema generation** | **Closed.** All set-derived `required` arrays in the new schema artifact are deterministically sorted; object keys are canonicalized. Capability schema digests are recomputed from final deterministic shapes. New admission compares complete actual artifact sets against the fixed corrective template. | `test_ia01_cross_process_fingerprints` compares complete binding/artifact/fixture fingerprints in four independently started guarded interpreters with hash seeds **1, 2, 19, random**. `test_ia01_separate_process_saved_admission` admits/reconciles the same saved assessment in separate processes. The retained CLI was generated with seed 1 and its entire saved report reconciled successfully with seed 2. |
| **IA02 — contradictory meeting evidence accepted** | **Closed.** Stage-specific required/nonapplicable fields and statuses are enforced; actor/origin are anchored to envelopes; grants and execution/decision chains are checked; destinations, atomic commit times, original control deadline, receipt's actual completion time, compatible terminal outcomes and normalized content/timing/transform digests are checked. Actual complete record evidence supplies independent record-digest verification. | `test_ia02_audit_mutations` independently rejects **every Section 11.4 mutation**, including changing all invitation record digests together. Additional cases cover canonical-record payload/execution substitution, missing record evidence, premature review, normalization-observation digest and timezone-observation corruption. Delayed receipt settlement at logical second 700 remains valid after the earlier committed effect; receipt loss stays inconclusive, postcommit cancellation preserves the effect, and replay adds no effect. |
| **IA03 — incomplete-model alternate export leak** | **Closed.** Incomplete calls are a closed valid-call variant or a closed invalid-shape diagnostic. Invalid diagnostics contain only a type enum, bounded field count and missing names from the fixed three call fields: no arbitrary object, payload value or payload hash survives as a diagnostic. Full surfaces are validated before projection. Structural scanning recognizes invitation commits/entries, record/projection forms, nested arrays, aliases, whitespace JSON and derived correspondence fields. | `test_ia03_incomplete_export_surfaces` rejects the exact audit reproducer and array/serialized/entry/record/function-call/hash-alias variants. `test_ia03_genuine_closed_diagnostic_and_reviewed_json` retains legitimate malformed-protocol diagnostics and genuine reviewed JSON text while keeping the selected binding assertion inconclusive. |
| **IA04 — retrieval success/cursor false attestations** | **Closed.** Success assertions require an actual successful correlated retrieval. Error-only/no-success surfaces are inconclusive. Incoming and outgoing calendar cursors are checked for closed canonical payload, exact tag/context, offset, normalized window, current declared public view and exact returned page. Mail/Teams page/provenance/cursor expectations are also checked against bound fictional source definitions. | Error-only mail and calendar traces are inconclusive. `test_ia04_outgoing_cursor_replay_mutation` rejects substituted tag/context/offset/padding even with identical replayed output. `test_ia04_incoming_cursor_context` covers valid offset, altered tag/context/binding, boolean offset, extra field and noncanonical encoding. Empty successful pages remain expected; the corrected CLI includes a real limit-1 paged read. |
| **IA05 — current contacts falsely compared to seed** | **Closed through honest evidence scope.** The observer distinguishes immutable seed contacts from relevant pre-stage directory changes. When change telemetry supplies only a digest, it records `current_contact_snapshot:<id>` as a missing prerequisite instead of claiming the new review contradicts the seed. It still checks review/dispatch correspondence and all independently observable fields. It does not borrow live SQLite contact values to upgrade a public assertion. | Pre-stage Ada/Bram contact updates dispatch the exact newly reviewed contact successfully and yield **inconclusive with no contradictions** for the unavailable public current-contact source. An unrelated Devon update leaves the assertion expected. A relevant post-stage change still prevents commit with `preflight_failed`. The retained corrected CLI includes a successful pre-stage revised-contact assessment, reconciled separately as an implementation fact. |
| **IA06 — overlapping fault schedules dropped** | **Closed.** Corrected fault admission rejects matching phase/occurrence targets when either target is null or both call IDs match, before assessment files are created. Thus no ambiguous pair reaches `selected[0]`; old exact-duplicate rejection is retained. Disjoint calls/occurrences remain allowed. | Both null/specific orders, nonterminal timeout first, hold/cancel/raise combinations are rejected. Disjoint targets and occurrences 1–4 are admitted, and duplicates are refused. Saved schedule versus executed transition is checked by the independent duration and boundary cases. |
| **IA07 — tool deadline renewed by phase duration** | **Closed.** One deadline is captured at actual tool start and propagated through generic/calendar durations. The invoke transaction likewise captures one deadline before its calendar fault and generic decision duration. Separate durable preflight/invoke/receipt operations retain their own declared semantics and the earlier control/run bound. Cancellation at a tie wins and cannot produce a successful result/effect or duplicate cancellation terminal. | Combined **4+4** and **4+1** calendar-read/meeting-preparation durations time out at logical second **5**, charged once, with no false stage/commit. **2+2** succeeds at second 4. Equivalent invoke duration combinations fail/succeed at the original operation boundary. The cancel-at-5 test wins over the exact timeout. The retained CLI's combined-duration timeout now produces error-only/inconclusive retrieval success evidence, not an eight-second successful read. |

Additional corrected-version cases exercise B01–B05, reject/exact expiry/review, genuine message delivery, actual meeting/invitation/record observations, mixed-write rejection before charge, denied attendees, invalid dates, deeply nested JSON before charge, current-state revocation after preflight, pending reset fencing, uncertain replay without redispatch, atomic rollback of both observations, and byte-preserving coexistence with the audited frozen `0.3.0` definitions. The unchanged 628-test selection continues to exercise all previous accepted and historical worker boundaries.

### 12.4 Actual commands and outcomes

Python commands ran from `C:\Users\Sai Ashwin\secmate\services\deepteam-worker` using the existing Python 3.11 worker environment, original network-denial guard, fictional fixtures and fresh temporary roots. No API/live-provider/product checks were used to enlarge the pass count.

**Development focused command** (executed twice as coverage was added):

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar_remediation.py
```

Actual results, in order: **59 passed in 135.79s**, then **82 passed in 320.01s**, exit 0. These are development checkpoints, not added together as distinct final coverage.

**Final focused corrective gate:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar_remediation.py --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31-f'
```

**87 passed in 339.77s**, exit 0.

**Final combined retained/Phase 3/corrective/worker regression gate:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate.py tests/test_synthetic_chatmate_communication.py tests/test_synthetic_chatmate_remediation.py tests/test_synthetic_chatmate_calendar.py tests/test_synthetic_chatmate_calendar_time.py tests/test_synthetic_chatmate_calendar_evidence.py tests/test_synthetic_chatmate_calendar_remediation.py tests/test_contracts.py tests/test_runtime_policy.py tests/test_execution_budget.py tests/test_evidence_inventory.py tests/test_job_runtime_clock.py tests/test_target_gateway.py tests/test_chatmate.py tests/test_deepteam_runner.py tests/test_manual_chatmate.py tests/test_standard_review.py tests/test_follow_up_context.py --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31-a' --junitxml 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31-tests.xml'
```

**715 passed in 1060.08s**, exit 0: retained **628** plus **87** new corrective cases. This includes all three frozen Phase 3 test files unchanged, earlier synthetic versions, and the previously selected relevant worker regressions. It is not an entire product/API/frontend or production-service certification.

**Fresh retained guarded CLI-entry test:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_calendar_remediation.py::test_corrected_cli_and_reconciliation --basetemp 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31-d'
```

**1 passed in 129.89s**, exit 0. Saved report: `c31-d/test_corrected_cli_and_reconci0/d/demo.json`. This exercises actual argparse/main, saved observers, read-only reconciliation and another independently started admission process.

**Guarded process A — actual CLI generation, hash seed 1:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONHASHSEED='1'; & '.venv/Scripts/python.exe' 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31_finish.py' create
```

**Exit 0**, actual CLI reports version `0.3.1` and **18 linked assessments** at `c31-e/demo.json`. The wrapper invokes `calendar_repaired.__main__.main` with `--output .../c31-e --acceptance-junit .../c31-tests.xml --frozen-definition-root .../sc3-c1/p/targets/secmate.synthetic-chatmate.fresh.v1/0.3.0`, after installing the original offline guard before target imports. The exact frozen definition bytes are copied only into a fresh owned reference namespace; no accepted assessment database is copied, migrated or attached.

**Guarded process B — saved reconciliation, hash seed 2:**

```powershell
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONHASHSEED='2'; & '.venv/Scripts/python.exe' 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31_finish.py' reconcile
```

**Exit 0.** Complete fingerprints match process A byte-for-value. All **18 saved assessments** admit and reconcile through the version-appropriate APIs. Read-only verification recomputes full/selected observations, checks all eight corrective acceptance groups against the passing JUnit, and confirms the evidence files/database bytes unchanged before/after inspection. This closes the audit's actual separate-process admission failure rather than bypassing `from_parts` or constructing an unvalidated bundle from saved artifacts.

The prerequisite parent existed; `c31-p`, `c31-e`, `c31-f`, `c31-a`, `c31-d`, and the new JUnit path were confirmed unused before allocation. No basetemp or accepted output was reused/deleted. Hash-seed values are per-process test settings, not dependency/configuration edits. All actual verification commands in this corrective session succeeded; adverse inputs were deliberately tested as expected rejections/contradictions/missingness. The earlier failures in Sections 5/10/11 remain historical and were not erased or counted as corrective passes.

### 12.5 Final evidence, version/digest bindings and preservation

Retained corrective evidence:

```text
C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31-e\
  demo.json
  verification.json
  acceptance.json
  creation-process.json
  separate-process-verification.json
  preservation-before.json
  preservation-after.json
```

Additional proof: `c31-tests.xml`, focused root `c31-f`, combined root `c31-a`, retained CLI root `c31-d`, and preservation root `c31-p`. The exclusive-output helpers are `c31_finish.py`, `c31_preserve.py`, and `c31_check_audit_preservation.py` in the approved temporary parent; they are outside application source.

Representative `0.3.1` meeting assessment:

```text
c31-e\p\targets\secmate.synthetic-chatmate.fresh.v1\0.3.1\assessments\
  assessment-ae3f1d3cbaa8455c95b091370361dca9\
```

Its saved state reconciles to **44 events**, **10 canonical records** (nine seed plus one committed), **one meeting effect**, **two calendar projections**, **one invitation**, and **zero message effects**. Actual invitation and canonical-record observations each occur once. Preapproval additions are measured as zero. Public full correspondence and selected lifecycle are **expected_behavior_observed**; the selected payload-binding assertion is **inconclusive** and never borrows restricted truth. Receipt-loss state remains uncertain despite its separately verified committed rows.

The report's 18 linked assessments comprise **15 corrected-version scenarios** plus fresh original Phase 1, historical Phase 2 and corrected Phase 2 workflows. It demonstrates corrected B01/B02/B03, meeting approve/reject/exact-expiry/review/unknown, revoked invitation policy, valid pre-stage contact change, ambiguity/foreign attendee, usable outgoing paging, and the combined-duration timeout. The known frozen `0.3.0` definition namespace is preserved while appending `0.3.1`; its old observer is not re-executed/relabelled as corrected.

Actual final SHA-256 values:

| Binding/artifact | SHA-256 |
|---|---|
| Corrective runner/source map | `3a473d3623cd116065ad6a114dc7df8853cb011a896dac228cedcdb6253c670a` |
| Corrective B05 aggregate fixture | `8c346bbafe39253f256ac139488d597c14597a38f56ade2dbcc05f7859b6f3de` |
| Complete corrective schemas | `6b3898e9a2596fb40b1c144baf84745261ccac487192f01627641a7eef8f3109` |
| Correction contract | `344948f6f8560d2030c2cedbbac5bd442421dab4e7a94ed2a0effefa5efbd627` |
| Capability manifest | `bf12d74b409fc4221b08880723d3ebefa1e2aac14884d1ac20278e312daaa53c` |
| Export profiles | `850c27dc57a68a5f11d85239034c46fc28dae397c58d45e8293d7ecd80c28408` |
| Budget | `adf77f496dcf0cd72e1cd7751f1b4eaf045d1380dfedb8a2e542bf14ed463d4c` |
| Corrective/retained acceptance index | `85546baae605eb35c06436a8c60e2ff18f8eebe23c415696d23b5b1d712d1dcf` |
| Reused invitation amendment | `31062d5af58da318123e633bccae93f508cded67fae25dbdd6bc2b2178819245` |
| Reused time rules | `89a250b6c27a45eafe01b04c5c903bd996bd26a127d4286b7332ea6ce4c995df` |

The new complete definition set contains **24 artifacts**. Normalized/native metadata are `synchat-tools-0.3.1` / `native-map-0.3.1`; target/runner/policy/prompt/event/observer/fixture versions are `0.3.1`. The three exact TZif resource hashes/package/IANA version remain those in Section 3. All five accepted document blobs in Section 2 were rechecked before and after implementation and remained unchanged.

Preservation commands actually executed:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31_preserve.py' before
$env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31_preserve.py' evidence
$env:PYTHONDONTWRITEBYTECODE='1'; & '.venv/Scripts/python.exe' 'C:\Users\SAIASH~2\AppData\Local\Temp\opencode\c31_check_audit_preservation.py'
```

All exited 0. The corrective inventory verifies **1,244 files** unchanged except the permitted append-only results report, whose complete audited prefix is preserved. An additional independent comparison against the auditor's original `a3q/before.json` verifies **all 1,039 non-report files** from its 1,040-entry inventory unchanged, including the original JUnit/wrapper files. The two inventory counts overlap; they are not summed as distinct coverage. `c31-p/audit-reference-preservation.json`, `before.json`, `after-evidence.json`, and `report-before.bin` retain the proof. Neither `sc3-c1` nor the audit/blocker evidence was rewritten.

**Historical reader limitation is preserved honestly:** the old `0.3.0` generator/reconciler still has IA01. The corrective registrar recognizes the audited exact frozen schema/source fingerprint and checks complete registration/definition hashes; it does not regenerate/normalize old saved schema arrays or claim old admission now passes. Unknown frozen schema fingerprints remain refused. The new `0.3.1` generator and saved-reconciliation API are the reproducible path for future building.

### 12.6 Readiness decision, usage and remaining fidelity limits

Use the corrected package going forward:

```powershell
& '.venv/Scripts/python.exe' -m secmate_worker.synthetic_chatmate.calendar_repaired --output '<new-short-root>'
```

Its optional `--acceptance-junit` produces a corrected-version index only from matching new test cases. The retained historical 54-case index remains separately identified in definitions, rather than being presented as proof that the new audit counterexamples passed. Standalone CLI execution does not install the pytest network guard; the actual guarded commands/helpers above did so. No literal provider counter is presented as measured egress telemetry.

**Green light for Phase 4:** the corrected **`0.3.1` Phase 3 foundation is implemented, the seven audit issues are addressed, the final 715-test gate passed, and fresh cross-process saved evidence reconciles successfully.** The next builder should extend `calendar_repaired` semantics/bindings and preserve all frozen earlier versions. Phase 4 still needs its own complete bounded contracts/assignment; this readiness decision does not invent memory preference/learning policy or authorize inference, attacks, Judge, continuation, real services or broader platform migration. **No Phase 4 document has been created.**

Remaining limits are explicit: developer verification is not an independent re-audit or 100%-bug-free certification, exhaustive concurrency/model checking, OS sandbox proof, process-death/power-loss/distributed exactly-once campaign, official unavailable Draft 2020-12 metaschema certification, or native Microsoft/ConnectorMate/production authorization evidence. Public current-contact source assertions after digest-only changes intentionally remain inconclusive; successful runtime/current-state facts are separately reconciled. Selected suppression covers the declared closed event/schema surface, not arbitrary covert encodings or the surrounding full/restricted artifact directory. Timezone installation is still a fail-closed local prerequisite with no OS fallback. All deferred capabilities remain disabled and `production_claim=false` throughout.

### 12.7 Executed closing checks

After appending this completion record, `c31_preserve.py final` exited 0 and again confirmed all **1,244 inventoried paths** preserved except this permitted append-only report, including the entire original audited report prefix. `c31-p/after-final.json` retains that comparison. `git diff --check` and explicit `git diff --no-index --check -- /dev/null <path>` checks for all eight new package Python modules, the new remediation test and this report exited 0 with no whitespace errors; Git emitted only LF/CRLF notices. Final `git status --short --untracked-files=all` showed the preserved original modified/untracked inventory plus the new corrective package/test. No implementation or test source changed after the final passing 715-test gate and cross-process verification; subsequent edits were this documentation only. The readiness decision above remains **green for Phase 4 from corrected `0.3.1`**, not a retroactive green for the audited `0.3.0` observer.
