import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FindingsPage, ReportsPage } from "./ModulePages";
import { chatmateService } from "./chatmateService";
import { platformService } from "./platformService";
import { modelConnectivityService } from "./modelConnectivityService";
import { evaluatedAudit, evaluatedRun } from "./chatmateTestFixtures";

function Location() { return <output aria-label="Current query">{useLocation().search}</output>; }
function page(Page: typeof ReportsPage, route = "/reports") {
  return render(<MemoryRouter initialEntries={[route]}><Page /><Location /></MemoryRouter>);
}
beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(platformService, "listReports").mockResolvedValue([]);
  vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
  vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
  vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(evaluatedRun());
  vi.spyOn(chatmateService, "getAudit").mockResolvedValue(evaluatedAudit());
});
afterEach(() => vi.restoreAllMocks());

it("shows only the history empty state with no redundant preview panel", async () => {
  page(ReportsPage);
  expect(await screen.findByText("No reports yet.")).toBeInTheDocument();
  expect(screen.getAllByText(/No reports yet/)).toHaveLength(1);
  expect(screen.queryByText("Complete an assessment to create your first report.")).not.toBeInTheDocument();
  expect(document.querySelector(".report-detail")).toBeNull();
});

it("confirms API source deletion, preserves another preview and filters, and prunes report selections", async () => {
  const user = userEvent.setup();
  const other = evaluatedRun({ run_id: "other" });
  vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun(), other]);
  vi.mocked(chatmateService.getRun).mockImplementation(async (id) => id === "other" ? other : evaluatedRun());
  vi.mocked(chatmateService.getAudit).mockImplementation(async (id) => evaluatedAudit(id === "other" ? other : evaluatedRun()));
  const remove = vi.spyOn(chatmateService, "deleteRun").mockResolvedValue();
  page(ReportsPage, "/reports?chatmate=other");
  await user.click(await screen.findByRole("checkbox", { name: "Select ChatMate chatmate-1" }));
  await user.click(screen.getByRole("checkbox", { name: "Select ChatMate other" }));
  await user.selectOptions(screen.getByLabelText("Source"), "chatmate");
  await user.click(screen.getByRole("button", { name: "Delete source run chatmate-1" }));
  expect(screen.getByRole("dialog")).toHaveTextContent(/Permanently delete.*saved evidence/);
  await user.click(screen.getByRole("button", { name: "Cancel removal" }));
  expect(remove).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Delete source run chatmate-1" }));
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(remove).toHaveBeenCalledExactlyOnceWith("chatmate-1");
  // Even an eventually consistent history response must not resurrect deletion.
  expect(screen.queryByRole("checkbox", { name: "Select ChatMate chatmate-1" })).not.toBeInTheDocument();
  expect(screen.getByText("1 selected")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create report" })).toBeEnabled();
  expect(screen.getByLabelText("Current query")).toHaveTextContent("?chatmate=other");
  expect(screen.getByLabelText("Source")).toHaveValue("chatmate");
});

it("retains the source, selection and retry confirmation on API rejection", async () => {
  const user = userEvent.setup();
  vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun()]);
  const remove = vi.spyOn(chatmateService, "deleteRun").mockRejectedValue(new Error("Unresolved durable worker"));
  page(ReportsPage);
  await user.click(await screen.findByRole("checkbox", { name: "Select ChatMate chatmate-1" }));
  await user.click(screen.getByRole("button", { name: "Delete source run chatmate-1" }));
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unresolved durable worker");
  expect(screen.getByRole("checkbox")).toBeChecked();
  expect(screen.getByRole("button", { name: "Confirm removal" })).toBeEnabled();
  expect(remove).toHaveBeenCalledOnce();
});

it("deletes a generation-failed report using its actual run ID, not the display key", async () => {
  const user = userEvent.setup();
  const id = "chatmate-run-15d22b13bd71";
  const failed = evaluatedRun({ run_id: id, status: "FAILED", final_status: null,
    candidate_batch: null, manual_evidence: null, evaluation_attempts: 0,
    artifact_available: false, error_code: "GENERATION_PROCESS_EXIT" });
  vi.mocked(chatmateService.listRuns).mockResolvedValue([failed]);
  vi.mocked(chatmateService.getRun).mockImplementation(async runId => {
    if (runId !== id) throw new Error("ChatMate run not found.");
    return failed;
  });
  const remove = vi.spyOn(chatmateService, "deleteRun").mockResolvedValue();
  page(ReportsPage);
  await user.click(await screen.findByRole("button", { name: `Delete source run ${id}` }));
  expect(screen.getByRole("dialog")).not.toHaveTextContent(`chatmate-${id}`);
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(remove).toHaveBeenCalledExactlyOnceWith(id);
  expect(screen.queryByRole("button", { name: `Delete source run ${id}` })).not.toBeInTheDocument();
});

it("rechecks active state before issuing DELETE and disables known running Critic deletion", async () => {
  const user = userEvent.setup();
  vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun(), evaluatedRun({ run_id: "critic", critic_status: "RUNNING" })]);
  vi.mocked(chatmateService.getRun).mockResolvedValue(evaluatedRun({ status: "EVALUATING" }));
  const remove = vi.spyOn(chatmateService, "deleteRun");
  page(ReportsPage);
  expect(await screen.findByRole("button", { name: "Delete source run critic" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Delete source run chatmate-1" }));
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This run is active");
  expect(remove).not.toHaveBeenCalled();
});

it("locks confirmation while deletion is pending and clears only the deleted preview", async () => {
  const user = userEvent.setup();
  vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun()]);
  let resolve!: () => void;
  const remove = vi.spyOn(chatmateService, "deleteRun").mockImplementation(() => new Promise<void>((done) => { resolve = done; }));
  page(ReportsPage, "/reports?chatmate=chatmate-1&keep=1");
  await user.click(await screen.findByRole("button", { name: "Delete source run chatmate-1" }));
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Working..." })).toBeDisabled());
  expect(screen.getByRole("button", { name: "Cancel removal" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await act(async () => resolve());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByRole("article", { name: "ChatMate report" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Current query")).toHaveTextContent("?keep=1");
  expect(remove).toHaveBeenCalledOnce();
});

it("removes only a browser SocMate reference and retains server evidence", async () => {
  const user = userEvent.setup();
  window.localStorage.setItem("secmate.deepteamRunHistory", '["saved"]');
  vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValue(new Error("Offline"));
  const remove = vi.spyOn(chatmateService, "deleteRun");
  page(ReportsPage);
  await user.click(await screen.findByRole("button", { name: "Remove report saved" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("API source run and its original evidence are retained");
  await user.click(screen.getByRole("button", { name: "Confirm removal" }));
  expect(await screen.findByText("No reports yet.")).toBeInTheDocument();
  expect(window.localStorage.getItem("secmate.deepteamRunHistory")).toBe("[]");
  expect(remove).not.toHaveBeenCalled();
});

it("opens URL-selected findings inline, supports keyboard toggle and returns focus on close", async () => {
  const user = userEvent.setup();
  vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun(), evaluatedRun({ run_id: "other" })]);
  page(FindingsPage, "/findings?chatmate=chatmate-1&keep=1");
  const trigger = await screen.findByRole("button", { name: "View details Run · 1" });
  const detail = await screen.findByText("Validated Judge rationale.");
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(detail.closest("tr")).toBe(trigger.closest("tr")!.nextElementSibling);
  expect(document.getElementById(trigger.getAttribute("aria-controls")!)).toContainElement(detail);
  await user.click(screen.getByRole("button", { name: "Close details" }));
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.getByLabelText("Current query")).toHaveTextContent("?keep=1");
  await user.keyboard("{Enter}");
  expect(await screen.findByText("Validated Judge rationale.")).toBeInTheDocument();
  await user.keyboard(" ");
  expect(screen.queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("button", { name: "CRITICAL" }));
  expect(await screen.findByText("Validated Judge rationale.")).toBeInTheDocument();
});

it("does not disclose a late audit under a newly selected findings run", async () => {
  const user = userEvent.setup();
  const other = evaluatedRun({ run_id: "other" });
  vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun(), other]);
  vi.mocked(chatmateService.getRun).mockImplementation(async (id) => id === "other" ? other : evaluatedRun());
  let resolve!: (audit: ReturnType<typeof evaluatedAudit>) => void;
  vi.mocked(chatmateService.getAudit).mockImplementationOnce(() => new Promise((done) => { resolve = done; })).mockRejectedValue(new Error("Other audit unavailable"));
  page(FindingsPage);
  await user.click(await screen.findByRole("button", { name: "View details Run · 1" }));
  await waitFor(() => expect(chatmateService.getAudit).toHaveBeenCalledWith("chatmate-1"));
  await user.click(screen.getByRole("button", { name: "View details Run · other" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Other audit unavailable");
  await act(async () => resolve(evaluatedAudit()));
  expect(screen.queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
  expect(within(screen.getByRole("article", { name: "ChatMate source finding detail" })).getByRole("link")).toHaveAttribute("href", "/reports?chatmate=other");
});

it("offers recovery for an unavailable findings deep link without loading another source", async () => {
  const user = userEvent.setup();
  page(FindingsPage, "/findings?chatmate=missing&keep=1");
  expect(await screen.findByText(/ChatMate result unavailable/)).toBeInTheDocument();
  expect(chatmateService.getRun).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Clear selection" }));
  expect(screen.getByLabelText("Current query")).toHaveTextContent("?keep=1");
});
