const targetLabels: Record<string, string> = {
  "synthetic-socmate-tier1": "SocMate",
  "socmate-vuln": "SocMate",
  "synthetic-chatmate-rag": "ChatMate",
  "chatmate-vuln": "ChatMate",
  "secmate.synthetic-chatmate.fresh.v1": "Synthetic ChatMate",
};

const assessmentLabels: Record<string, string> = {
  "ExcessiveAgency:permissions": "Permission controls",
  "IndirectInstruction:document_embedded_instructions": "Document instructions",
  "PromptLeakage:instructions": "Instruction leakage",
  "SensitiveInformationDisclosure:pii": "Personal data exposure",
};

function humanize(value: string) {
  return value
    .replace(/-v\d+$/i, "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function targetDisplayName(value: string) {
  return targetLabels[value] ?? humanize(value.replace(/^synthetic-/, ""));
}

export function assessmentDisplayName(value: string) {
  if (assessmentLabels[value]) return assessmentLabels[value];
  if (/\s|\//.test(value)) return value;
  return value.split(":").map(humanize).join(" / ");
}

export function assessmentFailureMessage(
  fallback: string | null,
  attempts: Array<Record<string, unknown>>,
) {
  const authenticationAttempt = attempts.find((attempt) => attempt.error_code === "AUTHENTICATION");
  if (authenticationAttempt) {
    const provider = typeof authenticationAttempt.provider === "string"
      ? humanize(authenticationAttempt.provider.toLowerCase())
      : "Model provider";
    return `${provider} rejected its API key. Update the configured key and restart SecMate.`;
  }
  if (attempts.some((attempt) => attempt.error_code === "BUDGET_EXHAUSTED")) {
    const jsonRejected = attempts.some((attempt) => attempt.provider_error_code === "json_validate_failed");
    return jsonRejected
      ? "The assessment stopped at its configured usage limit after the AI service rejected structured outputs. No security conclusion was reached."
      : "The assessment stopped at its configured usage limit. No security conclusion was reached.";
  }
  return fallback ?? "The assessment service could not complete this run.";
}
