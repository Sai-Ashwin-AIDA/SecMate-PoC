import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { applyNotificationReadState, getLiveNotifications, markNotificationsRead, notificationHistoryKey, notificationReadKey, projectNotifications } from "./notificationService";
import { evaluatedRun } from "./chatmateTestFixtures";
import { chatmateService } from "./chatmateService";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";
import { platformService } from "./platformService";
import type { Assessment } from "./platformService";

describe("durable run event projection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]);
    vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
  });
  afterEach(() => vi.restoreAllMocks());

  it.each(["COMPLETED", "FAILED", "REJECTED", "ABANDONED"] as const)("has only start/end for %s with stable end identity", (status) => {
    const record = evaluatedRun({ status });
    const result = projectNotifications([], [record, record]);
    expect(result.notifications.map((item) => item.id).sort()).toEqual(["chatmate:chatmate-1:run:end", "chatmate:chatmate-1:run:start"]);
    expect(result.hasActiveRuns).toBe(false);
    expect(projectNotifications([], [evaluatedRun({ status: "FAILED" })]).notifications[0].id).toBe(result.notifications[0].id);
  });

  it("does not invent starts for drafts; abandonment before generation has only an end", () => {
    expect(projectNotifications([], [evaluatedRun({ status: "DRAFT" })]).notifications).toEqual([]);
    const result = projectNotifications([], [evaluatedRun({ status: "ABANDONED", started_at: null })]);
    expect(result.notifications).toHaveLength(1);
    expect(result.notifications[0].id).toMatch(/:end$/);
  });

  it("does not invent synthetic run events for unstarted linked drafts", () => {
    const draft = { run_id: "draft", status: "DRAFT", execution_mode: "SINGLE", created_at: "2026-11-06T00:00:00Z" } as DeepTeamRunRecord;
    expect(projectNotifications([draft], []).notifications).toEqual([]);
    expect(projectNotifications([draft], []).hasActiveRuns).toBe(false);
  });

  it("tracks optional Standard reviews independently without adding Expanded review events", () => {
    const record = { run_id: "parent", status: "COMPLETED", final_status: "RESISTED", execution_mode: "SINGLE", target_profile_id: "synthetic-socmate-tier1",
      attack: "Permission Escalation", critic_review_id: "standard-review-test", critic_status: "RUNNING", critic_started_at: "2026-11-06T00:02:00Z", created_at: "2026-11-06T00:00:00Z" } as DeepTeamRunRecord;
    const running = projectNotifications([record], []);
    expect(running.hasActiveRuns).toBe(true);
    expect(running.notifications.some(item => item.title.includes("Critic review running"))).toBe(true);
    const completed = projectNotifications([{ ...record, critic_status: "COMPLETED", critic_completed_at: "2026-11-06T00:03:00Z" }], []);
    expect(completed.hasActiveRuns).toBe(false);
    expect(completed.notifications.some(item => item.title.includes("Critic review completed"))).toBe(true);
    expect(projectNotifications([{ ...record, execution_mode: "ADAPTIVE" }], []).notifications.some(item => item.title.includes("Critic"))).toBe(false);
  });

  it("bounds retained notifications while keeping the latest events", () => {
    const records = Array.from({ length: 600 }, (_, index) => evaluatedRun({ run_id: `run-${index}`, completed_at: new Date(Date.UTC(2026, 9, 15, 12, 0, index)).toISOString() }));
    const result = projectNotifications([], records);
    expect(result.notifications).toHaveLength(1000);
    expect(result.notifications[0].id).toBe("chatmate:run-599:run:end");
  });

  it("keeps source namespaces separate and emits cancellation only when terminal", () => {
    const browser = { id: "same", targetName: "Local", name: "Local assessment", status: "CANCEL_REQUESTED", createdAt: "2026-10-15T12:00:01Z", completedAt: null } as Assessment;
    const synthetic = { run_id: "same", target_profile_id: "synthetic-socmate-tier1", attack: "Permission Escalation", status: "CANCEL_REQUESTED", created_at: "2026-10-15T12:00:02Z" } as DeepTeamRunRecord;
    const chatmate = evaluatedRun({ run_id: "same", status: "AWAITING_RESPONSE", final_status: null, completed_at: null });
    const active = projectNotifications([synthetic], [chatmate], [browser]);
    expect(active.notifications).toHaveLength(3);
    expect(new Set(active.notifications.map((item) => item.id)).size).toBe(3);
    const ended = projectNotifications([{ ...synthetic, status: "CANCELLED", completed_at: "2026-10-15T12:01:02Z" }], [chatmate], [{ ...browser, status: "TIMED_OUT", completedAt: "2026-10-15T12:01:01Z" }]);
    expect(ended.notifications).toHaveLength(5);
    expect(ended.notifications[0].title).toContain("cancelled");
    expect(ended.notifications[1].title).toContain("timed out");
  });

  it("reconstructs runs finished while offline, caches outages and removes deleted source history on success", async () => {
    const history = vi.mocked(chatmateService.listRuns);
    history.mockResolvedValue([evaluatedRun()]);
    const first = await getLiveNotifications("reader");
    markNotificationsRead("reader", [first.notifications[0].id]);
    history.mockRejectedValue(new Error("offline"));
    const offline = await getLiveNotifications("reader");
    expect(offline.notifications).toHaveLength(2);
    expect(offline.notifications[0].read).toBe(true);
    expect((await getLiveNotifications("other-reader")).notifications).toEqual([]);
    history.mockResolvedValue([evaluatedRun(), evaluatedRun({ run_id: "finished-offline", completed_at: "2026-10-15T12:00:01Z" })]);
    const recovered = await getLiveNotifications("reader");
    expect(recovered.notifications).toHaveLength(4);
    expect(recovered.notifications[0]).toMatchObject({ id: "chatmate:finished-offline:run:end", read: false });
    history.mockResolvedValue([]);
    expect((await getLiveNotifications("reader")).notifications).toEqual([]);
    history.mockRejectedValue(new Error("offline"));
    expect((await getLiveNotifications("reader")).notifications).toEqual([]);
  });

  it("preserves legacy terminal reads without reading a start or future end from intermediate activity", () => {
    const notifications = projectNotifications([], [evaluatedRun()]).notifications;
    localStorage.setItem(notificationReadKey("legacy"), JSON.stringify([null, {}, "chatmate:chatmate-1:evaluation:COMPLETED"]));
    expect(applyNotificationReadState("legacy", notifications).map((item) => item.read)).toEqual([true, false]);
    localStorage.setItem(notificationReadKey("phase"), JSON.stringify(["chatmate:chatmate-1:generation:AWAITING_SELECTION"]));
    expect(applyNotificationReadState("phase", notifications).every((item) => !item.read)).toBe(true);
  });

  it.each([{ body: {} }, { body: [null] }])("retains cached source events if a successful response is malformed: %j", async ({ body }) => {
    vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun()]);
    const saved = await getLiveNotifications("reader");
    vi.mocked(chatmateService.listRuns).mockResolvedValue(body as never);
    const stale = await getLiveNotifications("reader");
    expect(stale.notifications).toEqual(saved.notifications);
    expect(stale.error).toContain("ChatMate activity unavailable");
    expect(stale.error).toContain("out of date");
  });

  it("keeps independent tab receipts even when their legacy array writes race", () => {
    const notifications = projectNotifications([], [evaluatedRun()]).notifications;
    markNotificationsRead("tabs", [notifications[0].id]);
    markNotificationsRead("tabs", [notifications[1].id]);
    localStorage.setItem(notificationReadKey("tabs"), JSON.stringify([notifications[1].id]));
    expect(applyNotificationReadState("tabs", notifications).every((item) => item.read)).toBe(true);
  });

  it.each(["chatmate", "synthetic", "browser"] as const)("rejects malformed %s rows without replacing a good cache", async (source) => {
    const valid = source === "chatmate" ? evaluatedRun() : source === "synthetic"
      ? { run_id: "soc-1", status: "COMPLETED", final_status: "RESISTED", target_profile_id: "synthetic-socmate-tier1", attack: "PromptInjection", created_at: "2026-10-15T12:00:00Z", completed_at: null }
      : { id: "local-1", status: "COMPLETED", targetName: "Local target", name: "Local assessment", createdAt: "2026-10-15T12:00:00Z", completedAt: null };
    const service = source === "chatmate" ? vi.mocked(chatmateService.listRuns)
      : source === "synthetic" ? vi.mocked(modelConnectivityService.listDeepTeamRuns) : vi.mocked(platformService.listAssessments);
    service.mockResolvedValue([valid] as never);
    const saved = await getLiveNotifications("row-validation");
    expect(saved.notifications).toHaveLength(2);
    const idKey = source === "browser" ? "id" : "run_id";
    const presentationKey = source === "chatmate" ? "attack_profile_id" : source === "synthetic" ? "target_profile_id" : "targetName";
    for (const invalid of [{}, { ...valid, [idKey]: undefined }, { ...valid, [idKey]: 12 },
      { ...valid, [idKey]: " " }, { ...valid, [idKey]: "undefined" }, { ...valid, [idKey]: "null" },
      { ...valid, status: "NOT_A_STATUS" }, { ...valid, [presentationKey]: null }, { ...valid, final_status: ["RESISTED"] },
      { ...valid, [source === "browser" ? "createdAt" : "created_at"]: 12 }]) {
      for (const rows of [[invalid], [valid, invalid]]) {
        service.mockResolvedValue(rows as never);
        const snapshot = await getLiveNotifications("row-validation");
        expect(snapshot.notifications).toEqual(saved.notifications);
        expect(snapshot.error).toContain("out of date");
        expect(snapshot.notifications.every((item) => !item.id.includes("undefined") && !item.href.includes("undefined"))).toBe(true);
      }
    }
    service.mockRejectedValue(new Error("offline"));
    expect((await getLiveNotifications("row-validation")).notifications).toEqual(saved.notifications);
    service.mockResolvedValue([{ ...valid, [idKey]: "recovered-run" }] as never);
    const recovered = await getLiveNotifications("row-validation");
    expect(recovered.error).toBe("");
    expect(recovered.notifications.every((item) => item.id.includes("recovered-run"))).toBe(true);
    service.mockResolvedValue([]);
    expect((await getLiveNotifications("row-validation")).notifications).toEqual([]);
  });

  it("refreshes healthy sources independently when ChatMate objects are malformed", async () => {
    vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun()]);
    await getLiveNotifications("partial-malformed");
    vi.mocked(chatmateService.listRuns).mockResolvedValue([{}] as never);
    vi.mocked(modelConnectivityService.listDeepTeamRuns).mockResolvedValue([{ run_id: "new-soc", status: "RUNNING",
      target_profile_id: "synthetic-socmate-tier1", attack: "PromptInjection", created_at: "2026-10-15T12:00:00Z" }] as never);
    const result = await getLiveNotifications("partial-malformed");
    expect(result.notifications).toHaveLength(3);
    expect(result.notifications[0].id).toBe("synthetic:new-soc:run:start");
    expect(result.error).toContain("ChatMate activity unavailable");
  });

  it("ignores malformed history and unsafe cached destinations", async () => {
    vi.mocked(chatmateService.listRuns).mockRejectedValue(new Error("offline"));
    const key = notificationHistoryKey("bad", "chatmate");
    localStorage.setItem(key, "not json");
    expect((await getLiveNotifications("bad")).notifications).toEqual([]);
    localStorage.setItem(key, JSON.stringify([null, {}, { id: "chatmate:x:run:end", title: "bad", detail: "bad", occurredAt: "bad", timestamp: 1, href: "javascript:alert(1)" }]));
    expect((await getLiveNotifications("bad")).notifications).toEqual([]);
  });

  it("does not resurrect phantom IDs cached by the earlier malformed-row bug during an outage", async () => {
    vi.mocked(chatmateService.listRuns).mockRejectedValue(new Error("offline"));
    const cached = ["undefined", "null", "real-run"].map((id) => ({
      id: `chatmate:${id}:run:start`, title: "Saved activity", detail: "Saved activity", occurredAt: "Date not recorded",
      timestamp: 1, href: `/assessments/chatmate?run=${id}`, read: false,
    }));
    localStorage.setItem(notificationHistoryKey("reader", "chatmate"), JSON.stringify(cached));
    const result = await getLiveNotifications("reader");
    expect(result.notifications.map((item) => item.id)).toEqual(["chatmate:real-run:run:start"]);
    expect(result.error).toContain("out of date");
  });

  it("orders by exact seconds across sources and shows unknown terminal dates truthfully", async () => {
    vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun({ completed_at: "2026-10-15T12:00:01Z" })]);
    vi.mocked(platformService.listAssessments).mockResolvedValue([{ id: "local", targetName: "Local", name: "Local", status: "COMPLETED", createdAt: "2026-10-15T11:00:00Z", completedAt: "2026-10-15T12:00:02Z" } as Assessment]);
    const result = await getLiveNotifications("dates");
    expect(result.notifications[0].id).toBe("browser:local:run:end");
    expect(result.notifications[1].id).toBe("chatmate:chatmate-1:run:end");
    expect(projectNotifications([], [evaluatedRun({ completed_at: null })]).notifications.find((item) => item.id.endsWith(":end"))?.occurredAt).toBe("Date not recorded");
  });

  it("aborts a stalled history read and allows a later refresh to recover", async () => {
    vi.useFakeTimers();
    try {
      let signal: AbortSignal | undefined;
      vi.mocked(chatmateService.listRuns).mockImplementationOnce((received) => { signal = received; return new Promise(() => {}); });
      const pending = getLiveNotifications("timeout");
      await vi.advanceTimersByTimeAsync(10000);
      expect((await pending).error).toContain("ChatMate activity unavailable");
      expect(signal?.aborted).toBe(true);
      vi.mocked(chatmateService.listRuns).mockResolvedValue([evaluatedRun()]);
      expect((await getLiveNotifications("timeout")).notifications).toHaveLength(2);
    } finally { vi.useRealTimers(); }
  });
});
