import type { ChatMateRunRecord } from "./chatmateService";

const attackNames = {
  "prompt-injection-v1": "Prompt Injection",
  "system-override-v1": "System Override",
  "prompt-probing-v1": "Prompt Probing",
  "goal-redirection-v1": "Goal Redirection",
  "context-poisoning-v1": "Context Poisoning",
};

export const chatMateAttackName = (run: ChatMateRunRecord) => attackNames[run.attack_profile_id] ?? "ChatMate assessment";

export function chatMateRunReference(runId: string) {
  const reference = runId.replace(/^chatmate[-_]?(?:run[-_]?)?/i, "");
  return `Run · ${(reference || runId).slice(0, 6)}`;
}

export function chatMateDate(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  }).format(new Date(value));
}

export function chatMateGenerationFailed(run: ChatMateRunRecord) {
  return run.status === "FAILED" && !run.manual_evidence
    && (run.evaluation_attempts === 0 || !run.candidate_batch);
}

export function chatMateCanRetryJudge(run: ChatMateRunRecord) {
  return run.status === "FAILED" && run.final_status === "ERROR"
    && Boolean(run.manual_evidence) && run.evaluation_attempts < 10;
}

export function chatMateStatusLabel(run: ChatMateRunRecord) {
  if (chatMateGenerationFailed(run)) return "Generation Failed";
  if (run.status === "FAILED" || run.final_status === "ERROR") return "Evaluation failed";
  const labels = {
    DRAFT: "Draft · configure assessment",
    QUEUED: "Waiting to generate", GENERATING: "Generating attacks", AWAITING_SELECTION: "Awaiting selection",
    AWAITING_RESPONSE: "Awaiting response", AWAITING_EVALUATION: "Awaiting evaluation", EVALUATING: "Evaluating response",
    COMPLETED: "Completed", REJECTED: "Candidates rejected", ABANDONED: "Run ended",
  };
  return labels[run.status];
}

// Diagnostics are server-supplied text, never markup. Bound before processing and
// redact common credential forms defensively even when server logs are sanitized.
export function chatMateSafeDiagnostic(value: string, limit = 1000) {
  const bounded = value.slice(0, 16_000);
  const safe = bounded
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\u0000-\u0008\u000b-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, "")
    .replace(/\bBearer\s+[^\s,;"']+/gi, "Bearer [REDACTED]")
    .replace(/\b(?:sk|gsk)[-_][a-zA-Z0-9_-]+/g, "[REDACTED]")
    .replace(/((?:["']?)(?:api[_-]?key|access[_-]?token|authorization|password|secret)(?:["']?)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}"']+)/gi, "$1[REDACTED]")
    .replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, "$1[REDACTED]@");
  return safe.length > limit ? `${safe.slice(0, limit)}…` : safe;
}

// Current records contain a concise backend reason. Older records can contain a
// whole worker traceback; keep that evidence in diagnostics, not the alert body.
export function chatMateErrorMessage(run: ChatMateRunRecord) {
  const fallback = chatMateGenerationFailed(run) ? "Attack generation could not be completed." : "The Judge evaluation failed closed.";
  const safe = chatMateSafeDiagnostic(run.error_message ?? fallback, 16_000).trim();
  const verbose = safe.length > 600 || /\n|Traceback|\bFile ".*", line \d+|["'](?:error|message)["']\s*:/i.test(safe);
  if (!verbose) return safe || fallback;

  const quotedReason = [...safe.matchAll(/["'](?:message|error_message)["']\s*:\s*(["'])(.*?)\1/g)].at(-1)?.[2];
  const lastLine = safe.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).at(-1);
  const reason = quotedReason || lastLine || safe;
  const evidence = `${run.error_code ?? ""} ${lastLine ?? ""} ${reason}`.toLowerCase();
  const mappings: Array<[RegExp, string]> = [
    [/context_length_exceeded|context length|maximum context/, "The request exceeded the provider's context limit."],
    [/insufficient_quota|quota exhausted/, "The provider quota was exhausted."],
    [/rate_limit|rate limit|too many requests|\b429\b/, "The provider rate limit prevented completion."],
    [/authentication|invalid_api_key|invalid api key|unauthorized|\b401\b/, "The provider rejected authentication."],
    [/permission_denied|\b403\b/, "The provider denied access to the request."],
    [/model_not_found|model_decommissioned|model_unavailable|model not found/, "The configured provider model is unavailable."],
    [/json_validate_failed|invalid_json|malformed_response|schema_validation|provider_invalid_response/, "The provider did not return a valid response in the required format."],
    [/timeout|timed out/, "The provider request timed out."],
    [/network_error|provider_unavailable|connecterror|connection refused/, "The provider could not be reached."],
    [/budget_exhausted|budget exhausted/, "The generation budget was exhausted."],
    [/unsupported_parameter|invalid_parameter/, "The provider rejected a request parameter."],
    [/content_policy_violation/, "The provider rejected the request under its content policy."],
  ];
  const mapped = mappings.find(([pattern]) => pattern.test(evidence))?.[1];
  const conciseReason = reason.replace(/^[\w.]*Error:\s*(?:Error code:\s*\d+\s*-\s*)?/i, "").replace(/\s+/g, " ").trim();
  return mapped ? `${mapped}${quotedReason ? ` ${chatMateSafeDiagnostic(quotedReason, 240)}` : ""}` : chatMateSafeDiagnostic(conciseReason || fallback, 360);
}
