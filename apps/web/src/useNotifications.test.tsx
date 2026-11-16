import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dashboardService } from "./dashboardService";
import type { NotificationSnapshot } from "./dashboardService";
import { notificationReadKey } from "./notificationService";
import { useNotifications } from "./useNotifications";

const snapshot = (id = "chatmate:run:evaluation:COMPLETED", active = false): NotificationSnapshot => ({
  notifications: [{ id, title: "ChatMate assessment completed", detail: "Prompt Injection · Boundary resisted", occurredAt: "Oct 8, 2026", href: "/reports?chatmate=run", read: false }],
  hasActiveRuns: active, error: "",
});
const settle = () => act(async () => { await Promise.resolve(); });

describe("live notifications hook", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    vi.spyOn(dashboardService, "getNotifications").mockResolvedValue(snapshot());
  });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it("polls across pages at 5 seconds even without active runs and removes deleted records", async () => {
    const { result, rerender } = renderHook(({ key }) => useNotifications("poll-user", key, false), { initialProps: { key: "targets" } });
    await settle();
    expect(result.current.unreadCount).toBe(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(2);
    expect(result.current.notifications).toHaveLength(1);
    rerender({ key: "findings" });
    await settle();
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(3);
    vi.mocked(dashboardService.getNotifications).mockResolvedValue({ notifications: [], error: "", hasActiveRuns: false });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(result.current.notifications).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
  });

  it("polls at 3 seconds for active generation/evaluation/Critic, then returns to 5 seconds", async () => {
    vi.mocked(dashboardService.getNotifications).mockResolvedValueOnce(snapshot("generating", true));
    const { result } = renderHook(() => useNotifications("active-user", "page", false));
    await settle();
    await act(async () => { await vi.advanceTimersByTimeAsync(2999); });
    expect(dashboardService.getNotifications).toHaveBeenCalledOnce();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(2);
    expect(result.current.notifications[0].id).toContain("COMPLETED");
    await act(async () => { await vi.advanceTimersByTimeAsync(4999); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(3);
  });

  it("refreshes on bell open, navigation, focus and visibility regain without auto-reading", async () => {
    const { result, rerender } = renderHook(({ key, open }) => useNotifications("trigger-user", key, open), { initialProps: { key: "one", open: false } });
    await settle();
    rerender({ key: "one", open: true });
    await settle();
    rerender({ key: "two", open: true });
    await settle();
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(5);
    expect(result.current.unreadCount).toBe(1);
    rerender({ key: "two", open: false });
    await settle();
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(5);
  });

  it("pauses hidden polling and resumes immediately", async () => {
    const visibility = vi.mocked(Object.getOwnPropertyDescriptor(document, "visibilityState")!.get!);
    renderHook(() => useNotifications("visible-user", "page", false));
    await settle();
    visibility.mockReturnValue("hidden");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); window.dispatchEvent(new Event("focus")); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(dashboardService.getNotifications).toHaveBeenCalledOnce();
    visibility.mockReturnValue("visible");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(2);
  });

  it("coalesces refresh storms while in flight and queues one immediate refresh", async () => {
    let resolve!: (value: NotificationSnapshot) => void;
    vi.mocked(dashboardService.getNotifications).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const { result, rerender } = renderHook(({ key }) => useNotifications("pending-user", key, false), { initialProps: { key: "one" } });
    rerender({ key: "two" });
    act(() => { result.current.refresh(); result.current.refresh(); window.dispatchEvent(new Event("focus")); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(dashboardService.getNotifications).toHaveBeenCalledOnce();
    await act(async () => { resolve(snapshot("old")); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(2);
    expect(result.current.notifications[0].id).not.toBe("old");
  });

  it("consumes a queued refresh once after a pending request finishes while hidden", async () => {
    let resolve!: (value: NotificationSnapshot) => void;
    vi.mocked(dashboardService.getNotifications).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const visibility = vi.mocked(Object.getOwnPropertyDescriptor(document, "visibilityState")!.get!);
    const { result } = renderHook(() => useNotifications("queued-hidden-user", "page", false));
    act(() => result.current.refresh());
    visibility.mockReturnValue("hidden");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); resolve(snapshot()); });
    expect(dashboardService.getNotifications).toHaveBeenCalledOnce();
    visibility.mockReturnValue("visible");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(dashboardService.getNotifications).toHaveBeenCalledTimes(2);
  });

  it("ignores stale results after a user change and hides the prior user's data immediately", async () => {
    let resolve!: (value: NotificationSnapshot) => void;
    const { result, rerender } = renderHook(({ user }) => useNotifications(user, "page", false), { initialProps: { user: "old-user" } });
    await settle();
    vi.mocked(dashboardService.getNotifications).mockReturnValueOnce(new Promise((done) => { resolve = done; })).mockResolvedValue(snapshot("new"));
    act(() => result.current.refresh());
    rerender({ user: "new-user" });
    expect(result.current.notifications).toEqual([]);
    await settle();
    expect(result.current.notifications[0].id).toBe("new");
    await act(async () => { resolve(snapshot("stale")); });
    expect(result.current.notifications[0].id).toBe("new");
  });

  it("does not publish or schedule another request after unmount", async () => {
    let resolve!: (value: NotificationSnapshot) => void;
    vi.mocked(dashboardService.getNotifications).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const { unmount } = renderHook(() => useNotifications("unmount-user", "page", false));
    unmount();
    await act(async () => { resolve(snapshot()); window.dispatchEvent(new Event("focus")); await vi.advanceTimersByTimeAsync(10000); });
    expect(dashboardService.getNotifications).toHaveBeenCalledOnce();
  });

  it("keeps explicit reads through polling/remounts without leaking to another user", async () => {
    const first = renderHook(() => useNotifications("read-user", "page", false));
    await settle();
    act(() => first.result.current.markRead(first.result.current.notifications[0].id));
    expect(first.result.current.unreadCount).toBe(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(first.result.current.unreadCount).toBe(0);
    first.unmount();
    const second = renderHook(({ user }) => useNotifications(user, "page", false), { initialProps: { user: "read-user" } });
    await settle();
    expect(second.result.current.unreadCount).toBe(0);
    second.rerender({ user: "other-read-user" });
    await settle();
    expect(second.result.current.unreadCount).toBe(1);
    act(() => second.result.current.markAllRead());
    expect(second.result.current.unreadCount).toBe(0);
  });

  it("does not revert a click's read state when an older request resolves", async () => {
    let resolve!: (value: NotificationSnapshot) => void;
    const { result } = renderHook(() => useNotifications("race-user", "page", false));
    await settle();
    vi.mocked(dashboardService.getNotifications).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    act(() => { result.current.refresh(); result.current.markAllRead(); });
    await act(async () => { resolve(snapshot()); });
    expect(result.current.unreadCount).toBe(0);
  });

  it("synchronizes read changes from another browser tab", async () => {
    const { result } = renderHook(() => useNotifications("storage-user", "page", false));
    await settle();
    const key = notificationReadKey("storage-user");
    window.localStorage.setItem(key, JSON.stringify([result.current.notifications[0].id]));
    act(() => window.dispatchEvent(new StorageEvent("storage", { key })));
    expect(result.current.unreadCount).toBe(0);
  });

  it("exposes partial errors and retains the last snapshot when a later refresh throws", async () => {
    const { result } = renderHook(() => useNotifications("failure-user", "page", false));
    await settle();
    vi.mocked(dashboardService.getNotifications).mockResolvedValue({ ...snapshot("synthetic:live:assessment:RUNNING"), error: "ChatMate activity unavailable." });
    await act(async () => result.current.refresh());
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].id).toContain("synthetic:");
    expect(result.current.error).toContain("ChatMate activity unavailable");
    vi.mocked(dashboardService.getNotifications).mockRejectedValue(new Error("secret=value"));
    await act(async () => result.current.refresh());
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].id).toContain("synthetic:");
    expect(result.current.error).toBe("Notifications unavailable. Saved notifications may be out of date. Retry to refresh.");
    expect(result.current.error).not.toContain("secret=value");
  });
});
