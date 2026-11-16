import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FindingsPage, ReportsPage } from "./ModulePages";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { chatmateService } from "./chatmateService";
import { platformService } from "./platformService";
import { modelConnectivityService } from "./modelConnectivityService";
import { evaluatedAudit, evaluatedRun } from "./chatmateTestFixtures";
import { chatMateDate } from "./chatmateDisplay";

beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(chatmateService, "listRuns").mockResolvedValue([evaluatedRun()]);
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(evaluatedRun());
  vi.spyOn(chatmateService, "getAudit").mockResolvedValue(evaluatedAudit());
  vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([]);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("ChatMate Reports", () => {
  it("combines report date, outcome and source filters without changing the selected report", async () => {
    const user = userEvent.setup();
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-10-12T12:00:00Z"));
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.mocked(chatmateService.listRuns).mockResolvedValue([
      evaluatedRun({ run_id: "older", completed_at: "2026-09-01T12:00:00Z", final_status: "COMPROMISED" }),
      evaluatedRun({ run_id: "recent", completed_at: "2026-10-12T10:00:00Z", final_status: "RESISTED" }),
    ]);
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    const history = await screen.findByRole("region", { name: "Report history" });
    expect(await within(history).findByText("Run · recent")).toBeInTheDocument();
    expect(within(history).getAllByRole("button").filter((button) => button.closest(".report-history-list"))[0]).toHaveTextContent("Run · recent");
    await user.selectOptions(within(history).getByLabelText("Date"), "7");
    expect(within(history).queryByText("Run · older")).not.toBeInTheDocument();
    await user.selectOptions(within(history).getByLabelText("Outcome"), "violation");
    expect(within(history).getByText("No reports match these filters.")).toBeInTheDocument();
    await user.selectOptions(within(history).getByLabelText("Outcome"), "all");
    await user.selectOptions(within(history).getByLabelText("Source"), "summary");
    expect(within(history).queryByText("Run · recent")).not.toBeInTheDocument();
    await user.selectOptions(within(history).getByLabelText("Source"), "chatmate");
    expect(within(history).getByText("Run · recent")).toBeInTheDocument();
  });

  it("puts verdict, verified metrics, response and rationale before collapsed technical disclosures", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    render(<ChatMateReportPanel runId="chatmate-1" onClose={close} />);
    const verdict = await screen.findByRole("heading", { name: "10/100 · Minor deviation" });
    expect(screen.queryByText(/Manual assessment|Manual testing|ASSURANCE/i)).not.toBeInTheDocument();
    expect(screen.getByText("ChatMate", { selector: "dd" })).toBeInTheDocument();
    const conversation = screen.getByText("Test conversation").closest("details")!;
    expect(conversation).not.toHaveAttribute("open");
    expect(screen.getByLabelText("Selected attack")).not.toBeVisible();
    await user.click(screen.getByText("Test conversation"));
    const metrics = screen.getByLabelText("Evaluation metrics");
    expect(within(metrics).getByText("Deviation score")).toBeInTheDocument();
    expect(within(metrics).getByText("Judge-reported confidence")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Selected attack" })).getByText(evaluatedRun().candidate_batch!.candidates[0].prompt)).toBeInTheDocument();
    expect(within(metrics).getByText("93")).toBeInTheDocument();
    expect(within(metrics).getByText("Evaluation attempts")).toBeInTheDocument();
    const response = screen.getByRole("region", { name: "Captured response" });
    const rationale = screen.getByRole("region", { name: "Judge rationale" });
    expect(within(response).getByText("Refused [REDACTED]").tagName).toBe("DIV");
    expect(within(rationale).getByText("Validated Judge rationale.")).toBeInTheDocument();
    expect(within(rationale).getByRole("region", { name: "Cited evidence" })).toBeInTheDocument();
    expect(within(rationale).queryByRole("region", { name: "Cited policies" })).not.toBeInTheDocument();
    const nextStep = screen.getByRole("region", { name: "Next step" });
    expect(within(nextStep).getByRole("link", { name: "View assessment" })).toHaveAttribute("href", "/assessments/chatmate?run=chatmate-1");
    const lifecycle = screen.getByText("Lifecycle timestamps");
    const metadata = screen.getByText("Evidence and evaluation metadata");
    const raw = screen.getByText("Raw audit");
    const ordered = [verdict, metrics, response, rationale, lifecycle, metadata, raw];
    ordered.slice(1).forEach((element, index) => expect(ordered[index].compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy());
    for (const summary of [lifecycle, metadata, raw]) {
      expect(summary.tagName).toBe("SUMMARY");
      expect(summary.closest("details")).not.toHaveAttribute("open");
      summary.focus();
      expect(summary).toHaveFocus();
      await user.click(summary);
      expect(summary.closest("details")).toHaveAttribute("open");
      await user.click(summary);
      expect(summary.closest("details")).not.toHaveAttribute("open");
    }
    expect(raw.closest("details")).toBe(screen.getByRole("article").lastElementChild);
    expect(screen.queryByText(/Operational failure|Native DeepTeam target evaluation/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to history" }));
    expect(close).toHaveBeenCalledOnce();
  });
  it.each(["COMPROMISED", "INCONCLUSIVE", "ERROR"] as const)("uses a concise %s verdict without placeholder confidence", async (final_status) => {
    const run = evaluatedRun({ final_status });
    vi.mocked(chatmateService.getRun).mockResolvedValue(run);
    vi.mocked(chatmateService.getAudit).mockResolvedValue(evaluatedAudit(run));
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled());
    expect(screen.getByRole("heading", { name: final_status === "COMPROMISED" ? "90/100 · Compromise-level deviation" : final_status === "ERROR" ? "Evaluation failed" : "Inconclusive" })).toBeInTheDocument();
    if (final_status !== "COMPROMISED") expect(screen.queryByText("Confidence", { selector: "dt" })).not.toBeInTheDocument();
  });
  it("styles loading and permits recovery after a report request fails", async () => {
    const user = userEvent.setup();
    vi.mocked(chatmateService.getRun).mockRejectedValueOnce(new Error("Temporarily unavailable"));
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveClass("chatmate-report-state");
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
    expect(await screen.findByRole("alert")).toHaveTextContent("Temporarily unavailable");
    await user.click(screen.getByRole("button", { name: "Retry report" }));
    expect(await screen.findByRole("heading", { name: "10/100 · Minor deviation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled();
  });
  it("loads authoritative history and selects the exact ChatMate report above history", async () => {
    const user = userEvent.setup();
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.mocked(chatmateService.listRuns).mockResolvedValue([
      evaluatedRun(), evaluatedRun({ run_id: "failed-eval", status: "FAILED", final_status: "ERROR", artifact_available: false }),
      evaluatedRun({ run_id: "generation-only", status: "FAILED", manual_evidence: null, evaluation_attempts: 0, candidate_batch: null }),
      evaluatedRun({ run_id: "rejected", status: "REJECTED" }), evaluatedRun({ run_id: "abandoned", status: "ABANDONED" }),
    ]);
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    const history = await screen.findByRole("region", { name: "Report history" });
    await waitFor(() => expect(within(history).getAllByRole("button", { name: /View report/ })).toHaveLength(3));
    expect(within(history).getByText("3", { selector: "strong" })).toBeInTheDocument();
    expect(within(history).getByText("Generation Failed")).toBeInTheDocument();
    expect(within(history).queryByText(/Manual assessment|Manual testing|ASSURANCE/i)).not.toBeInTheDocument();
    await user.click(within(history).getByRole("button", { name: /Run · 1/ }));
    const panel = await screen.findByRole("article", { name: "ChatMate report" });
    expect(await within(panel).findByText("Validated Judge rationale.")).toBeInTheDocument();
    expect(chatmateService.getRun).toHaveBeenCalledWith("chatmate-1");
    expect(panel.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(history).getByRole("button", { name: /Run · 1/ })).toHaveAttribute("aria-current", "true");
    expect(within(panel).getByText("Lifecycle timestamps").closest("details")).not.toHaveAttribute("open");
    expect(within(panel).queryByText("Legacy operator prompt time")).not.toBeInTheDocument();
  });
  it("does not substitute a valid history report for an invalid deep link", async () => {
    vi.mocked(chatmateService.getRun).mockRejectedValue(new Error("Run not found"));
    render(<MemoryRouter initialEntries={["/reports?chatmate=missing&id=RPT-SOCMATE-001"]}><ReportsPage /></MemoryRouter>);
    expect(await screen.findByText("Run not found")).toBeInTheDocument();
    expect(chatmateService.getRun).toHaveBeenCalledWith("missing");
    expect(chatmateService.getAudit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Delete report" })).not.toBeInTheDocument();
  });
  it("fails closed when the API returns a different run", async () => {
    render(<MemoryRouter initialEntries={["/reports?chatmate=other"]}><ReportsPage /></MemoryRouter>);
    expect(await screen.findByText("The requested run has no eligible evaluated report.")).toBeInTheDocument();
    expect(chatmateService.getAudit).not.toHaveBeenCalled();
  });
  it.each(["missing", "tampered"])("blocks disclosures and download for %s audit", async (kind) => {
    if (kind === "missing") vi.mocked(chatmateService.getAudit).mockRejectedValue(new Error("Audit not available"));
    else {
      const audit = evaluatedAudit(); audit.manifest.manual_correlation_sha256 = "tampered";
      vi.mocked(chatmateService.getAudit).mockResolvedValue(audit);
    }
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
    expect(screen.queryByText("Raw audit")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Boundary resisted" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Evaluation metrics")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Captured response" })).not.toBeInTheDocument();
    expect(screen.queryByText("Refused [REDACTED]")).not.toBeInTheDocument();
    expect(screen.queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
  });
  it("retains evaluated operational failure metadata when no artifact exists", async () => {
    vi.mocked(chatmateService.getRun).mockResolvedValue(evaluatedRun({ status: "FAILED", final_status: "ERROR", artifact_available: false, evaluation_attempts: 2 }));
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Evaluation failed" })).toBeInTheDocument();
    expect(screen.getByText("2", { selector: "dd" })).toBeInTheDocument();
    expect(chatmateService.getAudit).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
  });
  it("shows the backend failure reason even when the validated report artifact is unavailable", async () => {
    vi.mocked(chatmateService.getRun).mockResolvedValue(evaluatedRun({ status: "FAILED", final_status: "ERROR", artifact_available: false,
      error_code: "JUDGE_UNAVAILABLE", error_message: "The Judge provider rate limit was reached. Retry after 30 seconds." }));
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(await screen.findByText("The Judge provider rate limit was reached. Retry after 30 seconds.")).toBeInTheDocument();
    const diagnostic = screen.getByText("Error details").closest("details")!;
    expect(diagnostic).not.toHaveAttribute("open");
    expect(diagnostic).toHaveTextContent("JUDGE_UNAVAILABLE");
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
    expect(chatmateService.getAudit).not.toHaveBeenCalled();
  });
  it("downloads API-redacted JSON with no candidate batch or local draft", async () => {
    const user = userEvent.setup();
    const blobs: Blob[] = [];
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL(blob: Blob) { blobs.push(blob); return "blob:report"; }
      static revokeObjectURL = vi.fn();
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    window.localStorage.setItem("chatmate-draft", "SECRET LOCAL DRAFT");
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    const reader = new FileReader();
    const contents = await new Promise<string>((resolve) => { reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0]); });
    expect(contents).toContain("Refused [REDACTED]");
    expect(contents).not.toContain("SECRET LOCAL DRAFT");
    expect(contents).not.toContain("DO NOT EXPORT GENERATION SOURCE");
    expect(JSON.parse(contents).run).not.toHaveProperty("candidate_batch");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report");
  });
  it("clears previous audit immediately when switching run ID", async () => {
    const view = render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(await screen.findByText("Validated Judge rationale.")).toBeInTheDocument();
    vi.mocked(chatmateService.getRun).mockRejectedValue(new Error("Other missing"));
    view.rerender(<ChatMateReportPanel runId="other" onClose={vi.fn()} />);
    expect(screen.queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
    expect(await screen.findByText("Other missing")).toBeInTheDocument();
  });
  it("ignores a late audit from the previously selected report", async () => {
    let resolveAudit!: (audit: ReturnType<typeof evaluatedAudit>) => void;
    vi.mocked(chatmateService.getAudit).mockImplementationOnce(() => new Promise((resolve) => { resolveAudit = resolve; }));
    const view = render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    await waitFor(() => expect(chatmateService.getAudit).toHaveBeenCalledWith("chatmate-1"));
    vi.mocked(chatmateService.getRun).mockRejectedValue(new Error("New report missing"));
    view.rerender(<ChatMateReportPanel runId="other" onClose={vi.fn()} />);
    expect(await screen.findByText("New report missing")).toBeInTheDocument();
    resolveAudit(evaluatedAudit());
    await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled());
    expect(screen.queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
  });
  it("shows legacy operator times only when supplied by the API", async () => {
    const run = evaluatedRun();
    run.manual_evidence = { ...run.manual_evidence!, prompt_sent_at: "2026-10-08T12:02:30Z", response_observed_at: "2026-10-08T12:02:40Z" };
    vi.mocked(chatmateService.getRun).mockResolvedValue(run);
    vi.mocked(chatmateService.getAudit).mockResolvedValue(evaluatedAudit(run));
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(await screen.findByText("Legacy operator prompt time")).toBeInTheDocument();
    expect(screen.getAllByText(chatMateDate("2026-10-08T12:02:30Z"), { selector: "dd" }).length).toBeGreaterThan(0);
    expect(screen.queryByText("2026-10-08T12:02:30Z", { selector: "dd" })).not.toBeInTheDocument();
    expect(screen.getByText("Legacy operator observation time")).toBeInTheDocument();
  });
  it("discloses visible failure without inventing semantic Judge results", async () => {
    const run = evaluatedRun({ final_status: "INCONCLUSIVE" });
    run.manual_evidence = { ...run.manual_evidence!, outcome: "VISIBLE_FAILURE", redacted_response_text: null,
      failure_reason: "RESPONSE_COULD_NOT_BE_COMPLETED", persisted_response_sha256: null, judge_data_collection_attested: false };
    vi.mocked(chatmateService.getRun).mockResolvedValue(run);
    vi.mocked(chatmateService.getAudit).mockResolvedValue(evaluatedAudit(run));
    render(<ChatMateReportPanel runId="chatmate-1" onClose={vi.fn()} />);
    expect(await screen.findByText("Response could not be completed.")).toBeInTheDocument();
    expect(screen.getByText("No Judge evaluation was produced for this observation.")).toBeInTheDocument();
    expect(screen.getByText(/this observation has no semantic Judge evaluation/)).toBeInTheDocument();
    expect(screen.queryByText(/Expand Critic Review below/)).not.toBeInTheDocument();
    expect(screen.queryByText("Confidence", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.queryByText("Judge score", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled();
  });
  it("shows API history errors independently and retries", async () => {
    const user = userEvent.setup();
    vi.mocked(chatmateService.listRuns).mockRejectedValueOnce(new Error("History offline"));
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    expect(await screen.findByText(/ChatMate history unavailable: History offline/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry ChatMate history" }));
    expect(await screen.findByRole("button", { name: /Run · 1/ })).toBeInTheDocument();
  });
});

describe("ChatMate Findings read-only source semantics", () => {
  beforeEach(() => { vi.spyOn(platformService, "listFindings").mockResolvedValue([]); });
  it("classifies compact source rows, excludes pending runs and resisted outcomes from open count, and loads audit only on detail", async () => {
    const user = userEvent.setup();
    const compromised = evaluatedRun({ final_status: "COMPROMISED" });
    vi.mocked(chatmateService.listRuns).mockResolvedValue([
      compromised, evaluatedRun({ run_id: "resisted-result" }), evaluatedRun({ run_id: "inconclusive", final_status: "INCONCLUSIVE" }),
      evaluatedRun({ run_id: "operational", status: "FAILED", final_status: "ERROR" }),
      evaluatedRun({ run_id: "pending", status: "EVALUATING" }), evaluatedRun({ run_id: "rejected", status: "REJECTED" }),
    ]);
    vi.mocked(chatmateService.getRun).mockResolvedValue(compromised);
    vi.mocked(chatmateService.getAudit).mockResolvedValue(evaluatedAudit(compromised));
    const status = vi.spyOn(platformService, "updateFindingStatus");
    const regression = vi.spyOn(platformService, "toggleRegression");
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    const source = await screen.findByRole("region", { name: "ChatMate results" });
    expect(await within(source).findByText("1 policy violations · 1 boundary resisted")).toBeInTheDocument();
    expect(within(source).queryByText("CRITICAL")).not.toBeInTheDocument();
    expect(within(source).queryByText("HIGH")).not.toBeInTheDocument();
    expect(within(source).queryByText("MEDIUM")).not.toBeInTheDocument();
    const table = within(source).getByRole("table", { name: "ChatMate results" });
    expect(table.closest(".records-table")).toBeTruthy();
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    const resistedRow = within(table).getByText("Boundary resisted").closest("tr")!;
    expect(within(resistedRow).getByText("Completed")).toBeInTheDocument();
    expect(within(resistedRow).getAllByRole("cell")[0]).toHaveTextContent("ChatMate");
    expect(resistedRow.querySelector(".severity-chip")).toBeNull();
    expect(source.querySelector(".evidence-grid")).toBeNull();
    expect(source.querySelector(".chatmate-method-badge")).toBeNull();
    expect(screen.queryByText(/Manual assessment|Manual testing|ASSURANCE/i)).not.toBeInTheDocument();
    expect(screen.getByText("1 Findings · 3 completed results")).toBeInTheDocument();
    expect(screen.queryByText(/No live assessment selected|No persisted product findings|No findings or results yet/i)).not.toBeInTheDocument();
    expect(within(source).queryByText(/pending/)).not.toBeInTheDocument();
    expect(chatmateService.getAudit).not.toHaveBeenCalled();
    await user.click(within(source).getByRole("button", { name: "View details Run · 1" }));
    const detail = within(source).getByRole("article", { name: "ChatMate source finding detail" });
    expect(await within(detail).findByText("Judge-reported confidence: 93%")).toBeInTheDocument();
    expect(within(detail).getByText("Validated Judge rationale.")).toBeInTheDocument();
    expect(within(detail).getByRole("link", { name: "View report" })).toHaveAttribute("href", "/reports?chatmate=chatmate-1");
    await user.click(within(detail).getByRole("button", { name: "Close details" }));
    expect(within(source).queryByRole("article", { name: "ChatMate source finding detail" })).not.toBeInTheDocument();
    expect(within(source).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(source).queryByRole("button", { name: /Pin|Unpin|Resolve|Triage|Retest|remediation/i })).not.toBeInTheDocument();
    expect(status).not.toHaveBeenCalled(); expect(regression).not.toHaveBeenCalled();
  });
  it("keeps unscored ChatMate outcomes independent of severity filters", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    const source = await screen.findByRole("region", { name: "ChatMate results" });
    expect(await within(source).findByText("Boundary resisted")).toBeInTheDocument();
    expect(screen.getByText("0 Findings · 1 completed result")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "CRITICAL" }));
    expect(within(source).getByText("Boundary resisted")).toBeInTheDocument();
    expect(screen.getByText("0 Findings · 1 completed result")).toBeInTheDocument();
    expect(within(source).queryByText("No ChatMate results in this severity.")).not.toBeInTheDocument();
  });
  it("withholds confidence and rationale when detail audit is invalid", async () => {
    const user = userEvent.setup();
    vi.mocked(chatmateService.getAudit).mockRejectedValue(new Error("Audit integrity failed"));
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: "View details Run · 1" }));
    const detail = await screen.findByRole("article", { name: "ChatMate source finding detail" });
    expect(await within(detail).findByText("Audit integrity failed")).toBeInTheDocument();
    expect(within(detail).queryByText(/Confidence:/)).not.toBeInTheDocument();
    expect(within(detail).queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
    expect(within(detail).getByRole("link")).toHaveAttribute("href", "/reports?chatmate=chatmate-1");
  });
  it("includes persisted findings and open ChatMate rows in the filtered header", async () => {
    const user = userEvent.setup();
    vi.mocked(platformService.listFindings).mockResolvedValue([{
      id: "finding-1", assessmentId: "assessment-1", targetId: "socmate", targetName: "SOCMate", title: "Tool boundary violation",
      severity: "HIGH", status: "OPEN", confidence: .95, expectedBehavior: "Approval required", observedBehavior: "Approval bypassed",
      evidence: "Captured tool call", toolAttempt: "isolate_host", oracleResult: "DENY", judgeRationale: "Approval missing",
      standards: [], remediation: "Enforce approval", regressionPinned: false, createdAt: "2026-10-08T12:00:00Z",
    }]);
    vi.mocked(chatmateService.listRuns).mockResolvedValue([
      evaluatedRun({ final_status: "COMPROMISED" }), evaluatedRun({ run_id: "resisted-result" }),
    ]);
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    expect(await screen.findByText("2 Findings · 1 completed result")).toBeInTheDocument();
    const resultTable = screen.getByRole("table", { name: "ChatMate results" });
    const mainFinding = screen.getByRole("button", { name: /Tool boundary violation/ });
    expect(mainFinding.compareDocumentPosition(resultTable) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "CRITICAL" }));
    expect(screen.getByText("1 Findings · 1 completed result")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tool boundary violation/ })).not.toBeInTheDocument();
    expect(within(resultTable).getByText("Boundary resisted")).toBeInTheDocument();
    expect(within(resultTable).getByText("Policy violation detected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "HIGH" }));
    expect(screen.getByText("2 Findings · 1 completed result")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tool boundary violation/ })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "ChatMate results" })).toBeInTheDocument();
  });
  it("shows one true empty state only after both result sources finish loading", async () => {
    let resolve!: (runs: []) => void;
    vi.mocked(chatmateService.listRuns).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    expect(await screen.findByText("Loading ChatMate results...")).toBeInTheDocument();
    expect(screen.queryByText("No findings or results yet")).not.toBeInTheDocument();
    resolve([]);
    expect(await screen.findByText("No findings or results yet")).toBeInTheDocument();
    expect(screen.getAllByText("No findings or results yet")).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "ChatMate results" })).not.toBeInTheDocument();
    expect(screen.queryByText(/No live assessment selected|No persisted product findings/)).not.toBeInTheDocument();
  });
  it("retains the live findings panel for an actual selected DeepTeam run", async () => {
    window.localStorage.setItem("secmate.activeDeepteamRun", "active-worker-run");
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValue(new Error("Selected worker unavailable"));
    vi.mocked(chatmateService.listRuns).mockResolvedValue([]);
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    expect(await screen.findByText("Selected worker unavailable")).toBeInTheDocument();
    expect(modelConnectivityService.getDeepTeamRun).toHaveBeenCalledWith("active-worker-run");
    expect(screen.queryByText("No findings or results yet")).not.toBeInTheDocument();
  });
  it("shows a history error and retry without claiming there are no results", async () => {
    const user = userEvent.setup();
    vi.mocked(chatmateService.listRuns).mockRejectedValueOnce(new Error("History offline"));
    render(<MemoryRouter><FindingsPage /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("History offline");
    expect(screen.queryByText("No findings or results yet")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry ChatMate history" }));
    expect(await screen.findByText("Boundary resisted")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
