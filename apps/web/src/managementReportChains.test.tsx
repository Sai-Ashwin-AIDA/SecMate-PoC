import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as reports from "./managementReport";
import type { ManagementReportItem } from "./managementReport";
import { ManagementReportPanel } from "./ManagementReportPanel";
import { criticReview } from "./chatmateCriticFixtures";

function pair() {
  const review = criticReview();
  const parent: ManagementReportItem = { source: "ChatMate", runId: review.run_id,
    method: "Prompt Injection", target: "ChatMate", completed: "2026-10-21T08:00:00Z", outcome: "Resisted",
    evidenceStatus: "Verified", summary: "No violation observed.", originalAvailable: true,
    score: 10, confidence: .93, rationales: ["Parent Judge rationale."], citations: ["parent-turn"], actions: [], exchanges: [],
    appendix: { "Evaluation ID": review.source_evaluation_id, "Prompt SHA-256": review.source_candidate_sha256,
      "Correlation SHA-256": review.source_correlation_sha256 },
    lineage: { parentRunId: null, reviewId: review.critic_review_id, viaReviewId: null, profile: "prompt-injection-v1",
      specId: "chatmate-manual-prompt-injection-v1", specHash: "a".repeat(64), context: null },
    critic: { status: "Verified", review } };
  const child: ManagementReportItem = { ...parent, runId: "chatmate-run-child", method: "System Override", critic: undefined,
    outcome: "Inconclusive", score: 60, confidence: .7, rationales: ["Child Judge rationale."], citations: ["child-turn"],
    appendix: { "Evaluation ID": "child-evaluation" },
    lineage: { ...parent.lineage!, parentRunId: parent.runId, reviewId: null, viaReviewId: review.critic_review_id,
      profile: review.recommended_attack_profile_id,
      context: { parent_run_id: parent.runId, critic_review_id: review.critic_review_id,
        source_evaluation_id: review.source_evaluation_id, source_candidate_sha256: review.source_candidate_sha256,
        source_correlation_sha256: review.source_correlation_sha256, source_judge_sha256: review.source_judge_sha256,
        assessment_spec_sha256: "a".repeat(64), recommended_attack_profile_id: review.recommended_attack_profile_id,
        objective: review.recommended_follow_up_objective, expected_evidence: review.expected_evidence,
        recommendation_policy: "boundary-preserving-v1" } } };
  return { parent, child };
}

afterEach(() => vi.restoreAllMocks());

describe("selected assessment-chain reports", () => {
  it("verifies a current same-method continuation without reinterpreting historical policy", () => {
    const { parent, child } = pair();
    parent.lineage!.profile = child.lineage!.profile = "prompt-probing-v1";
    parent.lineage!.specId = child.lineage!.specId = "chatmate-manual-prompt-probing-v1";
    Object.assign(parent.critic!.review!, { weak_point_status: "NONE_OBSERVED", observed_weak_point: null,
      recommended_attack_profile_id: "prompt-probing-v1" });
    Object.assign(child.lineage!.context!, { recommended_attack_profile_id: "prompt-probing-v1",
      recommendation_policy: "single-turn-continuation-v1" });
    const { chains } = reports.assessmentChains([parent, child]);
    expect(chains).toHaveLength(1);
    expect(chains[0].status).toBe("Verified");
    expect(chains[0].transitions[0].policyAdjusted).toBe(false);
  });
  it("groups parent before follow-up regardless of selection order without merging verdicts", () => {
    const { parent, child } = pair();
    const { chains } = reports.assessmentChains([child, parent]);
    expect(chains).toHaveLength(1);
    expect(chains[0].status).toBe("Verified");
    expect(chains[0].stages.map((item) => [item.runId, item.score, item.outcome])).toEqual([
      [parent.runId, 10, "Resisted"], [child.runId, 60, "Inconclusive"]]);
    expect(chains[0].transitions[0].criticReviewId).toBe(parent.critic!.review!.critic_review_id);
  });
  it.each(["source_judge_sha256", "source_candidate_sha256", "source_evaluation_id", "critic_review_id",
    "assessment_spec_sha256", "objective", "expected_evidence", "recommended_attack_profile_id", "recommendation_policy"])("rejects a mismatched edge: %s", (field) => {
    const { parent, child } = pair();
    child.lineage!.context![field] = field === "expected_evidence" ? ["different"] : "tampered";
    const { chains } = reports.assessmentChains([parent, child]);
    expect(chains).toHaveLength(2);
    expect(chains.some((chain) => chain.status === "Conflict")).toBe(true);
    expect(parent.outcome).toBe("Resisted");
  });
  it("keeps selected-only scope explicit for a missing parent", () => {
    const { child } = pair();
    const { chains } = reports.assessmentChains([child]);
    expect(chains).toHaveLength(1);
    expect(chains[0].status).toBe("Partial");
    expect(chains[0].notice).toMatch(/Parent not selected/);
  });
  it("keeps valid Judge evidence available when Critic is invalid", () => {
    const { parent, child } = pair();
    parent.critic = { status: "Invalid", notice: "Critic verification failed." };
    expect(reports.assessmentChains([parent, child]).chains).toHaveLength(2);
    expect(parent.evidenceStatus).toBe("Verified");
  });
  it("exports chain structure and excludes unselected comparison prompts", () => {
    const { parent, child } = pair();
    child.lineage!.context!.parent_candidates = [{ prompt: "UNSELECTED_PRIVATE_COMPARISON" }];
    const bundle = reports.managementReportBundle("Test", "now", [child, parent], { reviewer: "", date: "", decision: "", notes: "" });
    expect(bundle.schemaVersion).toBe("1.1");
    expect(bundle.chains).toHaveLength(1);
    expect(JSON.stringify(bundle)).not.toContain("UNSELECTED_PRIVATE_COMPARISON");
    expect(bundle.items.map((item) => item.runId)).toEqual([child.runId, parent.runId]);
  });
  it("prints a dedicated Critic transition once alongside both independent Judge stages", async () => {
    const { parent, child } = pair();
    vi.spyOn(reports, "loadManagementReport").mockResolvedValue([child, parent]);
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    render(<ManagementReportPanel selections={[{ source: "ChatMate", runId: child.runId }, { source: "ChatMate", runId: parent.runId }]} onClose={() => {}} />);
    await screen.findByRole("heading", { name: /Assessment chain 1 ·/ });
    const chain = screen.getByRole("region", { name: "Assessment chain 1" });
    expect(within(chain).getByRole("heading", { name: "Stage 1 — Initial assessment" })).toBeInTheDocument();
    expect(within(chain).getByRole("heading", { name: "Stage 2 — Follow-up" })).toBeInTheDocument();
    expect(screen.getAllByText(parent.critic!.review!.management_summary)).toHaveLength(1);
    expect(within(chain).getByText(/does not modify either Judge verdict/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Print / Save PDF" }));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    expect(screen.getByRole("heading", { name: "Adaptive analysis · Critic" })).toBeInTheDocument();
  });
});
