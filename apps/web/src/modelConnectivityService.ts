export type ModelRole = "ATTACKER" | "ATTACK_CRITIC" | "OUTCOME_JUDGE" | "TARGET";
export type ModelProvider = "GROQ" | "OPENROUTER";
export type DeepTeamExecutionMode = "SINGLE" | "ADAPTIVE";
export type CapabilityState = "AVAILABLE" | "VERIFIED_OFFLINE" | "NOT_AVAILABLE" | "DEGRADED";

export type PlatformCapabilities = {
  schema_version: "1.0";
  mode: "POC";
  model_connectivity: {
    state: CapabilityState;
    live_tests_supported: boolean;
    assessment_grade: boolean;
  };
  deepteam_worker: {
    state: CapabilityState;
    invocation: "CLI_ONLY" | "LOCAL_SUBPROCESS";
    api_connected: boolean;
    api_contract_version?: string;
    supported_execution_modes?: DeepTeamExecutionMode[];
    max_paths?: number;
    cancellation_supported?: boolean;
    synthetic_only: boolean;
    verified_at: string;
    deepteam_version: string;
    deepteam_commit: string;
    deepeval_version: string;
    scenario_id: string;
    supported_vulnerabilities: string[];
    supported_attacks: string[];
    max_verified_cases: number;
    max_verified_turns: number;
    last_verified_result: "RESISTED" | "COMPROMISED" | "INCONCLUSIVE" | "ERROR";
    target_evaluator_verified: boolean;
    last_deviation_category: "ALIGNED" | "MINOR_DEVIATION" | "CONCERNING_DEVIATION" | "MAJOR_DEVIATION" | "COMPROMISED";
    last_deviation_score: number;
    last_evaluator_confidence: number;
  };
  assessment_api: {
    state: CapabilityState;
    lifecycle_source: "FRONTEND_SIMULATION";
  };
};

export type ModelProfile = {
  id: string;
  role: ModelRole;
  provider: ModelProvider;
  name: string;
  model: string;
  description: string;
  capabilities: string[];
};

export type ProviderQuota = {
  requests_limit: number | null;
  requests_remaining: number | null;
  tokens_limit: number | null;
  tokens_remaining: number | null;
  reset_requests: string | null;
  reset_tokens: string | null;
};

export type ProviderStatus = {
  provider: ModelProvider;
  configured: boolean;
  reachable: boolean;
  detail: string;
  quota: ProviderQuota | null;
};

export type ModelTestResult = {
  profile_id: string;
  provider: ModelProvider;
  model: string;
  status: "PASS" | "FAIL";
  latency_ms: number;
  summary: string;
  output: Record<string, unknown> | null;
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  } | null;
  quota: ProviderQuota | null;
};

export type AdaptiveTurnResult = {
  turn: number;
  attacker: {
    objective: string;
    strategy: string;
    probe: string;
    success_condition: string;
  };
  target: {
    response_text: string | null;
    tool_attempts: Array<{
      name: string;
      arguments: Record<string, unknown>;
      execution: "INTERCEPTED_NOT_EXECUTED";
    }>;
  };
  deterministic_check: {
    outcome: "NO_HARD_VIOLATION" | "CONFIRMED_VIOLATION";
    rule_id: string;
    detail: string;
  };
  judge: {
    verdict: "RESISTED" | "PARTIAL_SHIFT" | "CONFIRMED_VIOLATION";
    confidence: number;
    expected_behavior: string;
    observed_behavior: string;
    evidence: string[];
    concise_rationale: string;
  } | null;
  critic: {
    attack_quality_score: number;
    weaknesses: string[];
    unexplored_boundaries: string[];
    recommended_adaptation: string;
    must_not_repeat: string[];
  } | null;
};

export type AdaptiveHandoffResult = {
  scenario: string;
  max_turns: number;
  turns_completed: number;
  stop_reason: "CONFIRMED_DETERMINISTIC_VIOLATION" | "CONFIRMED_JUDGE_VIOLATION" | "TURN_BUDGET_EXHAUSTED";
  turns: AdaptiveTurnResult[];
};

export type DeepTeamRunRecord = {
  run_id: string;
  status: "DRAFT" | "QUEUED" | "RUNNING" | "CANCEL_REQUESTED" | "CANCELLED" | "COMPLETED" | "FAILED";
  created_at: string;
  started_at: string | null;
  cancellation_requested_at?: string | null;
  completed_at: string | null;
  scenario: string;
  scenario_version: string;
  target_profile_id: string;
  target_profile_version: string;
  target_name?: string | null;
  catalog_schema_version: string;
  onboarding_binding_version?: string | null;
  execution_profile_id?: string | null;
  execution_profile_version?: string | null;
  vulnerability: string;
  attack: string;
  vulnerability_profile_id: string;
  attack_profile_id: string;
  vulnerability_applicability: DeepTeamApplicability;
  vulnerability_capability_level: DeepTeamCapabilityLevel;
  attack_applicability: DeepTeamApplicability;
  attack_capability_level: DeepTeamCapabilityLevel;
  vulnerability_target_applicability?: DeepTeamApplicability;
  vulnerability_applicability_reason?: string | null;
  vulnerability_experimental_admission?: "ADMITTED" | null;
  vulnerability_experimental_admission_reason?: string | null;
  attack_target_applicability?: DeepTeamApplicability;
  attack_applicability_reason?: string | null;
  attack_experimental_admission?: "ADMITTED" | null;
  attack_experimental_admission_reason?: string | null;
  selection_admission?: "ESTABLISHED" | "EXPERIMENTAL" | null;
  execution_capability?: "EXECUTABLE" | "UNSUPPORTED" | null;
  execution_capability_code?: string | null;
  execution_capability_reason?: string | null;
  max_total_tokens: number;
  execution_mode: DeepTeamExecutionMode;
  max_paths: 1 | 2;
  final_status: "RESISTED" | "COMPROMISED" | "INCONCLUSIVE" | "ERROR" | null;
  artifact_available: boolean;
  logs: Array<{ timestamp: string; level: "INFO" | "WARNING" | "ERROR"; message: string }>;
  error_code: string | null;
  error_message: string | null;
  critic_status?: "RUNNING" | "COMPLETED" | "FAILED" | null;
  critic_review_id?: string | null;
  critic_review_sha256?: string | null;
  critic_attempts?: number;
  critic_started_at?: string | null;
  critic_completed_at?: string | null;
  linked_context?: LinkedAssessmentContext | null;
};

export type LinkedAssessmentContext = {
  schema_version: "socmate-linked-assessment-v1" | "secmate-target-linked-assessment-v1"; parent_run_id: string; parent_path_id: string;
  review_id: string; review_sha256: string; source_audit_sha256: string; assessment_spec_sha256: string;
  target_profile_id: string; target_profile_version: string; vulnerability_profile_id: string;
  scenario_id?: string | null; scenario_version?: string | null;
  target_model_sha256: string;
  attack_profile_id: string; priority: number; redacted_parent_context: Record<string, unknown>;
  redacted_parent_context_sha256?: string | null;
};
export type StandardReview = {
  schema_version: "socmate-standard-review-v1" | "socmate-standard-review-v2" | "secmate-target-standard-review-v1"; run_id: string; review_id: string;
  created_at: string; completed_at: string; input_sha256: string; source_audit_sha256: string;
  assessment_spec_sha256: string; source_path_id: string;
  recommendations: { attack_profile_id: string; priority: number }[];
  model: "qwen/qwen3.8-27b"; model_profile_id: "groq-qwen-critic";
  input_tokens_estimate: number; budget: Record<string, unknown>; model_attempts: Record<string, unknown>[];
};
export type StandardReviewView = {
  run_id: string; status: "READY" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | "UNCERTAIN" | "UNAVAILABLE" | "NOT_APPLICABLE";
  attempts: number; review_id: string | null; job_id: string | null; can_request: boolean; can_retry: boolean;
  message: string | null; review: StandardReview | null; review_canonical?: string; review_sha256?: string;
  cancel_requested?: boolean;
};

export type DeepTeamApplicability = "UNREVIEWED" | "APPLICABLE" | "NOT_APPLICABLE";
export type DeepTeamCapabilityLevel = "REGISTERED" | "APPLICABLE" | "OFFLINE_VERIFIED" | "LIVE_VERIFIED" | "CALIBRATED";

export type DeepTeamCatalog = {
  schema_version: string;
  scenario_id: string;
  scenario_version: string;
  target_profile_id: string;
  target_profile_version: string;
  synthetic_only: boolean;
  max_cases_per_run: number;
  target_profiles: Array<{
    id: string;
    name: string;
    version: string;
    purpose: string;
    scenario_id: string;
    scenario_version: string;
    synthetic_only: true;
    api_selectable: true;
    deterministic_vulnerable: boolean;
    binding_version?: string | null;
    target_id?: string | null;
    target_version?: string | null;
    gateway_kind?: string | null;
    api_registration?: boolean | null;
    deepteam_provider?: boolean | null;
    execution_modes?: DeepTeamExecutionMode[] | null;
    max_paths?: number | null;
    attack_profile_ids?: string[] | null;
    vulnerability_profile_ids?: string[] | null;
    execution_profiles?: Array<Record<string, unknown>> | null;
    unsupported_attack_profiles?: Record<string, string> | null;
    experimental_catalog_projection?: {
      schema_version: string;
      admission: "EXPERIMENTAL";
      attack_profile_ids: string[];
      vulnerability_profile_ids: string[];
    } | null;
  }>;
  attack_profiles: Array<{
    id: string;
    name: string;
    class_name: string;
    description: string;
    turn_mode: "SINGLE" | "MULTI";
    max_turns: number;
    status: "AVAILABLE";
    applicability: DeepTeamApplicability;
    applicability_reason: string;
    capability_level: DeepTeamCapabilityLevel;
    target_profile_ids: string[];
    scenario_ids: string[];
    required_target_capabilities: string[];
    evidence_references: string[];
    target_applicability?: Record<string, { applicability: DeepTeamApplicability; reason?: string }>;
    target_experimental_admission?: Record<string, { admission: "ADMITTED"; selectable: boolean; reason: string }>;
  }>;
  vulnerability_profiles: Array<{
    id: string;
    name: string;
    class_name: string;
    subtype: string;
    category: string;
    description: string;
    status: "AVAILABLE";
    applicability: DeepTeamApplicability;
    applicability_reason: string;
    capability_level: DeepTeamCapabilityLevel;
    target_profile_ids: string[];
    scenario_ids: string[];
    required_target_capabilities: string[];
    evidence_references: string[];
    target_applicability?: Record<string, { applicability: DeepTeamApplicability; reason?: string }>;
    target_experimental_admission?: Record<string, { admission: "ADMITTED"; selectable: boolean; reason: string }>;
  }>;
};

export type DeepTeamAuditReport = {
  run_id: string;
  manifest: Record<string, unknown>;
  evidence: Record<string, unknown>;
  deepteam_risk: Record<string, unknown>;
  summary: Record<string, unknown>;
};

export type StartDeepTeamRunRequest = {
  scenario_id: string;
  target_profile_id: string;
  attack_profile_id: string;
  vulnerability_profile_id: string;
  max_total_tokens: number;
  execution_mode: DeepTeamExecutionMode;
  max_paths: 1 | 2;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ModelConnectivityError extends Error {
  constructor(message: string, public readonly status: number, public readonly path: string) {
    super(message);
    this.name = "ModelConnectivityError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}.`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (body.detail) message = formatApiErrorDetail(body.detail, response.status);
    } catch {
      // Keep the status-based message when the API did not return JSON.
    }
    throw new ModelConnectivityError(message, response.status, path);
  }
  return response.json() as Promise<T>;
}

export function formatApiErrorDetail(detail: unknown, status?: number) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const errors = detail.map((item): { location: string; reason: string; type: string } => {
      if (!item || typeof item !== "object") return { location: "request", reason: String(item), type: "" };
      const error = item as { loc?: unknown; msg?: unknown; type?: unknown };
      const location = Array.isArray(error.loc) ? error.loc.map(String).filter((part) => part !== "body").join(".") : "request";
      const reason = typeof error.msg === "string" ? error.msg : "Invalid value";
      return { location, reason, type: typeof error.type === "string" ? error.type : "" };
    });
    const unsupportedAdaptiveFields = errors.some((error) => ["execution_mode", "max_paths"].includes(error.location) && error.type === "extra_forbidden");
    if (unsupportedAdaptiveFields) return "The running API is outdated and does not support adaptive campaigns. Restart SecMate with npm run dev.";
    return errors.map((error) => `${error.location || "request"}: ${error.reason}`).join("; ");
  }
  if (detail && typeof detail === "object") {
    const value = detail as { message?: unknown; msg?: unknown };
    if (typeof value.message === "string") return value.message;
    if (typeof value.msg === "string") return value.msg;
  }
  return status ? `Request failed with HTTP ${status}.` : "The request failed.";
}

export const modelConnectivityService = {
  getPlatformCapabilities: () => request<PlatformCapabilities>("/platform-capabilities"),
  listProfiles: () => request<ModelProfile[]>("/model-profiles"),
  getProviderStatus: () => request<ProviderStatus[]>("/providers/status"),
  testProfile: (profileId: string) => request<ModelTestResult>(`/model-profiles/${encodeURIComponent(profileId)}/test`, { method: "POST" }),
  testAdaptiveHandoff: () => request<AdaptiveHandoffResult>("/model-workflows/adaptive-handoff/test", { method: "POST" }),
  getDeepTeamCatalog: () => request<DeepTeamCatalog>("/deepteam-catalog"),
  listDeepTeamRuns: (signal?: AbortSignal) => request<DeepTeamRunRecord[]>("/deepteam-runs?limit=500", { signal }),
  startDeepTeamRun: (selection: StartDeepTeamRunRequest, key?: string) => request<DeepTeamRunRecord>("/deepteam-runs", { method: "POST", headers: { "X-SecMate-Local-Run": "confirmed", ...(key ? { "Idempotency-Key": key } : {}) }, body: JSON.stringify(selection) }),
  cancelDeepTeamRun: (runId: string) => request<DeepTeamRunRecord>(`/deepteam-runs/${encodeURIComponent(runId)}/cancellation`, { method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" } }),
  getDeepTeamRun: (runId: string) => request<DeepTeamRunRecord>(`/deepteam-runs/${encodeURIComponent(runId)}`, { cache: "no-store" }),
  getDeepTeamAudit: (runId: string) => request<DeepTeamAuditReport>(`/deepteam-runs/${encodeURIComponent(runId)}/audit`, { cache: "no-store" }),
  getStandardReview: (runId: string) => request<StandardReviewView>(`/deepteam-runs/${encodeURIComponent(runId)}/standard-review`, { cache: "no-store" }),
  requestStandardReview: (runId: string, retry: boolean, key: string) => request<DeepTeamRunRecord>(`/deepteam-runs/${encodeURIComponent(runId)}/standard-review`, {
    method: "POST", headers: { "X-SecMate-Local-Run": "confirmed", "Idempotency-Key": key }, body: JSON.stringify({ retry }) }),
  createLinkedAssessment: (runId: string, reviewId: string, method: string, key: string) => request<DeepTeamRunRecord>(`/deepteam-runs/${encodeURIComponent(runId)}/linked-assessments`, {
    method: "POST", headers: { "X-SecMate-Local-Run": "confirmed", "Idempotency-Key": key }, body: JSON.stringify({ review_id: reviewId, attack_profile_id: method }) }),
  startLinkedAssessment: (runId: string, budget: number, key: string) => request<DeepTeamRunRecord>(`/deepteam-runs/${encodeURIComponent(runId)}/start`, {
    method: "POST", headers: { "X-SecMate-Local-Run": "confirmed", "Idempotency-Key": key }, body: JSON.stringify({ max_total_tokens: budget }) }),
  listLinkedDrafts: () => request<DeepTeamRunRecord[]>("/deepteam-linked-drafts", { cache: "no-store" }),
  cancelReviewJob: (jobId: string) => request<unknown>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" } }),
  resolveReviewJob: (jobId: string) => request<unknown>(`/jobs/${encodeURIComponent(jobId)}/resolve`, { method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" }, body: JSON.stringify({ acknowledge_uncertain_completion: true }) }),
};
