import { webcrypto } from "node:crypto";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMatePage } from "./ChatMatePage";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { chatmateService } from "./chatmateService";
import { criticAudit, criticRun, followUpDraft, savedCriticRun } from "./chatmateCriticFixtures";
import type { ChatMateRunRecord } from "./chatmateService";

function Navigation() {
  const navigate = useNavigate(), location = useLocation();
  return <><output aria-label="Current route">{location.pathname}{location.search}</output><button type="button" onClick={() => navigate(-1)}>Back</button><button type="button" onClick={() => navigate(1)}>Forward</button></>;
}
function page(path = `/assessments/chatmate?run=${followUpDraft().run_id}`) {
  return render(<MemoryRouter initialEntries={[path]}><Navigation /><ChatMatePage /></MemoryRouter>);
}
beforeEach(() => {
  window.localStorage.removeItem("secmate.currentAssessment.v1");
  vi.stubGlobal("crypto", webcrypto);
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(followUpDraft());
  vi.spyOn(chatmateService, "getAudit").mockResolvedValue(criticAudit());
  vi.spyOn(chatmateService, "listRuns").mockResolvedValue([followUpDraft(), savedCriticRun()]);
  vi.spyOn(chatmateService, "createRun").mockResolvedValue(criticRun({ status: "QUEUED" }));
  vi.spyOn(chatmateService, "generateDraft").mockResolvedValue({ ...followUpDraft(), status: "QUEUED", authorization_attested: true });
  vi.spyOn(chatmateService, "getCritic").mockResolvedValue({});
  vi.spyOn(chatmateService, "requestCritic").mockResolvedValue(savedCriticRun());
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("Saved ChatMate follow-up drafts", () => {
  it("resumes at Configure with a locked method and waits for an explicit generation click", async () => {
    page();
    expect(await screen.findByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
    const steps = screen.getByRole("list", { name: "ChatMate assessment progress" });
    expect(within(steps).getByText("Configure").closest("li")).toHaveAttribute("aria-current", "step");
    const method = screen.getByRole("button", { name: /System Override/ });
    expect(method).toHaveAttribute("aria-pressed", "true");
    expect(method).toBeDisabled();
    expect(screen.getByRole("button", { name: /Prompt Injection/ })).toBeDisabled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate 2 attacks" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "View parent assessment" })).toHaveAttribute("href", `/assessments/chatmate?run=${followUpDraft().parent_run_id}`);
    expect(screen.getByText(followUpDraft().follow_up_objective!)).toBeInTheDocument();
    expect(screen.getByText(followUpDraft().follow_up_expected_evidence![0])).toBeInTheDocument();
    expect(screen.queryByText(/Evaluation failed|Attack generation failed|Selected attack/)).not.toBeInTheDocument();
    expect(chatmateService.getAudit).not.toHaveBeenCalled();
    expect(chatmateService.generateDraft).not.toHaveBeenCalled();
    expect(chatmateService.createRun).not.toHaveBeenCalled();
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
  it("dismissing the banner preserves provenance and generation uses the saved draft endpoint", async () => {
    const user = userEvent.setup();
    let resolve!: (run: ChatMateRunRecord) => void;
    vi.mocked(chatmateService.generateDraft).mockImplementation(() => new Promise((done) => { resolve = done; }));
    page();
    await user.click(await screen.findByRole("button", { name: "Dismiss follow-up context" }));
    expect(screen.queryByLabelText("Recommended follow-up context")).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Generation budget" }));
    await user.click(screen.getByRole("option", { name: "50,000 tokens" }));
    const generate = screen.getByRole("button", { name: "Generate 2 attacks" });
    await user.click(generate); fireEvent.click(generate);
    expect(chatmateService.generateDraft).toHaveBeenCalledOnce();
    expect(chatmateService.generateDraft).toHaveBeenCalledWith(followUpDraft().run_id, { max_total_tokens: 50000, authorization_attested: true });
    expect(chatmateService.createRun).not.toHaveBeenCalled();
    const queued = { ...followUpDraft(), status: "QUEUED" as const, authorization_attested: true, max_total_tokens: 50000 };
    vi.mocked(chatmateService.getRun).mockResolvedValue(queued);
    await act(async () => resolve(queued));
    expect(await screen.findByRole("heading", { name: "Generating two attack prompts" })).toBeInTheDocument();
    expect(screen.getByLabelText("Current route")).toHaveTextContent(followUpDraft().run_id);
    expect(screen.getByRole("link", { name: "View parent assessment" })).toBeInTheDocument();
  });
  it("retains the draft on a transient generation error and requires an explicit retry", async () => {
    const user = userEvent.setup();
    vi.mocked(chatmateService.generateDraft).mockRejectedValueOnce(new Error("Worker temporarily busy"));
    page();
    await user.click(await screen.findByRole("button", { name: "Generate 2 attacks" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Worker temporarily busy");
    expect(screen.getByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View parent assessment" })).toBeInTheDocument();
    expect(chatmateService.generateDraft).toHaveBeenCalledOnce();
    expect(chatmateService.createRun).not.toHaveBeenCalled();
  });
  it("keeps saved drafts reachable through Configure follow-up and restores authorization on browser history", async () => {
    const user = userEvent.setup();
    page("/assessments/chatmate");
    await user.click(screen.getByRole("button", { name: /Run history/ }));
    const resume = await screen.findByRole("link", { name: /Configure follow-up System Override/ });
    expect(resume).toHaveAttribute("href", `/assessments/chatmate?run=${followUpDraft().run_id}`);
    expect(screen.getByRole("link", { name: "View report" })).toHaveAttribute("href", `/reports?chatmate=${savedCriticRun().run_id}`);
    await user.click(resume);
    await screen.findByRole("heading", { name: "Choose an attack method" });
    await user.click(screen.getByRole("button", { name: "Return to new assessment" }));
    expect(screen.getByRole("button", { name: /Prompt Injection/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("link", { name: "View parent assessment" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(chatmateService.generateDraft).not.toHaveBeenCalled();
  });
  it("supports abandoning an unstarted draft without a provider call", async () => {
    const user = userEvent.setup();
    const abandon = vi.spyOn(chatmateService, "abandonRun").mockResolvedValue({ ...followUpDraft(), status: "ABANDONED" });
    page();
    await user.click(await screen.findByRole("button", { name: "Abandon draft" }));
    await waitFor(() => expect(screen.getByLabelText("Current route")).toHaveTextContent(/^\/assessments\/chatmate$/));
    expect(abandon).toHaveBeenCalledWith(followUpDraft().run_id);
    expect(chatmateService.generateDraft).not.toHaveBeenCalled();
  });
  it("exposes saved parent context in collapsed report metadata", async () => {
    const run = criticRun({ parent_run_id: followUpDraft().parent_run_id, follow_up_critic_review_id: followUpDraft().follow_up_critic_review_id,
      follow_up_objective: followUpDraft().follow_up_objective, follow_up_expected_evidence: followUpDraft().follow_up_expected_evidence });
    vi.mocked(chatmateService.getRun).mockResolvedValue(run);
    vi.mocked(chatmateService.getAudit).mockResolvedValue(criticAudit(run));
    render(<MemoryRouter><ChatMateReportPanel runId={run.run_id} onClose={vi.fn()} /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "10/100 · Minor deviation" })).toBeInTheDocument();
    const details = screen.getByText("Evidence and evaluation metadata").closest("details")!;
    expect(details).not.toHaveAttribute("open");
    await userEvent.setup().click(screen.getByText("Evidence and evaluation metadata"));
    expect(within(details).getByRole("link", { name: "View parent assessment" })).toHaveAttribute("href", `/assessments/chatmate?run=${run.parent_run_id}`);
    expect(within(details).getByText(run.follow_up_objective!)).toBeInTheDocument();
  });
});

describe("Optional manual conversation reference", () => {
  function responseRun() {
    return criticRun({ status: "AWAITING_RESPONSE", manual_evidence: null, response_submitted_at: null,
      evaluation_attempts: 0, evaluation_id: null, artifact_available: false, final_status: null });
  }
  async function attest() {
    const user = userEvent.setup();
    return user;
  }
  it("submits only a provided, trimmed and bounded conversation ID", async () => {
    vi.mocked(chatmateService.getRun).mockResolvedValue(responseRun());
    const submit = vi.spyOn(chatmateService, "submitResponse").mockResolvedValue(criticRun());
    page(`/assessments/chatmate?run=${responseRun().run_id}`);
    const input = await screen.findByLabelText("Conversation ID (optional)");
    expect(input).toHaveAttribute("maxlength", "128");
    const user = userEvent.setup();
    await user.type(input, "  chatmate-conversation-42  ");
    await user.type(screen.getByLabelText("Exact ChatMate response"), "Complete response.");
    await attest();
    await user.click(screen.getByRole("button", { name: "Submit response for evaluation" }));
    expect(submit).toHaveBeenCalledWith(responseRun().run_id, expect.objectContaining({ conversation_id: "chatmate-conversation-42" }));
  });
  it("resets a transient reference on outcome and route changes and omits blank references", async () => {
    vi.mocked(chatmateService.getRun).mockResolvedValue(responseRun());
    const submit = vi.spyOn(chatmateService, "submitResponse").mockResolvedValue(criticRun({ status: "AWAITING_EVALUATION" }));
    page(`/assessments/chatmate?run=${responseRun().run_id}`);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Conversation ID (optional)"), "temporary-reference");
    await user.click(screen.getByLabelText("Response could not be completed"));
    expect(screen.getByLabelText("Conversation ID (optional)")).toHaveValue("");
    await user.type(screen.getByLabelText("Conversation ID (optional)"), "  ");
    await attest();
    await user.click(screen.getByRole("button", { name: "Submit response for evaluation" }));
    expect(submit.mock.calls[0][1]).not.toHaveProperty("conversation_id");
    await user.click(screen.getByRole("button", { name: "Return to new assessment" }));
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByLabelText("Conversation ID (optional)")).toHaveValue("");
  });
  it("shows only one default-collapsed Critic panel on the completed assessment page", async () => {
    vi.mocked(chatmateService.getRun).mockResolvedValue(criticRun());
    page(`/assessments/chatmate?run=${criticRun().run_id}`);
    expect(await screen.findByRole("button", { name: /Critic Review/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByRole("region", { name: "Critic Review" })).toHaveLength(1);
    expect(chatmateService.getCritic).not.toHaveBeenCalled();
    expect(chatmateService.requestCritic).not.toHaveBeenCalled();
  });
});
