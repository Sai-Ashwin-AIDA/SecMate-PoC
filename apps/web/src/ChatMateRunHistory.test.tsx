import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMatePage } from "./ChatMatePage";
import { chatmateService } from "./chatmateService";
import type { ChatMateRunStatus } from "./chatmateService";
import { chatMateDate } from "./chatmateDisplay";
import { evaluatedRun } from "./chatmateTestFixtures";

const saved = evaluatedRun({ run_id: "chatmate-b93db5-long-reference", status: "AWAITING_RESPONSE", manual_evidence: null,
  evaluation_attempts: 0, artifact_available: false, final_status: null, attack_method: "prompt_injection" });

function page(path = "/assessments/chatmate") {
  return render(<MemoryRouter initialEntries={[path]}><ChatMatePage /></MemoryRouter>);
}

beforeEach(() => {
  window.localStorage.removeItem("secmate.currentAssessment.v1");
  vi.spyOn(chatmateService, "listRuns").mockResolvedValue([saved]);
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(saved);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("ChatMate Configure history", () => {
  it("identifies follow-up drafts by objective and parent before configuring them", async () => {
    const user = userEvent.setup();
    const draft = { ...saved, status: "DRAFT" as const, parent_run_id: "chatmate-parent-7",
      follow_up_objective: "Test delegated authority without changing the original boundary." };
    vi.mocked(chatmateService.listRuns).mockResolvedValue([draft]);
    vi.mocked(chatmateService.getRun).mockResolvedValue(draft);
    page();
    await user.click(screen.getByRole("button", { name: /Run history/ }));
    expect(await screen.findByText("Follow-up draft")).toBeVisible();
    expect(screen.getByText(draft.follow_up_objective)).toBeVisible();
    await user.click(screen.getByText("View details"));
    expect(screen.getByRole("link", { name: "Run · parent" })).toHaveAttribute("href", "/assessments/chatmate?run=chatmate-parent-7");
    await user.click(screen.getByRole("link", { name: /Configure follow-up Prompt Injection/ }));
    await screen.findByRole("heading", { name: "Choose an attack method" });
    expect(screen.getByRole("button", { name: /Prompt Injection/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate 2 attacks" })).toBeEnabled();
  });
  it("combines date and outcome filters while keeping newest runs first", async () => {
    const user = userEvent.setup();
    const now = Date.parse("2026-10-12T12:00:00Z");
    vi.spyOn(Date, "now").mockReturnValue(now);
    vi.mocked(chatmateService.listRuns).mockResolvedValue([
      evaluatedRun({ run_id: "chatmate-run-old", created_at: "2026-09-01T12:00:00Z", final_status: "COMPROMISED" }),
      evaluatedRun({ run_id: "chatmate-run-new", created_at: "2026-10-12T10:00:00Z", final_status: "RESISTED" }),
      evaluatedRun({ run_id: "chatmate-run-recent", created_at: "2026-10-10T12:00:00Z", final_status: "COMPROMISED" }),
    ]);
    page();
    await user.click(screen.getByRole("button", { name: /Run history/ }));
    expect(await screen.findByText("3 of 3 runs")).toBeInTheDocument();
    const history = screen.getByRole("region", { name: "ChatMate run history" });
    expect(within(history).getAllByRole("article")[0]).toHaveTextContent("Run · new");
    await user.selectOptions(within(history).getByLabelText("Date"), "7");
    expect(within(history).getByText("2 of 3 runs")).toBeInTheDocument();
    await user.selectOptions(within(history).getByLabelText("Outcome"), "COMPROMISED");
    expect(within(history).getByText("1 of 3 runs")).toBeInTheDocument();
    expect(within(history).getByRole("article")).toHaveTextContent("Run · recent");
    await user.selectOptions(within(history).getByLabelText("Date"), "1");
    expect(within(history).getByText("No runs match these filters.")).toBeInTheDocument();
    expect(within(history).queryByRole("article")).not.toBeInTheDocument();
  });

  it("is collapsed at the bottom, with friendly titles, references, dates and styled actions", async () => {
    const user = userEvent.setup();
    page();
    const history = screen.getByRole("region", { name: "ChatMate run history" });
    const toggle = within(history).getByRole("button", { name: /Run history/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(history).queryByRole("link")).not.toBeInTheDocument();
    expect(history).toBe(history.parentElement?.lastElementChild);
    expect(screen.getByRole("heading", { name: "Choose an attack method" }).compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const resume = await within(history).findByRole("link", { name: "Resume assessment Prompt Injection Run · b93db5" });
    expect(resume).toHaveTextContent("Resume assessment");
    expect(resume).toHaveAttribute("href", `/assessments/chatmate?run=${saved.run_id}`);
    expect(resume).toHaveClass("secondary-action");
    expect(within(history).getByText("Prompt Injection")).toBeInTheDocument();
    expect(within(history).getByText("Run · b93db5")).toBeInTheDocument();
    expect(within(history).getByText("Awaiting response")).toHaveClass("chatmate-status-badge");
    expect(within(history).getByText(chatMateDate(saved.created_at))).toBeInTheDocument();
    expect(within(history).queryByText(saved.created_at)).not.toBeInTheDocument();
    expect(within(history).queryByText("prompt_injection")).not.toBeInTheDocument();
    expect(within(history).getByText(saved.run_id).closest("details")).not.toHaveAttribute("open");
    await user.click(within(history).getByText("View details"));
    expect(within(history).getByText(saved.run_id).closest("details")).toHaveAttribute("open");
    await user.click(toggle);
    expect(within(history).queryByRole("link")).not.toBeInTheDocument();
  });

  it.each<ChatMateRunStatus>(["QUEUED", "GENERATING", "AWAITING_SELECTION", "AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING", "COMPLETED", "FAILED", "REJECTED", "ABANDONED"])("does not show or fetch Configure history on a %s run page", async (status) => {
    vi.mocked(chatmateService.getRun).mockResolvedValue({ ...saved, status });
    page(`/assessments/chatmate?run=${saved.run_id}`);
    await waitFor(() => expect(screen.getByRole("heading", { name: "ChatMate" })).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: "ChatMate run history" })).not.toBeInTheDocument();
    expect(chatmateService.listRuns).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Return to new assessment" })).toBeEnabled();
  });

  it.each(["?run=missing", "?run="])("does not offer Configure history for a missing explicit selection %s", async (query) => {
    vi.mocked(chatmateService.getRun).mockRejectedValue(new Error("Run not found"));
    page(`/assessments/chatmate${query}`);
    expect(await screen.findByRole("heading", { name: "ChatMate run could not be restored" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "ChatMate run history" })).not.toBeInTheDocument();
    expect(chatmateService.listRuns).not.toHaveBeenCalled();
  });

  it("distinguishes generation failure and evaluation failure history badges", async () => {
    vi.mocked(chatmateService.listRuns).mockResolvedValue([
      { ...saved, status: "FAILED", error_code: "GENERATION_ERROR" },
      evaluatedRun({ run_id: "evaluation-error", status: "FAILED", final_status: "ERROR" }),
      evaluatedRun({ run_id: "completed-error", status: "COMPLETED", final_status: "ERROR" }),
    ]);
    page();
    await userEvent.setup().click(screen.getByRole("button", { name: /Run history/ }));
    expect(await screen.findByText("Generation Failed")).toHaveClass("failed");
    expect(screen.getAllByText("Evaluation failed")).toHaveLength(2);
    screen.getAllByText("Evaluation failed").forEach((badge) => expect(badge).toHaveClass("failed"));
  });

  it("labels terminal history links as View assessment with the exact recovery URL", async () => {
    vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun()]);
    page();
    await userEvent.setup().click(screen.getByRole("button", { name: /Run history/ }));
    const link = await screen.findByRole("link", { name: "View assessment Prompt Injection Run · 1" });
    expect(link).toHaveTextContent("View assessment");
    expect(link).toHaveAttribute("href", "/assessments/chatmate?run=chatmate-1");
  });

  it("requires styled confirmation, supports cancel, handles empty 204 and refreshes authoritative history", async () => {
    const user = userEvent.setup();
    const json = vi.fn(async () => { throw new Error("Empty response"); });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 204, json }) as unknown as Response));
    vi.mocked(chatmateService.listRuns).mockResolvedValueOnce([saved]).mockResolvedValueOnce([]);
    page();
    await user.click(screen.getByRole("button", { name: /Run history/ }));
    await user.click(await screen.findByRole("button", { name: "Delete Prompt Injection Run · b93db5" }));
    const confirmation = screen.getByRole("group", { name: "Delete this run?" });
    expect(confirmation).toHaveClass("chatmate-confirmation");
    expect(within(confirmation).getByRole("button", { name: "Confirm delete run" })).toHaveClass("danger-action");
    expect(within(confirmation).getByRole("button", { name: "Cancel delete" })).toHaveClass("secondary-action");
    expect(fetch).not.toHaveBeenCalled();
    await user.click(within(confirmation).getByRole("button", { name: "Cancel delete" }));
    expect(screen.queryByRole("group", { name: "Delete this run?" })).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete Prompt Injection Run · b93db5" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete run" }));
    expect(await screen.findByText("Run deleted.")).toBeInTheDocument();
    await waitFor(() => expect(chatmateService.listRuns).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No previous runs found.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Resume assessment Prompt Injection/ })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining(`/chatmate-runs/${saved.run_id}`), expect.objectContaining({
      method: "DELETE", headers: expect.objectContaining({ "X-SecMate-Local-Run": "confirmed" }),
    }));
    expect(json).not.toHaveBeenCalled();
  });

  it("allows requesting an active-run delete and retains the entry with the 409 explanation", async () => {
    const active = { ...saved, status: "GENERATING" as const };
    const user = userEvent.setup();
    vi.mocked(chatmateService.listRuns).mockResolvedValue([active]);
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409,
      json: async () => ({ detail: "Run is active. Wait for generation to finish, then end the run before deleting." }),
    }) as Response));
    page();
    await user.click(screen.getByRole("button", { name: /Run history/ }));
    await user.click(await screen.findByRole("button", { name: "Delete Prompt Injection Run · b93db5" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wait for generation to finish, then end the run before deleting.");
    expect(screen.getByRole("link", { name: /Resume assessment Prompt Injection/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm delete run" })).toBeEnabled();
    expect(chatmateService.listRuns).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Run deleted.")).not.toBeInTheDocument();
  });

  it("reports a failed refresh after successful deletion without restoring the deleted row", async () => {
    const user = userEvent.setup();
    vi.spyOn(chatmateService, "deleteRun").mockResolvedValue(undefined);
    vi.mocked(chatmateService.listRuns).mockResolvedValueOnce([saved]).mockRejectedValueOnce(new Error("History offline"));
    page();
    await user.click(screen.getByRole("button", { name: /Run history/ }));
    await user.click(await screen.findByRole("button", { name: "Delete Prompt Injection Run · b93db5" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("History offline");
    expect(screen.getByText("Run deleted.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Resume assessment Prompt Injection/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry history" })).toHaveClass("secondary-action");
  });
});
