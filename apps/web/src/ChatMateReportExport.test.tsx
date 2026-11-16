import { webcrypto } from "node:crypto";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { chatMateExport } from "./chatmateProjections";
import * as criticValidation from "./chatmateCritic";
import { offlineChatMateContractFixture } from "./chatmateOfflineContractFixture";
import type { ChatMateCriticReview, ChatMateRunRecord } from "./chatmateService";

type Bundle = ReturnType<typeof chatMateExport> & { critic_review?: ChatMateCriticReview };
let blobs: Blob[];
let filenames: string[];
let requests: { url: string; init?: RequestInit }[];

beforeEach(() => {
  blobs = [];
  filenames = [];
  requests = [];
  window.localStorage.clear();
  vi.stubGlobal("crypto", webcrypto);
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL(blob: Blob) { blobs.push(blob); return "blob:report-export"; }
    static revokeObjectURL = vi.fn();
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    filenames.push(this.download);
  });
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function mockApi(handler: (url: string) => unknown | Promise<unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    if (init?.method && init.method !== "GET") throw new Error("Export attempted a non-GET request.");
    const body = await handler(url);
    if (body instanceof Error) throw body;
    return { ok: true, status: 200, json: async () => body } as Response;
  }));
}

function apiSnapshot(fixture = offlineChatMateContractFixture()) {
  if (!fixture.record.manual_evidence) throw new Error("Missing capture");
  const state: { run: ChatMateRunRecord | Error; audit: unknown; review: unknown } = {
    run: fixture.record, audit: fixture.audit, review: fixture.review,
  };
  mockApi((url) => {
    if (url.endsWith("/critic")) return state.review;
    if (url.endsWith("/audit")) return state.audit;
    if (url.endsWith(fixture.record.run_id)) return state.run;
    throw new Error(`Unexpected saved-data request: ${url}`);
  });
  return state;
}

function report(runId = offlineChatMateContractFixture().record.run_id) {
  return render(<MemoryRouter><ChatMateReportPanel runId={runId} onClose={vi.fn()} /></MemoryRouter>);
}

async function ready() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled());
}

async function readBundle() {
  await waitFor(() => expect(blobs).toHaveLength(1));
  const reader = new FileReader();
  return new Promise<Bundle>((resolve, reject) => {
    reader.onload = () => resolve(JSON.parse(String(reader.result)) as Bundle);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blobs[0]);
  });
}

const calls = (suffix: string) => requests.filter(({ url }) => url.endsWith(suffix));
const expectReadsOnly = () => expect(requests.every(({ init }) => !init?.method || init.method === "GET")).toBe(true);

describe("Latest saved ChatMate report export", () => {
  it("exports the actual completed Critic even when the parent hook predates completion, using fresh GETs only", async () => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    state.run = { ...fixture.record, critic_status: "RUNNING", critic_review_available: false, critic_review_sha256: null, critic_completed_at: null };
    window.localStorage.setItem("chatmate-draft", "SECRET UNSENT USER DRAFT");
    report();
    await ready();
    state.run = fixture.record;
    const user = userEvent.setup();
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: /Critic Review/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    vi.useRealTimers();
    expect(await screen.findByText(fixture.review.management_summary)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    const bundle = await readBundle();
    expect(bundle.critic_review).toEqual(fixture.review);
    expect(bundle.critic_review).toMatchObject({ source_candidate_sha256: fixture.record.selected_candidate_sha256,
      source_correlation_sha256: fixture.record.manual_evidence!.correlation_sha256,
      source_judge_sha256: "e6c7e912ba8b57a51aedb2ac58603bfc599ac5c1f1711df2724e770a35211243" });
    expect(bundle.run).toMatchObject({ critic_status: "COMPLETED", critic_review_available: true,
      critic_review_id: fixture.review.critic_review_id, critic_attempts: 1,
      conversation_id: fixture.record.conversation_id, final_status: "RESISTED" });
    expect(bundle.audit).toEqual(fixture.audit);
    const json = JSON.stringify(bundle);
    expect(json).toContain("<redacted>");
    expect(json).not.toContain("SECRET UNSENT USER DRAFT");
    expect(json).not.toContain("DeepTeam baseline");
    for (const field of ["candidate_batch", "logs", "follow_up_context", "assessment_spec_snapshot"]) expect(bundle.run).not.toHaveProperty(field);
    expect(calls(fixture.record.run_id)).toHaveLength(3);
    expect(calls("/audit")).toHaveLength(2);
    expect(calls("/critic")).toHaveLength(2);
    expect(filenames).toEqual([`chatmate-${fixture.record.run_id}.redacted.json`]);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report-export");
    expectReadsOnly();
  });

  it.each(["review ID", "Judge hash", "citations"])("blocks a completed review with invalid %s without falling back to the child panel's cache", async (kind) => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    report(); await ready();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Critic Review/ }));
    expect(await screen.findByText(fixture.review.management_summary)).toBeInTheDocument();
    state.review = { ...fixture.review,
      ...(kind === "review ID" ? { critic_review_id: "critic-review-000000000000" }
        : kind === "Judge hash" ? { source_judge_sha256: "0".repeat(64) } : { evidence_references: ["fabricated-evidence"] }),
    };
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Export unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent("does not match");
    expect(screen.getByRole("alert")).toHaveTextContent("No file was downloaded");
    expect(screen.getByText(fixture.review.management_summary)).toBeInTheDocument();
    expect(blobs).toHaveLength(0);
    expect(filenames).toHaveLength(0);
    expect(calls("/critic")).toHaveLength(2);
    expectReadsOnly();
  });

  it("does not use a cached review when the latest completed review cannot be read", async () => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    report(); await ready();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Critic Review/ }));
    expect(await screen.findByText(fixture.review.management_summary)).toBeInTheDocument();
    state.review = new Error("The saved Critic review failed source revalidation.");
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("failed source revalidation");
    expect(blobs).toHaveLength(0);
    expect(filenames).toHaveLength(0);
    expectReadsOnly();
  });

  it.each(["RUNNING", "FAILED"] as const)("exports only explicit %s Critic metadata while preserving the valid Judge result", async (critic_status) => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    const latest: ChatMateRunRecord = { ...fixture.record, critic_status, critic_review_available: false, critic_review_sha256: null,
      critic_completed_at: critic_status === "RUNNING" ? null : fixture.record.critic_completed_at,
      critic_error_code: critic_status === "FAILED" ? "CRITIC_PROVIDER_RATE_LIMIT" : null,
      critic_error_message: critic_status === "FAILED" ? "The provider was unavailable; no valid advisory review was produced." : null };
    state.run = latest;
    report(); await ready();
    await userEvent.setup().click(screen.getByRole("button", { name: "Export JSON" }));
    const bundle = await readBundle();
    expect(bundle).not.toHaveProperty("critic_review");
    expect(bundle.run).toMatchObject({ critic_status, critic_attempts: 1, critic_review_available: false,
      critic_review_id: fixture.record.critic_review_id, critic_started_at: fixture.record.critic_started_at,
      critic_completed_at: latest.critic_completed_at, critic_error_code: latest.critic_error_code, critic_error_message: latest.critic_error_message,
      final_status: "RESISTED" });
    expect(bundle.audit.summary.final_status).toBe("RESISTED");
    expect(JSON.stringify(bundle)).not.toContain(fixture.review.management_summary);
    expect(JSON.stringify(bundle)).not.toContain(fixture.review.attack_effectiveness_analysis);
    expect(calls("/critic")).toHaveLength(0);
    expectReadsOnly();
  });

  it("rejects a different latest run ID before reading its audit or creating a file", async () => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    report(); await ready();
    state.run = { ...fixture.record, run_id: "another-run" };
    await userEvent.setup().click(screen.getByRole("button", { name: "Export JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("does not match the requested assessment");
    expect(calls("/audit")).toHaveLength(1);
    expect(calls("/critic")).toHaveLength(0);
    expect(blobs).toHaveLength(0);
    expect(filenames).toHaveLength(0);
  });

  it("rejects an old audit when the latest original evaluation changed", async () => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    report(); await ready();
    state.run = { ...fixture.record, evaluation_id: "manual-eval-current" };
    await userEvent.setup().click(screen.getByRole("button", { name: "Export JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("audit does not match");
    expect(calls("/critic")).toHaveLength(0);
    expect(blobs).toHaveLength(0);
    expect(filenames).toHaveLength(0);
  });

  it("exports a newly validated original evaluation instead of the previous displayed audit", async () => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    report(); await ready();
    const currentAudit = structuredClone(fixture.audit);
    currentAudit.manifest.evaluation_id = "manual-eval-current";
    currentAudit.summary.evaluation_id = "manual-eval-current";
    ((currentAudit.evidence.review_results as Record<string, unknown>[])[0].target_evaluation as Record<string, unknown>).reasoning = "Latest validated Judge rationale.";
    state.run = { ...fixture.record, evaluation_id: "manual-eval-current", critic_status: null, critic_review_available: false,
      critic_review_id: null, critic_review_sha256: null, critic_attempts: 0, critic_started_at: null, critic_completed_at: null };
    state.audit = currentAudit;
    await userEvent.setup().click(screen.getByRole("button", { name: "Export JSON" }));
    const bundle = await readBundle();
    expect(bundle.run.evaluation_id).toBe("manual-eval-current");
    expect(bundle.audit).toEqual(currentAudit);
    expect(JSON.stringify(bundle)).toContain("Latest validated Judge rationale.");
    expect(JSON.stringify(bundle)).not.toContain(fixture.canonical_judge.reasoning);
    expect(bundle).not.toHaveProperty("critic_review");
    expect(calls("/critic")).toHaveLength(0);
    expectReadsOnly();
  });

  it("locks duplicate clicks while refreshing and downloading a validated snapshot", async () => {
    const fixture = offlineChatMateContractFixture();
    let waitForRun = false;
    let resolve!: (value: ChatMateRunRecord) => void;
    mockApi((url) => {
      if (url.endsWith("/audit")) return fixture.audit;
      if (url.endsWith("/critic")) return fixture.review;
      return waitForRun ? new Promise((done) => { resolve = done; }) : fixture.record;
    });
    report(); await ready();
    waitForRun = true;
    const button = screen.getByRole("button", { name: "Export JSON" });
    fireEvent.click(button); fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Exporting..." })).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(calls(fixture.record.run_id)).toHaveLength(2);
    await act(async () => resolve(fixture.record));
    await readBundle();
    expect(filenames).toHaveLength(1);
    expect(calls(fixture.record.run_id)).toHaveLength(2);
    expect(calls("/audit")).toHaveLength(2);
    expect(calls("/critic")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled();
    expectReadsOnly();
  });

  it.each([
    ["switch", "read"], ["unmount", "read"], ["switch", "validation"], ["unmount", "validation"],
  ] as const)("discards a late export after %s during Critic %s", async (lifecycle, phase) => {
    const fixture = offlineChatMateContractFixture();
    let release!: () => void;
    if (phase === "validation") vi.spyOn(criticValidation, "parseChatMateCriticReview").mockImplementationOnce(() => new Promise((resolve) => {
      release = () => resolve(fixture.review);
    }));
    mockApi((url) => {
      if (url.endsWith("/audit")) return fixture.audit;
      if (url.endsWith("/critic")) return phase === "read" ? new Promise((resolve) => { release = () => resolve(fixture.review); }) : fixture.review;
      if (url.endsWith("/other")) return new Error("Other report unavailable.");
      return fixture.record;
    });
    const view = report(); await ready();
    await userEvent.setup().click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(release).toBeTypeOf("function"));
    if (lifecycle === "switch") {
      view.rerender(<MemoryRouter><ChatMateReportPanel runId="other" onClose={vi.fn()} /></MemoryRouter>);
      expect(await screen.findByRole("alert")).toHaveTextContent("Other report unavailable");
    } else view.unmount();
    await act(async () => release());
    expect(blobs).toHaveLength(0);
    expect(filenames).toHaveLength(0);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    if (lifecycle === "switch") {
      expect(screen.getByRole("alert")).not.toHaveTextContent("Export unavailable");
      expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
    }
    expectReadsOnly();
  });

  it("blocks transient read errors and recovers only after a new explicit export click", async () => {
    const fixture = offlineChatMateContractFixture();
    const state = apiSnapshot(fixture);
    report(); await ready();
    state.run = new Error("Saved report refresh is temporarily unavailable.");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Saved report refresh is temporarily unavailable");
    expect(blobs).toHaveLength(0);
    expect(filenames).toHaveLength(0);
    state.run = fixture.record;
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    expect((await readBundle()).critic_review).toEqual(fixture.review);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(calls(fixture.record.run_id)).toHaveLength(3);
    expectReadsOnly();
  });
});
