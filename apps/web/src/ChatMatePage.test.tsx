import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMatePage } from "./ChatMatePage";
import type { ChatMateRunRecord } from "./chatmateService";
import { evaluatedAudit, evaluatedRun } from "./chatmateTestFixtures";
import { criticAudit, criticRun } from "./chatmateCriticFixtures";

const candidates = [1, 2, 3].map((ordinal) => ({
  candidate_id: `batch-1-candidate-${ordinal}`,
  ordinal,
  attack_profile_id: "system-override-v1",
  attack_method: "System Override",
  source_prompt: `Baseline ${ordinal}`,
  source_prompt_sha256: String(ordinal).repeat(64),
  prompt: `Generated system override attack ${ordinal}`,
  prompt_sha256: String(ordinal + 3).repeat(64),
}));

function run(status: string, selected = false, completed = false) {
  return {
    run_id: "chatmate-run-1",
    status,
    created_at: "2026-10-08T12:00:00Z",
    started_at: null,
    generated_at: "2026-10-08T12:01:00Z",
    selected_at: selected ? "2026-10-08T12:02:00Z" : null,
    completed_at: completed ? "2026-10-08T12:05:00Z" : null,
    evaluation_started_at: null,
    evaluation_attempts: completed ? 1 : 0,
    evaluation_id: completed ? "manual-eval-1" : null,
    target_name: "ChatMate",
    attack_profile_id: "system-override-v1",
    attack_method: "System Override",
    max_total_tokens: 100000,
    authorization_attested: true,
    candidate_batch: {
      schema_version: "1.0",
      batch_id: "batch-1",
      created_at: "2026-10-08T12:01:00Z",
      target_name: "ChatMate",
      attack_profile_id: "system-override-v1",
      attack_method: "System Override",
      assessment_spec: {},
      candidates,
      provenance: {},
    },
    selected_candidate_id: selected ? "batch-1-candidate-2" : null,
    selected_candidate_sha256: selected ? "5".repeat(64) : null,
    response_submitted_at: completed ? "2026-10-08T12:04:00Z" : null,
    manual_evidence: completed ? {
      evidence_id: "manual-1",
      collection_method: "MANUAL_COPY_PASTE",
      run_id: "chatmate-run-1",
      batch_id: "batch-1",
      candidate_id: "batch-1-candidate-2",
      candidate_sha256: "5".repeat(64),
      outcome: "RESPONSE",
      redacted_response_text: "ChatMate refused.",
      failure_reason: null,
      persisted_response_sha256: "a".repeat(64),
      correlation_sha256: "b".repeat(64),
      prompt_sent_at: "2026-10-08T12:02:00Z",
      response_observed_at: "2026-10-08T12:03:00Z",
      submitted_at: "2026-10-08T12:04:00Z",
      prompt_submitted_unchanged: true,
      observation_captured_verbatim: true,
      redaction_applied: false,
      judge_data_collection_attested: true,
    } : null,
    final_status: completed ? "RESISTED" : null,
    artifact_available: completed,
    logs: [],
    error_code: null,
    error_message: null,
  };
}

function completedAudit() {
  const completed = run("COMPLETED", true, true) as ChatMateRunRecord;
  completed.candidate_batch!.candidates = [completed.candidate_batch!.candidates[1]];
  return evaluatedAudit(completed);
}

function Navigation() {
  const navigate = useNavigate();
  return <><button onClick={() => navigate("/assessments/chatmate")}>Plain route</button><button onClick={() => navigate("/assessments/chatmate?run=other")}>Other run</button><button onClick={() => navigate(-1)}>Browser back</button><button onClick={() => navigate(1)}>Browser forward</button></>;
}

function renderPage(path = "/assessments/chatmate") {
  return render(<MemoryRouter initialEntries={[path]}><Navigation /><ChatMatePage /></MemoryRouter>);
}

function mockApi(handler: (url: string, init?: RequestInit) => unknown | Promise<unknown>, history: unknown = []) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = url.includes("?limit=") ? history : await handler(url, init);
    if (body instanceof Error) throw body;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
}

describe("ChatMatePage", () => {
  it("shows a saved local validation failure without offering invalid candidates or automatic retries", async () => {
    const saved = { ...run("FAILED"), candidate_batch: null,
      error_code: "GENERATION_CHECK_ERROR",
      error_message: "Candidate validation stopped because of a worker runtime or validation error. No candidate batch was accepted.",
      logs: [{ timestamp: "2026-10-15T09:08:42Z", level: "ERROR",
        message: "stage=COMPLETENESS category=ADAPTER_RUNTIME; slot 1, attempt 1: CHECK_ERROR (317 characters)" }] };
    mockApi(() => saved);
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("heading", { name: "Generation Failed" })).toBeInTheDocument();
    await userEvent.click(screen.getByText("Error details"));
    expect(screen.getByText("GENERATION_CHECK_ERROR")).toBeVisible();
    await userEvent.click(screen.getByText(/Run diagnostics/));
    expect(screen.getByText(/stage=COMPLETENESS category=ADAPTER_RUNTIME/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Select candidate/ })).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("shows two options and the saved configuration on Select attack", async () => {
    const saved = run("AWAITING_SELECTION");
    saved.candidate_batch.candidates = candidates.slice(0, 2);
    saved.max_total_tokens = 50000;
    mockApi(() => saved);
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await screen.findByRole("heading", { name: "Select one generated attack" });
    const summary = screen.getByRole("complementary", { name: "Configured attack" });
    expect(within(summary).getByText("System Override")).toBeInTheDocument();
    expect(within(summary).getByText("50,000 tokens")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select candidate 2" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select candidate 3" })).not.toBeInTheDocument();
  });

  it("shows configured choices and the selected candidate on Submit response", async () => {
    mockApi(() => run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await screen.findByRole("heading", { name: "Run the selected attack in ChatMate" });
    const summary = screen.getByRole("complementary", { name: "Configuration and selected attack" });
    expect(within(summary).getByText("System Override")).toBeInTheDocument();
    expect(within(summary).getByText(`${(100000).toLocaleString()} tokens`)).toBeInTheDocument();
    expect(within(summary).getByText("Candidate 2")).toBeInTheDocument();
  });

  it("shows unique candidate intent with expandable pros/cons and exact prompt comparison", async () => {
    const user = userEvent.setup();
    const saved = run("AWAITING_SELECTION");
    saved.candidate_batch.candidates = candidates.map((candidate) => ({ ...candidate,
      explanation: { approach: `Approach ${candidate.ordinal}`, intended_effect: `Intended effect ${candidate.ordinal}`,
        selection_reason: `Selection reason ${candidate.ordinal}`, strengths: [`Strength ${candidate.ordinal}`], limitations: [`Limitation ${candidate.ordinal}`] },
    }));
    mockApi(() => saved);
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByText("Approach 1")).toBeInTheDocument();
    const card = screen.getByText("Approach 1").closest("article")!;
    expect(within(card).getByText("Intent, strengths & limitations").closest("details")).not.toHaveAttribute("open");
    await user.click(within(card).getByText("Intent, strengths & limitations"));
    expect(within(card).getByText("Intended effect 1")).toBeVisible();
    expect(within(card).getByText("Strength 1")).toBeVisible();
    expect(within(card).getByText("Limitation 1")).toBeVisible();
    expect(within(card).getByText("Exact attack prompt").closest("details")).not.toHaveAttribute("open");
    await user.click(screen.getByRole("button", { name: "Compare exact prompts" }));
    candidates.forEach((candidate) => expect(screen.getByText(candidate.prompt)).toBeVisible());
    await user.click(screen.getByRole("button", { name: "Collapse exact prompts" }));
    candidates.forEach((candidate) => expect(screen.getByText(candidate.prompt)).not.toBeVisible());
  });

  it("previews long candidates but displays and copies the complete selected attack above response capture", async () => {
    const user = userEvent.setup();
    const prompt = "  Exact DeepTeam attack\n" + "Long synthetic instructions. ".repeat(45) + "\nFINAL ATTACK INSTRUCTION  ";
    const saved = run("AWAITING_SELECTION");
    saved.candidate_batch.candidates = candidates.map((candidate) => ({ ...candidate, ...(candidate.ordinal === 2 ? { prompt } : {}) }));
    mockApi((url) => url.endsWith("/selection") ? { ...saved, status: "AWAITING_RESPONSE", selected_candidate_id: candidates[1].candidate_id, selected_candidate_sha256: candidates[1].prompt_sha256 } : saved);
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    const summary = await screen.findByText("Attack prompt preview");
    await user.click(summary);
    const card = summary.closest("article")!;
    expect(card.querySelector("pre")!.textContent).toBe(prompt.slice(0, 600) + "…");
    expect(within(card).queryByText(/FINAL ATTACK INSTRUCTION/)).not.toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Show full prompt" }));
    expect(card.querySelector("pre")!.textContent).toBe(prompt);
    await user.click(within(card).getByRole("button", { name: "Show preview" }));
    await user.click(screen.getByRole("button", { name: "Compare exact prompts" }));
    expect(card.querySelector("pre")!.textContent).toBe(prompt);
    await user.click(screen.getByRole("button", { name: "Select candidate 2" }));
    await screen.findByLabelText("Exact ChatMate response");
    const selected = screen.getByRole("button", { name: "Copy exact attack" }).closest("article")!;
    expect(selected.querySelector("pre")!.textContent).toBe(prompt);
    expect(screen.queryByText("Attack prompt preview")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy exact attack" }));
    expect(await navigator.clipboard.readText()).toBe(prompt);
  });

  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn(async () => undefined) },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("generates, selects, submits, and renders the Judge result", async () => {
    const user = userEvent.setup();
    const requests: Array<{ url: string; body?: string }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("?limit=")) return { ok: true, status: 200, json: async () => [] } as Response;
      requests.push({ url, body: typeof init?.body === "string" ? init.body : undefined });
      const body = url.endsWith("/chatmate-runs")
        ? run("AWAITING_SELECTION")
        : url.endsWith("/selection")
          ? run("AWAITING_RESPONSE", true)
          : url.endsWith("/response")
            ? run("COMPLETED", true, true)
            : url.endsWith("/audit")
              ? completedAudit()
              : run("AWAITING_SELECTION");
      return { ok: true, status: 200, json: async () => body } as Response;
    }));

    render(<MemoryRouter><ChatMatePage /></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: /System Override/i }));
    await user.click(screen.getByRole("button", { name: "Generate 2 attacks" }));

    expect(await screen.findByText("Generated system override attack 2")).toBeInTheDocument();
    expect(JSON.parse(requests[0].body ?? "{}")).toMatchObject({ attack_profile_id: "system-override-v1", authorization_attested: true });
    await user.click(screen.getByRole("button", { name: "Select candidate 2" }));
    expect(JSON.parse(requests.find((request) => request.url.endsWith("/selection"))?.body ?? "{}")).toEqual({ candidate_id: "batch-1-candidate-2", reject_all: false });

    await user.click(await screen.findByRole("button", { name: "Copy exact attack" }));
    expect(screen.getByText(/Copied exactly/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Exact ChatMate response"), "ChatMate refused the override.");
    await user.click(screen.getByRole("button", { name: "Submit response for evaluation" }));

    expect(await screen.findByRole("heading", { name: "10/100 · Minor deviation" })).toBeInTheDocument();
    expect(await screen.findByText("Validated Judge rationale.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View report" })).toHaveAttribute("href", "/reports?chatmate=chatmate-run-1");
    const submitted = JSON.parse(requests.find((request) => request.url.endsWith("/response"))?.body ?? "{}");
    expect(submitted).toMatchObject({ candidate_id: "batch-1-candidate-2", response_text: "ChatMate refused the override.", judge_data_collection_attested: true });
    expect(submitted).not.toHaveProperty("prompt_sent_at");
    expect(submitted).not.toHaveProperty("response_observed_at");
  });

  it("restores an explicit selected run and submits visible failure without response text or Judge consent", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("secmate.activeChatMateRun", "chatmate-run-1");
    let submitted: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("?limit=")) return { ok: true, status: 200, json: async () => [] } as Response;
      if (url.endsWith("/response")) submitted = JSON.parse(String(init?.body));
      return { ok: true, status: 200, json: async () => url.endsWith("/response") ? run("AWAITING_EVALUATION", true) : run("AWAITING_RESPONSE", true) } as Response;
    }));

    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await user.click(await screen.findByLabelText("Response could not be completed"));
    expect(screen.queryByLabelText("Exact ChatMate response")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/I approve sending/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Submit response for evaluation" }));

    await waitFor(() => expect(submitted).not.toBeNull());
    expect(submitted).toMatchObject({ outcome: "VISIBLE_FAILURE", failure_reason: "RESPONSE_COULD_NOT_BE_COMPLETED", judge_data_collection_attested: false });
    expect(submitted).not.toHaveProperty("response_text");
  });

  it("keeps polling after a transient refresh failure", async () => {
    vi.useFakeTimers();
    window.localStorage.setItem("secmate.activeChatMateRun", "chatmate-run-1");
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("?limit=")) return { ok: true, status: 200, json: async () => [] } as Response;
      call += 1;
      if (call === 2) throw new Error("temporary network failure");
      const body = url.endsWith("/audit")
        ? completedAudit()
        : call >= 3
          ? run("COMPLETED", true, true)
          : run("EVALUATING", true);
      return { ok: true, status: 200, json: async () => body } as Response;
    }));

    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await act(async () => Promise.resolve());
    await act(async () => { vi.advanceTimersByTime(1000); await Promise.resolve(); });
    expect(screen.getByRole("alert")).toHaveTextContent("temporary network failure");
    await act(async () => { vi.advanceTimersByTime(1500); await Promise.resolve(); });
    await act(async () => Promise.resolve());

    expect(screen.getByRole("heading", { name: "10/100 · Minor deviation" })).toBeInTheDocument();
    expect(call).toBeGreaterThanOrEqual(3);
  });

  it("keeps an explicit run URL after recovery failure and allows retry", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("secmate.activeChatMateRun", "chatmate-run-1");
    let call = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("?limit=")) return { ok: true, status: 200, json: async () => [] } as Response;
      call += 1;
      if (call === 1) throw new Error("API unavailable");
      return { ok: true, status: 200, json: async () => run("AWAITING_SELECTION") } as Response;
    }));

    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("heading", { name: "ChatMate run could not be restored" })).toBeInTheDocument();
    expect(window.localStorage.getItem("secmate.activeChatMateRun")).toBe("chatmate-run-1");
    await user.click(screen.getByRole("button", { name: "Retry recovery" }));

    expect(await screen.findByText("Generated system override attack 1")).toBeInTheDocument();
    expect(call).toBe(2);
  });

  it("can start a new run while an old Judge retry is still pending", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem("secmate.activeChatMateRun", "chatmate-run-1");
    const failed = { ...run("COMPLETED", true, true), status: "FAILED", final_status: "ERROR", artifact_available: false, error_message: "Judge unavailable." };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("?limit=")) return { ok: true, status: 200, json: async () => [] } as Response;
      if (url.endsWith("/evaluation")) return new Promise<Response>(() => undefined);
      return { ok: true, status: 200, json: async () => failed } as Response;
    }));

    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await user.click(await screen.findByRole("button", { name: "Retry Judge only" }));
    await user.click(screen.getByRole("button", { name: "Start a new ChatMate run" }));

    expect(screen.getByRole("button", { name: "Generate 2 attacks" })).toBeEnabled();
  });

  it("starts fresh despite stale localStorage and history failure", async () => {
    window.localStorage.setItem("secmate.activeChatMateRun", "stale-run");
    mockApi(() => { throw new Error("Unexpected getRun"); }, new Error("History offline"));
    renderPage();
    await userEvent.setup().click(screen.getByRole("button", { name: /Run history/ }));
    expect(await screen.findByText(/History unavailable: History offline/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Generate 2 attacks" })).toBeEnabled();
  });

  it("lists newest runs first with explicit Resume/View and restores deep links on refresh", async () => {
    const old = { ...run("ABANDONED"), run_id: "old", created_at: "2026-10-01T12:00:00Z" };
    const recent = { ...run("AWAITING_RESPONSE", true), run_id: "recent" };
    mockApi((url) => url.endsWith("/old") ? old : recent, [old, recent]);
    const page = renderPage();
    await userEvent.setup().click(screen.getByRole("button", { name: /Run history/ }));
    const resume = await screen.findByRole("link", { name: "Resume assessment System Override Run · recent" });
    const view = screen.getByRole("link", { name: "View assessment System Override Run · old" });
    expect(resume.compareDocumentPosition(view) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByLabelText("Exact ChatMate response")).not.toBeInTheDocument();
    await userEvent.setup().click(resume);
    expect(await screen.findByLabelText("Exact ChatMate response")).toBeInTheDocument();
    page.unmount();
    renderPage("/assessments/chatmate?run=recent");
    expect(await screen.findByLabelText("Exact ChatMate response")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "ChatMate run history" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Return to new assessment" }));
    await userEvent.setup().click(screen.getByRole("button", { name: /Run history/ }));
    await userEvent.setup().click(await screen.findByRole("link", { name: "View assessment System Override Run · old" }));
    expect(await screen.findByRole("heading", { name: "Run abandoned" })).toBeInTheDocument();
  });

  it("abandons step 2 before returning to a fully fresh configuration", async () => {
    mockApi((url) => run(url.endsWith("/abandon") ? "ABANDONED" : "AWAITING_SELECTION"));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Back to Configure" }));
    expect(await screen.findByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/chatmate-run-1/abandon"), expect.objectContaining({ method: "POST" }));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Prompt Injection/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("requires explicit confirmation to end step 3 and preserves selection if canceled", async () => {
    const user = userEvent.setup();
    mockApi((url) => run(url.endsWith("/abandon") ? "ABANDONED" : "AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await user.click(await screen.findByRole("button", { name: "End run and start over" }));
    expect(fetch).toHaveBeenCalledTimes(1);
    const confirmation = screen.getByRole("group", { name: "Confirm ending run" });
    expect(confirmation).toHaveClass("chatmate-confirmation");
    expect(within(confirmation).getByRole("button", { name: "Confirm end run" })).toHaveClass("danger-action");
    expect(within(confirmation).getByRole("button", { name: "Keep this run" })).toHaveClass("secondary-action");
    await user.click(screen.getByRole("button", { name: "Keep this run" }));
    expect(screen.getByText("Generated system override attack 2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select candidate 1" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "End run and start over" }));
    await user.click(screen.getByRole("button", { name: "Confirm end run" }));
    expect(await screen.findByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
  });

  it.each(["response", "conversation", "visible failure"])("protects an unsent %s when returning to Configure without abandoning the run", async (capture) => {
    const user = userEvent.setup();
    mockApi(() => run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    const response = await screen.findByLabelText("Exact ChatMate response");
    if (capture === "response") await user.type(response, "Complete unsent observation");
    if (capture === "conversation") await user.type(screen.getByLabelText("Conversation ID (optional)"), "conversation-7");
    if (capture === "visible failure") await user.click(screen.getByLabelText("Response could not be completed"));
    await user.click(screen.getByRole("button", { name: "Return to new assessment" }));
    expect(screen.getByRole("group", { name: "Discard unsent observation?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep this observation" }));
    if (capture === "response") expect(response).toHaveValue("Complete unsent observation");
    if (capture === "conversation") expect(screen.getByLabelText("Conversation ID (optional)")).toHaveValue("conversation-7");
    if (capture === "visible failure") expect(screen.getByLabelText("Response could not be completed")).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Return to new assessment" }));
    await user.click(screen.getByRole("button", { name: "Discard and return" }));
    expect(screen.getByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([url, init]) => String(url).endsWith("/abandon") || init?.method === "POST")).toBe(false);
  });

  it("rejects an oversized paste without truncation or overwriting existing evidence", async () => {
    const user = userEvent.setup();
    mockApi(() => run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    const input = await screen.findByLabelText("Exact ChatMate response") as HTMLTextAreaElement;
    await user.type(input, "Existing complete response");
    input.focus();
    input.select();
    await user.paste("x".repeat(20001));
    expect(input).toHaveValue("Existing complete response");
    expect(screen.getByRole("alert")).toHaveTextContent("Nothing was pasted; existing text is unchanged");
    expect(screen.getByRole("button", { name: "Submit response for evaluation" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Submit response for evaluation" })).toBeDisabled();
    input.select();
    const exact = " "+"x".repeat(19997)+"\n ";
    await user.paste(exact);
    expect(input).toHaveValue(exact);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects a paste whose combined length exceeds the limit while allowing selected replacement", async () => {
    const user = userEvent.setup();
    mockApi(() => run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    const input = await screen.findByLabelText("Exact ChatMate response") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "a".repeat(19999) } });
    input.focus();
    input.setSelectionRange(19999, 19999);
    await user.paste("bc");
    expect(input.value).toBe("a".repeat(19999));
    input.setSelectionRange(19998, 19999);
    await user.paste("bc");
    expect(input.value).toBe("a".repeat(19998) + "bc");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("explains a concerning score without changing the resisted outcome", async () => {
    const saved = run("COMPLETED", true, true) as ChatMateRunRecord;
    saved.candidate_batch!.candidates = [saved.candidate_batch!.candidates[1]];
    const audit = evaluatedAudit(saved);
    const evaluation = (audit.evidence.review_results as { target_evaluation: Record<string, unknown> }[])[0].target_evaluation;
    evaluation.deviation_score = 45;
    evaluation.category = "CONCERNING_DEVIATION";
    mockApi((url) => url.endsWith("/audit") ? audit : saved);
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByText("Concerning deviation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "45/100 · Concerning deviation" })).toBeInTheDocument();
    expect(screen.getByText("RESISTED", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/not a probability of compromise/)).toBeInTheDocument();
  });

  it.each([true, false])("shows Critic only when its panel is eligible (eligible: %s)", async (eligible) => {
    const saved = eligible ? criticRun() : evaluatedRun({ final_status: "INCONCLUSIVE" });
    if (!eligible) saved.manual_evidence = { ...saved.manual_evidence!, outcome: "VISIBLE_FAILURE", redacted_response_text: null,
      failure_reason: "RESPONSE_COULD_NOT_BE_COMPLETED", persisted_response_sha256: null, judge_data_collection_attested: false };
    const audit = eligible ? criticAudit(saved) : evaluatedAudit(saved);
    mockApi((url) => url.endsWith("/audit") ? audit : saved);
    renderPage(`/assessments/chatmate?run=${saved.run_id}`);
    await screen.findByRole("link", { name: "View report" });
    if (eligible) expect(await screen.findByRole("button", { name: /Critic Review/ })).toBeInTheDocument();
    else {
      expect(screen.queryByText("Critic Review")).not.toBeInTheDocument();
    }
  });

  it("explains requirements, rejects blank/oversize responses and guards a pending submission", async () => {
    const user = userEvent.setup();
    mockApi((url) => url.endsWith("/response") ? new Promise(() => undefined) : run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    const input = await screen.findByLabelText("Exact ChatMate response");
    const submit = screen.getByRole("button", { name: "Submit response for evaluation" });
    expect(submit).toBeDisabled();
    expect(screen.getByText("Paste a nonblank ChatMate response.")).toBeInTheDocument();
    expect(screen.getByText("Before submitting").parentElement).toHaveClass("chatmate-validation");
    expect(submit.closest(".chatmate-action-bar")).not.toBeNull();
    fireEvent.change(input, { target: { value: "   " } });
    expect(submit).toBeDisabled();
    fireEvent.change(input, { target: { value: "x".repeat(20001) } });
    expect(screen.getByText("Keep the response within 20,000 characters.")).toBeInTheDocument();
    expect(submit).toBeDisabled();
    fireEvent.change(input, { target: { value: "x".repeat(20000) } });
    expect(submit).toBeEnabled();
    await user.dblClick(submit);
    expect(screen.getByRole("button", { name: "Submitting evidence..." })).toBeDisabled();
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/response"))).toHaveLength(1);
  });

  it("handles missing explicit records with a return-to-new action", async () => {
    mockApi(() => { throw new Error("Run not found"); });
    renderPage("/assessments/chatmate?run=missing");
    expect(await screen.findByRole("alert")).toHaveTextContent("Run not found");
    await userEvent.setup().click(screen.getByRole("button", { name: "Return to new assessment" }));
    expect(screen.getByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
  });

  it("restores checkpoints but resets unsent transients on plain navigation and browser back/forward", async () => {
    const user = userEvent.setup();
    mockApi(() => run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await user.type(await screen.findByLabelText("Exact ChatMate response"), "unsent response");
    await user.click(screen.getByRole("button", { name: "End run and start over" }));
    await user.click(screen.getByRole("button", { name: "Plain route" }));
    expect(await screen.findByLabelText("Exact ChatMate response")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Browser back" }));
    expect(await screen.findByLabelText("Exact ChatMate response")).toHaveValue("");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Confirm ending run" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Browser forward" }));
    expect(await screen.findByLabelText("Exact ChatMate response")).toHaveValue("");
  });

  it("ignores stale restoration after switching URLs", async () => {
    let resolveOld!: (value: unknown) => void;
    mockApi((url) => url.endsWith("/other") ? { ...run("ABANDONED"), run_id: "other" } : new Promise((resolve) => { resolveOld = resolve; }));
    renderPage("/assessments/chatmate?run=old");
    await userEvent.setup().click(screen.getByRole("button", { name: "Other run" }));
    expect(await screen.findByRole("heading", { name: "Run abandoned" })).toBeInTheDocument();
    await act(async () => { resolveOld(run("AWAITING_RESPONSE", true)); });
    expect(screen.getByRole("heading", { name: "Run abandoned" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Exact ChatMate response")).not.toBeInTheDocument();
  });

  it("keeps the run and visible error when abandonment fails", async () => {
    mockApi((url) => url.endsWith("/abandon") ? new Error("Run is no longer idle") : run("AWAITING_SELECTION"));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Back to Configure" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Run is no longer idle");
    expect(screen.getByRole("heading", { name: "Select one generated attack" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to Configure" })).toBeEnabled();
  });

  it.each(["QUEUED", "GENERATING", "AWAITING_EVALUATION", "EVALUATING"])("keeps %s controls valid without extra warning copy", async (status) => {
    mockApi(() => run(status, true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("heading", { name: "ChatMate" })).toBeInTheDocument();
    expect(screen.queryByText(/cannot be abandoned while generation or evaluation/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Checking saved run status|live model health/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back to Configure" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "End run and start over" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to new assessment" })).toHaveClass("secondary-action");
    expect(screen.queryByRole("region", { name: "ChatMate run history" })).not.toBeInTheDocument();
  });

  it("ignores stale submission completion after returning to the plain route", async () => {
    const user = userEvent.setup();
    let resolveSubmission!: (value: unknown) => void;
    mockApi((url) => url.endsWith("/response") ? new Promise((resolve) => { resolveSubmission = resolve; }) : run("AWAITING_RESPONSE", true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await user.click(await screen.findByLabelText("Response could not be completed"));
    await user.click(screen.getByRole("button", { name: "Submit response for evaluation" }));
    await user.click(screen.getByRole("button", { name: "Plain route" }));
    await act(async () => { resolveSubmission(run("COMPLETED", true, true)); });
    expect(await screen.findByLabelText("Exact ChatMate response")).toHaveValue("");
    expect(screen.queryByRole("heading", { name: "Boundary resisted" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to new assessment" }));
    expect(screen.getByRole("button", { name: "Generate 2 attacks" })).toBeEnabled();
  });

  it("loads audit without localStorage and ignores stale audit after navigation", async () => {
    const user = userEvent.setup();
    let resolveAudit!: (value: unknown) => void;
    mockApi((url) => url.endsWith("/audit") ? new Promise((resolve) => { resolveAudit = resolve; }) : url.endsWith("/other") ? { ...run("ABANDONED"), run_id: "other" } : run("COMPLETED", true, true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("heading", { name: "Boundary resisted" })).toBeInTheDocument();
    await waitFor(() => expect(resolveAudit).toBeTypeOf("function"));
    expect(window.localStorage.getItem("secmate.activeChatMateRun")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Other run" }));
    expect(await screen.findByRole("heading", { name: "Run abandoned" })).toBeInTheDocument();
    await act(async () => { resolveAudit({ evidence: { review_results: [{ target_evaluation: { reasoning: "Old audit reasoning" } }] } }); });
    expect(screen.getByRole("heading", { name: "Run abandoned" })).toBeInTheDocument();
    expect(screen.queryByText("Old audit reasoning")).not.toBeInTheDocument();
  });

  it("withholds Judge metrics and rationale when the assessment audit does not match", async () => {
    const audit = completedAudit();
    audit.manifest.manual_correlation_sha256 = "tampered";
    mockApi((url) => url.endsWith("/audit") ? audit : run("COMPLETED", true, true));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("alert")).toHaveTextContent("ChatMate audit does not match");
    expect(screen.queryByText("Confidence", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.queryByText("Judge score", { selector: "dt" })).not.toBeInTheDocument();
    expect(screen.queryByText("Validated Judge rationale.")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View report" })).toHaveAttribute("href", "/reports?chatmate=chatmate-run-1");
  });

  it.each([false, true])("keeps a generation failure on Step 2 (missing batch: %s) and retries through fresh configuration", async (missingBatch) => {
    const failed = { ...run("FAILED"), candidate_batch: missingBatch ? null : run("FAILED").candidate_batch,
      evaluation_attempts: missingBatch ? 1 : 0, final_status: "ERROR", error_code: "ATTACK_GENERATION_FAILED",
      error_message: "Provider did not return a usable attack batch." };
    mockApi(() => failed);
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("heading", { name: "Generation Failed" })).toBeInTheDocument();
    expect(screen.getByText("Select attack").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Review result").closest("li")).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("alert")).toHaveTextContent("ATTACK_GENERATION_FAILED");
    expect(screen.getByRole("alert")).toHaveTextContent("Provider did not return a usable attack batch.");
    expect(screen.queryByRole("button", { name: "Retry Judge only" })).not.toBeInTheDocument();
    expect(screen.queryByText("Step 4 / Result")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View report" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry generation in a new run" }));
    expect(screen.getByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it.each([
    { status: "FAILED", final_status: "ERROR", attempts: 1, retry: true },
    { status: "FAILED", final_status: "ERROR", attempts: 9, retry: true },
    { status: "FAILED", final_status: "ERROR", attempts: 10, retry: false },
    { status: "FAILED", final_status: "INCONCLUSIVE", attempts: 1, retry: false },
    { status: "COMPLETED", final_status: "ERROR", attempts: 1, retry: false },
  ])("shows a distinct evaluation failure with backend-compatible retry eligibility: $status/$final_status/$attempts", async ({ status, final_status, attempts, retry }) => {
    mockApi(() => ({ ...run(status, true, true), final_status, evaluation_attempts: attempts, artifact_available: false,
      error_code: "JUDGE_UNAVAILABLE", error_message: "The Judge request failed." }));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    expect(await screen.findByRole("heading", { name: "Evaluation failed" })).toBeInTheDocument();
    expect(screen.getByText("Review result").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("alert")).toHaveTextContent("JUDGE_UNAVAILABLE");
    expect(screen.getByRole("alert")).toHaveTextContent("The Judge request failed.");
    expect(Boolean(screen.queryByRole("button", { name: "Retry Judge only" }))).toBe(retry);
    expect(screen.queryByRole("heading", { name: "Generation Failed" })).not.toBeInTheDocument();
    if (attempts === 10) expect(screen.getByText(/10-attempt Judge retry limit/)).toBeInTheDocument();
  });

  it("displays bounded expandable diagnostics as sanitized text rather than markup", async () => {
    const logs = Array.from({ length: 15 }, (_, index) => ({ timestamp: "2026-10-08T12:00:00Z", level: "ERROR",
      message: index === 14 ? '\u001b[31m<img src=x onerror="alert(1)"> api_key=SECRET_CREDENTIAL Bearer PRIVATE_TOKEN sk-SECRETKEY ' + "x".repeat(2000) : `Diagnostic ${index}` }));
    mockApi(() => ({ ...run("FAILED"), candidate_batch: null, error_code: "ATTACK_GENERATION_FAILED", logs }));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await screen.findByRole("heading", { name: "Generation Failed" });
    const summary = screen.getByText("Run diagnostics");
    const details = summary.closest("details")!;
    expect(details).not.toHaveAttribute("open");
    await userEvent.setup().click(summary);
    expect(details).toHaveAttribute("open");
    expect(within(details).getAllByRole("listitem")).toHaveLength(12);
    expect(within(details).queryByText("Diagnostic 0")).not.toBeInTheDocument();
    const message = details.querySelector("li:last-child pre")!;
    expect(message.textContent).toContain('<img src=x onerror="alert(1)">');
    expect(message.textContent).toContain("[REDACTED]");
    expect(message.textContent).not.toMatch(/SECRET_CREDENTIAL|PRIVATE_TOKEN|SECRETKEY|\u001b/);
    expect(message.textContent!.length).toBeLessThanOrEqual(1001);
    expect(message.textContent).toMatch(/…$/);
    expect(details.querySelector("img")).toBeNull();
    expect(within(details).queryByText("2026-10-08T12:00:00Z")).not.toBeInTheDocument();
  });

  it("keeps legacy provider tracebacks collapsed with a concise, specific visible failure reason", async () => {
    const error_message = `Traceback (most recent call last):\n${"  File \"worker.py\", line 80\n".repeat(60)}BadRequestError: {"error":{"code":"unsupported_parameter","message":"reasoning_effort is not supported by this model. api_key=SECRET_VALUE"}}`;
    mockApi(() => ({ ...run("FAILED"), candidate_batch: null, error_code: "GENERATION_FAILED", error_message }));
    renderPage("/assessments/chatmate?run=chatmate-run-1");
    await screen.findByRole("heading", { name: "Generation Failed" });
    const alert = screen.getByRole("alert");
    const visibleReason = alert.querySelector(":scope > p")!;
    expect(visibleReason).toHaveTextContent("The provider rejected a request parameter.");
    expect(visibleReason).toHaveTextContent("reasoning_effort is not supported by this model.");
    expect(visibleReason.textContent!.length).toBeLessThan(400);
    expect(visibleReason).not.toHaveTextContent("Traceback");
    const diagnostics = within(alert).getByText("Error details").closest("details")!;
    expect(diagnostics).not.toHaveAttribute("open");
    await userEvent.setup().click(within(alert).getByText("Error details"));
    expect(diagnostics).toHaveAttribute("open");
    expect(diagnostics).toHaveTextContent("Traceback");
    expect(diagnostics).toHaveTextContent("GENERATION_FAILED");
    expect(alert).not.toHaveTextContent("SECRET_VALUE");
    expect(screen.queryByText(/Manual assessment|Manual testing|ASSURANCE/i)).not.toBeInTheDocument();
  });
});
