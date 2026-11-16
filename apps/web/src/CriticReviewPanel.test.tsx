import { webcrypto } from "node:crypto";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CriticReviewPanel } from "./CriticReviewPanel";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { chatmateService } from "./chatmateService";
import { criticAudit, criticReview, criticRun, followUpDraft, savedCriticRun } from "./chatmateCriticFixtures";
import type { ChatMateRunRecord } from "./chatmateService";
import { offlineChatMateContractFixture } from "./chatmateOfflineContractFixture";

function Location() { const location = useLocation(); return <output aria-label="Current route">{location.pathname}{location.search}</output>; }
function panel(run = criticRun()) {
  return render(<MemoryRouter><Location /><CriticReviewPanel run={run} audit={criticAudit(run)} /></MemoryRouter>);
}
async function open() { await userEvent.setup().click(screen.getByRole("button", { name: /Critic Review/ })); }

beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(savedCriticRun());
  vi.spyOn(chatmateService, "getCritic").mockResolvedValue(criticReview());
  vi.spyOn(chatmateService, "requestCritic").mockResolvedValue(savedCriticRun({ critic_status: "RUNNING", critic_review_available: false }));
  vi.spyOn(chatmateService, "createFollowUp").mockResolvedValue(followUpDraft());
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("Critic Review UI", () => {
  it("allows a no-weak-point same-method follow-up without starting generation", async () => {
    const parent = savedCriticRun();
    const review = criticReview(parent, { weak_point_status: "NONE_OBSERVED", observed_weak_point: null,
      recommended_attack_profile_id: parent.attack_profile_id });
    const draft = followUpDraft(parent, review);
    draft.attack_method = parent.attack_method;
    draft.follow_up_context!.recommendation_policy = "single-turn-continuation-v1";
    vi.mocked(chatmateService.getCritic).mockResolvedValue(review);
    vi.mocked(chatmateService.createFollowUp).mockResolvedValue(draft);
    const generate = vi.spyOn(chatmateService, "generateDraft");
    panel(parent); await open();
    const start = await screen.findByRole("button", { name: "Start recommended follow-up" });
    await waitFor(() => expect(start).toBeEnabled());
    await userEvent.click(start);
    await waitFor(() => expect(screen.getByLabelText("Current route")).toHaveTextContent(`?run=${draft.run_id}`));
    expect(chatmateService.createFollowUp).toHaveBeenCalledWith(parent.run_id);
    expect(generate).not.toHaveBeenCalled();
  });
  it("warns about legacy cut-off prose and suppresses control characters without altering evidence", async () => {
    const legacy = criticReview(undefined, { management_summary: "Legacy summary\u001f", attack_effectiveness_analysis: "ChatMate did not c" });
    vi.mocked(chatmateService.getCritic).mockResolvedValue(legacy);
    panel(savedCriticRun()); await open();
    expect(await screen.findByText(/Legacy Critic text may be incomplete/)).toBeInTheDocument();
    expect(screen.getByText("Legacy summary")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("\u001f");
    expect(legacy.management_summary).toBe("Legacy summary\u001f");
    expect(screen.getByRole("button", { name: "Start recommended follow-up" })).toBeEnabled();
  });
  it("blocks new follow-up creation from incomplete legacy actionable text", async () => {
    vi.mocked(chatmateService.getCritic).mockResolvedValue(criticReview(undefined, { recommended_follow_up_objective: "Test the boundary by" }));
    panel(savedCriticRun()); await open();
    expect(await screen.findByText(/follow-up creation is blocked/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start recommended follow-up" })).toBeDisabled();
    expect(chatmateService.createFollowUp).not.toHaveBeenCalled();
  });
  it("keeps the direct request action stable across identical run/audit refreshes", async () => {
    const captured = offlineChatMateContractFixture();
    const run: ChatMateRunRecord = { ...captured.record, critic_status: null, critic_review_id: null, critic_review_available: false,
      critic_review_sha256: null, critic_attempts: 0, critic_started_at: null, critic_completed_at: null };
    const view = render(<MemoryRouter><CriticReviewPanel run={run} audit={captured.audit} /></MemoryRouter>);
    await open();
    view.rerender(<MemoryRouter><CriticReviewPanel run={structuredClone(run)} audit={structuredClone(captured.audit)} /></MemoryRouter>);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request Critic Review" })).toBeEnabled();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
    expect(chatmateService.getRun).not.toHaveBeenCalled();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
  });
  it("keeps an actual saved review cached during parent run/audit object churn", async () => {
    const captured = offlineChatMateContractFixture();
    vi.mocked(chatmateService.getRun).mockResolvedValue(captured.record);
    vi.mocked(chatmateService.getCritic).mockResolvedValue(captured.review);
    const view = render(<MemoryRouter><CriticReviewPanel run={captured.record} audit={captured.audit} /></MemoryRouter>);
    await open();
    expect(await screen.findByText(captured.review.management_summary)).toBeInTheDocument();
    view.rerender(<MemoryRouter><CriticReviewPanel run={structuredClone(captured.record)} audit={structuredClone(captured.audit)} /></MemoryRouter>);
    expect(screen.getByText(captured.review.management_summary)).toBeInTheDocument();
    await open(); await open();
    expect(screen.getByText(captured.review.management_summary)).toBeInTheDocument();
    expect(chatmateService.getCritic).toHaveBeenCalledOnce();
    expect(chatmateService.getRun).toHaveBeenCalledOnce();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("does not duplicate or cancel an in-flight saved-review read on equivalent parent refreshes", async () => {
    const captured = offlineChatMateContractFixture();
    let resolve!: (value: unknown) => void;
    vi.mocked(chatmateService.getRun).mockResolvedValue(captured.record);
    vi.mocked(chatmateService.getCritic).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const view = render(<MemoryRouter><CriticReviewPanel run={captured.record} audit={captured.audit} /></MemoryRouter>);
    await open();
    await waitFor(() => expect(chatmateService.getCritic).toHaveBeenCalledOnce());
    view.rerender(<MemoryRouter><CriticReviewPanel run={structuredClone(captured.record)} audit={structuredClone(captured.audit)} /></MemoryRouter>);
    await act(async () => resolve(captured.review));
    expect(await screen.findByText(captured.review.management_summary)).toBeInTheDocument();
    expect(chatmateService.getRun).toHaveBeenCalledOnce();
    expect(chatmateService.getCritic).toHaveBeenCalledOnce();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("shows updated provider failure details without automatically retrying", async () => {
    const captured = offlineChatMateContractFixture();
    const run: ChatMateRunRecord = { ...captured.record, critic_status: "FAILED", critic_review_available: false,
      critic_review_sha256: null, critic_error_code: "CRITIC_PROVIDER_RATE_LIMIT", critic_error_message: "The Attack Critic provider returned HTTP 429. Wait before approving another attempt." };
    const view = render(<MemoryRouter><CriticReviewPanel run={run} audit={captured.audit} /></MemoryRouter>);
    await open();
    expect(screen.getByText(run.critic_error_message!)).toBeInTheDocument();
    const next: ChatMateRunRecord = { ...run, critic_review_id: "critic-review-000000000002", critic_attempts: 2,
      critic_error_message: "The configured provider is temporarily unavailable. Review the provider settings before retrying." };
    view.rerender(<MemoryRouter><CriticReviewPanel run={next} audit={structuredClone(captured.audit)} /></MemoryRouter>);
    expect(screen.getByText(next.critic_error_message!)).toBeInTheDocument();
    expect(screen.queryByText(run.critic_error_message!)).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry Critic Review" })).toBeEnabled();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
  });
  it("starts collapsed and makes no hidden reads or provider requests", async () => {
    panel();
    expect(screen.getByRole("button", { name: /Critic Review/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await open();
    expect(screen.getByRole("button", { name: "Request Critic Review" })).toBeEnabled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(chatmateService.getRun).not.toHaveBeenCalled();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
    expect(screen.getByText(/at most one provider call/)).toBeInTheDocument();
  });
  it.each([{ status: "FAILED" }, { final_status: "ERROR" }, { final_status: "COMPROMISED" }, { artifact_available: false },
    { status: "EVALUATING" }, { manual_evidence: null }] as Partial<ChatMateRunRecord>[])("hides all Critic actions for unavailable source %j", (overrides) => {
    const run = criticRun(overrides);
    render(<MemoryRouter><CriticReviewPanel run={run} audit={criticAudit()} /></MemoryRouter>);
    expect(screen.queryByRole("region", { name: "Critic Review" })).not.toBeInTheDocument();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("requires a request click, prevents duplicate POSTs and polls completion", async () => {
    vi.useFakeTimers();
    let resolve!: (run: ChatMateRunRecord) => void;
    vi.mocked(chatmateService.requestCritic).mockImplementation(() => new Promise((done) => { resolve = done; }));
    panel();
    fireEvent.click(screen.getByRole("button", { name: /Critic Review/ }));
    const request = screen.getByRole("button", { name: "Request Critic Review" });
    fireEvent.click(request); fireEvent.click(request);
    expect(chatmateService.requestCritic).toHaveBeenCalledOnce();
    await act(async () => resolve(savedCriticRun({ critic_status: "RUNNING", critic_review_available: false })));
    expect(screen.getByText(/review is in progress/)).toBeInTheDocument();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    vi.useRealTimers();
    expect(await screen.findByText("Advisory hypothesis, not proof of vulnerability.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Weak-point hypothesis" })).toBeInTheDocument();
    expect(screen.getByText("Critic provider metadata").closest("details")).not.toHaveAttribute("open");
    expect(chatmateService.getCritic).toHaveBeenCalledWith(criticRun().run_id);
    expect(chatmateService.createFollowUp).not.toHaveBeenCalled();
  });
  it("preserves the original verdict on failure and waits for a new retry click", async () => {
    vi.useFakeTimers();
    vi.mocked(chatmateService.getRun).mockResolvedValue(savedCriticRun({ critic_status: "FAILED", critic_review_available: false,
      critic_error_message: "The advisory provider failed closed." }));
    const change = vi.fn();
    const run = criticRun();
    render(<MemoryRouter><CriticReviewPanel run={run} audit={criticAudit(run)} onRunChange={change} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /Critic Review/ }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Request Critic Review" })));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText("The advisory provider failed closed.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry Critic Review" })).toBeEnabled();
    expect(change).toHaveBeenCalledWith(expect.objectContaining({ status: "COMPLETED", final_status: "RESISTED", critic_status: "RUNNING" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Retry Critic Review" })));
    expect(chatmateService.requestCritic).toHaveBeenCalledTimes(2);
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
  });
  it("limits explicit failed attempts to three", async () => {
    panel(savedCriticRun({ critic_status: "FAILED", critic_review_available: false, critic_attempts: 3 }));
    await open();
    expect(screen.getByText(/3-attempt Critic limit/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry Critic Review" })).not.toBeInTheDocument();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("loads a saved review only on expansion and caches it across collapse", async () => {
    panel(savedCriticRun());
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    await open();
    expect(await screen.findByText("Advisory hypothesis, not proof of vulnerability.")).toBeInTheDocument();
    await open(); await open();
    expect(screen.getByText("Advisory hypothesis, not proof of vulnerability.")).toBeInTheDocument();
    expect(chatmateService.getCritic).toHaveBeenCalledOnce();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("recovers transient saved-review read failures without another provider call", async () => {
    vi.mocked(chatmateService.getCritic).mockRejectedValueOnce(new Error("Temporary network failure"));
    panel(savedCriticRun()); await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Temporary network failure");
    await userEvent.setup().click(screen.getByRole("button", { name: "Reload saved review" }));
    expect(await screen.findByText("Advisory hypothesis, not proof of vulnerability.")).toBeInTheDocument();
    expect(chatmateService.getCritic).toHaveBeenCalledTimes(2);
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("can reload a cached review after a follow-up save error without re-requesting the provider", async () => {
    vi.mocked(chatmateService.createFollowUp).mockRejectedValueOnce(new Error("Temporary draft save failure"));
    panel(savedCriticRun()); await open();
    await userEvent.setup().click(await screen.findByRole("button", { name: "Start recommended follow-up" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Temporary draft save failure");
    await userEvent.setup().click(screen.getByRole("button", { name: "Reload saved review" }));
    await waitFor(() => expect(chatmateService.getCritic).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Advisory hypothesis, not proof of vulnerability.")).toBeInTheDocument();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
    expect(chatmateService.createFollowUp).toHaveBeenCalledOnce();
  });
  it.each([
    ["NONE_OBSERVED", null, "No weak point observed"], ["EVIDENCE_SUPPORTED", "An evidence-supported observation.", "Evidence-supported observation"],
  ] as const)("renders %s without changing its strength or the original verdict", async (weak_point_status, observed_weak_point, heading) => {
    vi.mocked(chatmateService.getCritic).mockResolvedValue(criticReview(undefined, { weak_point_status, observed_weak_point }));
    panel(savedCriticRun()); await open();
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.queryByText(/Advisory; not a vulnerability verdict/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Weak-point hypothesis" })).not.toBeInTheDocument();
  });
  it("does not infer a weak point from an inconclusive source before review", async () => {
    panel(criticRun({ final_status: "INCONCLUSIVE" })); await open();
    expect(screen.getByRole("button", { name: "Request Critic Review" })).toBeEnabled();
    expect(screen.queryByRole("heading", { name: /weak point|Weak-point|Evidence-supported/ })).not.toBeInTheDocument();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
  });
  it("continues polling after a transient status failure, and stops on collapse or unmount", async () => {
    vi.useFakeTimers();
    const running = savedCriticRun({ critic_status: "RUNNING", critic_review_available: false });
    vi.mocked(chatmateService.getRun).mockRejectedValueOnce(new Error("Temporary status failure")).mockResolvedValue(running);
    const view = panel(running);
    fireEvent.click(screen.getByRole("button", { name: /Critic Review/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByRole("alert")).toHaveTextContent("Temporary status failure");
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Critic Review/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(chatmateService.getRun).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: /Critic Review/ }));
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(chatmateService.getRun).toHaveBeenCalledTimes(2);
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("visibly disables follow-up when reference accounting is incomplete", async () => {
    vi.mocked(chatmateService.getCritic).mockResolvedValue(criticReview(undefined, {
      invalid_policy_references: ["invented-policy"], recommendation_available: false,
    }));
    panel(savedCriticRun()); await open();
    expect(await screen.findByText("Recommendation needs review")).toBeInTheDocument();
    expect(screen.getByText(/invented-policy/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start recommended follow-up" })).toBeDisabled();
    expect(chatmateService.createFollowUp).not.toHaveBeenCalled();
  });
  it("blocks mismatched review disclosures and follow-up", async () => {
    vi.mocked(chatmateService.getCritic).mockResolvedValue(criticReview(undefined, { source_judge_sha256: "0".repeat(64) }));
    panel(savedCriticRun()); await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("does not match");
    expect(screen.queryByText("Advisory hypothesis, not proof of vulnerability.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start recommended follow-up" })).not.toBeInTheDocument();
  });
  it("creates or resumes the exact saved follow-up draft with no generation call", async () => {
    const user = userEvent.setup();
    const generate = vi.spyOn(chatmateService, "generateDraft");
    let resolve!: (draft: ChatMateRunRecord) => void;
    vi.mocked(chatmateService.createFollowUp).mockImplementation(() => new Promise((done) => { resolve = done; }));
    panel(savedCriticRun()); await open();
    const start = await screen.findByRole("button", { name: "Start recommended follow-up" });
    await user.click(start); fireEvent.click(start);
    expect(chatmateService.createFollowUp).toHaveBeenCalledOnce();
    await act(async () => resolve(followUpDraft()));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(`/assessments/chatmate?run=${followUpDraft().run_id}`);
    expect(generate).not.toHaveBeenCalled();
  });
  it("ignores a late saved review when the selected source ID changes", async () => {
    let resolve!: (value: unknown) => void;
    vi.mocked(chatmateService.getCritic).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const run = savedCriticRun();
    const view = render(<MemoryRouter><CriticReviewPanel run={run} audit={criticAudit(run)} /></MemoryRouter>);
    await open(); await waitFor(() => expect(chatmateService.getCritic).toHaveBeenCalledOnce());
    const next = criticRun({ evaluation_id: "new-evaluation" });
    view.rerender(<MemoryRouter><CriticReviewPanel run={next} audit={criticAudit(next)} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /Critic Review/ })).toHaveAttribute("aria-expanded", "false");
    await act(async () => resolve(criticReview()));
    await open();
    expect(screen.queryByText("Advisory hypothesis, not proof of vulnerability.")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request Critic Review" })).toBeEnabled();
  });
  it("discards late request results when the source is replaced", async () => {
    let resolve!: (value: ChatMateRunRecord) => void;
    vi.mocked(chatmateService.requestCritic).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const run = criticRun(), change = vi.fn();
    const view = render(<MemoryRouter><CriticReviewPanel run={run} audit={criticAudit(run)} onRunChange={change} /></MemoryRouter>);
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Request Critic Review" }));
    const next = criticRun({ evaluation_id: "new-evaluation" });
    view.rerender(<MemoryRouter><CriticReviewPanel run={next} audit={criticAudit(next)} onRunChange={change} /></MemoryRouter>);
    await act(async () => resolve(savedCriticRun({ critic_status: "RUNNING", critic_review_available: false })));
    expect(change).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Critic Review/ })).toHaveTextContent("Not requested");
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
  });
  it("reloads the saved recommendation from history's report without a provider request", async () => {
    vi.spyOn(chatmateService, "getAudit").mockResolvedValue(criticAudit());
    render(<MemoryRouter><ChatMateReportPanel runId={savedCriticRun().run_id} onClose={vi.fn()} /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "10/100 · Minor deviation" })).toBeInTheDocument();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    await open();
    expect(await screen.findByText("Advisory hypothesis, not proof of vulnerability.")).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: "Critic Review" })).toHaveLength(1);
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
    expect(within(screen.getByRole("article")).getByRole("heading", { name: "10/100 · Minor deviation" })).toBeInTheDocument();
  });
});
