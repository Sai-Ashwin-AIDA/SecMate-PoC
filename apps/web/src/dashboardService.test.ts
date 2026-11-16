import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dashboardService } from "./dashboardService";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";
import { platformService } from "./platformService";
import { chatmateService } from "./chatmateService";
import { evaluatedRun } from "./chatmateTestFixtures";
import { applyNotificationReadState, notificationReadKey, projectNotifications } from "./notificationService";
import { targetProjectionService } from "./targetProjectionService";

function run(
  runId: string,
  createdAt: string,
  status: DeepTeamRunRecord["status"],
  finalStatus: DeepTeamRunRecord["final_status"],
): DeepTeamRunRecord {
  return {
    run_id: runId,
    status,
    created_at: createdAt,
    started_at: createdAt,
    completed_at: ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(status) ? null : createdAt,
    scenario: "socmate-tier1-permission-escalation",
    scenario_version: "1",
    target_profile_id: "synthetic-socmate-tier1",
    target_profile_version: "1",
    catalog_schema_version: "2.0",
    vulnerability: "ExcessiveAgency:permissions",
    attack: "Permission Escalation",
    vulnerability_profile_id: "ExcessiveAgency:permissions",
    attack_profile_id: "permission-escalation-v1",
    vulnerability_applicability: "APPLICABLE",
    vulnerability_capability_level: "OFFLINE_VERIFIED",
    attack_applicability: "APPLICABLE",
    attack_capability_level: "REGISTERED",
    max_total_tokens: 75000,
    execution_mode: "SINGLE",
    max_paths: 1,
    final_status: finalStatus,
    artifact_available: Boolean(finalStatus),
    logs: [],
    error_code: finalStatus === "ERROR" ? "WORKER_RUN_FAILED" : null,
    error_message: finalStatus === "ERROR" ? "Synthetic worker failure." : null,
  };
}

describe("dashboardService", () => {
  const emptyCounts = { total: 0, assessments: 0, drafts: 0, smoke_tests: 0, active: 0, completed: 0, evaluated: 0, conclusive: 0, resisted: 0, compromised: 0, inconclusive: 0, failed: 0, cancelled: 0, rejected: 0, abandoned: 0 };
  const summary = (extra = {}) => ({ schema_version: "console-summary-v2", generated_at: "2026-10-01T12:00:00Z", range: { days: 30, start: "2026-09-02T00:00:00Z", end_exclusive: "2026-10-02T00:00:00Z", timezone: "UTC" }, has_active_runs_global: false, has_active_runs_in_range: false, counts: emptyCounts, pass_rate: null, finding_severity: { available: false, counts: null }, targets: {}, activity: [], trend: [], ...extra });
  const respond = (body: unknown) => vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => body }));
  it("searches authoritative projected targets and does not promise assessment search", async () => {
    let resolveTargets!: (value: Awaited<ReturnType<typeof targetProjectionService.list>>) => void;
    vi.spyOn(targetProjectionService, "list").mockImplementation(() => new Promise((resolve) => { resolveTargets = resolve; }));
    const findings = vi.spyOn(platformService, "listFindings").mockResolvedValue([]);
    const pending = dashboardService.search("socmate");
    expect(targetProjectionService.list).toHaveBeenCalledOnce();
    expect(findings).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
    resolveTargets([]);
    expect(await pending).toEqual([]);
  });
  beforeEach(() => {
    respond(summary());
    window.localStorage.clear();
    vi.useFakeTimers();
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.setSystemTime(new Date("2026-10-01T12:00:00Z"));
    vi.spyOn(targetProjectionService, "list").mockResolvedValue([{ id: "synthetic-socmate-tier1", name: "SocMate", owner: "AIDA Security Assurance", purpose: "Synthetic SOC target" } as Awaited<ReturnType<typeof targetProjectionService.list>>[number]]);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("deduplicates canonical targets and projects truthful lifecycle metrics", async () => {
    vi.mocked(targetProjectionService.list).mockResolvedValue([
      { id: "synthetic-socmate-tier1", name: "SocMate", owner: "AIDA Security Assurance", purpose: "Synthetic SOC target" },
      { id: "secmate.synthetic-chatmate.fresh.v1", name: "Synthetic ChatMate", owner: null, purpose: "Fresh synthetic target" },
    ] as Awaited<ReturnType<typeof targetProjectionService.list>>);
    const assessmentSpy = vi.spyOn(platformService, "listAssessments");
    const findingSpy = vi.spyOn(platformService, "listFindings");
    const counts = { ...emptyCounts, total: 8, assessments: 5, drafts: 1, smoke_tests: 2, active: 1, completed: 4, evaluated: 3, conclusive: 2, resisted: 1, compromised: 1, failed: 1, cancelled: 1, rejected: 3, abandoned: 2 };
    const activity = { activity_id: "deepteam:running", run_id: "running", kind: "ASSESSMENT", family: "DEEPTEAM", target_id: "synthetic-socmate-tier1", target_name: "SocMate", target_owner: "AIDA Security Assurance", status: "RUNNING", outcome: null, evaluated: false, occurred_at: "2026-10-01T11:00:00Z" };
    respond(summary({ counts, pass_rate: 50, has_active_runs_global: true, has_active_runs_in_range: true, activity: [activity], targets: { "synthetic-socmate-tier1": { target_id: "synthetic-socmate-tier1", target_name: "Duplicate SocMate name ignored", target_owner: null, counts, latest_activity: activity } }, trend: [{ date: "2026-10-01", counts, pass_rate: 50 }] }));

    const data = await dashboardService.getDashboard("7");

    expect(data.targets).toHaveLength(2);
    expect(data.targets.filter(item => item.name === "SocMate")).toHaveLength(1);
    expect(data.targets.filter(item => item.name === "Synthetic ChatMate")).toHaveLength(1);
    expect(data.targets[0]).toMatchObject({ id: "synthetic-socmate-tier1", name: "SocMate", owner: "AIDA Security Assurance", outcomes: 3, risk: "Unrated", status: "Running" });
    expect(data.metrics.find((metric) => metric.id === "assessments")?.value).toBe("5");
    expect(data.metrics.find((metric) => metric.id === "assessments")?.detail).toBe("1 draft · 2 smoke tests");
    expect(data.metrics.find((metric) => metric.id === "pass-rate")?.value).toBe("50%");
    expect(data.metrics.find((metric) => metric.id === "exceptions")?.detail).toContain("1 failed · 1 cancelled");
    expect(data.metrics.find((metric) => metric.id === "exceptions")?.value).toBe("2");
    expect(data.metrics.find((metric) => metric.id === "exceptions")?.detail).not.toMatch(/rejected|abandoned/);
    expect(data.severity).toEqual({ available: false, counts: null });
    expect(data.activity[0]).toMatchObject({ id: "deepteam:running", href: "/reports?live=running" });
    expect(data.trend[0]).toEqual({ label: "Oct 1", passRate: 50, total: 8, assessments: 5, evaluated: 3 });
    expect(data.hasActiveRuns).toBe(true);
    expect(assessmentSpy).not.toHaveBeenCalled();
    expect(findingSpy).not.toHaveBeenCalled();
  });

  it("keeps legacy manual ChatMate separate and creates source-aware activity links", async () => {
    const activity = [
      { activity_id: "legacy:one", run_id: "one", kind: "ASSESSMENT", family: "LEGACY_CHATMATE", target_id: "legacy-chatmate-manual", target_name: "ChatMate", target_owner: null, status: "COMPLETED", outcome: "RESISTED", evaluated: true, occurred_at: "2026-10-01T10:00:00Z" },
      { activity_id: "smoke:two", run_id: "two", kind: "SMOKE_TEST", family: "SYNTHETIC_CHATMATE_SMOKE", target_id: "secmate.synthetic-chatmate.fresh.v1", target_name: "Synthetic ChatMate", target_owner: null, status: "COMPLETED", outcome: null, evaluated: false, occurred_at: "2026-10-01T09:00:00Z" },
    ];
    respond(summary({ activity, targets: { "legacy-chatmate-manual": { target_id: "legacy-chatmate-manual", target_name: "ChatMate", target_owner: null, counts: emptyCounts, latest_activity: activity[0] } } }));
    const data = await dashboardService.getDashboard("7");
    expect(data.targets.map(item => item.name)).toEqual(["ChatMate", "SocMate"]);
    expect(data.targets[0]).toMatchObject({ owner: "Not specified", description: "Legacy non-projected assessment scope.", href: "/assessments/chatmate" });
    expect(data.activity.map(item => item.href)).toEqual(["/reports?chatmate=one", "/targets?id=secmate.synthetic-chatmate.fresh.v1"]);
    expect(data.activity[0].title).toBe("ChatMate assessment completed");
  });

  it("links retained DeepTeam drafts to their linked-assessment review", async () => {
    const draft = { activity_id: "deepteam:draft-one", run_id: "draft-one", kind: "DRAFT", family: "DEEPTEAM", target_id: "secmate.synthetic-chatmate.fresh.v1", target_name: "Synthetic ChatMate", target_owner: "AIDA", status: "DRAFT", outcome: null, evaluated: false, occurred_at: "2026-10-01T09:00:00Z" };
    respond(summary({ counts: { ...emptyCounts, total: 1, drafts: 1 }, activity: [draft] }));
    expect((await dashboardService.getDashboard("30")).activity[0].href).toBe("/assessments?linked=draft-one");
  });

  it("limits dashboard activity to the three newest normalized records", async () => {
    const activity = Array.from({ length: 5 }, (_, index) => ({ activity_id: `deepteam:${index}`, run_id: String(index), kind: "ASSESSMENT", family: "DEEPTEAM", target_id: "synthetic-socmate-tier1", target_name: "SocMate", target_owner: null, status: "COMPLETED", outcome: "RESISTED", evaluated: true, occurred_at: `2026-10-01T0${5 - index}:00:00Z` }));
    respond(summary({ counts: { ...emptyCounts, total: 5, assessments: 5, completed: 5, evaluated: 5, conclusive: 5, resisted: 5 }, pass_rate: 100, activity }));

    expect((await dashboardService.getDashboard("30")).activity.map((item) => item.id)).toEqual(["deepteam:0", "deepteam:1", "deepteam:2"]);
  });

  it("shows nullable pass rate and unavailable severity without fabricated zeroes", async () => {
    const data = await dashboardService.getDashboard("30");
    expect(data.metrics.find((metric) => metric.id === "pass-rate")?.value).toBe("No evaluated results");
    expect(data.severity).toEqual({ available: false, counts: null });
    expect(data.activity).toEqual([]);
    expect(data.trend).toEqual([]);
    expect(data.targets[0]).toMatchObject({ outcomes: 0, lastAssessed: "Not assessed in period", status: "Not assessed", risk: "Unrated" });
    expect(data.hasActiveRuns).toBe(false);
    expect(data.metrics.find((metric) => metric.id === "assessments")?.detail).toBe("0 drafts");
    expect(data.metrics.find((metric) => metric.id === "assessments")?.detail).not.toContain("smoke tests");
  });

  it("uses recorded severity counts when the API explicitly makes them available", async () => {
    respond(summary({ finding_severity: { available: true, counts: { critical: 1, high: 2, medium: 3, low: 4 } } }));
    expect((await dashboardService.getDashboard("30")).severity).toEqual({ available: true, counts: { CRITICAL: 1, HIGH: 2, MEDIUM: 3, LOW: 4 } });
  });

  it("fetches both authoritative histories and never seeds notifications", async () => {
    const synthetic = vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([]);
    const chatmate = vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    expect(await dashboardService.getNotifications("empty-user")).toEqual({ notifications: [], error: "", hasActiveRuns: false });
    expect(synthetic).toHaveBeenCalledOnce();
    expect(chatmate).toHaveBeenCalledOnce();
  });

  it("sorts real dates, caps entries, deduplicates, and uses friendly synthetic targets", () => {
    const newest = run("synthetic / latest", "2026-10-10T12:00:00Z", "COMPLETED", "COMPROMISED");
    const records = Array.from({ length: 25 }, (_, index) => evaluatedRun({ run_id: `chat-${index}` }));
    const result = projectNotifications([newest, newest], records);
    expect(result.notifications).toHaveLength(52);
    expect(new Set(result.notifications.map((item) => item.id)).size).toBe(52);
    expect(result.notifications[0]).toMatchObject({ title: "SocMate assessment completed", href: "/reports?live=synthetic%20%2F%20latest" });
    expect(result.notifications[0].detail).toContain("Policy violation detected");
    expect(result.notifications[0].detail).not.toContain("synthetic-socmate-tier1");
    expect(result.notifications[0].occurredAt).toBe(new Date(newest.completed_at!).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }));
  });

  it.each([
    ["QUEUED", "ChatMate assessment started", true], ["GENERATING", "ChatMate assessment started", true],
    ["AWAITING_SELECTION", "ChatMate assessment started", true], ["AWAITING_RESPONSE", "ChatMate assessment started", true],
    ["AWAITING_EVALUATION", "ChatMate assessment started", true], ["EVALUATING", "ChatMate assessment started", true],
  ] as const)("projects %s as actionable current activity", (status, title, active) => {
    const record = evaluatedRun({ status, final_status: null, artifact_available: false, completed_at: null });
    const result = projectNotifications([], [record]);
    expect(result.notifications[0]).toMatchObject({ title, href: "/assessments/chatmate?run=chatmate-1", read: false });
    expect(result.notifications[0].detail).toContain("Prompt Injection");
    expect(result.hasActiveRuns).toBe(active);
  });

  it("keeps start identity through phases and uses a separate dated end", () => {
    const generating = evaluatedRun({ status: "GENERATING", completed_at: null, final_status: null });
    const first = projectNotifications([], [generating]).notifications[0];
    expect(projectNotifications([], [{ ...generating }]).notifications[0].id).toBe(first.id);
    const selected = projectNotifications([], [evaluatedRun({ status: "AWAITING_SELECTION", final_status: null })]).notifications[0];
    const completed = projectNotifications([], [evaluatedRun()]).notifications[0];
    expect(new Set([first.id, selected.id, completed.id]).size).toBe(2);
    expect(first.occurredAt).not.toBe(completed.occurredAt);
    expect(completed).toMatchObject({ title: "ChatMate assessment completed", href: "/reports?chatmate=chatmate-1" });
    expect(completed.detail).toContain("Boundary resisted");
  });

  it("distinguishes FAILED generation from Judge/native evaluation errors without exposing secrets", () => {
    const generation = evaluatedRun({ run_id: "generation", status: "FAILED", final_status: "ERROR", manual_evidence: null, candidate_batch: null, evaluation_attempts: 0, artifact_available: false,
      error_message: "password=super-secret gsk_secret123456789" });
    const judge = evaluatedRun({ run_id: "judge", status: "FAILED", final_status: "ERROR", error_code: "JUDGE_EVALUATION_FAILED", error_message: "sk-secret123456789" });
    const native = evaluatedRun({ run_id: "native", status: "FAILED", final_status: "ERROR", error_code: "NATIVE_EVALUATION_FAILED" });
    const result = projectNotifications([], [generation, judge, native]).notifications;
    expect(result.find((item) => item.id === "chatmate:generation:run:end")).toMatchObject({ title: "Attack generation failed", href: "/assessments/chatmate?run=generation" });
    expect(result.find((item) => item.id === "chatmate:judge:run:end")).toMatchObject({ title: "ChatMate evaluation failed", href: "/reports?chatmate=judge" });
    expect(result.find((item) => item.id === "chatmate:native:run:end")?.title).toBe("ChatMate evaluation failed");
    expect(JSON.stringify(result)).not.toMatch(/super-secret|gsk_|sk-secret/);
  });

  it("does not direct an artifact-less completed record to a report", () => {
    expect(projectNotifications([], [evaluatedRun({ artifact_available: false })]).notifications[0].href).toBe("/assessments/chatmate?run=chatmate-1");
  });

  it.each(["RUNNING", "COMPLETED", "FAILED"] as const)("suppresses Critic %s activity and retains only run start/end", (critic_status) => {
    const record = evaluatedRun({ critic_status, critic_started_at: "2026-10-09T12:00:00Z", critic_completed_at: critic_status === "RUNNING" ? null : "2026-10-09T12:01:00Z" });
    const result = projectNotifications([], [record]);
    expect(result.notifications).toHaveLength(2);
    expect(result.notifications[0]).toMatchObject({ title: "ChatMate assessment completed" });
    expect(result.notifications[1].title).toBe("ChatMate assessment started");
    expect(result.hasActiveRuns).toBe(false);
  });

  it("does not notify for an unstarted follow-up draft", () => {
    const draft = evaluatedRun({ run_id: "follow-up", parent_run_id: "parent", status: "DRAFT", final_status: null, artifact_available: false,
      created_at: "2026-10-10T12:00:00Z", completed_at: null });
    const result = projectNotifications([], [evaluatedRun(), draft]);
    expect(result.notifications).toHaveLength(2);
    expect(result.notifications.some((item) => item.id.includes("follow-up"))).toBe(false);
  });

  it.each(["synthetic", "chatmate"] as const)("preserves the successful source when %s fails, then recovers", async (failedSource) => {
    const synthetic = vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([run("live", "2026-10-01T11:00:00Z", "RUNNING", null)]);
    const chatmate = vi.spyOn(chatmateService, "listRuns").mockResolvedValue([evaluatedRun()]);
    if (failedSource === "synthetic") synthetic.mockRejectedValueOnce(new Error("password=private"));
    else chatmate.mockRejectedValueOnce(new Error("gsk_private"));
    const partial = await dashboardService.getNotifications("partial-user");
    expect(partial.notifications).toHaveLength(failedSource === "synthetic" ? 2 : 1);
    expect(partial.notifications[0].id.startsWith(failedSource === "synthetic" ? "chatmate:" : "synthetic:")).toBe(true);
    expect(partial.error).toContain(failedSource === "synthetic" ? "Synthetic assessments unavailable" : "ChatMate activity unavailable");
    expect(partial.error).not.toMatch(/password|gsk_/);
    const recovered = await dashboardService.getNotifications("partial-user");
    expect(recovered.notifications).toHaveLength(3);
    expect(recovered.error).toBe("");
  });

  it("shows an error and no fabricated entries when both histories fail", async () => {
    vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockRejectedValue(new Error("offline"));
    vi.spyOn(chatmateService, "listRuns").mockRejectedValue(new Error("offline"));
    const result = await dashboardService.getNotifications("offline-user");
    expect(result.notifications).toEqual([]);
    expect(result.error).toContain("Synthetic assessments and ChatMate activity unavailable");
  });

  it("retains a cached running Standard Critic event and active polling during a source outage", async () => {
    const criticRun = { ...run("critic", "2026-10-01T11:00:00Z", "COMPLETED", "RESISTED"),
      critic_status: "RUNNING" as const, critic_review_id: "standard-review-111111111111", critic_started_at: "2026-10-01T12:00:00Z" };
    const synthetic = vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValueOnce([criticRun]).mockRejectedValueOnce(new Error("offline"));
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);

    const saved = await dashboardService.getNotifications("critic-cache-user");
    expect(saved.notifications.some((item) => item.id.endsWith(":RUNNING"))).toBe(true);
    expect(saved.hasActiveRuns).toBe(true);

    const cached = await dashboardService.getNotifications("critic-cache-user");
    expect(synthetic).toHaveBeenCalledTimes(2);
    expect(cached.notifications.some((item) => item.id.endsWith(":RUNNING"))).toBe(true);
    expect(cached.hasActiveRuns).toBe(true);
  });

  it("coalesces overlapping requests and applies read state for each user separately", async () => {
    let resolve!: (records: ReturnType<typeof evaluatedRun>[]) => void;
    const pending = new Promise<ReturnType<typeof evaluatedRun>[]>((done) => { resolve = done; });
    const synthetic = vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([]);
    const chatmate = vi.spyOn(chatmateService, "listRuns").mockReturnValue(pending);
    const id = projectNotifications([], [evaluatedRun()]).notifications[0].id;
    dashboardService.markNotificationRead("one-user", id);
    const first = dashboardService.getNotifications("one-user");
    const second = dashboardService.getNotifications("two-user");
    await Promise.resolve();
    expect(synthetic).toHaveBeenCalledOnce();
    expect(chatmate).toHaveBeenCalledOnce();
    resolve([evaluatedRun()]);
    expect((await first).notifications[0].read).toBe(true);
    expect((await second).notifications[0].read).toBe(false);
  });

  it("persists explicit reads per normalized user, while transitions and deleted history stay accurate", async () => {
    vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([]);
    const history = vi.spyOn(chatmateService, "listRuns").mockResolvedValue([evaluatedRun()]);
    const first = await dashboardService.getNotifications(" Reader@Example.com ");
    dashboardService.markAllNotificationsRead(" Reader@Example.com ", first.notifications.map((item) => item.id));
    expect((await dashboardService.getNotifications("reader@example.com")).notifications[0].read).toBe(true);
    expect((await dashboardService.getNotifications("other@example.com")).notifications[0].read).toBe(false);
    history.mockResolvedValue([evaluatedRun({ critic_status: "RUNNING", critic_started_at: "2026-10-09T12:00:00Z" })]);
    const critic = await dashboardService.getNotifications("reader@example.com");
    expect(critic.notifications.filter((item) => !item.read)).toHaveLength(0);
    history.mockResolvedValue([]);
    expect((await dashboardService.getNotifications("reader@example.com")).notifications).toEqual([]);
  });

  it("does not claim Critic details are ready when the API says they are unavailable", () => {
    const result = projectNotifications([], [evaluatedRun({ critic_status: "COMPLETED", critic_review_available: false, critic_completed_at: "2026-10-09T12:00:00Z" })]);
    expect(result.notifications[0].title).toBe("ChatMate assessment completed");
    expect(result.notifications[0].detail).not.toContain("ready to inspect");
  });

  it("retains user-scoped reads when storage writes are blocked", () => {
    const notifications = projectNotifications([], [evaluatedRun()]).notifications;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Quota exceeded"); });
    dashboardService.markNotificationRead("blocked-storage-user", notifications[0].id);
    expect(applyNotificationReadState("blocked-storage-user", notifications)[0].read).toBe(true);
    expect(applyNotificationReadState("other-blocked-storage-user", notifications)[0].read).toBe(false);
  });

  it("does not persist anonymous read state and tolerates invalid persisted IDs", () => {
    const notifications = projectNotifications([], [evaluatedRun()]).notifications;
    dashboardService.markNotificationRead("  ", notifications[0].id);
    expect(window.localStorage.getItem(notificationReadKey(""))).toBeNull();
    expect(applyNotificationReadState("", notifications)[0].read).toBe(false);
    window.localStorage.setItem(notificationReadKey("invalid-storage-user"), "not-json");
    expect(applyNotificationReadState("invalid-storage-user", notifications)[0].read).toBe(false);
    window.localStorage.setItem(notificationReadKey("invalid-storage-user"), JSON.stringify([null, {}, notifications[0].id]));
    expect(applyNotificationReadState("invalid-storage-user", notifications)[0].read).toBe(true);
  });
});
