import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canonicalJudgeJson, chatMateCriticSource, chatMateTextHash, eligibleChatMateCritic, parseChatMateCriticReview, effectiveCriticRecommendation } from "./chatmateCritic";
import { criticAudit, criticReview, criticRun, savedCriticRun } from "./chatmateCriticFixtures";
import type { ChatMateRunRecord } from "./chatmateService";

beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => vi.unstubAllGlobals());

describe("Critic source eligibility", () => {
  it("adjusts a resisted same-profile recommendation only within a compatible boundary", () => {
    const review = criticReview(undefined, { weak_point_status: "NONE_OBSERVED", observed_weak_point: null,
      recommended_attack_profile_id: "prompt-injection-v1" });
    const plan = effectiveCriticRecommendation("prompt-injection-v1", "chatmate-manual-prompt-injection-v1", "RESISTED", review, "boundary-preserving-v1");
    expect(plan?.profile).toBe("system-override-v1");
    expect(plan?.adjusted).toBe(true);
    expect(review.recommended_attack_profile_id).toBe("prompt-injection-v1");
    expect(effectiveCriticRecommendation("prompt-probing-v1", "chatmate-manual-prompt-probing-v1", "RESISTED",
      { ...review, recommended_attack_profile_id: "prompt-probing-v1" }, "boundary-preserving-v1")).toBeNull();
  });
  it("allows a same-method Prompt Probing continuation when no weak point was observed", () => {
    const review = criticReview(undefined, { weak_point_status: "NONE_OBSERVED", observed_weak_point: null,
      recommended_attack_profile_id: "prompt-probing-v1" });
    expect(effectiveCriticRecommendation("prompt-probing-v1", "chatmate-manual-prompt-probing-v1", "RESISTED", review)).toEqual({
      profile: "prompt-probing-v1", objective: review.recommended_follow_up_objective, adjusted: false });
    expect(effectiveCriticRecommendation("prompt-probing-v1", "chatmate-manual-prompt-probing-v1", "RESISTED",
      { ...review, recommendation_available: false })).toBeNull();
    expect(effectiveCriticRecommendation("prompt-probing-v1", "chatmate-manual-prompt-probing-v1", "RESISTED",
      { ...review, recommended_attack_profile_id: "goal-redirection-v1" })).toBeNull();
  });
  it.each(["openrouter-nemotron-judge", "openrouter-xing-judge", "openrouter-nemotron-35-super-vl-judge"])("accepts validated Judge profile %s", (profile) => {
    const run = criticRun(), audit = criticAudit(run);
    const review = (audit.evidence.review_results as Record<string, unknown>[])[0];
    (review.target_evaluation as Record<string, unknown>).model_profile_id = profile;
    expect(chatMateCriticSource(run, audit).judge.model_profile_id).toBe(profile);
  });
  it("accepts canonical resisted and low-confidence inconclusive response audits", () => {
    for (const final_status of ["RESISTED", "INCONCLUSIVE"] as const) {
      const run = criticRun({ final_status });
      expect(eligibleChatMateCritic(run, criticAudit(run))).toBe(true);
    }
  });
  it.each([
    { status: "FAILED" }, { status: "EVALUATING" }, { status: "AWAITING_EVALUATION" }, { status: "DRAFT" },
    { final_status: "COMPROMISED" }, { final_status: "ERROR" }, { final_status: null },
    { error_code: "FAILED" }, { error_message: "Failed closed" }, { artifact_available: false },
    { manual_evidence: null }, { selected_candidate_id: "other" }, { evaluation_id: "other" },
  ] as Partial<ChatMateRunRecord>[])("blocks ineligible or stale source %j", (overrides) => {
    expect(eligibleChatMateCritic(criticRun(overrides), criticAudit())).toBe(false);
  });
  it("blocks missing audits, absent Judge, visible failure and noncanonical citations", () => {
    const run = criticRun();
    expect(eligibleChatMateCritic(run, null)).toBe(false);
    const audit = criticAudit();
    const review = (audit.evidence.review_results as Record<string, unknown>[])[0];
    review.target_evaluation = null;
    expect(eligibleChatMateCritic(run, audit)).toBe(false);
    run.manual_evidence = { ...run.manual_evidence!, outcome: "VISIBLE_FAILURE", redacted_response_text: null,
      failure_reason: "RESPONSE_COULD_NOT_BE_COMPLETED", persisted_response_sha256: null, judge_data_collection_attested: false };
    expect(eligibleChatMateCritic(run, criticAudit(run))).toBe(false);
    const inconclusive = criticRun({ final_status: "INCONCLUSIVE" });
    const invalid = criticAudit(inconclusive);
    ((invalid.evidence.review_results as Record<string, unknown>[])[0].target_evaluation as Record<string, unknown>).evidence_references = ["fabricated"];
    expect(eligibleChatMateCritic(inconclusive, invalid)).toBe(false);
  });
});

describe("Critic flat review validation", () => {
  it.each(["Cut off mid", "Complete\u001f sentence.", "Complete\u202e sentence."])("rejects malformed current-version prose: %s", async (bad) => {
    const run = savedCriticRun();
    await expect(parseChatMateCriticReview(run, criticAudit(run), criticReview(run, { schema_version: "1.1", management_summary: bad }))).rejects.toThrow();
  });
  it("accepts current complete prose while retaining legacy reader compatibility", async () => {
    const run = savedCriticRun();
    for (const schema_version of ["1.0", "1.1"] as const) {
      expect((await parseChatMateCriticReview(run, criticAudit(run), criticReview(run, { schema_version }))).schema_version).toBe(schema_version);
    }
  });
  it("verifies a Python-generated canonical Judge SHA and a content-derived candidate SHA", async () => {
    const run = savedCriticRun(), review = criticReview(run), audit = criticAudit(run);
    expect(await chatMateTextHash(canonicalJudgeJson(chatMateCriticSource(run, audit).judge))).toBe(review.source_judge_sha256);
    expect(await parseChatMateCriticReview(run, audit, review)).toEqual(review);
  });
  it("uses Python-compatible ASCII escaping and floating-point confidence", () => {
    expect(canonicalJudgeJson({ confidence: 1, reasoning: "café 😀", deviation_score: 0 }))
      .toBe('{"confidence":1.0,"deviation_score":0,"reasoning":"caf\\u00e9 \\ud83d\\ude00"}');
    expect(canonicalJudgeJson({ confidence: .000001 })).toBe('{"confidence":1e-06}');
  });
  it.each([
    ["run_id", "other"], ["critic_review_id", "critic-review-b00000000001"], ["source_evaluation_id", "other"],
    ["source_candidate_sha256", "0".repeat(64)], ["source_correlation_sha256", "0".repeat(64)], ["source_judge_sha256", "0".repeat(64)],
    ["created_at", "old"], ["schema_version", "2.0"], ["provider", "OTHER"], ["model", "other"], ["profile_id", "other"],
    ["evidence_references", ["other-turn"]], ["policy_references", ["other-policy"]],
    ["invalid_evidence_references", ["chatmate-run-c00000000001-turn-1"]], ["invalid_policy_references", ["CHATMATE_TRUSTED_INSTRUCTION_HIERARCHY"]],
    ["recommendation_available", false], ["recommendation_available", "true"], ["critic_data_collection_attested", false],
    ["weak_point_status", "UNPROVEN"], ["observed_weak_point", null], ["management_summary", ""],
    ["expected_evidence", []], ["recommended_attack_profile_id", "arbitrary-v1"], ["source_input_sha256", "invalid"],
    ["budget", { provider_calls_attempted: 2 }], ["model_attempts", []],
  ])("rejects mismatched or malformed %s", async (field, value) => {
    const review = { ...criticReview(), [field as string]: value };
    await expect(parseChatMateCriticReview(savedCriticRun(), criticAudit(), review)).rejects.toThrow();
  });
  it("rejects nested output, extra fields and missing strict fields", async () => {
    const review = criticReview();
    for (const value of [{ output: review }, { ...review, final_status: "COMPROMISED" }, { ...review, outcome_analysis: undefined }]) {
      await expect(parseChatMateCriticReview(savedCriticRun(), criticAudit(), value)).rejects.toThrow();
    }
  });
  it("does not accept a substituted candidate even with matching run and manifest hash labels", async () => {
    const run = savedCriticRun();
    run.candidate_batch!.candidates[0].prompt = "Replaced selected attack";
    await expect(parseChatMateCriticReview(run, criticAudit(run), criticReview(run))).rejects.toThrow();
  });
  it("does not accept substituted Judge reasoning", async () => {
    const audit = criticAudit();
    ((audit.evidence.review_results as Record<string, unknown>[])[0].target_evaluation as Record<string, unknown>).reasoning = "Substituted rationale";
    await expect(parseChatMateCriticReview(savedCriticRun(), audit, criticReview())).rejects.toThrow();
  });
  it("allows advisory analysis with invalid-reference accounting but blocks recommendations", async () => {
    const review = criticReview(undefined, { invalid_evidence_references: ["invented-turn"], recommendation_available: false });
    expect((await parseChatMateCriticReview(savedCriticRun(), criticAudit(), review)).recommendation_available).toBe(false);
    await expect(parseChatMateCriticReview(savedCriticRun(), criticAudit(), { ...review, weak_point_status: "EVIDENCE_SUPPORTED" })).rejects.toThrow();
  });
  it("permits NONE_OBSERVED only with a null observation", async () => {
    const review = criticReview(undefined, { weak_point_status: "NONE_OBSERVED", observed_weak_point: null });
    expect((await parseChatMateCriticReview(savedCriticRun(), criticAudit(), review)).weak_point_status).toBe("NONE_OBSERVED");
    await expect(parseChatMateCriticReview(savedCriticRun(), criticAudit(), { ...review, observed_weak_point: "Speculation" })).rejects.toThrow();
  });
  it.each([0, 4, 1.5])("rejects invalid recorded attempt count %s", async (critic_attempts) => {
    await expect(parseChatMateCriticReview(savedCriticRun({ critic_attempts }), criticAudit(), criticReview())).rejects.toThrow();
  });
  it("fails closed when browser source hashing is unavailable", async () => {
    vi.stubGlobal("crypto", {});
    await expect(parseChatMateCriticReview(savedCriticRun(), criticAudit(), criticReview())).rejects.toThrow("WebCrypto");
  });
});
