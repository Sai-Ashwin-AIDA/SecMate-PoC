# TEMPORARY — agent-only Windows device-transfer and exact-resume contract

**Audience: receiving coding agent. Not product documentation.** Snapshot reviewed
2026-11-16. Read this before importing execution modules, running tests, starting
services, or following old roadmap instructions. All paths below are relative to
the **receiving SecMate repository root**, unless explicitly marked historical.
The old machine used `C:\Users\Sai Ashwin\secmate`; do not assume that path exists.

**Lifetime:** retain until the receiving agent has verified source transfer/setup,
completed the pending usability check, and recorded the checkpoint and remaining
UI task in the durable build/integration records. Delete only after user acceptance
and explicit cleanup authorization; do not delete source analyses or build history.
This file's authority is limited to transfer/setup and this resume point.

## 1. Immediate briefing — do not restart completed phases

- Product: localhost internal AI-team security-testing PoC, not public SaaS.
- New target: **Synthetic ChatMate**, source-informed fictional employee assistant.
  It is implemented **inside SecMate**, not in the separate real ChatMate repository.
- Target ID `secmate.synthetic-chatmate.fresh.v1`; target version `0.5.0`.
- **Latest checkpoint is Section 17** of
  [SYNTHETIC_CHATMATE_PHASE5_BUILD_RESULTS.md](./SYNTHETIC_CHATMATE_PHASE5_BUILD_RESULTS.md).
  Check for any later append before acting. A new documented checkpoint supersedes
  this snapshot; never roll source back to match an old statement.
- Current execution profile `deepteam-conversation-v1` **2.1.0**: target token cap
  **12,000**, four logical model turns, two transport attempts per turn, four total
  accepted attempt slots, 500 output tokens/request, 45s operation cap, 120s target
  deadline. Outer DeepTeam campaign budget remains shared and independently enforced.
- Interface/prompt/provider-schema correction **0.5.1** is done offline (Section 15).
  Request-accounting correction is done offline (Section 16). Budget sizing is done
  offline (Section 17). **Do not repeat those implementation chunks by default.**
- **NEXT CHUNK:** after setup/offline checks and renewed authorization, repeat three
  benign live usability scenarios with the current interface/accounting/budget.
  It is not another attack campaign, blueprint phase, or full-system audit.
- FOLLOWING CHUNK: a small read-only capability/examples presentation and observed
  activity UI improvement, using actual live outcomes. Do not start it before
  establishing what the usability check actually demonstrated.

## 2. User decisions and permitted actions

The user approved a Windows-to-Windows **full source workspace** transfer including
`.git`, current modified AND untracked source, tests, documents, and lockfiles.
This is **source only**: no old runtime data, secrets, dependencies, build outputs,
or external temporary evidence should be assumed present.

The receiving agent MAY verify/install missing runtimes and the documented existing
dependencies, create fresh local virtual environments, run isolated offline checks,
and start localhost services. This is setup permission, not permission to change
application behavior, replace pinned frameworks, or launch inference automatically.

The user will enter provider keys themselves. Never request keys in chat, print
settings/environment values, include keys in arguments/logs/artifacts, or commit
local environment files. Prior preflight exposed credential values in internal
tool output; user rotation is recommended before further live use. Do not read or
reproduce old keys to investigate that event.

Live calls require a new explicit bounded authorization on the receiving machine,
including fictional-data submission under the configured provider policy. Existing
keys or CLI flags are not authorization. No automatic attack runs, approvals,
message/calendar effects, provider fallback, commits, pushes, resets or cleanup.

Work in small sequential chunks: state a short plan, implement only the assigned
slice, verify, record results, stop at its gate. Ask on real blockers, not routine
implementation choices. Do not reintroduce exhaustive artifact-per-test audits.

## 3. Transfer inventory — local filesystem is authoritative

Historical Git checkpoint: branch `Ashwin`, HEAD
`67171fe928b90c5538fc0a4e3202b86e7f660466`. Substantial new work remains modified
and **untracked**, including the synthetic target package, tests and phase docs.
Git/remote HEAD alone does not reproduce it. No commit/push is needed for transfer.

Before copying, stop the old localhost app and wait for workers to finish or cancel
through supported controls. Copy current source bytes, hidden `.git`, lockfiles,
all new `Documents/*.md`, and all modified/untracked implementation/tests. Exclude
`.venv`, `node_modules`, `dist`, caches, `.env`, `apps/api/data`, worker output
artifacts and machine-local temporary scripts/evidence. Never use `git clean`,
`git reset`, a clean clone, or archive-of-HEAD as a substitute for this workspace.
Do not alter source line endings during transfer: frozen source-map hashes bind
bytes. Preserve source data JSON under the synthetic package; it is not disposable
runtime output. Copy to a short writable local path on the work laptop rather than
running from the external HDD. Do not overwrite a nonempty destination workspace.

Receiving inventory, cwd repository root:

```powershell
Test-Path -LiteralPath ".git"
Test-Path -LiteralPath "apps/web/package-lock.json"
Test-Path -LiteralPath "services/deepteam-worker/src/secmate_worker/synthetic_chatmate/model_phase5/execution_profile.json"
Test-Path -LiteralPath "Documents/SYNTHETIC_CHATMATE_PHASE5_BUILD_RESULTS.md"
git status --short --untracked-files=all
git log -1 --oneline
```

If expected source/tests/docs are absent, stop for a corrected copy. Do not rebuild
them from conversation summaries. If `.git` did not transfer, report the discrepancy;
do not initialize/reclone over the source or claim a clean tracked tree.

Old history/dashboard/run evidence will be absent in a source-only transfer. Empty
local history is expected, not a synchronization defect or reason to fabricate demo
runs. Fresh browser preview sessions/preferences must also be recreated.

## 4. Authority and exact document navigation

| Read when | Repository-relative document | Purpose / current authority |
|---|---|---|
| FIRST | [Phase 5 results](./SYNTHETIC_CHATMATE_PHASE5_BUILD_RESULTS.md) §§15–17 | Current wire correction, accounting and 12,000-token sizing. Earlier failures remain historical. |
| FIRST | [Catalog integration status](./SYNTHETIC_CHATMATE_CATALOG_INTEGRATION_STATUS.md) latest sections, especially §§14–18 | Tool enablement, UI, publication parity, linked hash correction, dashboard. |
| Runtime context | [Phase 5 blueprint](./SYNTHETIC_CHATMATE_PHASE5_BLUEPRINT.md) including reviewer corrections | Initial adapter design; later results/profile increments supersede initial read-only/8,000-token restrictions. |
| Source facts | [chatmate_mapper.md](./chatmate_mapper.md) | Partial source-backed analysis of real ChatMate, revision `9335db39cd92f98cbefb91ffb98bb995fe32048b`; no source tests run. Earlier `CHATMATE_TARGET.md` means this actual file. |
| Synthetic design | [synthetic manifesto](./synthetic_chatmate_manifesto.md) | v0.1.2 bounded design, fictional services, baseline/variants, fidelity limits. |
| Inherited foundation | [build status](./SYNTHETIC_CHATMATE_BUILD_STATUS.md) §19 | Corrected communication `0.2.1`; earlier current-header Phase 2 status is not today's gate. |
| Calendar | [Phase 3 blueprint](./SYNTHETIC_CHATMATE_PHASE3_BLUEPRINT.md), [results](./SYNTHETIC_CHATMATE_PHASE3_BUILD_RESULTS.md) §12 | Corrected `calendar_repaired` `0.3.1`, not audited `0.3.0`. |
| Memory | [Phase 4 blueprint](./SYNTHETIC_CHATMATE_PHASE4_BLUEPRINT.md), [results](./SYNTHETIC_CHATMATE_PHASE4_BUILD_RESULTS.md) §15 and referenced amendments | Accepted facts-only memory closeout, not old blocked audit dispositions. |
| Future attack work | [REDTEAM_EXPANSION.md](./REDTEAM_EXPANSION.md), Part A | Framework-neutral attack definitions, delivery channels, evidence/rubrics. Appendix B remains unverified. Not the current implementation assignment. |
| Future real-target work | [adapter integration handoff](./CHATMATE-ADAPTER-INTEGRATION-HANDOFF.md) | Separate real ChatMate/Surya transport integration; no endpoint/access currently authorized. |
| Legacy manual flow | [workflow product integration](./CHATMATE-WORKFLOW-PRODUCT-INTEGRATION.md), [demo acceptance](./CHATMATE-DEMO-ACCEPTANCE.md) | Operator-mediated real ChatMate compatibility; not this synthetic target. |
| Architecture / safe tests | [TRD-4.md](./TRD-4.md), component pyproject files, runtime policy | Baseline constraints; reconcile historical assumptions against today's source. |

README's next-phase/frozen-Ashwin/verification-count statements are historical and
partly superseded by the user-authorized local implementation. Do not undo current
work to satisfy them. Latest user instruction → assigned scope/current results →
synthetic contracts/source facts → older roadmap. Resolve real conflicts explicitly.
Do not modify old frozen documents just to change a machine path or pass a digest.

## 5. Current product behavior and limitations

- Five available reads: conversation history, mail, Teams, directory, calendar.
- Two staged proposals: message and meeting. Trusted host approval is separate;
  the model cannot approve itself. Assessments can report `Awaiting approval`,
  but the current UI does not implement the full approval interaction.
- Seeded facts-only memory: eligibility/expiry/refresh and host controls, no
  autonomous learning or cross-assessment persistence.
- DeepTeam catalog: 27 methods and 125 risk profiles visible experimentally.
  Visibility is not verified coverage. Missing channels/protocols and tree sibling
  histories can produce explicit unsupported scoreless results.
- Standard = one path, possibly multiple exchanges; Expanded = two isolated paths
  with Critic guidance. Linked Standard follow-up = a NEW assessment using redacted
  parent evidence for generation, not continued target conversation.
- Within-path linear transcript support exists. Inspect gateway semantics before
  assuming all tool state carries between outer callbacks; do not claim full
  persistent-session fidelity.
- Exact Standard direct-user `prompt-injection-v1` baseline bypasses DeepTeam
  enhancement and is labeled unenhanced. Other methods retain transformations;
  Qwen `EnhancedInjection` format failures are not globally fixed. The user plans
  to reduce DeepTeam dependency later; do not prioritize broad enhancement repairs.
- Live direct attack→target refusal→Judge→sealed audit/report was demonstrated,
  including historical `api-run-68e21d205eec`; these old run files will not transfer.
- Targets is informational and read-only with shared cards/details, owner AIDA,
  five Available/two Requires approval, no smoke runner or developer phase labels.
- Dashboard uses canonical target identity and real retained activity, not the
  legacy internal `source="SocMate"` report-family discriminator as display name.
- Judge score 0 means no observed deviation in that case; confidence is not a
  calibrated security guarantee. Target/Judge use the same model family in separate
  roles; do not claim statistical independence.
- Fake data/effects only. No real Microsoft/ConnectorMate/SIEM/ChatMate connection.

## 6. Runtime map and package prerequisites

Observed old-machine versions (facts, not a claim installed on the new laptop):

| Component | Required / observed |
|---|---|
| Windows | PowerShell 5.1 commands; Windows job containment and clock behavior |
| API | Separate `apps/api/.venv`, observed CPython **3.14.7**; manifest allows >=3.11. Reproduce 3.14 if available; no silent cross-version substitution. |
| Worker | Separate `services/deepteam-worker/.venv`, **Python 3.11 only**; observed 3.11.9. `runtime_policy.py` rejects other major/minor versions. |
| Frontend | Observed Node **24.21.0**, npm **11.19.0**; use supported Node 24 LTS and copied lockfile. |
| Worker frameworks | Paramount DeepTeam fork commit **`2fd3445c5bb2070ce09834f66f1622eb914f6f46`**, DeepEval **3.6.2**. Not arbitrary PyPI DeepTeam. |
| Calendar data | **tzdata 2026.6 / IANA 2026f**, exact allowlisted TZif hashes checked by runtime; no OS fallback. Required although absent from worker pyproject direct dependencies. |

API source baseline packages: FastAPI 0.141.1, uvicorn 0.54.0, HTTPX 0.28.1,
Pydantic 2.13.5, python-dotenv 1.2.3, pytest 9.1.1, pytest-asyncio 1.4.0.
Worker pyproject additionally pins pytest-repeat 0.9.4 and its direct dependency
versions. Frontend dependencies are in `apps/web/package.json` and package-lock;
React/TypeScript/Vite include floating manifest ranges, so use **npm ci**, not a
fresh unbounded install/upgrade. No browser tooling is a declared app dependency.

Check Git, Python launcher, Node/npm first; these commands do not expose keys:

```powershell
git --version
py -0p
py -3.11 --version
py -3.14 --version
node --version
npm --version
```

If a runtime is missing, install the corresponding official Python 3.11 / 3.14,
Node 24 LTS, or Git for Windows using approved company software delivery. On a
Windows machine with permitted winget, inspect package IDs with `winget search`
before installing; do not bypass work-laptop policy/admin restrictions. Reopen
terminals so PATH updates apply. If exact timezone package or private fork access
is unavailable, stop with the precise missing prerequisite. Never use a different
fork/commit, tzdata release, OS zones or worker Python to make tests green.

## 7. Setup sequence — explicit cwd, no activation assumptions

Use each tool's working-directory parameter. Do not rely on an activated venv or
bare `python` selecting the right interpreter. Verify the expected parent directory
before creating files/venvs. If `.venv` unexpectedly exists, inspect it and stop
before replacement; copied venvs are not a supported portable installation.

### 7.1 Worker (cwd `services/deepteam-worker`)

```powershell
Test-Path -LiteralPath "pyproject.toml"
py -3.11 -m venv .venv
& ".venv/Scripts/python.exe" -m pip install -e ".[runtime,test]" "tzdata==2026.6"
& ".venv/Scripts/python.exe" --version
& ".venv/Scripts/python.exe" -m pip check
& ".venv/Scripts/python.exe" -m secmate_worker.doctor
& ".venv/Scripts/python.exe" -c "import tzdata; print(tzdata.__version__, tzdata.IANA_VERSION)"
```

The VCS dependency needs Git and authorized access to the Paramount fork. The
doctor checks Python, DeepEval version and installed DeepTeam VCS provenance via
`direct_url.json`; it does not make inference calls. Do not bypass a failed doctor.
Installing the exact tzdata runtime prerequisite is approved setup, not permission
to edit frozen package/schema/source-map definitions.

### 7.2 API (cwd `apps/api`)

```powershell
Test-Path -LiteralPath "pyproject.toml"
py -3.14 -m venv .venv
& ".venv/Scripts/python.exe" -m pip install -e ".[test]" "fastapi==0.141.1" "uvicorn==0.54.0" "httpx==0.28.1" "pydantic==2.13.5" "python-dotenv==1.2.3" "pytest==9.1.1" "pytest-asyncio==1.4.0"
& ".venv/Scripts/python.exe" --version
& ".venv/Scripts/python.exe" -m pip check
```

Do not install DeepTeam into the API environment. API paths resolve the separate
worker from the repository layout. Preserve this layout when moving the source.

### 7.3 Frontend (cwd `apps/web`)

```powershell
Test-Path -LiteralPath "package-lock.json"
npm ci
npm run build
```

If resolution/install fails, record the command/error; do not delete lockfiles or
upgrade packages as a setup workaround. A network/corporate proxy error is not an
application defect. Do not include credentials/proxy passwords in diagnostic logs.

## 8. Offline environment and safe test bootstrap

Do setup/offline verification **before the user enters keys** where possible.
Keep inherited provider credentials and `CONFIDENT_API_KEY` absent in test processes.
Never dump `Get-ChildItem Env:`, `.env`, settings objects, request headers or full
provider error bodies. Worker policy before framework imports is:

```powershell
$env:DEEPTEAM_TELEMETRY_OPT_OUT="YES"
$env:DEEPEVAL_TELEMETRY_OPT_OUT="1"
$env:DEEPTEAM_SHOW_PROGRESS="false"
$env:TELEMETRY_OPT_OUT="YES"
$env:ERROR_REPORTING="NO"
$env:PYTHONDONTWRITEBYTECODE="1"
```

Keep these in receiving-agent process setup, not new committed configuration.
The offline guard blocks DNS, ordinary localhost and remote connections; the only
reviewed exception is Windows asyncio's private socket-pair IPC. Do not relax it
to fix tests. HTTPX MockTransport does not need a real network connection.

### 8.1 Worker checkpoint (cwd `services/deepteam-worker`)

```powershell
$env:PYTHONPATH="tests;src"
& ".venv/Scripts/python.exe" -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_model_phase5.py -k "budget or accounting or proposal or profile"
& ".venv/Scripts/python.exe" -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_deepteam_chatmate_fresh.py tests/test_contracts.py tests/test_execution_budget.py
```

Then run the complete Phase 5 model file once with at least 900s tool timeout:

```powershell
& ".venv/Scripts/python.exe" -m pytest -q --tb=short -p no:cacheprovider -p offline_synthetic_guard tests/test_synthetic_chatmate_model_phase5.py
```

Section 17 recorded 14 selected tests and 57 adjacent tests passing; these are
historical comparisons, not promised counts after later changes. Its full Phase 5
run timed out at 240s; no full pass was claimed. Do not repeat that too-short limit.
Do not run every old audit suite by default. Split genuinely needed long suites
into files and report each result. Environment-gated saved-evidence skips are not
passes or unexpected on a source-only device.

### 8.2 API tests — isolate BEFORE execution-module imports

Current `config.py` supports `SECMATE_API_DATA_ROOT`; current `tests/conftest.py`
sets a temporary data root during collection. Older handoffs predate that feature.
For extra protection and to avoid dotenv/real-worker env-file access, the receiving
agent should create the following **temporary external** `api_offline_bootstrap.py`
(using its file-edit tool), not add it as a project dependency. Run it from
`apps/api`; its imports/bootstrap occur before pytest collection:

```python
import os
import sys
import tempfile
from pathlib import Path

import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
for name in ("GROQ_API_KEY", "GROQ_CRITIC_API_KEY", "OPENROUTER_API_KEY",
             "CONFIDENT_API_KEY", "SECMATE_PHASE5_LIVE_AUTHORIZATION"):
    os.environ.pop(name, None)
os.environ.update(DEEPTEAM_TELEMETRY_OPT_OUT="YES", DEEPEVAL_TELEMETRY_OPT_OUT="1",
                  DEEPTEAM_SHOW_PROGRESS="false", TELEMETRY_OPT_OUT="YES",
                  ERROR_REPORTING="NO", PYTHONDONTWRITEBYTECODE="1")
api = Path.cwd().resolve()
assert (api / "src/secmate_api/config.py").is_file(), "Run from apps/api"
worker = api.parents[1] / "services/deepteam-worker"
worker_python = worker / ".venv/Scripts/python.exe"
assert worker_python.is_file(), "Install the separate Python 3.11 worker first"
with tempfile.TemporaryDirectory(prefix="secmate-api-check-") as folder:
    root = Path(folder)
    sandbox_api = root / "apps/api"
    sandbox_api.mkdir(parents=True)
    os.environ["SECMATE_API_DATA_ROOT"] = str(root / "data")
    from secmate_api import config
    config.API_ROOT = sandbox_api
    config.DATA_ROOT = root / "data"
    # Imports now bind sandbox storage and a nonexistent sandbox .env, not live data.
    from secmate_api import deepteam_catalog, deepteam_runs, chatmate_runs
    from secmate_api import synthetic_chatmate_smoke
    for module in (deepteam_catalog, deepteam_runs, chatmate_runs, synthetic_chatmate_smoke):
        module.WORKER_ROOT = worker
        module.WORKER_PYTHON = worker_python
        if hasattr(module, "WORKSPACE_ROOT"):
            module.WORKSPACE_ROOT = api.parents[1]
    import pytest
    raise SystemExit(pytest.main(sys.argv[1:]))
```

The bootstrap above was exercised on the old machine with the actual current
source: `tests/test_target_projection.py` returned **9 passed, 1 existing
Starlette/httpx deprecation warning in 0.63s**. This validates that focused bootstrap
path, not every API test or new-device setup. Revalidate import/storage paths before
use if the source changes. The temporary old-machine helper is not a required
transfer artifact; recreate it from this block on the receiving machine.
`maintenance.py` includes a legacy direct `API_ROOT/data` cleanup path: do not run
maintenance/history deletion during setup or tests. Do not start a TestClient with
live storage while a real API owns it. Do not import real app modules before this
bootstrap. Do not point `API_ROOT` back to the actual API after importing modules.

Use the bootstrap's absolute receiving-machine path below, cwd `apps/api`:

```powershell
& ".venv/Scripts/python.exe" "<approved-temp>/api_offline_bootstrap.py" -q --tb=short -p no:cacheprovider tests/test_target_projection.py tests/test_fresh_deepteam_api.py
& ".venv/Scripts/python.exe" "<approved-temp>/api_offline_bootstrap.py" -q --tb=short -p no:cacheprovider tests/test_console_summary.py tests/test_standard_reviews.py
```

Allow 900s or split file selections if needed; a timeout is not a pass. Current
tests use mocked transports/subprocesses and real offline worker catalog exports;
the bootstrap is storage/credential isolation, not proof no network exists. If a
test attempts a live operation, stop and investigate rather than supplying keys.

### 8.3 Frontend (cwd `apps/web`)

```powershell
npm test -- --run src/TargetsPage.test.tsx src/targetProjectionService.test.ts src/DeepTeamAssessmentPanel.test.tsx src/AssessmentResultsPanel.test.tsx src/ManagementReport.test.tsx src/StandardReviewFlow.test.tsx src/ExecutiveDashboard.test.tsx src/dashboardService.test.ts --maxWorkers=4
npm run build
```

Use installed Edge/Chrome and existing tooling for optional real layout checks;
do not add Playwright to app dependencies just because old temp tooling is absent.
jsdom checks are not real-browser geometry checks. Relevant prior checks passed
at desktop/390px, but that is not new-device verification.

## 9. Local environment configuration — user enters keys

After offline checks, create `apps/api/.env` from `apps/api/.env.example` only if
absent. The user enters values privately. **Examples omit `GROQ_CRITIC_API_KEY`**;
it is required for dedicated Critic/Expanded/review behavior. Required names:

```dotenv
GROQ_API_KEY=
GROQ_CRITIC_API_KEY=
OPENROUTER_API_KEY=
SECMATE_REQUEST_TIMEOUT_SECONDS=45
SECMATE_API_HOST=127.0.0.1
SECMATE_API_PORT=8000
```

No values in this file are secrets. Do not copy this placeholder block over a
configured file. Do not print the completed file. Provider roles:

- Groq Qwen `qwen/qwen3.8-27b`: attacker/native evaluator via `GROQ_API_KEY`.
- Same Qwen Critic: **dedicated** `GROQ_CRITIC_API_KEY`, no key fallback.
- OpenRouter `nvidia/nemotron-3.5-super-vl:free`: target and separate Judge role via
  `OPENROUTER_API_KEY`. No alternate paid route or local hosted model.

API loads `apps/api/.env` at import. Managed worker commands normally use that
server configuration. A standalone target driver must explicitly load that file
or use user-configured process variables; cwd worker does not imply API dotenv is
loaded. Worker `.env.example` is not a substitute for the API configuration and
also omits the Critic key. Never disable test isolation to read keys.

`SECMATE_API_DATA_ROOT` defaults to `apps/api/data`; a source-only device should
start a new store, not borrow fake test roots. Keep test `PYTHONPATH`, temp-data
override and live-authorization flags out of the app startup terminal. Start a
fresh terminal if uncertain; do not dump its environment to check. Browser UI
never receives keys. The local preview login accepts nonempty fields and is not
enterprise authentication; do not use a real employee password for the preview.

## 10. Boot SecMate — only after offline checks and configuration

1. Check localhost 8000/5173 for an existing process. Do not kill another service
   or start two API controllers over one data directory. Ask if an owner is unclear.
2. Use a fresh terminal with no test store/PYTHONPATH overrides.
3. Cwd `apps/web`, run:

   ```powershell
   npm run dev
   ```

   This runs `concurrently`: API via `../api/.venv/Scripts/python.exe` at
   `127.0.0.1:8000`, and Vite at port 5173 with strictPort. Vite proxies `/api` to
   `http://127.0.0.1:8000`. Do not set API auto-reload while managed work is active.
4. Alternatively start two terminals (not in addition to `npm run dev`):

   ```powershell
   # cwd apps/api
   & ".venv/Scripts/python.exe" -m uvicorn secmate_api.main:app --app-dir src --host 127.0.0.1 --port 8000
   # cwd apps/web, separate terminal
   npm run dev:web
   ```

5. Open `http://localhost:5173`, create the local preview session, and verify GET-only
   pages: Targets, Assessments catalog, Reports empty history, Dashboard empty state.
   Targets should show one SocMate and one Synthetic ChatMate card; ChatMate profile
   shows AIDA, five reads and two approval-required proposals. Assessments target
   selection should expose current catalog and support/experimental explanations.
6. These observations do not require provider calls. Do not press Start/Launch or
   mocked/live smoke controls automatically. Readiness checks may show only key
   presence/configured status; never print values. Existing UI route for model-role
   readiness, if any, can itself call providers: inspect before using it.
7. Record runtime versions, install/doctor/offline results and actual UI behavior.
   Expected empty history is not a reason to restore unavailable old evidence.

If API code/catalog is changed later, restart once with no active worker so imported
code and cache align. Preserve uncertain-job resolution and never delete locks or
ledgers to force a green launch. Stop servers via normal foreground Ctrl+C after
workers settle. No fleet/distributed infrastructure is part of this setup.

## 11. Exact next chunk — live benign usability, not another budget fix

Historical non-adversarial scenarios (old evidence outside repo, NOT transferred):

| Scenario | Before corrections | What remains to demonstrate |
|---|---|---|
| s1 mail summary | String `"None"` cursor, invalid_cursor, no retrieval | Actual well-typed read/result/model summary |
| s2 directory + calendar | Directory succeeded; string `"20"`/`"null"` calendar args rejected | Useful combined factual answer grounded in seed |
| s3 message proposal | Correct directory/proposal; third reservation exceeded 8,000; verifier miscounted rejection | Staged review, correct replay/acknowledgement, honest pending result under 12,000, zero effects |

Sections 15–17 now fix descriptions/root schema/prompt contradictions, accounting,
and measured target budget. No new live usability result is recorded yet. Check
for a later result before asking authorization; if it exists, resume its actual gate.

Receiving-agent prompt for this chunk:

> Verify the current 0.5.1 model interface, request-accounting binding and execution
> profile 2.1.0 after local setup. Ask the user once for up to three bounded live
> target-only calls/scenarios through the usual OpenRouter route and configured
> fictional-data handling policy. Then run three independent fresh ordinary tasks
> using existing model_phase5 interfaces: summarize relevant seeded lunch mail or
> Teams; combine directory and seeded calendar information; prepare a polite message
> proposal to Bram, stopping at approval with no send. Inspect fictional seed to
> choose answerable requests without putting expected answers/tool scripts in model
> input. Use real model choices, current limits and fresh short temp namespaces;
> no DeepTeam, attacker, Judge, forced tools, argument coercion, semantic retries,
> approval, effects, provider fallback or automatic budget increase. Save request,
> actual model/host outputs, tools/arguments/results, source refs, memory inclusion,
> pending review, reservation-vs-HTTP counters, usage, time and failure reasons.
> Compare claims to actual fictional records; reconcile each saved outcome in a
> separate process, including early failures. Append exact results/evidence paths
> and limitations to the Phase 5 results file. Do not call a host pending-approval
> response a completed model acknowledgement or treat memory inclusion as demonstrated
> learning. If a scenario fails, report the concrete defect and stop that scenario;
> do not repeat until success or launch a broad audit. No application/UI changes,
> new dependencies, commits or pushes for this chunk.

Use the effective 12,000-token target allowance per fresh target scenario, four
logical turns/four cumulative attempt ceiling and 120s deadline; this is not three
calls total across all scenarios. State the exact proposed run/attempt/token bound
in the authorization request. No earlier machine/session authorization carries over.

Driver/CLI files may be temporary external helpers if existing CLI supports only
the old smoke shape. Reuse actual runtime, no fake provider labeled live. Inspect
current APIs before writing helpers; do not rely on unavailable old temp scripts.
Use an approved short temporary parent on the new laptop, validate it before
creating a new root, refuse collisions and avoid long Windows SQLite paths. No
`C:\Users\SAIASH~2` assumptions. Record new evidence paths in the durable result.

## 12. Following chunk — make depth visible, after actual outcomes

Targets remains read-only and manager-focused. Do not restore smoke buttons,
technical dropdowns, phase labels or huge duplicate tool panels. Current details
already distinguish SocMate's SOC scope from seven employee-assistant capabilities.
The agreed future UI improvement is small:

- Add concise capability/workflow examples explaining retrieval, directory/calendar
  combination and approval-gated preparation. Use actual available capability metadata.
- Label an example demonstrated live only if fresh retained evidence supports it;
  otherwise available/not-yet-demonstrated, never mock success presented as live.
- In actual Results, derive a short activity sequence from recorded events, such
  as `Looked up recipient → Prepared message → Awaiting approval — not sent`.
  Model prose alone cannot create activity or completion claims.
- Keep detailed arguments/usage/evidence in appropriate report/export disclosures.
  Do not change target/attack/scoring behavior just to improve the demo story.

Do not start a general frontend redesign or attack-catalog rewrite as part of
setup/usability validation. New framework-neutral attack work later uses expansion
Part A, with real delivery hooks (e.g. controlled fake-email injection), predicates
and evidence; existing direct text tests do not prove hidden channel coverage.

## 13. First response / completion contract for the receiving agent

First response: report actual workspace/OS, detected interpreters, copied-source
inventory and latest result sections. Explain that Section 17 budget work is already
done, historical data/temp evidence are absent by design, and the immediate task is
setup/offline checks followed by separately authorized live usability. If setup is
blocked, list the exact missing runtime/package/access; do not request secrets in chat.

Record actual commands, exit codes, skipped/deselected scope, timeouts, version
bindings and newly generated evidence. Never count timeout/progress dots as passes,
mechanical check counts as substantive coverage, or missing old evidence as a failure
of a new run. Accepted trusted-local-storage scope excludes arbitrary external writers;
stable seeded fact IDs remain valid only under current generation/owner authority.

Resume small chunks rather than planning endlessly or rebuilding working layers.
Do not spawn agents solely because old history mentions third-party review. Latest
user instructions govern delegation and scope. After the continuation checkpoint is
accepted and durable records contain what is needed, request deletion of **this
temporary handoff only**. No commit/push is implied by any step in this document.

## 14. This handoff's authoring verification (not a new product acceptance gate)

- Read current manifests, lockfile presence, runtime policy, timezone validation,
  API storage configuration/conftest, startup scripts and Section 17 before writing.
- Observed `node --version` / `npm --version`: 24.21.0 / 11.19.0; API/worker
  executable versions: Python 3.14.7 / 3.11.9; timezone package: 2026.6 / 2026f.
- Worker `python -m secmate_worker.doctor`: **PASS**. Read-only effective-profile
  load: version **2.1.0**, provider token limit **12,000**.
- Isolated API bootstrap + `tests/test_target_projection.py`: **9 passed**, one
  existing deprecation warning; real dotenv disabled and sandbox API/data roots
  selected before execution imports. No inference or real run storage used.
- `git diff --no-index --check -- /dev/null Documents/TEMP_AGENT_DEVICE_HANDOFF.md`:
  clean apart from Git's existing LF/CRLF working-copy notice.
- No runtime/package/environment configuration or other repo document was edited
  to author this file. No packages installed, servers started, keys read, provider
  calls made, old run/evidence copied, staging, commit or push performed. Existing
  modified/untracked application and document work remains the transfer source.

Recompute these checks as needed on the receiving device; do not copy historical
success statements into its new setup report as if newly executed there.
