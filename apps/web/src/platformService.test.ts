import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { platformService } from "./platformService";

const assessmentInput = {
  targetId: "socmate",
  name: "Lifecycle test",
  attackerProfileId: "groq-qwen-attacker",
  judgeProfileId: "openrouter-nemotron-35-super-vl-judge",
  scenarios: ["Excessive agency"],
  maxTurns: 3,
  tokenBudget: 8000,
};

async function settle<T>(promise: Promise<T>, milliseconds = 700) {
  await vi.advanceTimersByTimeAsync(milliseconds);
  return promise;
}

describe("platformService assessment lifecycle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => vi.useRealTimers());

  it("starts with only the verified SOCMate PoC baseline", async () => {
    const targetsPromise = platformService.listTargets();
    const assessmentsPromise = platformService.listAssessments();
    const findingsPromise = platformService.listFindings();
    await vi.advanceTimersByTimeAsync(400);

    const [targets, assessments, findings] = await Promise.all([targetsPromise, assessmentsPromise, findingsPromise]);
    expect(targets.map((target) => target.id)).toEqual(["socmate"]);
    expect(targets[0].modelName).toBe("nvidia/nemotron-3.5-super-vl:free");
    expect(assessments.map((assessment) => assessment.id)).toEqual(["ASM-SOCMATE-001"]);
    expect(assessments[0].advisoryResult).toBe("PASS");
    expect(assessments[0].judgeProfileId).toBe("openrouter-nemotron-judge");
    expect(findings).toEqual([]);
  });

  it("rejects an Assessment with no scenario coverage", async () => {
    const promise = platformService.createAssessment({ ...assessmentInput, scenarios: [] });
    const rejection = expect(promise).rejects.toThrow("Select at least one applicable scenario");
    await vi.advanceTimersByTimeAsync(700);
    await rejection;
  });

  it("rejects unsupported scenario identifiers", async () => {
    const promise = platformService.createAssessment({ ...assessmentInput, scenarios: ["Unknown scenario"] });
    const rejection = expect(promise).rejects.toThrow("unsupported scenario");
    await vi.advanceTimersByTimeAsync(700);
    await rejection;
  });

  it("rejects whitespace-only Target profiles", async () => {
    const promise = platformService.createTarget({ name: "   ", description: " ", owner: " ", environment: "Test", criticality: "Tier 2", modelProvider: "OpenRouter", modelName: "nvidia/nemotron-3-ultra-550b-a55b:free", tools: [" "], guardrails: [" "], dataClasses: [" "] });
    const rejection = expect(promise).rejects.toThrow("Target name, description, and owner are required");
    await vi.advanceTimersByTimeAsync(400);
    await rejection;
  });

  it("creates a non-terminal Assessment and finalizes evidence later", async () => {
    const created = await settle(platformService.createAssessment(assessmentInput));
    expect(created.status).toBe("VALIDATING");
    expect(created.advisoryResult).toBeNull();

    await vi.advanceTimersByTimeAsync(6500);
    const assessments = await settle(platformService.listAssessments(), 400);
    const completed = assessments.find((assessment) => assessment.id === created.id);
    expect(completed?.status).toBe("COMPLETED");
    expect(completed?.advisoryResult).toBe("CRITICAL_RISK_DETECTED");

    const reports = await settle(platformService.listReports(), 400);
    const findings = await settle(platformService.listFindings(), 400);
    expect(reports.some((report) => report.assessmentId === created.id && report.status === "AVAILABLE")).toBe(true);
    expect(findings.some((finding) => finding.assessmentId === created.id)).toBe(true);
  });

  it("supports safe cancellation before completion", async () => {
    const created = await settle(platformService.createAssessment({ ...assessmentInput, name: "Cancellation test" }));
    const requested = await settle(platformService.cancelAssessment(created.id), 300);
    expect(requested.status).toBe("CANCEL_REQUESTED");

    await vi.advanceTimersByTimeAsync(800);
    const assessment = await settle(platformService.getAssessment(created.id), 200);
    expect(assessment?.status).toBe("CANCELLED");
    expect(assessment?.advisoryResult).toBeNull();
  });

  it("does not mutate an Assessment while it remains in the same lifecycle stage", async () => {
    const created = await settle(platformService.createAssessment({ ...assessmentInput, name: "Stable polling test" }));
    await vi.advanceTimersByTimeAsync(700);
    const first = await settle(platformService.getAssessment(created.id), 200);
    const firstUpdatedAt = first?.updatedAt;
    const second = await settle(platformService.getAssessment(created.id), 200);
    expect(second?.status).toBe(first?.status);
    expect(second?.progress).toBe(first?.progress);
    expect(second?.updatedAt).toBe(firstUpdatedAt);
  });
});
