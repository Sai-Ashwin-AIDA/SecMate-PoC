export type TargetModelProfile = { profile_id: string; provider: "OPENROUTER"; model: string };
export type TargetProfileMetadata = { profile_schema_version: string; profile_id: string; profile_version: string; scenario_id: string; scenario_version: string; binding_version: string | null };
export type TargetSummary = {
  schema_version: "target-projection-v1";
  id: string;
  name: string;
  version: string;
  purpose: string;
  environment: "SYNTHETIC";
  ownership: "SERVER_OWNED";
  owner: string | null;
  synthetic: true;
  selectable: true;
  model_profile: TargetModelProfile;
  tool_count: number;
  tool_count_basis: "TOTAL_INVENTORY";
  profile: TargetProfileMetadata;
};
export type TargetTool = { canonical_name: string; display_name?: string; native_names: string[]; native_details: string; description: string; effect: "READ" | "WRITE"; effect_scope: "SIMULATED" | "FICTIONAL_DATA"; model_exposure: "EXPOSED"; implementation_status: "IMPLEMENTED"; execution_status: "AVAILABLE" | "REQUIRES_APPROVAL" | "NOT_ENABLED" | "EXECUTABLE" | "DEFERRED"; execution_details: string };
export type TargetGuardrail = { id: string; name: string; description: string; enforcement: "TRUSTED_APPLICATION" | "TARGET_RUNTIME" | "ASSESSMENT_DISPATCH" };
export type TargetDataMemory = { data_environment: "SYNTHETIC"; data_sources: string[]; production_data: false; memory_kind: "NONE_CLAIMED" | "SEEDED_FACTS_ONLY"; facts_only_seeded_memory: boolean | null; natural_learning: boolean | null; cross_run_memory: "NOT_CLAIMED" | "DISABLED"; assessment_state: "RUN_SCOPED" | "FRESH_ISOLATED_PER_PATH"; details: string[] };
export type ExecutionLimitProfile = { id: "deepteam-profile" | "smoke" | "target-runtime"; description: string; execution_modes: Array<"SINGLE" | "ADAPTIVE">; max_paths: number | null; max_conversation_turns: number | null; max_model_turns: number | null; max_tool_calls: number | null; max_output_tokens_per_turn: number | null; max_provider_attempts: number | null; deadline_seconds: number | null };
export type TargetDetail = TargetSummary & {
  tools: TargetTool[];
  guardrails: TargetGuardrail[];
  data_memory: TargetDataMemory;
  execution: { supported: true; channels: Array<"TEXT" | "MODEL_TOOLS" | "DEEPTEAM" | "BOUNDED_SMOKE">; limits: ExecutionLimitProfile[]; limitations: string[] };
  references: Array<{ path: string; kind: "SOURCE" | "DESIGN"; description: string }>;
};

const API = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store", method: "GET", signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : `Targets API failed with HTTP ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export const targetProjectionService = {
  list: (signal?: AbortSignal) => get<TargetSummary[]>("/targets", signal),
  get: (id: string, signal?: AbortSignal) => get<TargetDetail>(`/targets/${encodeURIComponent(id)}`, signal),
};
