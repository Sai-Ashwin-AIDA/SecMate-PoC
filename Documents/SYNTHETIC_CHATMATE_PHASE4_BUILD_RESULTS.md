# Synthetic ChatMate Phase 4 build results

## 1. Disposition and scope

Phase 4 is implemented as an additive, offline, deterministic, facts-only personal-memory projection in `services/deepteam-worker/src/secmate_worker/synthetic_chatmate/memory_phase4/`, target `secmate.synthetic-chatmate.fresh.v1` version `0.4.0`. It adds owner-scoped seed facts, eligibility and expiry filtering, request-bound context publication, host-only inspect/forget/clear/disable controls, revision/CAS and replay handling, evidence projection, and read-only reconciliation while retaining the seven model-callable tools.

This is not a production or live-service certification. All saved evidence has `production_claim=false`; registration records `api_registration=false` and `deepteam_provider=false`. No provider, Microsoft service, real ChatMate identity/data, live transport, dependency/configuration change or install, staging, commit, or push was used. No accepted blueprint, mapper, manifesto, status, predecessor result, frozen implementation, test, artifact, evidence, or verdict document was edited by this results task.

## 2. Governing and predecessor bindings

The governing Phase 4 blueprint is `Documents/SYNTHETIC_CHATMATE_PHASE4_BLUEPRINT.md`, Git blob `2e748b1f55c0d95195f0126bf22d8d8ab53bcde8`. The corrected predecessor bindings rechecked from the current workspace are:

| Input | Git blob |
|---|---|
| `Documents/SYNTHETIC_CHATMATE_PHASE3_BUILD_RESULTS.md` | `c48d3336cc68bc8e57f343f935918059a6b2a3e9` |
| `Documents/SYNTHETIC_CHATMATE_BUILD_STATUS.md` | `6899f5c6df6bce98f4118bc2adc984d8a1c282f3` |
| `Documents/SYNTHETIC_CHATMATE_PHASE3_BLUEPRINT.md` | `34bbffff2929dc236806cb1d2fdc39a07f62ea28` |
| `Documents/synthetic_chatmate_manifesto.md` | `518b848480a43f8e7d17838c6f7136cd1d903765` |
| `Documents/chatmate_mapper.md` | `559bf61ace74094996df9a871dd276569a7a7aa9` |
| `Documents/REDTEAM_EXPANSION.md` | `1549398da71cc0142b6e50cced3c7aa7bd9f9cb8` |

Saved `0.4.0` bindings retain corrected Phase 3 blueprint blob `34bbffff...`, file SHA-256 `6879c19bf06b554744f90642dbbadac9dde1cd0076cd95c826f1632561f05729`, source revision `9335db39cd92f98cbefb91ffb98bb995fe32048b`, manifesto `0.1.2`, and invitation-commit amendment digest `31062d5af58da318123e633bccae93f508cded67fae25dbdd6bc2b2178819245`. The Phase 4 governing blob above is the build/report authority; it is not retroactively substituted into already generated predecessor-derived binding fields.

Runtime inspection returned Python `3.11.9`; SHA-256 of the venv interpreter was `21bb438c0d4a6f1f164b9a646f6ee000340185e5871180aec06db8d3f07c0082`. Installed `tzdata` was `2026.6`, IANA `2026f`, with exact bound resources: UTC `fddce1e648a1732ac29afd9a16151b2973cdf082e7ec0c690f7e42be6b598b93`, America/New_York `d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9`, and Asia/Kolkata `3a00bdbe1bc4959e727567c730ba51b03455ecd455f7c190c5ad14386eb79b0d`. The inherited time-rules digest is `89a250b6c27a45eafe01b04c5c903bd996bd26a127d4286b7332ea6ce4c995df`; no OS timezone fallback was used.

## 3. Added files and responsibilities

Implementation and data:

| File | Responsibility |
|---|---|
| `memory_phase4/__init__.py` | Public `MemoryBundle`, `MemoryTarget`, and `Phase4FaultPlan` entry points. |
| `memory_phase4/__main__.py` | Offline scripted CLI/demo and evidence export. |
| `memory_phase4/acceptance.py` | M01-M40-to-test references and optional JUnit-derived records. |
| `memory_phase4/artifacts.py` | Deterministic 28-artifact `0.4.0` bundle, predecessor adaptation, admission, bindings, and fingerprints. |
| `memory_phase4/context.py` | Eligibility, expiry/order, snapshot, request binding, and refresh construction. |
| `memory_phase4/contracts.py` | Strict memory DTOs, constants, and fault contracts. |
| `memory_phase4/evidence.py` | Public observations and missing/contradictory evidence handling. |
| `memory_phase4/runtime.py` | Target registration, assessment flow, host controls, retries, reset/fencing, and export. |
| `memory_phase4/services.py` | Deterministic scripted memory service and fault behavior. |
| `memory_phase4/store.py` | New-assessment SQLite memory tables, immutable journal, snapshots, controls, and atomic transitions. |
| `memory_phase4/verification.py` | Independent read-only saved-report and assessment reconciliation. |
| `memory_phase4/data/memory_seed.json` | Six owner-scoped synthetic facts and initial memory state. |
| `memory_phase4/data/memory_contexts.json` | Context eligibility and developer-placement definitions. |
| `memory_phase4/data/policy.json` | Facts-only memory/control policy. |
| `memory_phase4/data/host_schedules.json` | Deterministic inspect/control schedules. |
| `memory_phase4/data/scripts.json` | Phase 4 scripted scenarios. |

Tests:

| File | Responsibility |
|---|---|
| `tests/test_synthetic_chatmate_memory.py` | Store, controls, concurrency/replay/fencing, registration, CLI, and demo. |
| `tests/test_synthetic_chatmate_memory_context.py` | Eligibility, ownership, expiry/order, context placement, retries, and refresh. |
| `tests/test_synthetic_chatmate_memory_evidence.py` | Suppression, observer mutation checks, read-only reconciliation, and saved-evidence reader. |

## 4. Materialized artifacts and evidence

The exact 28 definition names are `acceptance_matrix`, `baseline`, `budget`, `calendar_records`, `calendar_seed`, `canary_catalog`, `capabilities`, `comparison`, `corrections`, `event_schema`, `export_profiles`, `host_schedule`, `implementation`, `invitation_commit_amendment`, `memory_contexts`, `memory_policy`, `memory_seed`, `native_metadata`, `policy`, `prompt`, `record_digests`, `scenario_id`, `schemas`, `script`, `scripts`, `seed`, `time_rules`, and `transformation`.

The complete artifact aggregate reported for independently varied hash seeds is `47c0941fada33bc295a679f63081d295c4665a7e00a1fc2e3b3aca793b290ff6`. Key current definition digests are:

| Definition | SHA-256 |
|---|---|
| `implementation` | `de6ce0a2e05627e512438cb6ff75c620b63b02f25d57d925c1cfbd27a9c440ca` |
| `schemas` | `3e488ce76bed987cc7aa2b67ab9fee4373bf6d923b3b862cabb3359d3647f611` |
| `memory_seed` | `b32c5fc21923fc12d96976c6ec90e6a15fc4ab071d6c7af32f9a6e0f0233042a` |
| `memory_contexts` | `9109c73213904e49c795cd57a3a5440fd5dbdd50d12fc10ddc4f014294f6ff2c` |
| `memory_policy` | `7a00b49b1168eaa6e5e487a9faa1a03616e9302a0c77913dc95cfe19d09d8ec5` |
| `host_schedule` | `7ba393bbc02bf776855b5cc42f72371408e5b8e3890ab3e4257cdecab7f1fc7f` |
| `acceptance_matrix` | `85546baae605eb35c06436a8c60e2ff18f8eebe23c415696d23b5b1d712d1dcf` |
| `capabilities` | `92eadb8409491ffe81dc436fceb713d27cca9675cba9e24257f33f7890d0e164` |
| `record_digests` | `d1f746287a320bd58421cbec7fc6c343644e6c77c2d354dff5db8212485275c2` |
| `policy` | `97f8a9427a08f32fba299706f39eb8c232f0ecbed0d3945aef7d088f6157be53` |
| `prompt` | `3f4b8df2b0679ca272b58980c2e9f695f8ecb4c87fef8790a7e4a508a9b538cd` |
| `script` | `76b4697dbfc5b1c76d4ec99c627b8054d064ddc1d679908355be38ad706d6a7f` |
| `scripts` | `41b64ce04c4230e600d89ead9a52bcb9e0f44385475506a5278bf6150cccb60d` |
| `seed` | `dcfe5a715fb945b96c47f7ab3d9e6ba3ac03b465652cc57e810ff2f294307a37` |
| `transformation` | `6099f01cc824dc4f5f87c6907416d32f68065d4057319b6ac9be39cc3cb37659` |

An inspected assessment additionally binds fixture digest `b1bc8e92d3b8cc820f4bc38bd5490589c7232d09b4ed2a3baada0e167b3d9988` and baseline fault schedule digest `ca0ab85b366545775bc4b7bd5215e406b034f8de6000fc26a50971d7cf0bf6a9`.

The retained evidence root is `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ev1` (resolved saved paths use the long user path). It contains 14 scenarios: `bram`, `clear`, `cyra`, `disable`, `expiry`, `forget`, `ineligible-conversation_disabled`, `ineligible-deleted`, `ineligible-multiparticipant`, `ineligible-project`, `ineligible-shared`, `inspect`, `response-loss`, and `unavailable`. Key evidence hashes are `demo.json` `d8f5713bd578725e4831b68c8f0051f61967368e25f1b1a1b208eff5f36407c9`, `verification.json` `4cf9ca626f38e6b14e6c5d65ad8591a78124d571405f580671bef8b3af148a3e`, and `acceptance.json` `0c7861b1d6eba08211e830478f7e6c507ab2a425c329cb94b28d6fcc4ab401e3`. Fresh pytest basetemps were separate from this evidence root; their transient names are not retained as contractual evidence.

## 5. Executed verification record

All Python test commands were run from `services/deepteam-worker` with `PYTHONPATH=tests;src`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, the repository `offline_synthetic_guard`, and fresh basetemps.

| Selection | Recorded result |
|---|---|
| `tests/test_synthetic_chatmate_memory_context.py` | `10 passed in 34.35s` |
| `tests/test_synthetic_chatmate_memory.py tests/test_synthetic_chatmate_memory_context.py tests/test_synthetic_chatmate_memory_evidence.py` | `24 passed, 2 skipped in 144.10s` |
| Exact blueprint §18 combined list of 21 test files, with `--deselect tests/test_synthetic_chatmate_calendar_remediation.py::test_corrected_frozen_predecessor_bytes_preserved --junitxml C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4.xml` | `738 passed, 2 skipped, 1 deselected in 1298.27s` |
| `tests/test_synthetic_chatmate_memory.py::test_offline_phase4_demo` | `1 passed in 66.74s` |
| `PYTHONHASHSEED=1`, `SYNCHAT_PHASE4_EVIDENCE_ROOT=p4ev1`, `test_phase4_cli_generate` | `1 passed in 66.72s` |
| `PYTHONHASHSEED=2`, same evidence input read-only, `test_phase4_saved_report_reconcile` | `1 passed in 7.89s` |

`p4.xml` records 740 collected test cases, zero failures/errors, two skips, and suite time `1298.223s`; its SHA-256 is `a147b0c492d7b20497cff3c616da9628081e6d5ab458eef79dcb6cdb886e1c56`. The exact combined selection is the command in blueprint §18 lines 692-694; the sole deselection is the optional frozen-reference byte-preservation case because that machine-local historical reference is not required by the portable gate. Mandatory fresh `0.3.1` predecessor admission, drift, schema/source, collision, and byte-preservation replacements remained selected.

The two focused-suite skips are environment-driven harness cases: CLI generation skips without `SYNCHAT_PHASE4_EVIDENCE_ROOT`, and saved-report reconciliation skips without that same explicit input. Each was run separately with the environment set and passed as shown above. Initial development was reported as `15 passed, 2 skipped`, followed by `24 passed, 2 skipped`; only the latter continuation and the independent final records above are treated as completion evidence because no retained execution artifact was found for the initial count.

Separate-process generation with hash seed 1 and reader admission with seed 2 passed. Seed 19 and a default-random process produced the same complete aggregate `47c0941fada33bc295a679f63081d295c4665a7e00a1fc2e3b3aca793b290ff6`. The exact timezone prerequisite output was Python `3.11.9`, tzdata `2026.6`, IANA `2026f`, with the three resource hashes in §2.

## 6. M01-M40 acceptance interpretation

The implementation matrix maps all M01-M40 to concrete Phase 4 tests covering owned private context and seven-tool exposure; eligibility exclusions; forget/clear/disable and sticky disable; revisions, CAS and concurrent controls; exact expiry/order and retry snapshots; timeout/no-stale publication; response loss/replay; checkpoint/reset fencing; request-digest and selected-evidence suppression; inherited meeting suppression; deterministic registration/collision; saved reconciliation; demo/CLI; and read-only verification.

The focused and combined executions passed those referenced test functions. However, current `p4ev1/acceptance.json` contains exactly 40 records, all with `status="inconclusive"`, `junit_path=null`, and `junit_sha256=null`. Therefore this report does not overwrite that artifact, does not claim 40 independently unique tests, and does not relabel M01-M40 as formally accepted from `acceptance.json`. Several cases intentionally share one test reference. The honest disposition is: test-backed behavior passed under the offline synthetic fixture, while the saved acceptance index remains inconclusive because it was generated without the final JUnit binding. This is neither a live certification nor proof of native Microsoft/ChatMate behavior.

## 7. Disabled scope, fidelity, and unresolved items

Model-callable memory control, memory learning, owner re-enable, rich preferences, continuation, attacks, Judge, files/knowledge, dynamic discovery, background jobs, calendar update/cancel, rooms/free-busy, external services, and broad API/UI/catalog integration remain disabled. Memory controls are host-only and are never added as an eighth model tool.

The implementation is a fictional SQLite and deterministic logical-clock projection with v2-shaped developer placement. It does not provide proprietary prompt/native-wire parity, autonomous learning/classification, physical erasure of prior requests/history/outputs, real-time purge, deployed tenant/permission guarantees, provider availability, distributed/process-death/power-loss certification, or arbitrary synchronous-handler preemption. Removal affects future active memory input, not historical content. Native rich preference/control schemas remain unknown.

No functional test failure is documented in the final runs. The unresolved evidence issue is the unbound/inconclusive `acceptance.json` described above. The optional frozen historical reference was unavailable/not selected; this is not a waiver of the selected self-contained ownership checks.

Closing checks re-ran all seven governing `git hash-object` inputs and reproduced the values in §2, including the Phase 4 blueprint blob. Final `git status --short --untracked-files=all` preserved the pre-existing modified expansion file and untracked historical synthetic files and added only the Phase 4 package, three tests, and this report; nothing was staged, reset, cleaned, or deleted. `git diff --check` exited 0 with only Git's pre-existing LF/CRLF notice for `REDTEAM_EXPANSION.md`. The first attempted explicit no-index check was invalid because `rg` was unavailable and checked zero files; it is not counted as a pass. The corrected explicit-list command checked all 20 new Phase 4 implementation/data/test/report files and reported `whitespace_errors=0`.

## 8. Gate

The bounded Phase 4 implementation and offline test gates are green at the test level, subject to the explicit acceptance-index and preservation/whitespace limitations above. Stop before Phase 5. Do not begin inference variants, attacks, Judge, continuation, live services, or wider product integration without a separate assignment and approved bindings.

## 9. Independent audit - 2026-11-13

### 9.1 Disposition

Independent offline audit disposition: **Phase 4 completion is not justified; the Phase 4 acceptance gate is blocked.** The existing focused tests reproduce as passing, and the retained JUnit has no test failures, but material implementation, schema, evidence, acceptance-mapping, and demonstration requirements are absent or contradicted. This is not a finding that the retained fictional baseline leaked data or contacted a live service. It is a finding that the implementation and evidence do not establish the blueprint's claimed contract.

The report's Section 8 statement that the implementation and offline gates are green is therefore superseded for audit purposes. `p4ev1/acceptance.json` and `p4ev2/acceptance.json` each contain 40 inconclusive records; neither is an accepted M01-M40 index. The aggregate `p4.xml` proves only that its selected pytest cases terminated without failures under that run. It does not close the clause-level requirements below.

### 9.2 Findings

#### IA4-01 - High - The normative schema/event/output contract was not materialized or admitted

- **Evidence/reproduction:** blueprint lines 161-242 and 344-425 require the complete local catalog, closed event registry, control/host-output/restricted roots, semantic stage rules, and strict serializers. `memory_phase4/artifacts.py:49-53` adds only `MemorySeed`, `Phase4FaultPlan`, and `facts_only` beneath `schemas.memory`. Runtime inspection printed `memory_keys=['MemorySeed','Phase4FaultPlan','facts_only']` and confirmed no `ControlInput`, `EventEnvelope`, or `HostOutput`. `contracts.py:159-188` checks only field-name sets for listed memory events; it does not validate their types, status-dependent semantics, digests, IDs, timestamps, or inherited event payload roots. Several required events are absent from the registry and runtime, including `memory.control.validation_rejected` and `memory.control.cancel_requested`.
- **Impact/acceptance:** artifact admission can claim the required 28-name set while omitting most Phase 4 schemas. M17, M28, M32, M35, M37, and the schema/evidence portions of M38 are not established. Malformed stored/public structures can pass the local validator.
- **Remediation:** materialize the complete combined Draft 2020-12 catalog and closed event registry; validate every root/reference and all stage-dependent semantics before activation/export; make artifact admission compare the complete pinned catalog and source map; add negative tests for every memory DTO/event/output/restricted root, unknown event data, null-stage contradictions, bool-as-int, nonfinite values, duplicate keys, depth, and semantic identity/digest mismatches.

#### IA4-02 - High - Host-control persistence, fencing, cancellation, and conformance controls do not satisfy the transaction contract

- **Evidence/reproduction:** `runtime.py:276-363` accepts, applies, journals, settles, emits, and returns a control inside one transaction, contrary to blueprint lines 295-313 requiring durable acceptance before application and a separately safe settlement path. There is no active-control database fence or control-cancellation API. `store.py:20` omits assessment, generation, tenant, result digest, and cancellation/fence fields required by the declared `ControlRecord`; `restricted_truth` emits neither those fields nor an actual fence (`runtime.py:441-448`). `failure_recording_unavailable` sets only process memory (`runtime.py:295-297`), while exported `fence` is always null. Postcommit handling selects one matching fault rather than executing all declared ordered phases (`runtime.py:354`). `fixture_set_enabled` and `fixture_context_change` mutate directly without accepted control records, quota, deadlines, journals, committed witnesses, host outputs, or control events (`runtime.py:405-430`), contrary to blueprint lines 315-322.
- **Impact/acceptance:** process death/interruption cannot be reconciled as the specified accepted/applying/settled protocol; reset safety depends on an ephemeral boolean; cancellation/tie behavior is absent; conformance mutations bypass the evidence and CAS discipline they are intended to prove. M10, M18-M24, M36-M38 are incomplete. The passing tests at `test_synthetic_chatmate_memory.py:51-104` cover only serialized outcomes, an in-memory fence, and direct fixture mutations.
- **Remediation:** persist acceptance in its own committed transaction; add a scoped durable fence and closed status transitions; implement trusted cancellation and deadline/tie checks; atomically bind state/result/result digest/journal/public witness; durably represent recording failure; route both conformance operations through the same accepted control, quota, CAS, witness, output, and event pipeline; test process-boundary recovery and both legal control/request interleavings.

#### IA4-03 - High - Evidence observers produce false positive assertions and reconciliation is not the required independent semantic verifier

- **Evidence/reproduction:** `evidence.py:18-45` performs one request/binding digest comparison and then applies the same global missing/contradiction list to almost every assertion. It does not compare actual memory text/ref/owner/revision/order against the bound seed or snapshot candidate, reconstruct controls, inspect eligibility facts, prove history separation/no-learning/expiry/refresh, or scope scenario prerequisites. In a read-only probe against a copied in-memory `p4ev1/inspect` event list, the first fact text was changed to `FOREIGN_OR_SUBSTITUTED_TEXT` and the binding digest recomputed. The observer still returned `expected_behavior_observed` for source-owner, eligibility, request-correspondence, refresh-after-forget, refresh-after-clear, conversation-disable, expiry, history-separation, and no-learning. `verification.py:25-80` verifies selected row counts and hashes but does not perform most blueprint lines 659-670 checks, including initial seed equality, context/control identities, expiry/eligibility semantics, event logical-time monotonicity, host-output equality/digests, public committed witnesses versus journals/results, counters/deadlines/fences, or inherited effects.
- **Impact/acceptance:** public observations can attest behaviors not present in the trace, and read-only reconciliation can admit evidence without establishing the claimed security/correctness properties. M27-M31 and M38 are blocked; all saved `observations.json` results have weak evidentiary value.
- **Remediation:** implement assertion-specific prerequisites and causal validators; independently reconstruct selected facts and owner state from definitions plus committed controls; compare actual request payloads to exact source records/snapshots; reconcile every control, journal, witness, host output, counter, deadline, fence, inherited effect, and export against SQLite; add mutation tests for every identity, text, ref, revision, time, order, stage, and alternate surface.

#### IA4-04 - High - M01-M40 JUnit mapping is broken and the matrix does not map clause-complete tests

- **Evidence/reproduction:** `acceptance.py:60` uses `any(case.iter(tag) for tag in ...)`. Each `Element.iter(...)` generator is truthy, so every testcase is treated as failed/skipped and `passed` remains empty. Re-running `records(p4ev1 demo, p4.xml)` returned `Counter({'inconclusive': 40})`. `p4ev2/acceptance.json` binds the exact final JUnit path/hash but is still 40/40 inconclusive; `p4ev1` is 40/40 inconclusive with null JUnit. The parser also matches only bare testcase names (`acceptance.py:59-64`), not file/class/node ID, which is ambiguous in this JUnit (many bare names occur multiple times). More importantly, the matrix assigns clauses to tests that do not exercise their required cases: for example M02 maps to a single Ada control test, M04 maps to profile eligibility rather than owner mismatch, M11 maps to a two-fact expiry helper rather than 30/31/validation admission, M19 maps to two concurrent controls rather than control-vs-request publication, M23 maps to checkpoint/reset rather than cancellation ties, M34 maps only to the memory demo rather than B01-B05, and M40 maps only to a collision/count assertion.
- **Impact/acceptance:** no M case has a formally accepted saved record, and a parser repair alone would falsely convert broad requirements to passes based on partial tests. Report lines 106-108 overstate that the mapped tests cover all listed boundaries. Completion remains blocked even if the XML parser is fixed.
- **Remediation:** match exact pytest node IDs including file/class and parameter instances; correctly detect child failure/error/skipped nodes; require expected suite identity and unique nodes; expand each M row to tests and evidence that exercise every positive/negative requirement; record scenario/fault bindings and per-case observed evidence/status/reason; regenerate evidence in a new root and reconcile it in a separate process.

#### IA4-05 - High - Required APIs, isolation boundaries, and demonstrations are missing

- **Evidence/reproduction:** no `memory_boundary` implementation, trusted memory-control cancellation API, or tested `fixture_context_change` path exists. Searches of all three Phase 4 test files found none. The CLI at `__main__.py:42-74` generates only baseline memory scenarios. It does not demonstrate foreign/unknown owner boundaries, stale controls, conformance context changes, both transaction interleavings, inherited B01-B05, actual staged/approved message and meeting effects, inherited replay/uncertainty, or the saved meeting-suppression profile required by blueprint lines 600-625. Bram/Cyra use the Ada-bound baseline script (`data/scripts.json:1`), whose history call is `ada-note-1`, contrary to blueprint lines 606-608 requiring each owner's own note ID. `p4ev1` and `p4ev2` each contain only the same 14 scenario names listed in report line 83.
- **Impact/acceptance:** owner/foreign/unknown service-boundary claims, inherited behavior under `0.4.0`, and required public/restricted demonstrations are unsupported. M02, M04, M10, M19, M23, M30-M31, M34-M36, M39-M40 are not closed. Passing inherited tests under older fixture versions is not evidence for new-version behavior.
- **Remediation:** add the specified authenticated read-only boundary and cancellation APIs; add strict conformance context controls; create separately bound owner-specific scripts/schedules; implement all required demo scenarios and exports, including actual B01-B05 local effects and both suppression profiles; add offline-guarded positive/negative tests and fresh saved evidence for each.

#### IA4-06 - Medium - Basic ineligibility is evaluated after load faults/time, violating privacy ordering and budget rules

- **Evidence/reproduction:** `_prepare_memory` applies the configured load fault and advances/charges before loading context and calling `evaluate` (`runtime.py:170-195`). A fresh offline probe used profile `shared` with a five-second `mode=none` load fault. Actual result was `status=unavailable`, `reason=memory_timeout`, one load fault hit, logical time 5, and `checks_remaining=7`. Blueprint lines 246-268 and 326-330 require basic ineligibility to be decided before private service/fault invocation or memory-check charge, yielding `ineligible/shared`.
- **Impact/acceptance:** ineligible requests consume private-read budget/faults and expose service timing/disposition instead of the deterministic scope reason. M03, M15-M16, and eligibility evidence are incorrect for this case.
- **Remediation:** derive and validate basic context eligibility first; only then charge a check and consume a load fault/read owner state; add assertions that every ineligible profile leaves memory check count, fault schedule, and logical time untouched and reports the correct reason.

#### IA4-07 - Medium - Strict control-input and output-limit contracts are not enforced

- **Evidence/reproduction:** `strict_control_json` exists at `contracts.py:133-136` but is unused. `memory_control` accepts Python dictionaries directly and validates only the Pydantic operation shape (`runtime.py:272-275`), so the required raw 8,192-character, duplicate-key, bounded-depth JSON boundary is not exercised. The report's tests contain no duplicate-key/depth/nonfinite control cases. `memory_control_output_characters` is added to artifacts but never applied before `_host_output` (`runtime.py:376-384`), despite blueprint lines 505-513.
- **Impact/acceptance:** M17 and the output-limit portion of M16/M35 are unsupported; oversized inspect/host output is not guaranteed to become `memory_output_limit_exceeded` without partial publication.
- **Remediation:** define one actual public input representation and run it through bounded duplicate-rejecting JSON parsing before acceptance/charge; enforce the configured host-output cap before publication with committed-mutation rules preserved; add exact-boundary and malformed-input tests.

#### IA4-08 - Medium - Store integrity relies on application convention rather than required database constraints

- **Evidence/reproduction:** `store.py:15-24` lacks FKs from seed facts to seed owners, tenant consistency constraints, revision/enabled checks, immutable owner/tenant triggers, immutable context identity/sticky-disable triggers, prepared-control freeze triggers, and append-only event-specific relationship checks required by blueprint lines 465-486. Live fact delete is not restricted by a database predicate to an authenticated current control; direct SQL from any holder of the store connection can delete it. Context is a single opaque JSON payload.
- **Impact/acceptance:** corruption or an implementation error can create cross-owner/tenant or mutable identity state that subsequent code trusts. M18-M20, M28, M37-M38 are not established by current SQLite integrity checks.
- **Remediation:** add normalized scoped columns, FKs/checks/unique constraints, immutable triggers, sticky-transition guards, control identity/status/result constraints, and transaction predicates; have reconciliation intentionally probe/reject malformed copied databases without touching accepted evidence.

### 9.3 Test and evidence assessment

- Fresh focused command from `services/deepteam-worker` with `PYTHONPATH=tests;src`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider -p offline_synthetic_guard`, and fresh basetemp `.../opencode/p4audit-t1`: **24 passed, 2 skipped in 115.44s**. This reproduces the suite result but does not cure the coverage defects above.
- Retained `p4.xml`: 740 testcase elements; suite metadata 740 tests, 0 failures, 0 errors, 2 skips, time 1298.223 seconds; SHA-256 `a147b0c492d7b20497cff3c616da9628081e6d5ab458eef79dcb6cdb886e1c56` matched the report.
- `p4ev1` reported hashes matched: demo `d8f5713bd578725e4831b68c8f0051f61967368e25f1b1a1b208eff5f36407c9`, verification `4cf9ca626f38e6b14e6c5d65ad8591a78124d571405f580671bef8b3af148a3e`, acceptance `0c7861b1d6eba08211e830478f7e6c507ab2a425c329cb94b28d6fcc4ab401e3`.
- `p4ev2` is a distinct retained root, not documented in the original report. Its demo/verification/acceptance hashes were respectively `a5968ae0b87632950fc1849aab613677deb64d33e65bacd008b7a347e0d5d2bf`, `c9c34e2e13350d4fddbc35f071f9da116cb0e0e47327a01248e8e8820c49cfc6`, and `ba7de3827aefc4898e477144cb65f8b401edec2229014702466558324c75643d`. Its acceptance records bind `p4.xml` and its exact SHA-256 but remain 40/40 inconclusive because of IA4-04.
- Existing saved verification summaries are successful executions of the current weak reconciler, not independent proof that blueprint clauses were checked. No accepted evidence was modified during this audit.

### 9.4 Commands and preservation checks actually run

Commands were read-only except for fresh pytest/probe temporary roots and this append-only report edit:

```powershell
git status --short --branch
git hash-object Documents/SYNTHETIC_CHATMATE_PHASE3_BUILD_RESULTS.md Documents/SYNTHETIC_CHATMATE_BUILD_STATUS.md Documents/SYNTHETIC_CHATMATE_PHASE3_BLUEPRINT.md Documents/synthetic_chatmate_manifesto.md Documents/chatmate_mapper.md Documents/REDTEAM_EXPANSION.md Documents/SYNTHETIC_CHATMATE_PHASE4_BLUEPRINT.md
git diff --check
$env:PYTHONPATH='tests;src'; $env:PYTHONDONTWRITEBYTECODE='1'; & '.venv\Scripts\python.exe' -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py tests/test_synthetic_chatmate_memory_context.py tests/test_synthetic_chatmate_memory_evidence.py --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4audit-t1
```

Additional Python 3.11.9 read-only probes parsed `p4.xml`, both acceptance files, artifact schema keys, and copied in-memory events; one fresh offline runtime probe was created under `.../opencode/p4aud-9686b6yt`. `Get-FileHash -Algorithm SHA256` checked `p4.xml` and the demo/verification/acceptance files in both evidence roots. `git diff --check` exited 0 with only the pre-existing `REDTEAM_EXPANSION.md` LF/CRLF warning.

The seven governing blob results remained exactly `c48d3336...`, `6899f5c6...`, `34bbffff...`, `518b8484...`, `559bf61a...`, `1549398d...`, and `2e748b1f...`. Initial and pre-append status showed the pre-existing modified expansion document and untracked synthetic work; nothing was staged, reset, cleaned, deleted, committed, or pushed. No live service was accessed and no dependency was installed. The only repository file edited by this independent audit is this build-results document, by appending Section 9.

## 10. Remediation re-audit - 2026-11-13

### 10.1 Disposition

Independent targeted remediation re-audit disposition: **Phase 4 remains blocked and is not ready to authorize Phase 5 planning.** IA4-02, IA4-05, IA4-06, and IA4-07 are verified closed against their original counterexamples. IA4-01, IA4-03, IA4-04, and IA4-08 remain open. Three of the remaining findings are High contract/evidence issues, so the gate cannot be green. In addition, the fresh focused run exposed a Medium portability/reproducibility defect in the required demo tests on the audit's fresh root.

This section preserves Sections 1-9 as historical records. It assesses the current remediated source, all files under `memory_phase4/` (including five data definitions), all three Phase 4 tests, fresh evidence `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ve1`, and JUnit `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4v.xml` read-only. No implementation, test, or evidence file was edited.

### 10.2 Finding closure decisions

#### IA4-01 - High - OPEN

The remediation now materializes 74 `$defs`, includes the previously absent control/event/host/restricted names, and dispatches known memory events through named roots. It is not the complete normative catalog semantically. `contracts.py:324-351` synthesizes many schemas from field-name heuristics, with untyped `{}` slots and bare arrays, rather than the blueprint's exact constraints. `validate_root` checks selected fields and selected roots but does not validate the full `ErrorResult` contract or recursively validate every generated root.

Adversarial probe result: `validate_root("ErrorResult", {"control_id":"c","status":"error","error":"not-an-error-code","field":"not-json-pointer","current_revision":null,"current_context_revision":null})` returned the malformed object instead of rejecting its unknown error and invalid field pointer. Thus artifact admission can still present a nominally complete catalog while runtime validation accepts values forbidden by blueprint §§6 and 10. IA4-01 and its M17/M28/M32/M35/M37/M38 implications are not closed.

#### IA4-02 - High - VERIFIED CLOSED

`runtime.py:278-295` commits acceptance and the durable singleton fence before apply; `runtime.py:301-409` applies in a later transaction; `store.py:20-21,44-47` persists full scope/deadline/result fields, closed transitions, the active fence, and delete authorization. Cancellation and tie handling are present at `runtime.py:306-322,473-486`; failure-recording unavailability sets a durable persistence fence; all ordered postcommit phases execute at `runtime.py:397-404`. Both conformance methods route through `_execute_memory_control` at `runtime.py:498-508`. Focused tests exercise cancellation/tie, durable conformance, response loss, fencing, both request/control orders, and reset blocking. No reproduction of the original single-transaction/direct-mutation defect was found.

Residual risk: process-kill recovery is represented by durable rows and read-only inspection but is not exercised by an actual killed/restarted controller process. Cancellation while an apply transaction already holds SQLite's write lock is necessarily serialized; postcommit state remains authoritative.

#### IA4-03 - High - OPEN

The source-substitution counterexample is fixed: `evidence.py:54-67` compares actual request items against bound seed text, owner, ref identity, full-record digest, and numeric lifetime. Saved report reconciliation succeeds read-only, and `verification.py` now checks definitions/source bindings, SQL integrity/FKs/triggers, exported ledger equality, event validation/causes, seed equality, owner digests, journal chains, control/result digests, snapshot candidate/ref bindings, host outputs, observations, and selected suppression.

The verifier and observers remain materially short of blueprint §§10.3 and 17. `evidence.py:110-116` still propagates generic request errors/missing prerequisites to history separation and no-learning; `memory-history-separation` never compares immutable history snapshots, and no-learning does not independently reconstruct the current set from seed plus controls. `verification.py:77-98` does not prove full operation-specific before/after/CAS/context/run semantics, actual eligibility and expiry selection at each read, logical-time/formatted-time consistency, or exact committed-event/host-output/result equality. Its corruption test removes a trigger and changes a duplicated context column, not adversarial semantic corruption across each independent surface. Consequently the saved successful `verification.json` is a successful execution of this partial reconciler, not clause-complete independent proof.

#### IA4-04 - High - OPEN

The parser defect is fixed. `acceptance.py:20-42` forms file-qualified pytest nodes, correctly detects child failure/error/skipped elements, rejects duplicate nodes, and the supplied artifacts contain exactly 40 unique parameterized M nodes and 40 `status="pass"` records bound to JUnit SHA-256 `692f6ecc5e24f1e573da72b594bfc54f5cceeac1d08e71aeeaa82eb966aa798d`.

The mapping remains contract-incomplete. `test_phase4_clause_acceptance` is one parameterized function whose broad branches substitute smoke checks for complete clauses. Examples: M01/M03/M12/M14-M16/M25-M29/M35 merely assert that a request-bound event exists (`test_synthetic_chatmate_memory.py:265-268`); M05-M08/M18/M20-M22/M36-M37 share one successful forget (`274-276`); M11 checks only a blank fact (`282-284`); M32/M33/M40 check only catalog count/tool count (`281-292`); and M38 only runs the current partial reconciler. Passing unique node names therefore do not establish each matrix row's required positive, negative, fault, and evidence cases. Exact 40-record mechanics are repaired, but IA4-04's clause-completeness requirement is not.

#### IA4-05 - High - VERIFIED CLOSED

The previously missing `memory_boundary`, `cancel_memory_control`, and durable `fixture_context_change` APIs now exist and have focused tests. `run_demo` produces owner-specific Bram/Cyra scenarios using `bram-note-1` and `cyra-note-1`, all five ineligibility scenarios, conformance context, response loss/replay, B01-B05 under `0.4.0`, actual approved message/meeting effects, rejection, selected memory suppression, and meeting suppression. Fresh `p4ve1` contains 20 scenarios and its verification index covers all 20; `forget` contains the selected-memory projection and B05 contains the meeting-suppression projection.

Residual issue recorded separately: the same required demo failed in this re-audit's longer pytest path because SQLite could not open a deeply nested database path. The supplied short-root evidence is readable and reconciles, so this does not refute presence/behavior of the remediated APIs and demos, but it is a portability defect.

#### IA4-06 - Medium - VERIFIED CLOSED

`runtime.py:171-183` now loads context and evaluates basic eligibility before the check budget, private owner header/facts, or load fault. The targeted regression uses a five-second load fault with `shared` and obtains `ineligible/shared`, read time `0.0`, no fault hits, and all eight checks remaining. The original `unavailable/memory_timeout`, clock advance, and budget charge counterexample is closed.

#### IA4-07 - Medium - VERIFIED CLOSED

The public normal-control boundary now requires raw JSON and calls `strict_control_json` (`runtime.py:273-276`), which applies the 8,192-character inherited bounded parser before typed control validation. Focused tests reject a Python dictionary, duplicate key, and depth 33. Inspect response and host-output caps are enforced at `runtime.py:332-337,424-434`; the cap regression settles the control as failed and emits no inspected event. The original unused-parser/unused-cap defect is closed.

Residual risk: exact 8,192/8,193, bool-as-int, and nonfinite public-boundary cases are not all individually asserted by the focused tests, although the strict models/inherited parser cover those categories.

#### IA4-08 - Medium - OPEN

The store now has meaningful FKs, checks, unique keys, immutable seed/evidence triggers, immutable owner/context identities, sticky disable, prepared/settled control guards, closed status transitions, and an active-control fact-delete guard (`store.py:15-47`). The direct unauthorized delete and owner-tenant update probes are rejected.

It still relies on application convention for important live mutations. Database triggers do not require owner revision/enabled changes or context revision/payload changes to be made by the current authenticated applying control; arbitrary SQL can directly change `memory_owners.enabled/revision/state_digest` or `memory_contexts.revision/payload` while respecting the limited identity/sticky triggers. There is no trigger tying `memory_mutations` to the matching control scope/status/result or enforcing operation-specific row relationships. Reconciliation catches some stale digest/duplicated-column corruption after the fact, but that is not the blueprint §12 database predicate requirement. IA4-08 remains open.

### 10.3 Fresh commands and results

All Python commands used `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=tests;src` (or `src` for probes), no cache provider, the repository `offline_synthetic_guard`, and fresh temporary roots. No live service, install, stage, commit, or push occurred.

```powershell
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py tests/test_synthetic_chatmate_memory_context.py tests/test_synthetic_chatmate_memory_evidence.py --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4reaudit-t1
# 73 passed, 2 failed, 2 skipped in 266.30s
# failures: test_phase4_clause_acceptance[M34], test_offline_phase4_demo
# both: sqlite3.OperationalError: unable to open database file during nested demo scenario creation

$env:SYNCHAT_PHASE4_EVIDENCE_ROOT='C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ve1'
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory_evidence.py::test_phase4_saved_report_reconcile --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4r2
# 1 passed in 9.06s; evidence inventory remained unchanged
```

Read-only parsing found JUnit: 77 testcase elements, zero failures, zero errors, two skips, and exactly 40 `test_phase4_clause_acceptance[...]` nodes. Acceptance: 40 records, all pass, 40 distinct primary references. Evidence: 20 scenarios, 20 verification entries, and 727 files. These mechanical facts do not override IA4-01/03/04.

### 10.4 Evidence identities and preservation

| Artifact | SHA-256 |
|---|---|
| `p4v.xml` | `692f6ecc5e24f1e573da72b594bfc54f5cceeac1d08e71aeeaa82eb966aa798d` |
| `p4ve1/demo.json` | `6edfc610f8031f1d1fa171d4c0784366c47e6298ca4e16dc7311e3520bdd50bd` |
| `p4ve1/verification.json` | `0ad695a07b5829a4ec2709a07988b476b6fe28146850c94bfc8b5a2bf961c6bb` |
| `p4ve1/acceptance.json` | `3a1acf4fb51bb5889cb13ada2f2e9c05b4968e25e4c71e1268757f6d82d97e4f` |

The Phase 4 blueprint Git blob remains `2e748b1f55c0d95195f0126bf22d8d8ab53bcde8`. Initial and pre-edit status retained the pre-existing modified/untracked synthetic workspace. This re-audit edited only this document by appending Section 10. Evidence/JUnit were read-only; implementation and tests were not changed.

### 10.5 Gate and residual risks

Phase 4 is **not ready to authorize Phase 5 planning**. Required remediation is: replace heuristic schemas with the exact closed catalog and recursive semantic validation; make observers and reconciliation independently prove each declared causal/state property and reject semantic substitutions; replace smoke-node acceptance with clause-complete tests/evidence mappings; and enforce remaining live-state/control relationships in SQLite. The Windows demo path-length failure must also be fixed and rerun from a genuinely short fresh root. No green status is granted while IA4-01, IA4-03, IA4-04, and IA4-08 remain open.

## 11. Final remediation verification - 2026-11-13

### 11.1 Final disposition

Independent adversarial disposition: **Phase 4 remains blocked; Phase 5 is not authorized.** IA4-02, IA4-05, IA4-06, IA4-07, and the Section 10 long-path issue are closed against their original counterexamples. IA4-01, IA4-03, and IA4-04 remain High blueprint blockers, and IA4-08 remains a Medium blueprint blocker. The fresh focused and exact combined suites pass, but passing suites and a mechanical 40/40 index do not override the reproduced contract defects.

This verification inspected the current source/tests plus `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4last.xml` and `p4last-e` read-only. No implementation, test, or evidence file was edited; only this section was appended.

### 11.2 Finding decisions

#### IA4-01 - High - OPEN

Malformed `ErrorResult` is now rejected and the generated catalog recursively contains no untyped empty schema except the intentional empty `Preferences` object. The exact recursive catalog is still not enforced. Fresh direct probes showed that `validate_root` accepted both a `Snapshot` with `status="forged"` and a `ControlCommittedData` with `operation="forged"` (`Snapshot:ACCEPTED_INVALID`, `ControlCommittedData:ACCEPTED_INVALID`). This follows from heuristic `_field_schema` string generation and missing root-specific semantic checks in `contracts.py:337-372,442-535`. The nominal 74-plus-root catalog therefore still differs materially from blueprint §§6 and 10 and cannot close M17/M28/M32/M35/M37/M38.

#### IA4-02 - High - CLOSED

Re-evaluation found the durable acceptance/apply split, persistent fence, cancellation/deadline handling, ordered postcommit phases, durable failure fence, and conformance controls still present. Focused control, replay, CAS, cancellation, interleaving, and reset tests passed. No original IA4-02 counterexample was reproduced. Residual risk remains that actual process-kill/restart recovery is represented but not exercised by killing a controller process.

#### IA4-03 - High - OPEN

Source substitution, request binding, expiry, control/CAS transitions, history mutation, and reconstructed no-learning checks are materially improved, and the saved reports reconcile read-only. The observers and verifier are not clause-complete: history comparison is hard-coded to request items `[1:4]`; replay observation checks only event presence rather than replay event/output/stored-result equality; and reconciliation does not establish every §17 deadline/counter/fence/terminal-queue and inherited-effect relationship. `verification.py` validates many operation surfaces but still relies on the implementation's emitted journal/event model for portions of the reconstruction. Thus successful `verification.json` and mutation tests do not independently prove every assertion-specific prerequisite and cross-surface equality required by §§10.3 and 17.

#### IA4-04 - High - OPEN

The JUnit parser and unique node mechanics are closed: fresh artifacts contain 40 pass records, 40 distinct primary nodes, and the exact JUnit hash. Clause completeness remains open. The single parameterized function still substitutes bounded checks for complete matrix clauses; examples include M02/M04 sharing only a foreign requested-owner boundary, M23 checking one pre-apply cancellation path, M32 checking one forged seed tenant, M38 invoking the still-incomplete reconciler, M39 testing only a socket denial, and M40 checking only target-directory/tool-count existence. `acceptance.py` marks a case pass solely from node termination and does not require each row's positive/negative/fault/evidence bindings to have been observed. Therefore the saved 40/40 result is mechanically valid but not blueprint-clause acceptance.

#### IA4-05 - High - CLOSED

The authenticated `memory_boundary`, cancellation, durable context-control path, owner-specific Bram/Cyra scripts, 20-scenario demo, B01-B05 effects, and selected suppression profiles remain implemented and tested. The fresh demo and combined gate passed. The prior missing-API/demo finding was not reproduced.

#### IA4-06 - Medium - CLOSED

Basic ineligibility remains evaluated before private read/fault/check charge. The regression test again passed and preserved `ineligible/shared`, zero read time, no fault hit, and all eight checks. No original privacy-ordering counterexample was reproduced.

#### IA4-07 - Medium - CLOSED

Normal controls still require raw bounded JSON; duplicate/depth malformed inputs and host-output caps are tested and passed. The malformed `ErrorResult` negative test also passed. Exact 8,192/8,193 and every numeric subtype are not individually tested, but no original unused-boundary/output-cap counterexample remains.

#### IA4-08 - Medium - OPEN

The added triggers reject ordinary direct SQL without the registered authorization function, but authorization is client-forgeable. In a fresh temporary assessment, an external `sqlite3` client registered its own `memory_authorized()` returning 1, inserted an `applying` `fixture_set_enabled` control and matching singleton fence, then directly updated `memory_owners.revision/enabled`. SQLite committed it and returned `FORGED_EXTERNAL_UPDATE (2, 0)`. The database cannot distinguish the trusted store connection from an external holder that registers the same function; the control/fence tables themselves also permit the forged rows. Blueprint §12's external-client authorization predicate is therefore not established.

#### Section 10 long-path issue - CLOSED

`run_demo` now allocates scenario databases under the short approved temp parent independently of the output/basetemp depth. `test_offline_phase4_demo` passed from a deliberately deep Windows basetemp in `76.82s`. The first setup attempt failed before collection because the manually supplied parent hierarchy did not exist; after creating that hierarchy under the approved temp parent, the same deep-path test passed. No SQLite long-path failure recurred.

### 11.3 Fresh artifacts and commands

Read-only artifact identities:

| Artifact | SHA-256 / result |
|---|---|
| `p4last.xml` | `063f89a200a9ec7d252c550badaa905d5cf7057e17a208d8add06bb0ff218abf` |
| `p4last-e/acceptance.json` | `701f1e308b392de176c8e6c0cb43ca5fc5ff3f265963de0390344d410182f1d6` |
| `p4last-e/demo.json` | `5b82c7a2ec2ac32c948bac6cca60da0a6899abbeb925982b2b0cd97eb00ad738` |
| `p4last-e/verification.json` | `78c082c4f85634e2eaa8a843cbe3cf84f600a13648faeeae0da160109ecc7b06` |
| Phase 4 blueprint Git blob | `2e748b1f55c0d95195f0126bf22d8d8ab53bcde8` |

`p4last.xml` contains 79 testcase elements, zero failures, zero errors, and two skips. `acceptance.json` has 40 pass records, 40 distinct primary references, and every record binds the exact JUnit hash above. `demo.json` has 20 scenarios and `verification.json` has corresponding successful read-only summaries. These are mechanical/evidence inventory facts, not waivers for IA4-01/03/04/08.

Commands were run from `services/deepteam-worker` with the existing `.venv`, `PYTHONPATH=tests;src` (or `src` for probes), `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and `-p offline_synthetic_guard`:

```powershell
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py tests/test_synthetic_chatmate_memory_context.py tests/test_synthetic_chatmate_memory_evidence.py --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4final-focus
# 77 passed, 2 skipped in 403.75s

.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard <blueprint §18 exact 21-file list> --deselect tests/test_synthetic_chatmate_calendar_remediation.py::test_corrected_frozen_predecessor_bytes_preserved --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4final-combined
# 791 passed, 2 skipped, 1 deselected in 1425.85s

.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py::test_offline_phase4_demo --basetemp <existing-deep-Windows-parent>
# 1 passed in 76.82s

git diff --check
git hash-object Documents/SYNTHETIC_CHATMATE_PHASE4_BLUEPRINT.md
git status --short --untracked-files=all
# diff check exit 0 with the pre-existing REDTEAM_EXPANSION.md LF/CRLF warning; blob 2e748b1f...; nothing staged
```

Additional Python 3.11 probes called `validate_root` with the two malformed roots above, parsed JUnit/acceptance/demo counts, and created only fresh temporary assessments for the forged-fence check. Two initial external-probe invocations failed with PowerShell quoting `SyntaxError`; the corrected variable-based invocation completed and produced the forged update result. No live service was accessed, no dependency was installed, and no stage/commit/push occurred.

### 11.4 Residual risk and required remediation

The exact selected inherited gate has no observed regression, the long-path issue is closed, and the current implementation is substantially stronger than Section 9's baseline. Phase 5 nevertheless remains blocked. Required remediation is to: materialize and enforce the exact recursive schema/event catalog rather than heuristic field schemas; make observers and reconciliation independently clause-complete across history/no-learning/replay/operation/CAS/time/host-output/counter/fence/inherited effects; bind every M01-M40 record to clause-complete positive, negative, fault, and evidence checks; and replace client-registerable SQLite authorization with a design where an external connection plus forged control/fence cannot authorize live-state mutation. A green light requires fresh adversarial evidence closing all four remaining findings.

## 12. Closeout requirement amendment and final independent audit - 2026-11-14

### 12.1 Requirement amendment and disposition

The user-approved closeout amendment is authoritative for this bounded audit: local application/host processes and assessment database files are trusted; arbitrary external direct database writes are outside the supported threat model; and `memory_authorized` is an application-path integrity predicate, not external authentication. This amendment supersedes only Section 11's IA4-08 external-writer interpretation. It does not waive application-path authorization, CAS, closed transitions, transactional state/result/witness integrity, or read-only reconciliation, and it does not alter the other Phase 4 requirements.

Final independent disposition: **Phase 4 is not ready for Phase 5 documentation. Phase 5 implementation is also not authorized.** IA4-01 is closed for the bounded forged-status/operation, malformed nested-data, and closed-recursion requirements. IA4-08 is closed under the approved threat-model amendment. IA4-03 and IA4-04 remain supported-path High blockers: the read-only verifier does not independently establish every required deadline/counter/fence/queue/inherited-effect relationship, and the saved acceptance contract does not provide meaningful distinct positive, negative, fault, and evidence checks for every M01-M40 clause.

This audit used current source/tests plus `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4c-e` and `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4c.xml` read-only. Sections 1-11 remain historical and unchanged. No implementation, test, evidence, accepted blueprint, or other accepted document was edited.

### 12.2 Amendment traceability and artifact preservation

The amendment is materialized as `memory_phase4/data/closeout_correction.json`, artifact ID `phase4-closeout-correction-0.4.0-2026-11-13`. It states the trusted-local-files boundary, describes `memory_authorized` as application-connection integrity only, preserves five supported-path guarantees, and expressly disclaims external database-writer authentication, OS broker/service isolation, and database encryption.

The correction is not an unbound report-only waiver. Current artifact admission requires exactly 29 definitions; a supplied assessment had 29 definition files and 29 registration digests, all canonical content digests matched, and `closeout_correction` was registered as SHA-256 `83d5870ca16b158e5d577363d44ad89beb85ccffa69b1dad78f4faaae255006a`. `MemoryBundle.from_parts` and read-only reconciliation require the 29-artifact set and reject drift. The correction's `evidence_policy` is `fresh_roots_only; previously saved evidence remains immutable under its original binding`.

Older evidence was not overwritten. Recomputed `p4last-e` hashes still equal Section 11: acceptance `701f1e308b392de176c8e6c0cb43ca5fc5ff3f265963de0390344d410182f1d6`, demo `5b82c7a2ec2ac32c948bac6cca60da0a6899abbeb925982b2b0cd97eb00ad738`, and verification `78c082c4f85634e2eaa8a843cbe3cf84f600a13648faeeae0da160109ecc7b06`. Supplied `p4c-e` remained unchanged across the saved-report reader pass.

### 12.3 Finding dispositions

#### IA4-01 - High - VERIFIED CLOSED FOR BOUNDED CLOSEOUT

`Snapshot.status` is now a closed enum and `ControlCommittedData.operation` is now a closed enum. Recursive `$ref` validation reaches nested `OwnerMeta.stored_fact_refs[*].source_kind`; untyped empty schemas are rejected except the intentional empty `Preferences` object. Fresh focused execution and the five-probe selection rejected forged `Snapshot.status`, forged committed operation, malformed nested source kind, nonfinite data, malformed `ErrorResult`, and extra/invalid closed-root data. The original Section 11 supported-path counterexamples no longer reproduce.

Limitation: this closure is for the explicitly bounded malformed-root and recursive-validation requirements, not a claim that every theoretically possible JSON Schema mutation has an individual test.

#### IA4-03 - High - OPEN

Assertion-specific missing-versus-contradictory behavior is materially improved. Missing selected request binding is inconclusive; request-digest, source-text, immutable-history, no-learning, and control semantic substitutions become contradictions. Source identities, request order, control acceptance/commit order, owner/context transitions, CAS, replay output equality, host-output ownership, snapshot selection/expiry, and several inherited effects are checked. The original source-substitution counterexample is closed.

The required independent closeout is still incomplete. `verification.py` reads control `accepted_seconds` and `deadline_seconds` but does not independently prove deadline derivation/order against every event/fault/terminal outcome. It exports counts but does not reconcile `MemoryCounters` consumption across all reads/controls, does not independently prove the persisted fence and queue/terminal state relationships, and does not comprehensively reconstruct all inherited communication/calendar effects from their independent records. Observer checks still consume implementation-produced event/journal surfaces for parts of their reconstruction. The supplied successful `verification.json` therefore proves that the current verifier accepted 20 scenarios read-only, not that every required IA4-03 relationship was independently established.

#### IA4-04 - High - OPEN

Mechanical JUnit handling is correct: `p4c.xml` has 87 cases, zero failures/errors, two skips; all 40 acceptance records are `pass`, have distinct primary M nodes, and bind exact JUnit SHA-256 `e946c7826b9c4de0163645beade3d96d9eabb8145ad147e40c7da59190f1502c`.

The coverage contract is not meaningful four-kind coverage. `coverage_contract()` assigns the same test references to `positive`, `negative`, `fault`, and `evidence` for each M case and gives every kind the same predicate, `bound_scenarios_have_existing_evidence_directories`. `records()` marks each kind passed from node termination plus directory existence; it does not require kind-specific observed outcomes. Many M cases have no kind-specific negative or fault execution, while default scenario binding can attach every demo directory without proving the clause. The seven supplemental weak-clause regressions improve selected M cases but do not cure all 40 records. The 40/40 index is mechanically honest about skips, but it overstates clause coverage and does not satisfy the approved IA4-04 closeout contract.

The two skips are honestly reported and are not counted as passes: `test_phase4_cli_generate` requires an explicit fresh output root, and `test_phase4_saved_report_reconcile` requires an explicit saved evidence root. Both were independently run with those inputs and passed. The focused JUnit records no deselection. The separately reported combined gate has one deliberate deselection, the optional machine-local frozen predecessor byte-preservation test; selected portable predecessor admission/drift/ownership checks remain in scope. No deferred clause is identified in `acceptance.json`; absent kind-specific checks are therefore not honestly represented as deferred or inconclusive.

#### IA4-08 - Medium - VERIFIED CLOSED UNDER AMENDED REQUIREMENT

The unsupported external SQLite writer forgery from Section 11 is outside the amended threat model and is not an authentication claim. On the supported application path, fresh tests confirmed direct live owner/context updates and journal insertion fail without the current applying control and registered authorization function. The existing triggers, CAS checks, closed transitions, transaction boundaries, result/witness binding, and read-only reconciliation remain selected and passing. The immutable registered correction artifact makes the scope change traceable and does not disable those checks.

Limitations retained: filesystem/host compromise, arbitrary external SQLite writers, process isolation, encryption, and deployed-service authentication are not certified.

### 12.4 Commands, results, and evidence identities

Commands ran offline from `services/deepteam-worker` using the existing `.venv`, `PYTHONPATH=tests;src` (or `src` for inspection), `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `-p offline_synthetic_guard`, and fresh approved temporary roots.

```powershell
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py tests/test_synthetic_chatmate_memory_context.py tests/test_synthetic_chatmate_memory_evidence.py --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4audit-close-focus
# 85 passed, 2 skipped in 463.22s

$env:PYTHONHASHSEED='1'; $env:SYNCHAT_PHASE4_EVIDENCE_ROOT='C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4audit-close-gen'
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py::test_phase4_cli_generate --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4audit-close-gen-t
# 1 passed in 81.74s

$env:PYTHONHASHSEED='2'; $env:SYNCHAT_PHASE4_EVIDENCE_ROOT='C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4c-e'
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory_evidence.py::test_phase4_saved_report_reconcile --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4audit-close-read
# 1 passed in 16.28s; supplied evidence inventory unchanged

.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard <five targeted schema/store/observer/reconciler probes> --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4audit-close-probes
# 5 passed in 14.86s
```

One ad hoc inline schema probe command failed with a PowerShell/Python quoting `SyntaxError`; it is not counted. The equivalent named pytest probes above passed and provide the retained reproduction result.

| Supplied artifact | SHA-256 / observed result |
|---|---|
| `p4c.xml` | `e946c7826b9c4de0163645beade3d96d9eabb8145ad147e40c7da59190f1502c`; 87 tests, 0 failures, 0 errors, 2 skips |
| `p4c-e/acceptance.json` | `a98435a6bffbc249100f7c5b383346bcb4f8c1c019460e58aa0dbc93ca3778b6`; 40 pass records |
| `p4c-e/demo.json` | `72f53e615df3f195b1f57d2d69ec523e4add271a37c833a6460804ce983376b6`; 20 scenarios |
| `p4c-e/verification.json` | `64e9dfaf097e9148fe414909746b2c27e17d6018ba2ac66fbc0f78f8da0f2b2c`; 20 read-only summaries |
| Phase 4 blueprint Git blob | `2e748b1f55c0d95195f0126bf22d8d8ab53bcde8` |

The independently observed focused result is **85 passed, 2 skipped**. Generator and reader passed in separate processes and roots/hash seeds as shown. A **799 passed, 2 skipped, 1 deselected** combined result was described in the supplied closeout context, but neither `p4c.xml` nor `p4c-e` contains that combined execution record; this audit did not rerun the approximately full combined gate and therefore does **not** promote that count to independently verified evidence. The deselection description is retained above, not counted as a pass, and does not cure IA4-03/04.

`git diff --check` exited 0 with only the pre-existing `REDTEAM_EXPANSION.md` LF/CRLF warning. No live call, dependency install, stage, commit, or push occurred. Fresh probe/generator roots were outside the repository. The only repository edit made by this audit is this appended Section 12.

### 12.5 Final readiness decision

No Phase 5 documentation readiness is granted because supported-path High blockers IA4-03 and IA4-04 remain. This is separately and more strongly not an authorization to implement Phase 5. Readiness requires fresh evidence showing independent reconciliation of identities/order/transitions/replay/CAS/deadlines/counters/fence/queue/inherited effects and an acceptance contract whose positive, negative, fault, and evidence checks are genuinely kind-specific, with skips, deselections, and deferred clauses represented without conversion to pass.

## 13. Bounded closeout implementation record - 2026-11-14

### 13.1 Additive requirement binding

The trusted-local-storage amendment in Section 12 remains the approved IA4-08 boundary. It is bound in the new immutable `closeout_correction` definition, SHA-256 `83d5870ca16b158e5d577363d44ad89beb85ccffa69b1dad78f4faaae255006a`. Fresh targets now require exactly 29 definitions; the complete current artifact aggregate is `344809fbf4e9c750b8d2326cb41f7a61cbabc58f0c1355fa5f424f7eded13d80`. Existing 28-definition evidence remains unchanged under its historical binding. No external-writer authentication, OS broker, separate database service, encryption, or dependency was introduced or claimed.

### 13.2 Implemented closeout changes

- IA4-01: replaced the reproduced permissive paths with explicit closed enum-bearing schemas and recursive validation. Forged `Snapshot.status`, forged `ControlCommittedData.operation`, malformed nested `FactRef.source_kind`, nonfinite values, malformed `ErrorResult`, and extra fields are rejected by named regressions.
- IA4-03: the read-only verifier now checks exact 60-second control deadlines, acceptance/terminal/fault ordering, counters derived from snapshots and controls, replay no-charge/single-journal behavior, active and persistence fences, empty terminal queues and leases, and inherited approval/execution/message/meeting/calendar/invitation/effect relationships from SQLite and public exports. Adversarial copied-root tests cover deadline, counter, fence, queue, replay, fault-time, and inherited-effect substitutions. Public missing prerequisites remain inconclusive; restricted truth is not used to upgrade selected public evidence.
- IA4-04: acceptance records now contain separate positive, negative, fault, and evidence descriptors with exact nodes, applicability, scenarios, expected observations, and predicates. Non-applicable fault checks carry explicit reasons; missing scenarios or predicates remain inconclusive. Skips and deselections are retained as metadata and cannot count as passes.
- IA4-08: application-path ownership, CAS, transitions, transactions, witnesses, triggers, and reconciliation remain enforced. Direct external database writers remain outside the approved PoC threat model; `memory_authorized` is documented only as an application-connection integrity marker.

Changed closeout files are confined to `memory_phase4/{contracts,acceptance,artifacts,evidence,store,verification}.py`, `memory_phase4/data/closeout_correction.json`, and the three Phase 4 test files. No inherited source, accepted blueprint, prior evidence, dependency, Phase 5 file, inference path, attack/Judge path, API/UI, live-service integration, or continuation behavior was changed.

### 13.3 Actual final executions

All commands used the existing Python 3.11 worker environment, fictional data, fresh short roots, `PYTHONPATH=tests;src`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and `-p offline_synthetic_guard`.

| Execution | Actual result |
|---|---|
| Three Phase 4 files, final expanded coverage, JUnit `p4z.xml` | **209 passed, 2 skipped in 477.84s**, exit 0 |
| Guarded CLI generation, `PYTHONHASHSEED=1`, fresh `p4z-e` | **1 passed in 81.13s**, exit 0 |
| Separate-process saved reconciliation, `PYTHONHASHSEED=2` | **1 failed in 15.57s** because the reader requires all 40 acceptance records to pass and the fresh artifact honestly contained 40 inconclusive records |
| Exact portable inherited/Phase 4 combined selection | **923 passed, 2 skipped, 1 deselected in 1566.38s**, exit 0 |

The two focused skips are the environment-gated CLI generator and saved-report reader. The generator was separately supplied a fresh root and passed. The reader was separately run and failed for the acceptance disposition above, not for SQLite mutation or reconciliation corruption. The single combined deselection is the blueprint-authorized optional machine-local frozen predecessor byte-reference test; portable predecessor ownership, drift, collision, and preservation checks remained selected.

Fresh identities:

| Artifact | SHA-256 / disposition |
|---|---|
| `p4z.xml` | `a3aaa5e55e0c75d9c2b708061e4a14ceb4877a3ff1e2ff8eced3dc6b9e28d979` |
| `p4z-e/demo.json` | `1038ff2b70e25791f1b8398bc9b685aa32b087c2be1ed8502392da51a4128bcf` |
| `p4z-e/verification.json` | `65db54673c4fa3ffacdd19ce5b936fc864f5c35e83718d778f2681b988d4ede6` |
| `p4z-e/acceptance.json` | `c0031b64da22d565c806935a5aeab9170c3d52c22cdf26736aad0777cfcffd63`; 40 inconclusive |

### 13.4 Per-finding closeout disposition

- **IA4-01: closed** for the required closed recursive validation and reproduced malformed-root/nested-data counterexamples.
- **IA4-02: closed** as recorded by the independent audits.
- **IA4-03: implementation substantially completed and focused/combined regressions pass, but final acceptance remains unverified** because the fresh saved-reader command is coupled to the unresolved IA4-04 acceptance gate. No contradictory reconciliation result was observed.
- **IA4-04: open, High.** The new contract no longer manufactures passes, but the generated 20-scenario demo does not provide distinct negative/fault scenario evidence for every applicable descriptor. The current `test_phase4_matrix_check` negative branch also reuses a generic forged-snapshot check across clauses, and several fault/evidence branches validate descriptors rather than each clause's actual runtime outcome. All 40 saved records therefore correctly remain inconclusive.
- **IA4-05, IA4-06, IA4-07: closed** as recorded by Sections 10-12 and retained regressions.
- **IA4-08: closed under the approved trusted-local-files amendment**, with external direct writers explicitly out of scope and no external-authentication claim.

### 13.5 Final gate

The implementation and inherited regression suites are green, and the acceptance design now fails closed instead of converting missing evidence to passes. However, the required Phase 4 acceptance gate is **not complete**: IA4-04 still lacks clause-specific negative/fault/evidence scenarios and all 40 fresh records are inconclusive. Consequently **Phase 4 is not ready for Phase 5 documentation, and Phase 5 implementation is not authorized**. This is a supported-path evidence blocker, not an IA4-08 external-writer issue. No green result is forced from passing test totals.

## 14. Final narrow independent IA4-04/IA4-03 review - 2026-11-14

### 14.1 Scope and disposition

This review was limited to IA4-04 closure and the current IA4-03 disposition. It inspected blueprint rows M01-M40, current `memory_phase4/acceptance.py`, the clause/matrix and reconciliation tests, and supplied fresh artifacts `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ia404-e` plus `p4ia404.xml` read-only. It did not reopen any other finding, add an IA4-03 requirement, or edit implementation, tests, evidence, blueprint, or the trusted-local-storage amendment in Section 12.

Final narrow disposition: **IA4-04 remains open and Phase 4 acceptance does not close. IA4-03 is verified at its current supported-path disposition: the saved verifier and targeted adversarial verifier probes pass, and no contradictory supported-path evidence was found.** Because IA4-04 does not genuinely close, readiness to begin Phase 5 documentation/planning is **not granted**. Phase 5 execution is separately and unconditionally **not authorized under this assignment**.

### 14.2 IA4-04 independent result

The supplied mechanics are internally consistent: `p4ia404.xml` has 211 testcases, zero failures/errors, two skips, and no recorded deselection; `acceptance.json` has 40 records marked `pass`, four distinct check descriptors per row, and binds the exact JUnit hash. The tokens are not, however, all emitted only after actual clause-specific positive, negative, fault, and evidence behavior.

- Every applicable evidence node calls the positive clause helper, then creates a separate generic assessment containing `"Evidence."`, exports it, runs `reconcile`, checks only that observations are non-unexpected, and emits `<Mxx>:evidence` (`test_synthetic_chatmate_memory.py:303-312`). It does not prove that the bound demo scenario satisfied that row's evidence predicate. `acceptance.py:70-74` then checks only that each reused scenario has a structurally valid nonempty `observations.json`; it does not select a row-specific assertion or expected result. Rows without positive scenario bindings reduce evidence to token presence alone.
- Negative nodes are distinct JUnit nodes but several execute substitutes rather than the blueprint row's adverse cases. M01/M12-M16/M19/M27-M28, for example, share an altered request digest; M32-M34/M38/M40 share a forged memory-seed tenant; and M25/M26 merely count unchanged seed facts. The token is emitted after those substitutes, not after the complete row-specific negative behavior (`test_synthetic_chatmate_memory.py:236-287,312`).
- Applicable injected-fault rows are M13, M15, M16, M20, M21, M23, and M24. Their fault nodes rerun the positive helper and emit a fault token. M13/M16/M20/M23/M24 have no scenario binding, so `_predicate` returns token presence without requiring any saved fault hit (`acceptance.py:63-65`). M15 and M21 bind `unavailable` and `response-loss`, but `reached_fault_hit` accepts any hit whose status is not `not_reached`, rather than the clause-specific phase/mode/outcome (`acceptance.py:75-77`). Thus the artifacts contain real fault behavior, but the acceptance predicate does not establish the required row-specific fault behavior for all seven rows.
- The other 33 rows mark fault as not applicable with the explicit reason that the blueprint row specifies deterministic positive/negative/evidence coverage and no injected fault. That reason is facially appropriate for an injected-fault category and is honestly retained as `not_applicable`; it does not compensate for missing positive, negative, or evidence proof.
- Reused demo evidence is genuine evidence for its own scenario: the saved report reconciles read-only, and the scenario files are present. It does not genuinely meet the acceptance contract's scenario-bound predicate for each reused M row because `events_export_present`, `observations_export_present`, and `reached_fault_hit` are only structural/any-hit predicates. No causal check ties those files to each row's `expected_observed` text.
- Missing nodes, scenario directories, or structural predicates remain `inconclusive` in `records()`. Missing semantic requirements do not: a token plus the weak structural predicate converts them to `pass`. The required fail-closed property therefore remains incomplete.

### 14.3 M01-M40 disposition

All rows are **mechanically pass in the supplied index but not independently accepted; acceptance disposition is inconclusive for M01-M40**. The row groups below state the directly observed reason without expanding their blueprint requirements.

| Rows | Independent disposition |
|---|---|
| M01-M12 | Inconclusive: each evidence check is generic/structural; shared negative substitutions affect M01 and M12, while other rows still lack a scenario-bound clause-specific evidence predicate. |
| M13-M16 | Inconclusive: evidence is generic; M13/M16 fault acceptance requires no saved fault hit, and M15 accepts any reached hit rather than its exact fault/outcome. |
| M17-M24 | Inconclusive: evidence is generic; M20/M23/M24 fault acceptance requires no saved hit, M21 accepts any reached hit, and several negatives are generic stale-clear controls rather than the row-specific adverse case. |
| M25-M31 | Inconclusive: evidence is generic/structural; M25/M26 negatives only count facts, M27-M30 reuse request/projection substitutions, and M31 checks a completeness-gap shape without a row-specific saved-evidence predicate. |
| M32-M40 | Inconclusive: evidence is generic/structural; M32-M34/M38/M40 negatives reuse forged seed tenancy, and saved B01-B05/event/observation presence is not tied to each row's expected behavior. |

This disposition does not assert that every positive runtime behavior is absent. It states that no M row has all applicable kinds established by the current token and predicate path, so none can close IA4-04.

### 14.4 Current IA4-03 disposition

The current read-only verifier still passes the supplied 20-scenario report. Targeted mutations for deadline, counter, fence, queue, replay output, fault timing, and inherited message/meeting effect substitutions remain rejected. The targeted command completed **4 passed in 34.69s**. No contradictory supported-path evidence was found in the supplied root or these probes.

This verifies the current IA4-03 disposition only. It does not use IA4-03 to upgrade IA4-04 tokens, does not add new IA4-03 requirements, and does not claim that generic acceptance predicates are made clause-specific merely because `reconcile()` succeeds.

### 14.5 Commands, skips, deselections, and identities

Commands ran offline from `services/deepteam-worker` with the existing `.venv`, `PYTHONPATH=tests;src`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `-p offline_synthetic_guard`, and fresh approved basetemps:

```powershell
$env:SYNCHAT_PHASE4_EVIDENCE_ROOT='C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ia404-e'
.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory_evidence.py::test_phase4_saved_report_reconcile tests/test_synthetic_chatmate_memory_evidence.py::test_reconcile_rejects_deadline_counter_fence_queue_replay_and_fault_mutations tests/test_synthetic_chatmate_memory_evidence.py::test_reconcile_reconstructs_inherited_effects_and_rejects_row_substitution --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ia404-review-verifier
# 4 passed in 34.69s

.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_memory.py::test_acceptance_requires_exact_unique_passing_pytest_node tests/test_synthetic_chatmate_memory.py::test_coverage_contract_has_distinct_kind_specific_descriptors 'tests/test_synthetic_chatmate_memory.py::test_phase4_matrix_check[M34-evidence]' 'tests/test_synthetic_chatmate_memory.py::test_phase4_matrix_check[M38-negative]' 'tests/test_synthetic_chatmate_memory.py::test_phase4_matrix_check[M15-fault]' --basetemp C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ia404-review-matrix
# 5 passed in 98.12s

git hash-object Documents/SYNTHETIC_CHATMATE_PHASE4_BLUEPRINT.md
# 2e748b1f55c0d95195f0126bf22d8d8ab53bcde8
git hash-object services/deepteam-worker/src/secmate_worker/synthetic_chatmate/memory_phase4/acceptance.py
# cf76c78aac78591213a924bc95c949e81de93906
```

| Supplied artifact | SHA-256 |
|---|---|
| `p4ia404.xml` | `b867142ef64d95e0f5a9cf59c0a2c3b96c6276016069aa8dd49c33b36c68a9b7` |
| `p4ia404-e/acceptance.json` | `5572d521b25a3866cc1c3882576eb2e9f4457532822cf3b67a5c773fd8728715` |
| `p4ia404-e/demo.json` | `4e885b8cfb17533c111c6a51434085b7c0dfa34cc818647a376988ab744d6d2f` |
| `p4ia404-e/verification.json` | `6615a53a743185ea769ffe1f2a45943004555a3d879b13dda109fa9e2470b359` |

The two supplied JUnit skips are the explicit-environment CLI generator and saved-report reader. They are not counted as passes; the saved reader was rerun with its evidence root and passed. `p4ia404.xml` records no deselection. This narrow review did not rerun or claim the full combined gate, so the historically authorized optional predecessor deselection is neither promoted nor reinterpreted here. No live service, dependency install, staging, commit, push, or evidence mutation occurred. The only repository edit is this append-only Section 14; all prior history and the trusted-local-storage amendment remain intact.

### 14.6 Readiness decisions

- **Readiness to begin Phase 5 documentation/planning: NOT GRANTED.** IA4-03 is verified at its current disposition, but IA4-04 does not genuinely close.
- **Authorization to execute Phase 5: NOT AUTHORIZED.** This assignment cannot grant execution authorization regardless of planning readiness.

## 15. IA4-04 bounded acceptance amendment and closeout - 2026-11-14

### 15.1 Approved amendments

The user approved two narrow clarifications without rewriting Sections 1-14:

1. **Bounded IA4-04 evidence rule:** every applicable M01-M40 requirement requires clause-specific runtime assertions bound to exact executed test identities, outcomes, source/configuration bindings, and JUnit hashes. One test may cover multiple clauses only when each clause is independently asserted and traceably mapped. Saved artifacts are required for the blueprint demonstrations and representative failure, replay, uncertainty, and suppression scenarios, not as a redundant retained demo for every check. Descriptor-only checks, generic forged-snapshot checks, skips, missing properties, or missing evidence cannot pass.
2. **M24 stable identity clarification:** seeded fact IDs remain stable across independently reseeded generations and resolve only inside the current trusted assessment/generation/owner authority. Stale sessions, control IDs, generated memory-snapshot IDs, cursors, leases, callbacks, and operations carrying previous-generation authority are rejected before read or mutation. A fresh authorized operation may legitimately select the same seeded fact ID; the bare ID grants no access to an older generation.

These amendments are additive members of the immutable closeout correction binding. They do not alter the trusted-local-storage limitation, enable Phase 5 capabilities, or reinterpret historical evidence.

### 15.2 Implemented acceptance evidence

The final IA4-04 implementation replaces legacy plain tokens and generic descriptor checks with structured observations emitted only after the corresponding clause assertions complete. Each applicable check binds:

- exact pytest node and successful executed outcome;
- case ID, check kind, expected observation, and evidence basis;
- acceptance amendment ID `phase4-ia4-04-clause-acceptance-2026-11-14`;
- complete Phase 4 source/configuration binding digest `760069123c385b235fd1a51ca21e74f9cfe8e5f8e153c0b5c78c88bf329fb557`;
- exact JUnit SHA-256 and, where required by the bounded amendment, semantic predicates over saved representative scenario evidence.

Clause-specific runtime coverage now includes the strict input/admission matrices, capacity and ordering boundaries, all required load/control fault paths, rollback/witness failures, cancellation/publication/reset and stale-authority boundaries, source/identity/CAS/status/digest substitutions, inherited output validators/effects, reconciliation corruption checks, and offline transport boundaries. Conformance-only fault hooks remain strict, saved, deterministic, and unavailable as model tools or product features.

For fault applicability, M13, M15, M16, M20, M21, M23, and M24 have executed fault checks. The other 33 rows retain explicit `not_applicable` fault dispositions because their blueprint rows specify deterministic positive/negative/evidence behavior rather than injected faults. No inapplicable fault was made mandatory or counted as pass.

### 15.3 Actual verification and evidence

All executions used the existing Python 3.11 worker environment, fictional data, `offline_synthetic_guard`, fresh temporary roots, and no network/provider/service access.

| Execution | Actual result |
|---|---|
| Targeted amended descriptor/runtime execution | **161 passed** |
| Complete three-file Phase 4 suite | **209 passed, 2 skipped**, exit 0 |
| Guarded fresh JUnit-bound CLI generation | **1 passed**, exit 0 |
| Separate-process saved reader, `PYTHONHASHSEED=2` | **1 passed in 16.66s**, exit 0 |
| `git diff --check` | Exit 0; only the pre-existing `REDTEAM_EXPANSION.md` LF/CRLF warning |

The two focused skips are the environment-gated CLI generator and saved-report reader. They were not counted as passes in the focused JUnit. Both were subsequently supplied their required fresh/read-only roots and passed separately. The final focused JUnit records no deselection. The historical combined-gate optional predecessor deselection is not converted into new evidence by this closeout.

Fresh retained root: `C:\Users\SAIASH~2\AppData\Local\Temp\opencode\p4ia404-final2-e`.

| Artifact | SHA-256 / observed disposition |
|---|---|
| `p4ia404-final2.xml` | `f56727ff2f73fddf01b42f323675f484f62220878ddc675fdf96fba882364398` |
| `demo.json` | `70ffdc33c62cda2ff1eb18d6033e659bd64c3b30ea718402213693e85e489e3b` |
| `verification.json` | `8e2f031821e91fbc60ea41f50f04449a75bf0eb5e1405a0119082356a70e3c21` |
| `acceptance.json` | `4a23b9c5700154fffcc1027c8e18e54bd69d1cea1e2a71ca6e3e8e8d0d676ceb` |

Independent parsing found exactly 40 M records, all `pass`; 127 applicable checks, all `pass`; and 33 explicitly reasoned fault checks marked `not_applicable`. There are 160 distinct bound test references. The separate reader reconciled the complete saved report read-only and did not modify its inventory.

### 15.4 Finding dispositions and readiness

- **IA4-04: closed under the approved bounded acceptance amendment.** The final evidence no longer depends on descriptor-only checks or generic substitutions, and missing nodes/properties/scenarios/predicates remain inconclusive.
- **IA4-03: verified at its current supported-path disposition.** The Section 14 targeted deadline, counter, fence, queue, replay, fault-timing, and inherited-effect mutation probes remain passing, and the final saved report reconciles in a separate process. No contradictory supported-path evidence was found. This closeout did not add or waive IA4-03 requirements.
- All other finding dispositions and the approved trusted-local-storage limitation remain as recorded; no closed finding was reopened.

**Phase 5 documentation/planning readiness: GRANTED.** Phase 4 now has passing clause-specific test-backed acceptance, required representative saved-artifact evidence, and independent saved-report reconciliation under the immutable closeout amendments.

**Phase 5 execution authorization: NOT GRANTED.** This closeout authorizes only readiness to begin separately scoped Phase 5 documentation/planning. It does not authorize Phase 5 implementation, inference, attacks, Judge integration, continuation, live services, dependencies, or API/UI/catalog work.
