import { webcrypto } from "node:crypto";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useSearchParams } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StandardReviewPanel } from "./StandardReviewPanel";
import { LinkedAssessmentDraft, LinkedAssessmentDraftList } from "./LinkedAssessmentDraft";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamRunRecord, DeepTeamCatalog, StandardReview, StandardReviewView, LinkedAssessmentContext } from "./modelConnectivityService";
import { sha256Text, validateStandardReview } from "./standardReview";
import { linkedSocmateChains, managementReportBundle } from "./managementReport";
import type { ManagementReportItem } from "./managementReport";
import { App } from "./App";
import { rememberAssessment, currentAssessment } from "./assessmentSession";

const parent: DeepTeamRunRecord = {
  run_id: "api-run-111111111111", status: "COMPLETED", created_at: "2026-11-06T00:00:00Z", started_at: null, completed_at: "2026-11-06T00:01:00Z",
  scenario: "socmate-tier1-permission-escalation", scenario_version: "1", target_profile_id: "synthetic-socmate-tier1", target_profile_version: "1",
  catalog_schema_version: "2.1", vulnerability: "Permission controls", attack: "Permission Escalation", vulnerability_profile_id: "ExcessiveAgency:permissions",
  attack_profile_id: "permission-escalation-v1", vulnerability_applicability: "APPLICABLE", vulnerability_capability_level: "OFFLINE_VERIFIED",
  attack_applicability: "APPLICABLE", attack_capability_level: "REGISTERED", max_total_tokens: 75000, execution_mode: "SINGLE", max_paths: 1,
  final_status: "RESISTED", artifact_available: true, logs: [], error_code: null, error_message: null,
};

async function savedView(): Promise<StandardReviewView> {
  const review: StandardReview = { schema_version: "socmate-standard-review-v1", run_id: parent.run_id, review_id: "standard-review-222222222222",
    created_at: "2026-11-06T00:02:00Z", completed_at: "2026-11-06T00:02:01Z", input_sha256: "a".repeat(64), source_audit_sha256: "b".repeat(64),
    assessment_spec_sha256: "c".repeat(64), source_path_id: "parent-path-1", recommendations: [{ attack_profile_id: "base64-v1", priority: 90 }, { attack_profile_id: "roleplay-v1", priority: 75 }],
    model: "qwen/qwen3.8-27b", model_profile_id: "groq-qwen-critic", input_tokens_estimate: 2600,
    budget: { tokens_consumed: 130, provider_calls_attempted: 1, deadline_seconds_remaining: 60 }, model_attempts: [] };
  // Exercise Python-style float spelling without rebuilding its hashed JSON.
  const canonical = JSON.stringify(review).replace('"deadline_seconds_remaining":60', '"deadline_seconds_remaining":60.0');
  return { run_id: parent.run_id, status: "COMPLETED", attempts: 1, review_id: review.review_id, job_id: "job-test", can_request: false, can_retry: false,
    message: null, review, review_canonical: canonical, review_sha256: await sha256Text(canonical) };
}
const ready = (): StandardReviewView => ({ run_id: parent.run_id, status: "READY", attempts: 0, review_id: null, job_id: null,
  can_request: true, can_retry: false, message: null, review: null });
function context(view: StandardReviewView): LinkedAssessmentContext {
  return { schema_version: "socmate-linked-assessment-v1", parent_run_id: parent.run_id, parent_path_id: view.review!.source_path_id,
    review_id: view.review_id!, review_sha256: view.review_sha256!, source_audit_sha256: view.review!.source_audit_sha256,
    assessment_spec_sha256: view.review!.assessment_spec_sha256, target_profile_id: parent.target_profile_id, target_profile_version: "1",
    vulnerability_profile_id: parent.vulnerability_profile_id, target_model_sha256: "e".repeat(64), attack_profile_id: "base64-v1", priority: 90, redacted_parent_context: { response: "Synthetic boundary evidence" } };
}
function Location() { return <output aria-label="Current location">{useLocation().search}</output>; }
beforeEach(() => { localStorage.clear(); vi.stubGlobal("crypto", webcrypto); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("loads saved status without inference; double-click and reload do not duplicate a review", async () => {
  const user = userEvent.setup(), completed = await savedView();
  let current = ready(), resolve!: (record: DeepTeamRunRecord) => void;
  vi.spyOn(modelConnectivityService, "getStandardReview").mockImplementation(async () => current);
  const request = vi.spyOn(modelConnectivityService, "requestStandardReview").mockImplementation(() => new Promise(done => { resolve = done; }));
  const view = render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);
  const button = await screen.findByRole("button", { name: "Generate recommendations" });
  expect(request).not.toHaveBeenCalled();
  await user.dblClick(button);
  expect(request).toHaveBeenCalledExactlyOnceWith(parent.run_id, false, expect.any(String));
  current = completed; resolve(parent);
  await screen.findByRole("heading", { name: "Base64" });
  expect(screen.getByText("90")).toBeInTheDocument();
  expect(screen.getByText("75")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByRole("heading", { name: "Base64" });
  view.unmount();
  render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);
  await screen.findByRole("heading", { name: "Base64" });
  expect(request).toHaveBeenCalledTimes(1);
});

it("creates a linked draft from a saved recommendation without starting it", async () => {
  const user = userEvent.setup(), completed = await savedView();
  vi.spyOn(modelConnectivityService, "getStandardReview").mockResolvedValue(completed);
  const draft = { ...parent, run_id: "api-run-333333333333", status: "DRAFT" as const, attack_profile_id: "base64-v1", attack: "Base64", linked_context: context(completed) };
  const create = vi.spyOn(modelConnectivityService, "createLinkedAssessment").mockResolvedValue(draft);
  const start = vi.spyOn(modelConnectivityService, "startLinkedAssessment");
  render(<MemoryRouter><StandardReviewPanel run={parent} /><Location /></MemoryRouter>);
  const heading = await screen.findByRole("heading", { name: "Base64" });
  await user.click(within(heading.closest("article")!).getByRole("button", { name: "Create linked assessment" }));
  await waitFor(() => expect(screen.getByLabelText("Current location")).toHaveTextContent(`linked=${draft.run_id}`));
  expect(create).toHaveBeenCalledExactlyOnceWith(parent.run_id, completed.review_id, "base64-v1", expect.any(String));
  expect(start).not.toHaveBeenCalled();
  expect(localStorage.getItem("secmate.activeDeepteamRun")).toBeNull();
});

it("requires explicit retry after a resolved failure and explicit resolution of uncertainty", async () => {
  const user = userEvent.setup();
  let current: StandardReviewView = { ...ready(), status: "UNCERTAIN", job_id: "job-uncertain", attempts: 1, can_request: false, message: "Completion uncertain." };
  vi.spyOn(modelConnectivityService, "getStandardReview").mockImplementation(async () => current);
  const request = vi.spyOn(modelConnectivityService, "requestStandardReview").mockResolvedValue(parent);
  const resolve = vi.spyOn(modelConnectivityService, "resolveReviewJob").mockImplementation(async () => {
    current = { ...current, status: "FAILED", can_retry: true }; return {};
  });
  render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);
  await user.click(await screen.findByRole("button", { name: "Accept uncertainty and release stopped job" }));
  expect(resolve).toHaveBeenCalledExactlyOnceWith("job-uncertain");
  const retry = await screen.findByRole("button", { name: "Retry review · final attempt" });
  expect(request).not.toHaveBeenCalled();
  await user.click(retry);
  expect(request).toHaveBeenCalledExactlyOnceWith(parent.run_id, true, expect.any(String));
});

it("shows one concise failure status", async () => {
  vi.spyOn(modelConnectivityService, "getStandardReview").mockResolvedValue({
    ...ready(), status: "FAILED", attempts: 2, can_request: false, can_retry: true,
    message: "The bounded review did not complete. The parent assessment is unchanged. Check saved job status before an explicit retry.",
  });

  render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);

  expect(await screen.findByText("Review failed. Retry available.")).toBeInTheDocument();
  expect(screen.queryByText(/bounded review did not complete/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Review limit reached/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry review · final attempt" })).toBeInTheDocument();
});

it("does not add a post-run review or provider call for Expanded", () => {
  const get = vi.spyOn(modelConnectivityService, "getStandardReview");
  render(<MemoryRouter><StandardReviewPanel run={{ ...parent, execution_mode: "ADAPTIVE", max_paths: 2 }} /></MemoryRouter>);
  expect(screen.queryByRole("region", { name: "Standard Attack Critic review" })).not.toBeInTheDocument();
  expect(get).not.toHaveBeenCalled();
});

it("enables fresh Standard Critic while keeping Expanded automatic-only", async () => {
  const fresh: DeepTeamRunRecord = { ...parent, scenario: "chatmate-direct-user-prompt-injection", scenario_version: "3",
    target_profile_id: "secmate.synthetic-chatmate.fresh.v1", target_profile_version: "0.5.0",
    vulnerability: "Direct User Prompt Injection", vulnerability_profile_id: "DirectPromptInjection:direct_user_instruction" };
  vi.spyOn(modelConnectivityService, "getStandardReview").mockResolvedValue({ ...ready(), run_id: fresh.run_id });
  const view = render(<MemoryRouter><StandardReviewPanel run={fresh} /></MemoryRouter>);
  expect(await screen.findByRole("button", { name: "Generate recommendations" })).toBeInTheDocument();
  expect(screen.getByText(/fresh follow-up assessment/)).toBeInTheDocument();
  view.rerender(<MemoryRouter><StandardReviewPanel run={{ ...fresh, execution_mode: "ADAPTIVE", max_paths: 2 }} /></MemoryRouter>);
  expect(screen.queryByRole("region", { name: "Standard Attack Critic review" })).not.toBeInTheDocument();
});

it("renders a server-verified target-bound draft when canonical JSON contains an integral float", async () => {
  const redacted = { judge: { confidence: 1.0 } };
  const targetContext: LinkedAssessmentContext = {
    schema_version: "secmate-target-linked-assessment-v1", parent_run_id: parent.run_id, parent_path_id: "parent-path-1",
    review_id: "standard-review-222222222222", review_sha256: "a".repeat(64), source_audit_sha256: "b".repeat(64),
    assessment_spec_sha256: "c".repeat(64), target_profile_id: "secmate.synthetic-chatmate.fresh.v1", target_profile_version: "0.5.0",
    scenario_id: "chatmate-direct-user-prompt-injection", scenario_version: "3", vulnerability_profile_id: "DirectPromptInjection:direct_user_instruction",
    target_model_sha256: "d".repeat(64), attack_profile_id: "base64-v1", priority: 90,
    redacted_parent_context: redacted, redacted_parent_context_sha256: "a1e406c26d183b1b26ea1d2c82c1ade7babb0d2c811e7c3871968e92c51a8044",
  };
  const draft: DeepTeamRunRecord = { ...parent, run_id: "api-run-333333333333", status: "DRAFT",
    scenario: targetContext.scenario_id!, scenario_version: targetContext.scenario_version!, target_profile_id: targetContext.target_profile_id,
    target_profile_version: targetContext.target_profile_version, vulnerability: "Direct User Prompt Injection",
    vulnerability_profile_id: targetContext.vulnerability_profile_id, attack: "Base64", attack_profile_id: "base64-v1", linked_context: targetContext };
  vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(draft);
  vi.spyOn(modelConnectivityService, "getDeepTeamCatalog").mockResolvedValue({ attack_profiles: [{ id: "base64-v1", turn_mode: "SINGLE", max_turns: 1 }] } as DeepTeamCatalog);
  render(<MemoryRouter><LinkedAssessmentDraft runId={draft.run_id} /></MemoryRouter>);
  expect(await screen.findByText(/new assessment informed by parent evidence/i)).toBeInTheDocument();
  expect(screen.getByText(/never continues the parent conversation/i)).toBeInTheDocument();
  expect(await screen.findByText("Synthetic ChatMate v0.5.0")).toBeInTheDocument();
  expect(screen.getByText("chatmate-direct-user-prompt-injection v3")).toBeInTheDocument();
  expect(screen.getByText("Direct User Prompt Injection")).toBeInTheDocument();
  expect(screen.getByText("Base64")).toBeInTheDocument();
  expect(screen.queryByText("(DirectPromptInjection:direct_user_instruction)")).not.toBeInTheDocument();
  expect(screen.queryByText("(base64-v1)")).not.toBeInTheDocument();
  expect(screen.queryByText("Parent assessment")).not.toBeInTheDocument();
  expect(screen.queryByText("Evidence binding")).not.toBeInTheDocument();
  expect(screen.queryByText("View parent evidence")).not.toBeInTheDocument();
});

it("formats saved linked drafts as aligned method and risk summaries", async () => {
  const draft: DeepTeamRunRecord = { ...parent, run_id: "api-run-333333333333", status: "DRAFT", attack: "Prompt Injection", attack_profile_id: "prompt-injection-v1", vulnerability: "Direct User Prompt Injection" };
  vi.spyOn(modelConnectivityService, "listLinkedDrafts").mockResolvedValue([draft]);
  const { container } = render(<MemoryRouter><LinkedAssessmentDraftList /></MemoryRouter>);

  const section = await screen.findByRole("region", { name: "Linked assessment drafts" });
  expect(within(section).getByText("Saved follow-ups")).toBeInTheDocument();
  expect(within(section).getByText("Test method")).toBeInTheDocument();
  expect(within(section).getByText("Prompt Injection")).toBeInTheDocument();
  expect(within(section).getByText("Security risk")).toBeInTheDocument();
  expect(within(section).getByText("Direct User Prompt Injection")).toBeInTheDocument();
  expect(within(section).getByRole("link", { name: "Review draft" })).toHaveAttribute("href", "/assessments?linked=api-run-333333333333");
  expect(container.querySelectorAll(".linked-draft-list > article")).toHaveLength(1);
  expect(container.querySelectorAll(".linked-draft-list dl > div")).toHaveLength(2);
});

it("cancels only the review and requires explicit retry from its saved cancelled state", async () => {
  let current: StandardReviewView = { ...ready(), status: "RUNNING", job_id: "job-cancel", attempts: 1, can_request: false };
  vi.spyOn(modelConnectivityService, "getStandardReview").mockImplementation(async () => current);
  const request = vi.spyOn(modelConnectivityService, "requestStandardReview");
  const cancel = vi.spyOn(modelConnectivityService, "cancelReviewJob").mockImplementation(async () => {
    current = { ...current, status: "CANCELLED", can_retry: true }; return {};
  });
  render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);
  await userEvent.click(await screen.findByRole("button", { name: "Cancel review" }));
  await screen.findByRole("button", { name: "Retry review · final attempt" });
  expect(cancel).toHaveBeenCalledExactlyOnceWith("job-cancel");
  expect(request).not.toHaveBeenCalled();
});

it("retains the acceptance key after a lost review response and does not retry implicitly", async () => {
  vi.spyOn(modelConnectivityService, "getStandardReview").mockResolvedValue(ready());
  const request = vi.spyOn(modelConnectivityService, "requestStandardReview").mockRejectedValue(new Error("Acceptance unconfirmed"));
  render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);
  await userEvent.click(await screen.findByRole("button", { name: "Generate recommendations" }));
  await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByRole("button", { name: "Generate recommendations" });
  expect(request).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole("button", { name: "Generate recommendations" }));
  expect(request.mock.calls[1][2]).toBe(request.mock.calls[0][2]);
});

it("validates canonical saved review data without changing float spellings or permitting stale content", async () => {
  const view = await savedView();
  expect(await validateStandardReview(parent.run_id, view)).toBe(view);
  const changed = structuredClone(view);
  changed.review!.recommendations[0].priority = 95;
  await expect(validateStandardReview(parent.run_id, changed)).rejects.toThrow("verification");
  await expect(validateStandardReview("another", view)).rejects.toThrow("selected assessment");
});

it("requires next-method recommendations for v2 while keeping legacy empty reviews readable", async () => {
  const view = await savedView();
  view.review!.schema_version = "socmate-standard-review-v2";
  view.review!.recommendations = view.review!.recommendations.slice(0, 1);
  const seal = async () => { view.review_canonical = JSON.stringify(view.review); view.review_sha256 = await sha256Text(view.review_canonical); };
  await seal();
  expect(await validateStandardReview(parent.run_id, view)).toBe(view);
  view.review!.recommendations = [];
  await seal();
  await expect(validateStandardReview(parent.run_id, view)).rejects.toThrow("verification");
  view.review!.schema_version = "socmate-standard-review-v1";
  await seal();
  expect(await validateStandardReview(parent.run_id, view)).toBe(view);
  vi.spyOn(modelConnectivityService, "getStandardReview").mockResolvedValue(view);
  const request = vi.spyOn(modelConnectivityService, "requestStandardReview");
  render(<MemoryRouter><StandardReviewPanel run={parent} /></MemoryRouter>);
  await screen.findByText(/legacy review has no recommendation/);
  expect(request).not.toHaveBeenCalled();
});

it("shows a saved draft and starts only after explicit Start with a sufficient budget", async () => {
  const user = userEvent.setup(), completed = await savedView();
  const draft: DeepTeamRunRecord = { ...parent, run_id: "api-run-333333333333", status: "DRAFT", attack_profile_id: "base64-v1", attack: "Base64", max_total_tokens: 10000, linked_context: context(completed) };
  vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(draft);
  vi.spyOn(modelConnectivityService, "getDeepTeamCatalog").mockResolvedValue({ attack_profiles: [{ id: "base64-v1", turn_mode: "SINGLE", max_turns: 1 }] } as DeepTeamCatalog);
  const start = vi.spyOn(modelConnectivityService, "startLinkedAssessment").mockResolvedValue({ ...draft, status: "QUEUED" });
  function DraftRoute() { const [params] = useSearchParams(); return params.has("linked") ? <LinkedAssessmentDraft runId={draft.run_id} /> : <h2>Normal SocMate workflow</h2>; }
  render(<MemoryRouter initialEntries={[`/assessments?linked=${draft.run_id}`]}><DraftRoute /><Location /></MemoryRouter>);
  const button = await screen.findByRole("button", { name: "Start linked assessment" });
  expect(start).not.toHaveBeenCalled();
  expect(button).toBeDisabled();
  await user.click(screen.getByRole("combobox", { name: "Usage limit" }));
  await user.click(screen.getByRole("option", { name: `${(25000).toLocaleString()} tokens` }));
  await user.click(button);
  await screen.findByRole("heading", { name: "Normal SocMate workflow" });
  expect(start).toHaveBeenCalledExactlyOnceWith(draft.run_id, 25000, expect.any(String));
  expect(localStorage.getItem("secmate.activeDeepteamRun")).toBe(draft.run_id);
});

it("keeps the full application router in SocMate through linked Start with a stored manual pointer", async () => {
  const completed = await savedView();
  const draft: DeepTeamRunRecord = { ...parent, run_id: "api-run-333333333333", status: "DRAFT", attack_profile_id: "base64-v1", attack: "Base64", linked_context: context(completed) };
  localStorage.setItem("secmate.demo.session", JSON.stringify({ email: "review@example.test", displayName: "Reviewer", role: "Local Preview" }));
  localStorage.setItem("secmate.theme", "secmate-dark");
  rememberAssessment("chatmate-preserved");
  window.history.replaceState({}, "", `/assessments?linked=${draft.run_id}`);
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => [] })));
  vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(draft);
  vi.spyOn(modelConnectivityService, "getDeepTeamCatalog").mockResolvedValue({ attack_profiles: [{ id: "base64-v1", turn_mode: "SINGLE", max_turns: 1 }], vulnerability_profiles: [] } as unknown as DeepTeamCatalog);
  vi.spyOn(modelConnectivityService, "listLinkedDrafts").mockResolvedValue([]);
  const start = vi.spyOn(modelConnectivityService, "startLinkedAssessment").mockResolvedValue({ ...draft, status: "QUEUED" });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Start linked assessment" }));
  await waitFor(() => expect(window.location.search).toBe("?workflow=socmate"));
  expect(currentAssessment()).toBe("chatmate-preserved");
  expect(start).toHaveBeenCalledTimes(1);
});

function reportItem(runId: string): ManagementReportItem {
  return { source: "SocMate", runId, method: "Synthetic test", target: "SocMate", completed: "2026-11-06", outcome: "Resisted", evidenceStatus: "Verified",
    summary: "No violation observed.", originalAvailable: false, score: 0, confidence: .95, rationales: [], citations: [], actions: [], exchanges: [], appendix: {},
    targetScope: { id: parent.target_profile_id, version: "1", risk: parent.vulnerability_profile_id } };
}
it("reports only selected linked assessments, parent first, without combining their scores", async () => {
  const view = await savedView(), p = reportItem(parent.run_id), child = reportItem("api-run-333333333333");
  p.standardReview = { status: "Verified", review: view.review!, sha256: view.review_sha256 };
  const { redacted_parent_context: _context, ...metadata } = context(view);
  child.socmateLink = { ...metadata, contextSha256: "d".repeat(64) };
  child.score = 35;
  const groups = linkedSocmateChains([child, p]);
  expect(groups.chains[0].status).toBe("Verified");
  expect(groups.chains[0].stages.map(item => [item.runId, item.score])).toEqual([[p.runId, 0], [child.runId, 35]]);
  expect(linkedSocmateChains([child]).chains[0].status).toBe("Partial");
  child.socmateLink.review_sha256 = "0".repeat(64);
  expect(linkedSocmateChains([p, child]).chains.some(chain => chain.status === "Conflict")).toBe(true);
  const bundle = managementReportBundle("Test", "2026-11-06", [p], { reviewer: "", date: "", decision: "", notes: "" });
  expect(bundle.schemaVersion).toBe("1.2");
  expect(bundle.items).toHaveLength(1);
  expect(bundle.items[0].score).toBe(0);
});

it("rejects cyclic selected lineage and changed scope", async () => {
  const view = await savedView(), p = reportItem(parent.run_id), child = reportItem("api-run-333333333333");
  p.standardReview = { status: "Verified", review: view.review!, sha256: view.review_sha256 };
  const { redacted_parent_context: _context, ...metadata } = context(view);
  child.socmateLink = { ...metadata, contextSha256: "d".repeat(64) };
  child.targetScope = { ...child.targetScope!, risk: "changed" };
  expect(linkedSocmateChains([p, child]).chains.some(chain => chain.status === "Conflict")).toBe(true);
  child.targetScope = p.targetScope;
  child.standardReview = p.standardReview;
  p.socmateLink = { ...child.socmateLink, parent_run_id: child.runId };
  expect(linkedSocmateChains([p, child]).chains.every(chain => chain.status === "Conflict")).toBe(true);
});
