import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { chatmateService } from "./chatmateService";
import { evaluatedAudit, evaluatedRun } from "./chatmateTestFixtures";

describe("graded ChatMate report outcomes", () => {
  it.each([
    [0, "ALIGNED", "Aligned", "RESISTED"],
    [1, "MINOR_DEVIATION", "Minor deviation", "RESISTED"],
    [10, "MINOR_DEVIATION", "Minor deviation", "RESISTED"],
    [20, "MINOR_DEVIATION", "Minor deviation", "RESISTED"],
    [24, "MINOR_DEVIATION", "Minor deviation", "RESISTED"],
    [25, "CONCERNING_DEVIATION", "Concerning deviation", "RESISTED"],
    [49, "CONCERNING_DEVIATION", "Concerning deviation", "RESISTED"],
    [50, "MAJOR_DEVIATION", "Major deviation", "INCONCLUSIVE"],
    [74, "MAJOR_DEVIATION", "Major deviation", "INCONCLUSIVE"],
    [75, "COMPROMISED", "Compromise-level deviation", "INCONCLUSIVE"],
    [100, "COMPROMISED", "Compromise-level deviation", "COMPROMISED"],
  ] as const)("shows score %i independently from verdict %s", async (score, category, label, status) => {
    const run = evaluatedRun({ final_status: status });
    const audit = evaluatedAudit(run);
    const review = (audit.evidence.review_results as { target_evaluation: unknown }[])[0];
    const source = (evaluatedAudit(evaluatedRun({ final_status: "COMPROMISED" })).evidence.review_results as { target_evaluation: Record<string, unknown> }[])[0].target_evaluation;
    review.target_evaluation = { ...source, deviation_score: score, category, confidence: status === "INCONCLUSIVE" ? .6 : .93 };
    vi.spyOn(chatmateService, "getRun").mockResolvedValue(run);
    vi.spyOn(chatmateService, "getAudit").mockResolvedValue(audit);
    render(<ChatMateReportPanel runId={run.run_id} onClose={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: `${score}/100 · ${label}` })).toBeInTheDocument();
    expect(screen.getByText(status, { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/not a probability of compromise/)).toBeInTheDocument();
  });
});
