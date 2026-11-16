# SecMate

SecMate is Paramount Computer Systems' internal AI security-assessment proof of
concept. It supports controlled synthetic testing and an operator-mediated
workflow for assessing company chatbots.

**Next development phase:** [SecMate–ChatMate adapter integration handoff](./Documents/CHATMATE-ADAPTER-INTEGRATION-HANDOFF.md).
SecMate is exclusively a local internal testing tool for the company's AI team
to test internal AI products, not a wide-scale industry platform. The next phase
will connect Surya's adapter through Targets and the normal assessment platform
on a new integration branch. Ashwin runtime code remains frozen; documentation
updates are permitted. The actual ChatMate environment still needs confirmation.

**Accepted implementation reference:** [Documents/TRD-4.md](./Documents/TRD-4.md).
Read it for the accepted architecture, execution constraints, verification
history, known gaps, and recovery procedures. This is a local PoC, not a
production deployment or a calibrated assurance control.

## Assessment workflows

### Manual ChatMate assessment

1. Select one of five supported single-turn attack methods.
2. Generate exactly two prompts with one Groq call.
3. Review their method alignment with a second Groq call.
4. Select and freeze a prompt, then manually submit it through the authorized
   ChatMate interface.
5. Capture the exact response or visible failure.
6. Evaluate the evidence with an independent Judge and review saved results.
7. Optionally request a Critic review and create a linked single-turn follow-up.

Generation uses a direct model workflow, **not DeepTeam's AttackEngine**.
Method alignment is advisory; structural validation and evidence bindings remain
mandatory. Generation has a two-call cap and zero automatic retries. Follow-up
draft creation does not generate prompts, and a child assessment is a fresh
single-turn interaction rather than a stateful target conversation.

SecMate does not automate ChatMate login, browser sessions, internal APIs, or
prompt delivery. Manual evidence captures text, not the target's internal tools,
retrieval, hidden instructions, or external side effects.

### Synthetic SocMate assessment

The separate synthetic path runs a pinned DeepTeam runtime in an isolated
Python 3.11 worker. It supports constrained single/adaptive execution against
worker-owned target fixtures, intercepted tools, and deterministic policy checks.
Catalog availability is not proof of live coverage or calibrated detection.

## Architecture

```text
React / TypeScript frontend
          |
          v
FastAPI control plane
  run records, durable local jobs, reporting, console summaries
          |
          v
Isolated Python 3.11 worker
  manual generation / Judge / Critic   |   synthetic DeepTeam execution
          |
          v
Provider APIs and local evidence storage
```

- Run records and jobs use local SQLite-backed control and evidence structures.
- Execution includes budgets, deadlines, fencing, cancellation, sealed
  publication, and conservative recovery from uncertain completion.
- Evidence handling preserves hashes, provenance, original/redacted separation,
  and parent/Critic/child relationships.
- Reports support selected assessment chains and PDF/JSON workflows.
- Some product metadata and preferences remain browser-local.
- Local hash chains detect changes against retained baselines; they are not
  externally signed or immutable evidence.

## Model roles

| Role | Model | Credential |
|---|---|---|
| Attacker and manual method review | `qwen/qwen3.8-27b` via Groq | `GROQ_API_KEY` |
| Manual Critic | `qwen/qwen3.8-27b` via Groq | Dedicated `GROQ_CRITIC_API_KEY` |
| Independent Judge | `nvidia/nemotron-3.5-super-vl:free` via OpenRouter | `OPENROUTER_API_KEY` |
| Synthetic target | `nvidia/nemotron-3.5-super-vl:free` via OpenRouter | `OPENROUTER_API_KEY` |

Secrets remain server-side in ignored environment files. Known integration gaps
for other Critic paths are documented in TRD-4. Provider availability and Judge
accuracy are not guaranteed. Judge scores describe observed deviation, not
attack strength or probability of compromise.

## Local development

Prerequisites:

- Node.js compatible with the frontend's Vite dependencies.
- An API virtual environment installed from `apps/api/pyproject.toml`.
- A separate Python 3.11 worker environment installed from
  `services/deepteam-worker/pyproject.toml` with `.[runtime,test]` dependencies.
- Ignored `apps/api/.env` configured with the provider credentials above.
  Consult the component `.env.example` files and TRD-4 for configuration.

From `apps/web`:

```powershell
npm install
npm run dev
```

The frontend uses `http://localhost:5173`; the API uses
`http://127.0.0.1:8000`. Preview sign-in is not enterprise authentication.
Consult TRD-4 before starting backend processes or recovery operations. Do not
enable API auto-reload during an active worker run.

## Verification

The latest recorded verification checkpoint passed 432 frontend tests, 367
sandboxed API tests, 405 worker tests, and the TypeScript/Vite production build.
These are historical results, not a claim that tests run on every checkout.
TRD-4 records their scope and remaining acceptance gaps.

Frontend checks, from `apps/web`:

```powershell
npm test
npm run build
```

Backend verification must use sandboxed run roots and mocked providers as
documented in TRD-4, preserving accepted local evidence and avoiding unintended
inference.

## Repository map

| Path | Purpose |
|---|---|
| `apps/web/` | React interface, assessment lifecycle, findings, reports, and dashboard |
| `apps/api/` | FastAPI control plane, local storage, jobs, and reporting |
| `services/deepteam-worker/` | Isolated model execution and synthetic DeepTeam integration |
| `Documents/` | Requirements, architecture history, and current engineering handoff |

Local secrets, saved API run data, worker artifacts, dependencies, and build
outputs are excluded from Git. Local `todo.md` is intentionally not published.
A source checkout does not include the machine's saved assessment evidence.

## Scope and next steps

The accepted manual baseline is frozen on Ashwin. Follow the
[adapter integration handoff](./Documents/CHATMATE-ADAPTER-INTEGRATION-HANDOFF.md)
for implementation on the user's new branch, including conditional retirement
of the manual entry point after the automated replacement is verified.
Runtime changes require explicit scope;
do not silently add enhancement loops, retries, fallback models, or target
automation on Ashwin. The immediate goal is the local ChatMate adapter connection,
retaining the Nemotron 3.5 Judge and saved evidence. Distributed scheduling,
commercial tenancy and public deployment are outside this internal-tool phase.

For the complete requirement lineage, start with
[TRD-4](./Documents/TRD-4.md), which links to TRD-1, TRD-2, TRD-2A, TRD-2B,
and TRD-3 and explains which historical statements have been superseded.
