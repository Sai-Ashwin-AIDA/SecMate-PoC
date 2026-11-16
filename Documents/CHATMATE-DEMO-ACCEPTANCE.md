# ChatMate score-first MVP acceptance

> **Current acceptance update:** [TRD-4 run history](./TRD-4.md#run-history) records the successful manual parent/follow-up and read-only integrity checks. The checklist and counts below are the earlier MVP checkpoint, not a claim that the core workflow is still wholly untested. Direct buttons have replaced consent checkboxes. Five-method coverage, calibration, broader recovery and screen-reader acceptance remain distinct open gates.

## Implemented presentation

Step 4 and the dedicated ChatMate report lead with the validated Judge score and
category, for example **20/100 · Minor deviation**. The persisted security result is
shown separately as the **Evidence-qualified verdict**. Score bands and backend
thresholds are unchanged. A score is not a probability of compromise.

The 75–100 category is displayed as “Compromise-level deviation”; an inconclusive
verdict remains inconclusive even at this score. Failure paths do not invent scores.
History, notifications and summary rows retain their existing status-based labels.
Management reports and JSON exports retain their existing saved score/verdict data.

## Automated verification

- Frontend: `npm test -- --run` — 396 tests passed across 29 files.
- Production: `npm run build` — TypeScript and Vite passed.
- Coverage includes score-band boundaries, nonzero resisted results, high-score
  inconclusive results, report recovery, Critic/follow-up, audit validation and export.
- No model or target calls were made for this presentation change.

## Operator rehearsal — still to complete

1. Open ChatMate assessments and choose a supported direct attack method.
2. Generate two candidates; inspect them and freeze one selection.
3. Copy its exact prompt into ChatMate manually.
4. Capture the response verbatim, complete existing attestations/consent, and evaluate.
5. Confirm the headline shows score/category and the separate verdict is visible.
6. Inspect Judge confidence, rationale, cited evidence and missing evidence.
7. Open the dedicated report and export JSON; compare score/verdict to Step 4.
8. Where eligible, run Critic review and create a follow-up draft; verify parent
   lineage and that the original verdict is unchanged. Deliver any follow-up manually.
9. Record revision, run IDs, method, observed result, report/export consistency and
   any failures. Do not require the target to compromise for a successful rehearsal.

This validates one operator-mediated single-turn lifecycle. Broader acceptance still
requires the five-method matrix and recovery drills. Automated target invocation,
multi-turn hooks, tool use and real retrieval-source injection require separate
general SecMate validation.

## Human review

`services/deepteam-worker/verification/manual-chatmate-human-annotations-v1.json`
records all 30 user classifications separately: nine compromised, twelve resisted,
nine benign. These are single-reviewer provisional annotations. BENIGN is not mapped
to a stored machine verdict or a zero score. Historical labels and predictions are
unchanged. An agreed rubric/mapping and complete review metadata are needed before
three-way human-label calibration metrics can be reported.
