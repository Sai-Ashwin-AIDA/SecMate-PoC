import type { ChatMateRunRecord } from "./chatmateService";
import type { DeepTeamAuditReport } from "./modelConnectivityService";

export function evaluatedRun(overrides: Partial<ChatMateRunRecord> = {}): ChatMateRunRecord {
  return {
    run_id: "chatmate-1", status: "COMPLETED", target_name: "ChatMate", created_at: "2026-10-08T12:00:00Z",
    started_at: "2026-10-08T12:00:01Z", generated_at: "2026-10-08T12:01:00Z", selected_at: "2026-10-08T12:02:00Z",
    response_submitted_at: "2026-10-08T12:03:00Z", evaluation_started_at: "2026-10-08T12:04:00Z", completed_at: "2026-10-08T12:05:00Z",
    evaluation_attempts: 1, evaluation_id: "eval-1", attack_profile_id: "prompt-injection-v1", attack_method: "Prompt Injection",
    max_total_tokens: 100000, authorization_attested: true, selected_candidate_id: "candidate-1", selected_candidate_sha256: "a".repeat(64),
    candidate_batch: { schema_version: "1.0", batch_id: "batch-1", created_at: "2026-10-08T12:01:00Z", target_name: "ChatMate",
      attack_profile_id: "prompt-injection-v1", attack_method: "Prompt Injection", assessment_spec: { policies: [{ policy_id: "policy-1" }] }, provenance: {},
      candidates: [{ candidate_id: "candidate-1", ordinal: 1, attack_profile_id: "prompt-injection-v1", attack_method: "Prompt Injection",
        source_prompt: "DO NOT EXPORT GENERATION SOURCE", source_prompt_sha256: "c".repeat(64), prompt: "Selected attack", prompt_sha256: "a".repeat(64) }] },
    manual_evidence: { evidence_id: "evidence-1", collection_method: "MANUAL_COPY_PASTE", run_id: "chatmate-1", batch_id: "batch-1",
      candidate_id: "candidate-1", candidate_sha256: "a".repeat(64), outcome: "RESPONSE", redacted_response_text: "Refused [REDACTED]",
      failure_reason: null, persisted_response_sha256: "d".repeat(64), correlation_sha256: "b".repeat(64), submitted_at: "2026-10-08T12:03:00Z",
      prompt_submitted_unchanged: true, observation_captured_verbatim: true, redaction_applied: true, judge_data_collection_attested: true },
    final_status: "RESISTED", artifact_available: true, logs: [], error_code: null, error_message: null, ...overrides,
  };
}

export function evaluatedAudit(run = evaluatedRun()): DeepTeamAuditReport {
  const candidate = run.candidate_batch!.candidates[0], manual = run.manual_evidence!;
  const conclusive = ["RESISTED", "COMPROMISED"].includes(run.final_status ?? "");
  return {
    run_id: run.run_id,
    manifest: { run_id: run.run_id, evaluation_id: run.evaluation_id, execution_kind: "MANUAL_CHATMATE", target_invocation: "OPERATOR_MEDIATED",
      target_name: "ChatMate", candidate_batch_id: run.candidate_batch!.batch_id, assessment_spec: run.candidate_batch!.assessment_spec,
      selected_candidate_id: candidate.candidate_id, selected_candidate_sha256: candidate.prompt_sha256, manual_evidence_id: manual.evidence_id,
      manual_correlation_sha256: manual.correlation_sha256, upload_to_confident: false, telemetry_disabled: true },
    summary: { run_id: run.run_id, evaluation_id: run.evaluation_id, final_status: run.final_status, model_attempts: [] },
    evidence: { run_id: run.run_id, paths: [{ path_id: "path-1", status: run.final_status,
      turns: [{ turn_id: "turn-1", probe: candidate.prompt, target_response: manual.redacted_response_text, manual_collection: [manual] }] }],
      review_results: [{ path_id: "path-1", decision: run.final_status, authoritative_evidence_references: conclusive ? [manual.evidence_id, "turn-1"].sort() : [],
        target_evaluation: conclusive ? { category: run.final_status === "RESISTED" ? "MINOR_DEVIATION" : "COMPROMISED",
          deviation_score: run.final_status === "RESISTED" ? 10 : 90, confidence: .93, reasoning: "Validated Judge rationale.",
          evidence_references: [manual.evidence_id, "turn-1"], policy_references: run.final_status === "COMPROMISED" ? ["policy-1"] : [],
          invalid_evidence_references: [], invalid_policy_references: [] } : null }] },
    deepteam_risk: { run_id: run.run_id, execution_kind: "MANUAL_CHATMATE", target_invocation: "OPERATOR_MEDIATED",
      deepteam_native_evaluation: "NOT_EXECUTED", test_cases: [{ input: candidate.prompt, actual_output: manual.redacted_response_text, manual_collection: true }] },
  };
}
