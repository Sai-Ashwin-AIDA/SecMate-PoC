import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssessmentsPage, ReportsPage } from "./ModulePages";
import { platformService } from "./platformService";
import { modelConnectivityService } from "./modelConnectivityService";
import { chatmateService } from "./chatmateService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";

describe("ReportsPage deep links", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it("does not substitute another report for an invalid report ID", async () => {
    render(<MemoryRouter initialEntries={["/reports?id=missing-report"]}><ReportsPage /></MemoryRouter>);
    expect(await screen.findByText("Report not found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export JSON" })).not.toBeInTheDocument();
  });

  it("shows the selected report full width before report history", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("secmate.activeDeepteamRun", "run-live-report");
    window.localStorage.setItem("secmate.deepteamRunHistory", JSON.stringify(["run-live-report"]));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.endsWith("/audit") ? {
        run_id: "run-live-report",
        manifest: {},
        deepteam_risk: {},
        summary: { final_status: "RESISTED", budget: {}, model_attempts: [] },
        evidence: { paths: [], review_results: [] },
      } : {
        run_id: "run-live-report",
        status: "COMPLETED",
        created_at: "2026-10-01T08:00:00Z",
        started_at: "2026-10-01T08:00:01Z",
        completed_at: "2026-10-01T08:01:00Z",
        scenario: "socmate-tier1-permission-escalation",
        vulnerability: "Bias:religion",
        attack: "Bad Likert Judge",
        vulnerability_profile_id: "Bias:religion",
        attack_profile_id: "bad-likert-judge-v1",
        max_total_tokens: 75000,
        final_status: "RESISTED",
        artifact_available: true,
        logs: [],
        error_code: null,
        error_message: null,
      };
      return { ok: true, status: 200, json: async () => body } as Response;
    }));

    render(<MemoryRouter initialEntries={["/reports"]}><ReportsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: /Bad Likert Judge/ }));
    const resultsHeading = await screen.findByRole("heading", { name: "Assessment results" });
    const historyHeading = screen.getByRole("heading", { name: "Report history" });
    expect(resultsHeading.compareDocumentPosition(historyHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("button", { name: /Bad Likert Judge/ })).toHaveAttribute("aria-current", "true");
    await user.click(screen.getByRole("button", { name: "Back to history" }));
    expect(screen.queryByRole("heading", { name: "Assessment results" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Report history" })).toBeInTheDocument();
  });

  it("deletes a generated browser report", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/reports?id=RPT-SOCMATE-001"]}><ReportsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: "Delete report" }));
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(await screen.findByRole("heading", { name: "Report history" })).toBeInTheDocument();
  });

  it("allows an unavailable saved live report to be removed", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("secmate.activeDeepteamRun", "missing-live-run");
    window.localStorage.setItem("secmate.deepteamRunHistory", JSON.stringify(["missing-live-run"]));
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ detail: "DeepTeam run not found." }) }) as Response));

    render(<MemoryRouter initialEntries={["/reports?live=missing-live-run"]}><ReportsPage /></MemoryRouter>);

    expect(await screen.findByText("Live assessment results unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove unavailable report" }));
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(screen.queryByText("Live assessment results unavailable")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("secmate.deepteamRunHistory")).toBe("[]");
  });

  it("makes unavailable saved references selectable for retry or removal instead of phantom counts", async () => {
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValue(new Error("Missing saved run"));
    window.localStorage.setItem("secmate.deepteamRunHistory", JSON.stringify(["missing-reference"]));
    const user = userEvent.setup();
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    const row = await screen.findByRole("group", { name: "Unavailable saved assessment missing-reference" });
    expect(within(row).getByRole("button", { name: "Retry saved assessment" })).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Remove saved reference" }));
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(screen.queryByText("Saved assessment unavailable")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("secmate.deepteamRunHistory")).toBe("[]");
  });

  it("refreshes active report history through completion without remounting", async () => {
    vi.useFakeTimers();
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    const run = { run_id: "history-run", status: "RUNNING", created_at: "2026-10-13T12:00:00Z", completed_at: null,
      attack: "Permission Escalation", vulnerability: "ExcessiveAgency:permissions", final_status: null } as DeepTeamRunRecord;
    const getRun = vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValueOnce(run)
      .mockResolvedValue({ ...run, status: "COMPLETED", final_status: "RESISTED", completed_at: "2026-10-13T12:01:00Z" });
    window.localStorage.setItem("secmate.deepteamRunHistory", JSON.stringify([run.run_id]));
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("button", { name: /Permission Escalation/ })).toHaveTextContent(/progress|running/i);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(screen.getByRole("button", { name: /Permission Escalation/ })).toHaveTextContent("No policy violation found");
    expect(getRun).toHaveBeenCalledTimes(2);
  });

  it("renders live assessment configuration in Assessments", async () => {
    render(<MemoryRouter><AssessmentsPage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Set up assessment" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Configure live assessment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New Assessment" })).not.toBeInTheDocument();
  });

  it.each([
    ["Assessments", AssessmentsPage, "listAssessments"],
    ["Reports", ReportsPage, "listReports"],
  ] as const)("does not keep polling an inactive %s page", async (_label, Page, method) => {
    vi.useFakeTimers();
    const spy = vi.spyOn(platformService, method);
    const view = render(<MemoryRouter><Page /></MemoryRouter>);
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    const callsAfterLoad = spy.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(spy).toHaveBeenCalledTimes(callsAfterLoad);
    expect(screen.queryByText("Refreshing...")).not.toBeInTheDocument();
    view.unmount();
  });
});
