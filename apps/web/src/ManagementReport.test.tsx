import { webcrypto } from "node:crypto";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ManagementReportPanel } from "./ManagementReportPanel";
import { ReportsPage } from "./ModulePages";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { loadManagementReport, managementReportBundle } from "./managementReport";
import { chatMateTextHash } from "./chatmateCritic";
import { offlineChatMateContractFixture } from "./chatmateOfflineContractFixture";
import { chatmateService } from "./chatmateService";
import { modelConnectivityService } from "./modelConnectivityService";
import { platformService } from "./platformService";
import { saveDeepTeamRunId } from "./deepTeamRunStorage";
import type { DeepTeamRunRecord } from "./modelConnectivityService";

beforeEach(() => { window.localStorage.clear(); vi.stubGlobal("crypto", webcrypto); });
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function chatData() {
  const fixture = offlineChatMateContractFixture();
  const response = "Original full response: operator@example.test token=synthetic-original-value. 安全な応答";
  return { source: "ChatMate", run: fixture.record, audit: fixture.audit, critic: fixture.review,
    original: { run_id: fixture.record.run_id, prompt: fixture.record.candidate_batch!.candidates[0].prompt,
      candidate_sha256: fixture.record.selected_candidate_sha256, correlation_sha256: fixture.record.manual_evidence!.correlation_sha256,
      response_text: response, response_sha256: await chatMateTextHash(response) } };
}
function socData() {
  const run = { run_id: "api-run-report", status: "COMPLETED", final_status: "RESISTED", attack: "Prompt Injection",
    created_at: "2026-10-01T12:00:00Z", completed_at: "2026-10-01T12:02:00Z", vulnerability: "Instruction boundary",
    target_profile_id: "synthetic-socmate-tier1", scenario: "socmate-tier1-permission-escalation", artifact_available: true };
  const original = { run_id: run.run_id, manifest: { run_id: "run-worker" }, deepteam_risk: { paths: [{ path_id: "path-1" }] },
    summary: { run_id: "run-worker", final_status: "RESISTED" },
    evidence: { run_id: "run-worker", paths: [{ path_id: "path-1", attack_method: "Prompt Injection", status: "RESISTED", turns: [{ probe: "SocMate exact prompt", target_response: "SocMate full response",
      tool_attempts: [{ name: "isolate", arguments: { approval_token: "synthetic-tool-original" } }] }] }],
      review_results: [{ path_id: "path-1", decision: "RESISTED", target_evaluation: { deviation_score: 0, confidence: .94, reasoning: "Policy preserved.", evidence_references: ["turn-1"] } }] } };
  const audit = structuredClone(original);
  audit.evidence.paths[0].turns[0].tool_attempts[0].arguments.approval_token = "<redacted>";
  return { source: "SocMate", run, original, audit };
}
function mockFetch(chat: Awaited<ReturnType<typeof chatData>>, soc = socData()) {
  return vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    expect(!init?.method || init.method === "GET").toBe(true);
    const path = String(url);
    if (!path.endsWith("/report-data")) throw new Error("Unexpected report request");
    return { ok: true, status: 200, json: async () => path.includes("/chatmate-runs/") ? chat : soc } as Response;
  }));
}
function Location() { return <output aria-label="Location">{useLocation().search}</output>; }

describe("Management reports", () => {
  it("retains verified Judge results when the Critic component is invalid", async () => {
    const chat = await chatData();
    chat.critic.source_judge_sha256 = "0".repeat(64);
    mockFetch(chat);
    const items = await loadManagementReport([{ source: "ChatMate", runId: chat.run.run_id }]);
    expect(items[0].evidenceStatus).toBe("Verified");
    expect(items[0].critic?.status).toBe("Invalid");
    expect(items[0].score).not.toBeUndefined();
    expect(items[0].rationales).not.toContain(chat.critic.management_summary);
  });
  it("prints and exports full original evidence and transient notes in selection order", async () => {
    const chat = await chatData(), soc = socData();
    mockFetch(chat, soc);
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    const blobs: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => { blobs.push(blob as Blob); return "blob:report"; });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    window.localStorage.setItem("unrelated-draft", "DO NOT EXPORT THIS DRAFT");
    render(<ManagementReportPanel selections={[{ source: "SocMate", runId: soc.run.run_id }, { source: "ChatMate", runId: chat.run.run_id }]} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("SocMate"); expect(rows[2]).toHaveTextContent("ChatMate");
    expect(screen.getByText(chat.original.response_text)).toBeInTheDocument();
    expect(screen.getByText(/synthetic-tool-original/)).toBeInTheDocument();
    expect(screen.queryByText("Synthetic")).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Reviewer"), "Internal reviewer");
    await user.type(screen.getByLabelText("Notes"), "Validated manually.");
    await user.click(screen.getByRole("button", { name: "Print / Save PDF" }));
    await waitFor(() => expect(print).toHaveBeenCalledOnce());
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(blobs).toHaveLength(1));
    const json = await new Promise<string>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0]); });
    const exported = JSON.parse(json);
    expect(exported.items.map((item: { source: string }) => item.source)).toEqual(["SocMate", "ChatMate"]);
    expect(exported.review.reviewer).toBe("Internal reviewer");
    expect(json).toContain(chat.original.response_text);
    expect(json).toContain("synthetic-tool-original");
    expect(json).not.toContain("DO NOT EXPORT THIS DRAFT");
    expect(json).not.toContain('"candidate_batch"');
    expect(json).not.toContain('"audit"');
  });

  it("keeps invalid and unavailable entries without exposing their content", async () => {
    const chat = await chatData();
    chat.audit.manifest.selected_candidate_sha256 = "0".repeat(64);
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => String(url).includes("chatmate-runs")
      ? { ok: true, status: 200, json: async () => chat }
      : { ok: false, status: 404 }));
    const items = await loadManagementReport([{ source: "ChatMate", runId: chat.run.run_id }, { source: "SocMate", runId: "missing" }]);
    expect(items.map((item) => item.summary)).toEqual(["Validation failed.", "Evidence unavailable."]);
    expect(items.every((item) => !item.exchanges.length && item.outcome === "Unavailable")).toBe(true);
  });

  it("rejects mismatched SocMate identity and malformed Judge metrics", async () => {
    const chat = await chatData(), soc = socData();
    soc.audit.summary.run_id = "another-worker";
    mockFetch(chat, soc);
    expect((await loadManagementReport([{ source: "SocMate", runId: soc.run.run_id }]))[0].evidenceStatus).toBe("Invalid");
    soc.audit.summary.run_id = "run-worker";
    soc.audit.evidence.review_results[0].target_evaluation.confidence = 5;
    expect((await loadManagementReport([{ source: "SocMate", runId: soc.run.run_id }]))[0].evidenceStatus).toBe("Invalid");
  });

  it("accepts native SocMate output without a root run ID but rejects contradictory identity or paths", async () => {
    const chat = await chatData(), soc = socData();
    mockFetch(chat, soc);
    const selection = [{ source: "SocMate" as const, runId: soc.run.run_id }];
    const [item] = await loadManagementReport(selection);
    expect(item).toMatchObject({ evidenceStatus: "Verified", outcome: "Resisted", score: 0, confidence: .94, originalAvailable: true });
    expect(item.pathResults).toMatchObject([{ pathId: "path-1", score: 0, confidence: .94 }]);
    Object.assign(soc.audit.deepteam_risk, { run_id: "another-worker" });
    expect((await loadManagementReport(selection))[0].evidenceStatus).toBe("Invalid");
    Object.assign(soc.audit.deepteam_risk, { run_id: "run-worker" });
    expect((await loadManagementReport(selection))[0].evidenceStatus).toBe("Verified");
    soc.audit.deepteam_risk.paths[0].path_id = "another-path";
    const [invalid] = await loadManagementReport(selection);
    expect(invalid.evidenceStatus).toBe("Invalid");
    expect(invalid.exchanges).toEqual([]);
  });

  it("keeps multiple path scores independent in the UI and exported report", async () => {
    const chat = await chatData(), soc = socData();
    for (const bundle of [soc.audit, soc.original]) {
      bundle.summary.final_status = "INCONCLUSIVE";
      bundle.evidence.paths.push({ ...structuredClone(bundle.evidence.paths[0]), path_id: "path-2", attack_method: "Crescendo", status: "INCONCLUSIVE" });
      bundle.deepteam_risk.paths.push({ path_id: "path-2" });
      bundle.evidence.review_results.push({ path_id: "path-2", decision: "INCONCLUSIVE", target_evaluation: {
        deviation_score: 60, confidence: .7, reasoning: "Partial deviation with insufficient confidence.", evidence_references: ["turn-2"] } });
    }
    soc.run.final_status = "INCONCLUSIVE";
    mockFetch(chat, soc);
    const selection = [{ source: "SocMate" as const, runId: soc.run.run_id }];
    const [item] = await loadManagementReport(selection);
    expect(item.score).toBeUndefined();
    expect(item.confidence).toBeUndefined();
    expect(item.pathResults?.map(path => [path.pathId, path.score, path.confidence])).toEqual([["path-1", 0, .94], ["path-2", 60, .7]]);
    const bundle = managementReportBundle("Test", "2026-11-06", [item], { reviewer: "", date: "", decision: "", notes: "" });
    expect(bundle.items[0].pathResults?.map(path => path.score)).toEqual([0, 60]);
    render(<ManagementReportPanel selections={selection} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    expect(within(screen.getByRole("table")).getByText("0/100")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("60/100")).toBeInTheDocument();
    expect(screen.queryByText("30/100")).not.toBeInTheDocument();
  });

  it("does not invent a zero score when no Judge evaluation was recorded", async () => {
    const chat = await chatData(), soc = socData();
    for (const bundle of [soc.audit, soc.original]) delete (bundle.evidence.review_results[0] as { target_evaluation?: unknown }).target_evaluation;
    mockFetch(chat, soc);
    const [item] = await loadManagementReport([{ source: "SocMate", runId: soc.run.run_id }]);
    expect(item.evidenceStatus).toBe("Verified");
    expect(item.score).toBeUndefined();
    expect(item.pathResults?.[0].score).toBeUndefined();
    expect(item.pathResults?.[0].scoreNote).toContain("No Judge score");
  });

  it("keeps typed unsupported reports scoreless with zero usage after reload", async () => {
    const chat = await chatData(), soc = socData();
    Object.assign(soc.run, { status: "FAILED", final_status: "ERROR", execution_capability: "UNSUPPORTED",
      execution_capability_code: "FRESH_TREE_SPECULATIVE_HISTORY_UNSUPPORTED",
      execution_capability_reason: "Tree Jailbreaking requires speculative sibling histories.", selection_admission: "EXPERIMENTAL" });
    for (const bundle of [soc.audit, soc.original]) {
      bundle.summary.final_status = "ERROR";
      Object.assign(bundle.summary, { turns: 0, budget: { provider_calls_attempted: 0, turns_consumed: 0, tokens_consumed: 0 } });
      bundle.evidence.paths[0].status = "ERROR";
      bundle.evidence.paths[0].turns = [];
      bundle.evidence.review_results = [{ path_id: "path-1", decision: "ERROR", target_evaluation: null }] as never;
    }
    mockFetch(chat, soc);
    const selection = [{ source: "SocMate" as const, runId: soc.run.run_id }];
    const [item] = await loadManagementReport(selection);
    expect(item).toMatchObject({ outcome: "Failed", evidenceStatus: "Verified", unsupported: true,
      unsupportedReason: "Tree Jailbreaking requires speculative sibling histories." });
    expect(item.score).toBeUndefined();
    render(<ManagementReportPanel selections={selection} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    const row = within(screen.getByRole("table")).getAllByRole("row")[1];
    expect(row).toHaveTextContent("Not evaluated");
    expect(row).toHaveTextContent("Not recorded");
    expect(screen.getByText("Execution mode").parentElement).toHaveTextContent("Not executed / unsupported");
    expect(screen.getByText("AI requests").parentElement).toHaveTextContent("0");
    expect(screen.getByText("Captured turns").parentElement).toHaveTextContent("0");
  });

  it("normalizes fresh Synthetic ChatMate labels and metadata without changing the deep-team source reader", async () => {
    const chat = await chatData(), soc = socData();
    Object.assign(soc.run, {
      target_profile_id: "secmate.synthetic-chatmate.fresh.v1",
      target_profile_version: "0.5.0",
      scenario: "chatmate-direct-user-prompt-injection",
      scenario_version: "3",
      vulnerability_profile_id: "DirectPromptInjection:direct_user_instruction",
    });
    for (const bundle of [soc.audit, soc.original]) {
      Object.assign(bundle.manifest, { execution_provenance: {
        schema_version: "baseline-execution-v1",
        execution_mode: "BASELINE_UNENHANCED",
        enhancement_applied: false,
        delivery: "DIRECT_GENERATED_ATTACK",
      } });
    }
    soc.source = "Synthetic ChatMate";
    mockFetch(chat, soc);
    const [item] = await loadManagementReport([{ source: "SocMate", runId: soc.run.run_id }]);

    expect(item).toMatchObject({
      source: "SocMate",
      target: "Synthetic ChatMate",
      evidenceStatus: "Verified",
      targetScope: { id: "secmate.synthetic-chatmate.fresh.v1", version: "0.5.0", risk: "DirectPromptInjection:direct_user_instruction" },
    });
    expect(item.standardReview).toBeUndefined();
    expect(item.socmateLink).toBeUndefined();
    render(<ManagementReportPanel selections={[{ source: "SocMate", runId: soc.run.run_id }]} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    expect(within(screen.getByRole("table")).getByText("Synthetic ChatMate")).toBeInTheDocument();
    expect(screen.getByText("Target profile").parentElement).toHaveTextContent("secmate.synthetic-chatmate.fresh.v1");
    expect(screen.getByText("Execution mode").parentElement).toHaveTextContent("Baseline / unenhanced");
  });

  it("shows the fresh target label in deep-team report history while retaining SocMate selection routing", async () => {
    const chat = await chatData(), soc = socData();
    Object.assign(soc.run, { target_profile_id: "secmate.synthetic-chatmate.fresh.v1", target_profile_version: "0.5.0" });
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(soc.run as DeepTeamRunRecord);
    saveDeepTeamRunId(soc.run.run_id);
    mockFetch(chat, soc);
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);

    expect(await screen.findByText("Synthetic ChatMate")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: `Select Synthetic ChatMate ${soc.run.run_id}` }));
    await userEvent.setup().click(screen.getByRole("button", { name: "Create report" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    expect(within(screen.getByRole("table")).getByText("Synthetic ChatMate")).toBeInTheDocument();
  });

  it("creates a verified individual SocMate report from one history selection", async () => {
    const chat = await chatData(), soc = socData(), user = userEvent.setup();
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(soc.run as DeepTeamRunRecord);
    saveDeepTeamRunId(soc.run.run_id);
    mockFetch(chat, soc);
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("checkbox", { name: `Select SocMate ${soc.run.run_id}` }));
    expect(screen.getByRole("button", { name: "Create report" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Create report" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("Resisted");
    expect(rows[1]).toHaveTextContent("0/100");
    expect(rows[1]).toHaveTextContent("94%");
    expect(screen.queryByText(/0 ChatMate assessment chains/)).not.toBeInTheDocument();
  });

  it("opens the individual Report action from a live results URL with the same saved score", async () => {
    const chat = await chatData(), soc = socData(), user = userEvent.setup();
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(soc.run as DeepTeamRunRecord);
    vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockResolvedValue(soc.audit);
    saveDeepTeamRunId(soc.run.run_id);
    mockFetch(chat, soc);
    render(<MemoryRouter initialEntries={["/reports?live=1"]}><ReportsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: "Report" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    expect(within(screen.getByRole("table")).getByText("0/100")).toBeInTheDocument();
    expect(screen.getByText("1 / 1 evidence verified")).toBeInTheDocument();
  });

  it("does not invent historical originals or count missing audits as resistance", async () => {
    const chat = await chatData();
    mockFetch({ ...chat, original: null } as unknown as typeof chat);
    render(<ManagementReportPanel title="ChatMate Report" selections={[{ source: "ChatMate", runId: chat.run.run_id }]} onClose={vi.fn()} />);
    expect(await screen.findAllByText("Original evidence unavailable.")).not.toHaveLength(0);
    expect(screen.queryByText(chat.original.response_text)).not.toBeInTheDocument();
    mockFetch({ ...chat, audit: null } as unknown as typeof chat);
    const items = await loadManagementReport([{ source: "ChatMate", runId: chat.run.run_id }]);
    expect(items[0].outcome).toBe("Unavailable");
  });

  it("offers Report alongside the existing ChatMate technical export", async () => {
    const chat = await chatData();
    vi.spyOn(chatmateService, "getRun").mockResolvedValue(chat.run);
    vi.spyOn(chatmateService, "getAudit").mockResolvedValue(chat.audit);
    mockFetch(chat);
    render(<MemoryRouter><ChatMateReportPanel runId={chat.run.run_id} onClose={vi.fn()} /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("button", { name: "Report" })).toBeEnabled());
    expect(screen.getByRole("button", { name: "Export JSON" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Report" }));
    expect(await screen.findByRole("heading", { name: "ChatMate Report" })).toBeInTheDocument();
  });

  it("selects mixed history independently of navigation and preserves selections across filters", async () => {
    const chat = await chatData(), soc = socData();
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([chat.run]);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(soc.run as DeepTeamRunRecord);
    saveDeepTeamRunId(soc.run.run_id);
    mockFetch(chat, soc);
    render(<MemoryRouter><ReportsPage /><Location /></MemoryRouter>);
    const user = userEvent.setup();
    expect(await screen.findByRole("button", { name: "Create report" })).toBeDisabled();
    await user.click(await screen.findByRole("checkbox", { name: `Select SocMate ${soc.run.run_id}` }));
    expect(screen.getByRole("button", { name: "Create report" })).toBeEnabled();
    await user.click(screen.getByRole("checkbox", { name: `Select ChatMate ${chat.run.run_id}` }));
    expect(screen.getByLabelText("Location")).toHaveTextContent("");
    expect(screen.getByRole("button", { name: "Create report" })).toBeEnabled();
    await user.selectOptions(screen.getByLabelText("Source"), "chatmate");
    expect(screen.queryByRole("checkbox", { name: `Select SocMate ${soc.run.run_id}` })).not.toBeInTheDocument();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create report" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("SocMate"); expect(rows[2]).toHaveTextContent("ChatMate");
    expect(screen.getByRole("heading", { name: "SecMate Report" })).toBeInTheDocument();
  });

  it("revalidates before export rather than downloading stale cached originals", async () => {
    const chat = await chatData();
    const fetcher = vi.fn(async () => ({ ok: true, status: 200, json: async () => chat }));
    vi.stubGlobal("fetch", fetcher);
    const blobs: Blob[] = [];
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => { blobs.push(blob as Blob); return "blob:fresh"; });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ManagementReportPanel selections={[{ source: "ChatMate", runId: chat.run.run_id }]} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Export JSON" })).toBeEnabled());
    fetcher.mockResolvedValueOnce({ ok: false, status: 404, json: async () => chat });
    await userEvent.setup().click(screen.getByRole("button", { name: "Export JSON" }));
    await waitFor(() => expect(blobs).toHaveLength(1));
    const json = await new Promise<string>((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blobs[0]); });
    expect(JSON.parse(json).items[0].evidenceStatus).toBe("Unavailable");
    expect(json).not.toContain(chat.original.response_text);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("selects unavailable saved SocMate references and keeps them in the report", async () => {
    vi.spyOn(platformService, "listReports").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValue(new Error("Missing"));
    saveDeepTeamRunId("api-run-missing-a"); saveDeepTeamRunId("api-run-missing-b");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404 })));
    render(<MemoryRouter><ReportsPage /></MemoryRouter>);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Select Managed / DeepTeam api-run-missing-a" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Managed / DeepTeam api-run-missing-b" }));
    await user.click(screen.getByRole("button", { name: "Create report" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Print / Save PDF" })).toBeEnabled());
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(3);
    expect(screen.getAllByText("Evidence unavailable.")).toHaveLength(2);
  });
});
