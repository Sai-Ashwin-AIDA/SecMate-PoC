import { describe, expect, it } from "vitest";
import { chatMateCandidate, chatMateClassification, chatMateExport, chatMateReportLink, eligibleChatMateResult, parseChatMateAudit } from "./chatmateProjections";
import { evaluatedAudit, evaluatedRun } from "./chatmateTestFixtures";
import type { ChatMateRunRecord } from "./chatmateService";

describe("ChatMate source projections", () => {
  it.each([
    ["COMPROMISED", null, true], ["INCONCLUSIVE", null, false], ["ERROR", null, false], ["RESISTED", null, false],
  ] as const)("classifies %s with severity %s and open=%s", (final_status, severity, open) => {
    expect(chatMateClassification(evaluatedRun({ final_status }))).toMatchObject({ severity, open });
  });
  it("prioritizes operational failure over a stale compromise verdict", () => {
    expect(chatMateClassification(evaluatedRun({ status: "FAILED", final_status: "COMPROMISED" })))
      .toEqual({ severity: null, label: "Evaluation failed", open: false });
  });
  it.each(["QUEUED", "GENERATING", "AWAITING_SELECTION", "AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING", "REJECTED", "ABANDONED"] as const)("excludes %s even with stale result data", (status) => {
    const run = evaluatedRun({ status });
    expect(eligibleChatMateResult(run)).toBe(false);
    expect(chatMateClassification(run)).toBeNull();
  });
  it.each([
    { status: "FAILED", manual_evidence: null }, { status: "FAILED", evaluation_attempts: 0 },
  ] as Partial<ChatMateRunRecord>[])("excludes generation-only failure %j", (overrides) => {
    expect(eligibleChatMateResult(evaluatedRun(overrides))).toBe(false);
  });
  it("retains evaluated failures without artifacts in history", () => {
    expect(eligibleChatMateResult(evaluatedRun({ status: "FAILED", final_status: "ERROR", artifact_available: false }))).toBe(true);
  });
  it("requires candidate ID and hash to match", () => {
    expect(chatMateCandidate(evaluatedRun())).toMatchObject({ candidate_id: "candidate-1" });
    expect(chatMateCandidate(evaluatedRun({ selected_candidate_sha256: "wrong" }))).toBeNull();
  });
  it("encodes exact run IDs in report links", () => {
    expect(chatMateReportLink("run/one &two")).toBe("/reports?chatmate=run%2Fone%20%26two");
  });
});

describe("validated ChatMate audit parsing and export", () => {
  it.each(["RESISTED", "COMPROMISED", "INCONCLUSIVE", "ERROR"] as const)("parses a canonical %s audit", (final_status) => {
    const run = evaluatedRun({ final_status });
    expect(parseChatMateAudit(run, evaluatedAudit(run)).audit.summary.final_status).toBe(final_status);
  });
  it.each(["run_id", "evaluation_id", "selected_candidate_id", "selected_candidate_sha256", "manual_evidence_id", "manual_correlation_sha256", "candidate_batch_id", "execution_kind", "target_invocation"])("blocks mismatched manifest %s", (field) => {
    const audit = evaluatedAudit();
    audit.manifest[field] = "tampered";
    expect(() => parseChatMateAudit(evaluatedRun(), audit)).toThrow();
  });
  it.each(["manifest", "summary", "evidence", "deepteam_risk"] as const)("blocks cross-run %s", (field) => {
    const audit = evaluatedAudit();
    audit[field].run_id = "other";
    expect(() => parseChatMateAudit(evaluatedRun(), audit)).toThrow();
  });
  it.each([null, {}, { evidence: {} }])("blocks malformed audit %j", (audit) => {
    expect(() => parseChatMateAudit(evaluatedRun(), audit)).toThrow();
  });
  it.each([NaN, Infinity, -1, 1.1, "0.9"])("blocks invalid confidence %s", (confidence) => {
    const audit = evaluatedAudit();
    const review = (audit.evidence.review_results as Record<string, unknown>[])[0];
    (review.target_evaluation as Record<string, unknown>).confidence = confidence;
    expect(() => parseChatMateAudit(evaluatedRun(), audit)).toThrow();
  });
  it("blocks redacted observation substitution", () => {
    const audit = structuredClone(evaluatedAudit());
    const path = (audit.evidence.paths as { turns: Record<string, unknown>[] }[])[0];
    path.turns[0].target_response = "Unrelated response";
    expect(() => chatMateExport(evaluatedRun(), audit)).toThrow();
  });
  it("blocks a conclusive verdict without Judge evidence", () => {
    const audit = evaluatedAudit();
    (audit.evidence.review_results as Record<string, unknown>[])[0].target_evaluation = null;
    expect(() => parseChatMateAudit(evaluatedRun(), audit)).toThrow();
  });
  it("exports only API-selected data and validated redacted audit", () => {
    const run = evaluatedRun();
    run.logs = [{ timestamp: run.created_at, level: "INFO", message: "DO NOT EXPORT LOGS" }];
    const exported = chatMateExport(run, evaluatedAudit(run));
    const json = JSON.stringify(exported);
    expect(json).toContain("Refused [REDACTED]");
    expect(json).not.toContain("DO NOT EXPORT");
    expect(exported.run).not.toHaveProperty("candidate_batch");
    expect(exported.run).not.toHaveProperty("logs");
    expect(exported.source).toBe("ChatMate");
    expect(exported.audit.manifest.execution_kind).toBe("MANUAL_CHATMATE");
    expect(exported.audit.manifest.target_invocation).toBe("OPERATOR_MEDIATED");
    expect(exported.run.manual_evidence?.collection_method).toBe("MANUAL_COPY_PASTE");
  });
  it("whitelists and sanitizes saved conversation/follow-up context and explicit Critic status metadata", () => {
    const run = evaluatedRun({ conversation_id: "session-42\u0000 api_key=sk-sensitive-value",
      parent_run_id: "chatmate-parent", follow_up_critic_review_id: "critic-review-parent",
      follow_up_objective: "Test delegated authority; password=secret-password", follow_up_expected_evidence: ["Refusal or adoption. Bearer private-token"],
      follow_up_context: { browser_draft: "DO NOT EXPORT CONTEXT EXTRAS" },
      critic_status: "FAILED", critic_attempts: 2, critic_review_id: "critic-review-current", critic_review_available: false,
      critic_error_code: "CRITIC_PROVIDER_RATE_LIMIT", critic_error_message: "Provider unavailable. Bearer private-key" });
    const bundle = chatMateExport(run, evaluatedAudit(run));
    expect(bundle.run).toMatchObject({ conversation_id: "session-42 api_key=[REDACTED]", parent_run_id: "chatmate-parent",
      follow_up_critic_review_id: "critic-review-parent", follow_up_objective: "Test delegated authority; password=[REDACTED]",
      follow_up_expected_evidence: ["Refusal or adoption. Bearer [REDACTED]"], critic_status: "FAILED", critic_attempts: 2,
      critic_review_id: "critic-review-current", critic_review_available: false,
      critic_error_code: "CRITIC_PROVIDER_RATE_LIMIT", critic_error_message: "Provider unavailable. Bearer [REDACTED]" });
    const json = JSON.stringify(bundle);
    for (const secret of ["sk-sensitive-value", "secret-password", "private-token", "private-key", "DO NOT EXPORT CONTEXT EXTRAS"]) expect(json).not.toContain(secret);
    expect(bundle.run).not.toHaveProperty("follow_up_context");
    expect(bundle).not.toHaveProperty("critic_review");
  });
  it("gives legacy reports explicit unrequested Critic metadata without inventing advice", () => {
    const bundle = chatMateExport(evaluatedRun(), evaluatedAudit());
    expect(bundle.run).toMatchObject({ critic_status: null, critic_attempts: 0, critic_review_available: false,
      conversation_id: null, parent_run_id: null, follow_up_critic_review_id: null, follow_up_objective: null, follow_up_expected_evidence: [] });
    expect(bundle).not.toHaveProperty("critic_review");
  });
});
