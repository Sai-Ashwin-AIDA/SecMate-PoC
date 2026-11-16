import { formatApiErrorDetail } from "./modelConnectivityService";
import type { DeepTeamAuditReport } from "./modelConnectivityService";

export type ChatMateAttackProfileId =
  | "prompt-injection-v1"
  | "system-override-v1"
  | "prompt-probing-v1"
  | "goal-redirection-v1"
  | "context-poisoning-v1";

export type ChatMateRunStatus =
  | "DRAFT"
  | "QUEUED"
  | "GENERATING"
  | "AWAITING_SELECTION"
  | "AWAITING_RESPONSE"
  | "AWAITING_EVALUATION"
  | "EVALUATING"
  | "COMPLETED"
  | "REJECTED"
  | "ABANDONED"
  | "FAILED";

export type ChatMatePromptCandidate = {
  candidate_id: string;
  ordinal: number;
  explanation?: { approach: string; intended_effect: string; selection_reason: string; strengths: string[]; limitations: string[] } | null;
  generation_mode?: "BASELINE_DIRECT" | "BASELINE_METHOD_ALIGNED" | "BASELINE_METHOD_REVIEWED";
  method_review?: {
    candidate_id: string;
    prompt_sha256: string;
    verdict: "ALIGNED" | "NOT_ALIGNED" | "UNCERTAIN";
    reviewer_instruction_version: "baseline-method-review-v1";
    reviewer_instruction_sha256: string;
  };
  attack_profile_id: ChatMateAttackProfileId;
  attack_method: string;
  source_prompt: string;
  source_prompt_sha256: string;
  prompt: string;
  prompt_sha256: string;
};

export type ChatMateCandidateBatch = {
  schema_version: "1.0";
  batch_id: string;
  created_at: string;
  target_name: "ChatMate";
  attack_profile_id: ChatMateAttackProfileId;
  attack_method: string;
  assessment_spec: Record<string, unknown>;
  candidates: ChatMatePromptCandidate[];
  provenance: Record<string, unknown>;
};

export type ChatMateManualEvidence = {
  evidence_id: string;
  collection_method: "MANUAL_COPY_PASTE";
  run_id: string;
  batch_id: string;
  candidate_id: string;
  candidate_sha256: string;
  outcome: "RESPONSE" | "VISIBLE_FAILURE";
  redacted_response_text: string | null;
  failure_reason: "RESPONSE_COULD_NOT_BE_COMPLETED" | null;
  persisted_response_sha256: string | null;
  correlation_sha256: string;
  prompt_sent_at?: string | null;
  response_observed_at?: string | null;
  submitted_at: string;
  prompt_submitted_unchanged: true;
  observation_captured_verbatim: true;
  redaction_applied: boolean;
  judge_data_collection_attested: boolean;
};

export type ChatMateRunRecord = {
  run_id: string;
  status: ChatMateRunStatus;
  created_at: string;
  started_at: string | null;
  generated_at: string | null;
  selected_at: string | null;
  completed_at: string | null;
  evaluation_started_at: string | null;
  evaluation_attempts: number;
  evaluation_id: string | null;
  target_name: "ChatMate";
  attack_profile_id: ChatMateAttackProfileId;
  attack_method: string;
  max_total_tokens: number;
  authorization_attested: boolean;
  candidate_batch: ChatMateCandidateBatch | null;
  selected_candidate_id: string | null;
  selected_candidate_sha256: string | null;
  response_submitted_at: string | null;
  manual_evidence: ChatMateManualEvidence | null;
  final_status: "RESISTED" | "COMPROMISED" | "INCONCLUSIVE" | "ERROR" | null;
  artifact_available: boolean;
  logs: Array<{ timestamp: string; level: "INFO" | "WARNING" | "ERROR"; message: string }>;
  error_code: string | null;
  error_message: string | null;
  conversation_id?: string | null;
  critic_status?: "RUNNING" | "COMPLETED" | "FAILED" | null;
  critic_review_id?: string | null;
  critic_review_available?: boolean;
  critic_review_sha256?: string | null;
  critic_attempts?: number;
  critic_error_code?: string | null;
  critic_error_message?: string | null;
  critic_started_at?: string | null;
  critic_completed_at?: string | null;
  parent_run_id?: string | null;
  follow_up_critic_review_id?: string | null;
  follow_up_objective?: string | null;
  follow_up_expected_evidence?: string[];
  follow_up_context?: Record<string, unknown> | null;
  assessment_spec_snapshot?: Record<string, unknown> | null;
};

export type CreateChatMateRunRequest = {
  attack_profile_id: ChatMateAttackProfileId;
  max_total_tokens: number;
  authorization_attested: true;
};

export type SubmitChatMateResponseRequest = {
  candidate_id: string;
  candidate_sha256: string;
  outcome: "RESPONSE" | "VISIBLE_FAILURE";
  response_text?: string;
  failure_reason?: "RESPONSE_COULD_NOT_BE_COMPLETED";
  prompt_submitted_unchanged: true;
  observation_captured_verbatim: true;
  judge_data_collection_attested: boolean;
  conversation_id?: string;
};

export type ChatMateCriticReview = {
  schema_version: "1.0" | "1.1";
  critic_review_id: string;
  run_id: string;
  source_evaluation_id: string;
  created_at: string;
  provider: "GROQ";
  model: "qwen/qwen3.8-27b";
  profile_id: "groq-qwen-critic";
  source_candidate_sha256: string;
  source_correlation_sha256: string;
  source_judge_sha256: string;
  source_input_sha256: string;
  critic_system_instruction_sha256: string;
  critic_user_prompt_sha256: string;
  attack_effectiveness_analysis: string;
  outcome_analysis: string;
  observed_weak_point: string | null;
  weak_point_status: "NONE_OBSERVED" | "HYPOTHESIS" | "EVIDENCE_SUPPORTED";
  management_summary: string;
  recommended_attack_profile_id: ChatMateAttackProfileId;
  recommended_follow_up_objective: string;
  expected_evidence: string[];
  evidence_references: string[];
  policy_references: string[];
  invalid_evidence_references: string[];
  invalid_policy_references: string[];
  recommendation_available: boolean;
  budget: Record<string, unknown>;
  model_attempts: Record<string, unknown>[];
  critic_data_collection_attested: true;
};

import { RUNS_CHANGED, forgetAssessment, rememberAssessment } from "./assessmentSession";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let missingRun = false;
    let message = `Request failed with HTTP ${response.status}.`;
    try {
      const body = await response.json() as { detail?: unknown };
      missingRun = response.status === 404 && body.detail === "ChatMate run not found.";
      if (
        response.status === 404
        && body.detail === "Not Found"
        && path.startsWith("/chatmate-runs")
      ) {
        message = "The running SecMate API is outdated and does not expose the ChatMate workflow. Restart SecMate with npm run dev, then try again.";
      } else if (body.detail) {
        message = formatApiErrorDetail(body.detail, response.status);
      }
    } catch {
      // Retain the HTTP status when no structured body is available.
    }
    throw Object.assign(new Error(message), { status: response.status, missingRun });
  }
  const result = response.status === 204 ? undefined : await response.json();
  if (init?.method && init.method !== "GET") {
    if (init.method === "DELETE") forgetAssessment(decodeURIComponent(path.split("/").at(-1)!));
    if (result?.run_id && (path === "/chatmate-runs" || /\/(generation|follow-up)$/.test(path))) rememberAssessment(result.run_id);
    window.dispatchEvent(new Event(RUNS_CHANGED));
  }
  return result as T;
}

const confirmedHeaders = { "X-SecMate-Local-Run": "confirmed" };

export const chatmateService = {
  createRun: (selection: CreateChatMateRunRequest) => request<ChatMateRunRecord>(
    "/chatmate-runs",
    { method: "POST", headers: confirmedHeaders, body: JSON.stringify(selection) },
  ),
  listRuns: (signal?: AbortSignal) => request<ChatMateRunRecord[]>("/chatmate-runs?limit=500", { signal }),
  deleteRun: (runId: string): Promise<void> => request<void>(
    `/chatmate-runs/${encodeURIComponent(runId)}`,
    { method: "DELETE", headers: confirmedHeaders },
  ),
  abandonRun: (runId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/abandon`,
    { method: "POST", headers: confirmedHeaders },
  ),
  getRun: (runId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}`,
  ),
  selectCandidate: (runId: string, candidateId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/selection`,
    {
      method: "POST",
      headers: confirmedHeaders,
      body: JSON.stringify({ candidate_id: candidateId, reject_all: false }),
    },
  ),
  rejectCandidates: (runId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/selection`,
    {
      method: "POST",
      headers: confirmedHeaders,
      body: JSON.stringify({ candidate_id: null, reject_all: true }),
    },
  ),
  submitResponse: (runId: string, submission: SubmitChatMateResponseRequest) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/response`,
    { method: "POST", headers: confirmedHeaders, body: JSON.stringify(submission) },
  ),
  retryEvaluation: (runId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/evaluation`,
    { method: "POST", headers: confirmedHeaders },
  ),
  getAudit: (runId: string) => request<DeepTeamAuditReport>(
    `/chatmate-runs/${encodeURIComponent(runId)}/audit`,
  ),
  requestCritic: (runId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/critic`,
    { method: "POST", headers: confirmedHeaders, body: JSON.stringify({ critic_data_collection_attested: true }) },
  ),
  getCritic: (runId: string) => request<unknown>(`/chatmate-runs/${encodeURIComponent(runId)}/critic`),
  createFollowUp: (runId: string) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/follow-up`,
    { method: "POST", headers: confirmedHeaders },
  ),
  generateDraft: (runId: string, selection: { max_total_tokens: number; authorization_attested: true }) => request<ChatMateRunRecord>(
    `/chatmate-runs/${encodeURIComponent(runId)}/generation`,
    { method: "POST", headers: confirmedHeaders, body: JSON.stringify(selection) },
  ),
};
