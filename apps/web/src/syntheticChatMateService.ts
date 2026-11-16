export type SyntheticChatMateRun = {
  run_id: string; job_id: string | null; target_id: "secmate.synthetic-chatmate.fresh.v1"; target_name: "Synthetic ChatMate";
  mode: "MOCKED"; status: "QUEUED" | "RUNNING" | "CANCEL_REQUESTED" | "CANCELLED" | "COMPLETED" | "FAILED";
  verification: "UNVERIFIED" | "MOCK_VERIFIED"; progress: number; stage: string; created_at: string;
  started_at: string | null; completed_at: string | null; final_response: string | null; evidence_available: boolean;
  error_code: string | null; error_message: string | null;
};

export type SyntheticChatMateEvidence = {
  schema_version: "synthetic-chatmate-phase5-smoke-v1"; target_id: "secmate.synthetic-chatmate.fresh.v1"; target_version: "0.5.0";
  mode: "MOCKED"; provider_profile: "openrouter-nemotron-35-super-vl-target"; model: "nvidia/nemotron-3.5-super-vl:free";
  request_text: string; limits: { max_model_turns: 2; max_tool_calls: 1; max_output_tokens_per_turn: 500; deadline_seconds: 120; permitted_effect: "READ_ONLY_RETRIEVAL" };
  model_turns_completed: number; tool_activity: Array<{ tool_call_id: string; name: "secmate.search_mail" | "secmate.read_teams"; arguments: Record<string, unknown>; authorization: "ALLOWED"; execution: "FICTIONAL_READ_COMPLETED"; source_refs: Array<Record<string, unknown>> }>;
  final_response: string; terminal_outcome: "COMPLETED"; fake_write_count: 0; fake_effect_count: 0; reconciled: true; artifacts_sha256: Record<string, string>;
};

export type SyntheticChatMateTarget = { id: "secmate.synthetic-chatmate.fresh.v1"; name: "Synthetic ChatMate"; ownership: "SERVER_OWNED"; version: "0.5.0"; mode: "MOCKED_ONLY"; state: "UNFINISHED_UNVERIFIED" | "MOCK_VERIFIED"; latest_run_id: string | null };
const API = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store", ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : `Smoke-test API failed with HTTP ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export const syntheticChatMateService = {
  getTarget: () => request<SyntheticChatMateTarget>("/synthetic-chatmate-target"),
  getRun: (id: string) => request<SyntheticChatMateRun>(`/synthetic-chatmate-smoke-runs/${encodeURIComponent(id)}`),
  getEvidence: (id: string) => request<SyntheticChatMateEvidence>(`/synthetic-chatmate-smoke-runs/${encodeURIComponent(id)}/evidence`),
  start: (key: string) => request<SyntheticChatMateRun>("/synthetic-chatmate-smoke-runs", { method: "POST", headers: { "X-SecMate-Local-Run": "confirmed", "Idempotency-Key": key }, body: JSON.stringify({ target_id: "secmate.synthetic-chatmate.fresh.v1", mode: "MOCKED", bounded_test_attested: true }) }),
  cancel: (id: string, key: string) => request<SyntheticChatMateRun>(`/synthetic-chatmate-smoke-runs/${encodeURIComponent(id)}/cancellation`, { method: "POST", headers: { "X-SecMate-Local-Run": "confirmed", "Idempotency-Key": key } }),
};
