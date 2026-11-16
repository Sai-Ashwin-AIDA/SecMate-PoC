"""Quota-bounded synthetic replay of the actual manual ChatMate Judge.

Expected labels/reviewer notes never enter production requests. This does not
generate attacks, invoke ChatMate, or publish assessment runs into the application.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .chatmate_candidates import chatmate_candidate_assessment_spec
from .contracts import (CampaignBudget, ChatMateCandidateBatch, ChatMateCandidateProvenance,
    ChatMatePromptCandidate, ManualChatMateEvidence, ManualChatMateEvaluationInput,
    ModelRole, manual_chatmate_correlation_sha256)
from .execution_budget import CampaignBudgetManager
from .manual_chatmate import (ManualChatMateEvaluator, ManualChatMateJudgeOutput,
    _build_path_and_review, _model_attempt_payload, manual_chatmate_judge_request)
from .model_adapters import OpenRouterDeepEvalModel
from .model_clients import ModelClientSettings, StructuredModelClients
from .model_profiles import GROQ_QWEN_ATTACKER, OPENROUTER_NEMOTRON_EVALUATOR
from .role_prompts import chatmate_candidate_attacker_system_instruction, chatmate_candidate_generation_guidelines
from .runtime_policy import DEEPTEAM_COMMIT, DEEPEVAL_VERSION


def digest(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CalibrationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    split: Literal["development", "holdout"]
    attack_profile_id: Literal["prompt-injection-v1", "system-override-v1", "prompt-probing-v1", "goal-redirection-v1", "context-poisoning-v1"]
    prompt: str = Field(min_length=1, max_length=20000)
    response: str = Field(min_length=1, max_length=20000)
    expected_status: Literal["RESISTED", "COMPROMISED", "INCONCLUSIVE"]
    rationale: str = Field(min_length=1, max_length=2000)
    label_status: Literal["ENGINEERING_PROVISIONAL", "SINGLE_REVIEWER_PROVISIONAL"] = "ENGINEERING_PROVISIONAL"
    reviewer: str | None = Field(default=None, max_length=200)
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def review_provenance(self):
        if self.label_status == "SINGLE_REVIEWER_PROVISIONAL" and (
            not self.reviewer or not self.reviewer.strip() or self.reviewed_at is None
            or self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("A human-review label requires reviewer identity and timezone-aware review time")
        if not self.prompt.strip() or not self.response.strip():
            raise ValueError("Calibration text cannot be blank")
        return self


class CalibrationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    suite_id: str
    version: str
    synthetic_only: Literal[True]
    description: str
    cases: list[CalibrationCase] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Calibration case IDs must be unique")
        if not {"development", "holdout"}.issubset({case.split for case in self.cases}):
            raise ValueError("Both development and holdout cases are required")
        return self


def fixture_input(case: CalibrationCase) -> ManualChatMateEvaluationInput:
    """Construct valid synthetic evidence, not a claim of real target execution."""
    opaque = digest(case.case_id)[:16]  # Labels/splits/rationales are excluded.
    run_id, batch_id = f"chatmate-run-{opaque}", f"chatmate-batch-{opaque}"
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)
    spec = chatmate_candidate_assessment_spec(case.attack_profile_id)
    method = {"prompt-injection-v1": "Prompt Injection", "system-override-v1": "System Override",
              "prompt-probing-v1": "Prompt Probing", "goal-redirection-v1": "Goal Redirection",
              "context-poisoning-v1": "Context Poisoning"}[case.attack_profile_id]
    candidates = []
    for ordinal, prompt in enumerate((case.prompt, "Alternative synthetic fixture probe; not selected or executed."), 1):
        source = f"Synthetic calibration source {ordinal}"
        candidates.append(ChatMatePromptCandidate(candidate_id=f"{batch_id}-c{ordinal}", ordinal=ordinal,
            attack_profile_id=case.attack_profile_id, attack_method=method, source_prompt=source,
            source_prompt_sha256=digest(source), prompt=prompt, prompt_sha256=digest(prompt)))
    batch = ChatMateCandidateBatch(batch_id=batch_id, created_at=now, attack_profile_id=case.attack_profile_id,
        attack_method=method, assessment_spec=spec, candidates=candidates,
        provenance=ChatMateCandidateProvenance(deepteam_version=version("deepteam"), deepteam_commit=DEEPTEAM_COMMIT,
            deepeval_version=DEEPEVAL_VERSION, attacker_profile_id=GROQ_QWEN_ATTACKER.profile_id,
            attacker_provider="GROQ", attacker_model=GROQ_QWEN_ATTACKER.model,
            assessment_spec_sha256=digest(spec.model_dump(mode="json")),
            attacker_system_instruction_sha256=digest(chatmate_candidate_attacker_system_instruction(spec, method)),
            generation_guidelines_sha256=digest(chatmate_candidate_generation_guidelines(spec, method)),
            source_input_sha256=digest(spec.attack_objective)))
    correlation = dict(run_id=run_id, batch_id=batch_id, candidate_id=candidates[0].candidate_id,
        candidate_sha256=candidates[0].prompt_sha256, outcome="RESPONSE", persisted_response_sha256=digest(case.response),
        failure_reason=None, redaction_applied=False, judge_data_collection_attested=True, submitted_at=now)
    manual = ManualChatMateEvidence(evidence_id=f"{run_id}-evidence", **correlation,
        redacted_response_text=case.response, collection_method="MANUAL_COPY_PASTE",
        correlation_sha256=manual_chatmate_correlation_sha256(**correlation),
        prompt_submitted_unchanged=True, observation_captured_verbatim=True)
    return ManualChatMateEvaluationInput(run_id=run_id, max_total_tokens=50000, candidate_batch=batch,
        selected_candidate_id=candidates[0].candidate_id, selected_candidate_sha256=candidates[0].prompt_sha256,
        manual_evidence=manual)


def request_fingerprint(case: CalibrationCase) -> str:
    value = fixture_input(case)
    system, prompt = manual_chatmate_judge_request(value, f"{value.run_id}-turn-1")
    return digest({"system": system, "prompt": prompt, "schema": ManualChatMateJudgeOutput.model_json_schema()})


def experiment_identity(suite: CalibrationSuite, settings: ModelClientSettings | None = None) -> dict:
    return {"suite_sha256": digest(suite.model_dump(mode="json")),
        "request_sha256": {case.case_id: request_fingerprint(case) for case in suite.cases},
        "model": OPENROUTER_NEMOTRON_EVALUATOR.model, "profile": OPENROUTER_NEMOTRON_EVALUATOR.profile_id,
        "provider_data_collection_allowed": settings.openrouter_allow_data_collection if settings else False,
        "deepteam_commit": DEEPTEAM_COMMIT, "deepeval_version": DEEPEVAL_VERSION,
        "code_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("manual_judge_calibration.py", "manual_chatmate.py", "contracts.py", "role_prompts.py",
                         "model_clients.py", "model_adapters.py", "execution_budget.py", "model_profiles.py", "evidence_inventory.py")}}


class CalibrationModel(OpenRouterDeepEvalModel):
    """Observe the decoded output; do not change the production request or verdict."""
    last_output = None

    async def a_generate(self, prompt, schema=None):
        self.last_output = await super().a_generate(prompt, schema)
        return self.last_output


def summarize(suite: CalibrationSuite, entries: list[dict]) -> dict:
    metrics = {}
    for split in ("development", "holdout"):
        cases = {case.case_id: case for case in suite.cases if case.split == split}
        rows = [row for row in entries if row["case_id"] in cases]
        completed = [row for row in rows if row["state"] == "COMPLETED"]
        matrix = {status: dict(Counter(row["observed_status"] for row in completed if cases[row["case_id"]].expected_status == status))
                  for status in ("RESISTED", "COMPROMISED", "INCONCLUSIVE")}
        correct = sum(row["observed_status"] == cases[row["case_id"]].expected_status for row in completed)
        metrics[split] = {"planned_cases": len(cases), "reserved_cases": len(rows), "completed": len(completed),
            "execution_errors": sum(row["state"] == "ERROR" for row in rows),
            "uncertain_inflight": sum(row["state"] == "STARTED" for row in rows),
            "correct": correct, "agreement_on_completed": correct / len(completed) if completed else None,
            "confusion_matrix": matrix,
            "false_resistance": sum(row["observed_status"] == "RESISTED" and cases[row["case_id"]].expected_status != "RESISTED" for row in completed),
            "false_compromise": sum(row["observed_status"] == "COMPROMISED" and cases[row["case_id"]].expected_status != "COMPROMISED" for row in completed),
            "complete_required_citations": sum(row["required_citations_complete"] for row in completed),
            "invalid_citation_cases": sum(row["invalid_citations"] for row in completed),
            "disagreements": [row["case_id"] for row in completed if row["observed_status"] != cases[row["case_id"]].expected_status]}
    return metrics


def save_report(path: Path, report: dict):
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="ascii")
    temporary.replace(path)


async def execute(suite: CalibrationSuite, path: Path, settings: ModelClientSettings, *, split="development",
                  max_calls=30, max_tokens=150000, limit=None, freeze_development=False, clients_factory=StructuredModelClients) -> dict:
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[4] / "apps" / "api" / "data"):
        raise ValueError("Calibration must not write into application runtime data")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive lock prevents duplicate calls by concurrent runners. A leftover
    # lock after a crash requires review, not automatic provider replay.
    lock = path.with_suffix(".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    clients = None
    try:
        identity = experiment_identity(suite, settings)
        if path.exists():
            report = json.loads(path.read_text(encoding="ascii"))
            if report.get("format") != "chatmate-judge-calibration-v1" or report.get("identity") != identity:
                raise ValueError("Existing experiment identity differs; do not overwrite or mix results")
            if report["limits"] != {"max_calls": max_calls, "max_tokens": max_tokens}:
                raise ValueError("Resume must preserve the original experiment limits")
        else:
            report = {"format": "chatmate-judge-calibration-v1", "identity": identity,
                "synthetic_only": True, "candidate_origin": "FIXTURE_NOT_GENERATED", "target_execution": "NOT_PERFORMED",
                "labels": "PROVISIONAL_NOT_HUMAN_APPROVED", "stability_measured": False,
                "limits": {"max_calls": max_calls, "max_tokens": max_tokens}, "entries": [], "development_frozen_at": None}
        entries = report["entries"]
        done_ids = {row["case_id"] for row in entries}  # Includes uncertain/error calls: never silently replay.
        if freeze_development:
            if not all(any(row["case_id"] == case.case_id and row["state"] == "COMPLETED" for row in entries)
                       for case in suite.cases if case.split == "development"):
                raise ValueError("Complete development before freezing it")
            report["development_frozen_at"] = report["development_frozen_at"] or datetime.now(timezone.utc).isoformat()
        if split == "holdout" and not report["development_frozen_at"]:
            raise ValueError("Freeze completed development before evaluating holdout")
        if split == "development" and report["development_frozen_at"]:
            raise ValueError("Frozen development cannot be rerun in this experiment")
        remaining_calls = max_calls - len(entries)
        remaining_tokens = max_tokens - sum(row.get("tokens_charged", 0) for row in entries)
        if any(row["state"] == "STARTED" for row in entries):
            raise ValueError("Uncertain inflight reservation needs manual review; no automatic replay")
        report["stop_reason"] = None
        if remaining_calls <= 0 or remaining_tokens <= 0:
            report["stop_reason"] = "EXPERIMENT_BUDGET_EXHAUSTED"
        else:
            budget = CampaignBudgetManager(CampaignBudget(max_paths=1, max_turns_per_path=1,
                max_provider_calls=remaining_calls, max_concurrent_provider_calls=1,
                max_total_tokens=remaining_tokens, timeout_seconds=1800, max_retries_per_call=0))
            attempts = []
            clients = clients_factory(settings, budget_manager=budget, event_sink=attempts.append)
            model = CalibrationModel(clients, OPENROUTER_NEMOTRON_EVALUATOR.model,
                profile_id=OPENROUTER_NEMOTRON_EVALUATOR.profile_id, role=ModelRole.TARGET_EVALUATOR)
            evaluator = ManualChatMateEvaluator(model, OPENROUTER_NEMOTRON_EVALUATOR.profile_id)
            pending = [case for case in suite.cases if case.split == split and case.case_id not in done_ids]
            for case in pending[:limit] if limit is not None else pending:
                if len(entries) >= max_calls:
                    report["stop_reason"] = "CALL_CAP"
                    break
                value = fixture_input(case)
                turn_id = f"{value.run_id}-turn-1"
                row = {"case_id": case.case_id, "state": "STARTED", "request_sha256": request_fingerprint(case),
                       "started_at": datetime.now(timezone.utc).isoformat()}
                entries.append(row)
                report["summary"] = summarize(suite, entries)
                save_report(path, report)  # Persist reservation BEFORE any inference.
                before = await budget.snapshot()
                start = len(attempts)
                try:
                    evaluation = await evaluator.evaluate(value, turn_id)
                    now = datetime.now(timezone.utc)
                    _, _, status = _build_path_and_review(value, "calibration-evaluation", turn_id, now, now, evaluation, None)
                    required = {turn_id, value.manual_evidence.evidence_id}
                    row.update(state="COMPLETED", observed_status=status, evaluation=evaluation.model_dump(mode="json"),
                        raw_judge=model.last_output.model_dump(mode="json"),
                        expected_status=case.expected_status, label_status=case.label_status,
                        required_citations_complete=required.issubset(evaluation.evidence_references),
                        invalid_citations=bool(evaluation.invalid_evidence_references or evaluation.invalid_policy_references))
                except Exception as error:
                    code = getattr(error, "code", None)
                    status_code = getattr(error, "status_code", None)
                    row.update(state="ERROR", error_code=getattr(code, "value", "LOCAL_CALIBRATION_ERROR"),
                        status_code=status_code if type(status_code) is int else None)
                    report["stop_reason"] = "EXECUTION_ERROR_REVIEW_REQUIRED"
                after = await budget.snapshot()
                row.update(tokens_charged=max(0, after.tokens_consumed - before.tokens_consumed),
                    attempts=[_model_attempt_payload(event) for event in attempts[start:]],
                    completed_at=datetime.now(timezone.utc).isoformat())
                report["summary"] = summarize(suite, entries)
                save_report(path, report)
                if row["state"] == "ERROR":
                    break  # Do not burn quota on unavailable/auth/rate-limited routes.
            report["last_session_budget"] = asdict(await budget.snapshot())
        report["summary"] = summarize(suite, entries)
        save_report(path, report)
        return report
    finally:
        try:
            if clients is not None:
                try:
                    await clients.close()
                except Exception:
                    report["cleanup_failed"] = True
                    save_report(path, report)
        finally:
            lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--split", choices=["development", "holdout"], default="development")
    parser.add_argument("--max-calls", type=int, default=30)
    parser.add_argument("--max-tokens", type=int, default=150000)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--freeze-development", action="store_true")
    parser.add_argument("--allow-provider-data-collection", action="store_true",
        help="Explicit consent for these synthetic fixture requests, matching the production manual-Judge consent policy")
    args = parser.parse_args()
    if args.max_calls < 1 or args.max_tokens < 1 or (args.limit is not None and args.limit < 1):
        parser.error("Limits must be positive")
    suite = CalibrationSuite.model_validate_json(args.suite.read_text(encoding="utf-8"))
    if args.env_file:
        load_dotenv(args.env_file)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        parser.error("OPENROUTER_API_KEY is required")
    settings = ModelClientSettings(groq_api_key="", openrouter_api_key=key, request_timeout_seconds=90,
        openrouter_allow_data_collection=args.allow_provider_data_collection)
    report = asyncio.run(execute(suite, args.report, settings, split=args.split, max_calls=args.max_calls,
        max_tokens=args.max_tokens, limit=args.limit, freeze_development=args.freeze_development))
    print(json.dumps({"report": str(args.report), "stop_reason": report["stop_reason"], "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
