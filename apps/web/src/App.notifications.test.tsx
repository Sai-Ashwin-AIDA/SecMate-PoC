import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { saveSession } from "./auth";
import { chatmateService } from "./chatmateService";
import { modelConnectivityService } from "./modelConnectivityService";
import { platformService } from "./platformService";
import { evaluatedRun } from "./chatmateTestFixtures";
import { notificationReadKey, notificationClearedKey } from "./notificationService";
import { saveTheme } from "./theme";

vi.mock("./ModulePages", () => ({ TargetsPage: () => <p>Targets content</p>, AssessmentsPage: () => <p>Assessments content</p>, FindingsPage: () => <p>Findings content</p>, ReportsPage: () => <p>Reports content</p> }));
vi.mock("./ChatMatePage", () => ({ ChatMatePage: () => <p>ChatMate content</p> }));
vi.mock("./SettingsPage", () => ({ SettingsPage: () => <p>Settings content</p> }));
const settle = () => act(async () => { await Promise.resolve(); });
const bell = (count: number) => screen.getByRole("button", { name: `Notifications, ${count} unread` });
const open = async (count: number) => { fireEvent.click(bell(count)); await settle(); return screen.getByRole("dialog", { name: "Notifications" }); };
const tick = (ms = 3000) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("run notifications in the authenticated shell", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
    saveTheme("secmate-dark");
    window.history.replaceState({}, "", "/targets");
    saveSession({ email: "shell-reader", displayName: "Reader", role: "Local Preview" });
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    vi.spyOn(modelConnectivityService, "listDeepTeamRuns").mockResolvedValue([]);
    vi.spyOn(platformService, "listAssessments").mockResolvedValue([]);
    vi.spyOn(chatmateService, "listRuns").mockResolvedValue([evaluatedRun()]);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Unexpected network request")));
  });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("keeps mark all read in a persistent footer, supports focus wrapping and survives remount", async () => {
    const view = render(<App />);
    await settle();
    const panel = await open(2);
    const announcements = screen.getByRole("status", { name: "Notification updates" });
    expect(announcements).toHaveAttribute("aria-live", "polite");
    expect(announcements).toHaveAttribute("aria-atomic", "true");
    expect(announcements).toHaveTextContent("2 unread run notifications");
    const action = within(panel).getByRole("button", { name: "Mark all read" });
    expect(action.closest("footer")).toHaveAttribute("aria-label", "Notification actions");
    expect(action.closest(".notification-scroll")).toBeNull();
    const close = within(panel).getByRole("button", { name: "Close notifications" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(within(panel).getByRole("button", { name: "Clear history" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.click(action);
    expect(bell(0)).toBeInTheDocument();
    expect(announcements).toHaveTextContent("0 unread run notifications");
    expect(action).toBeDisabled();
    expect(panel).toHaveTextContent("No unread notifications");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(bell(0)).toHaveFocus();
    view.unmount();
    render(<App />);
    await settle();
    await open(0);
    expect(screen.getByText("ChatMate assessment completed")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByText("Targets content"));
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
    expect(bell(0)).toHaveFocus();
    expect(vi.mocked(fetch).mock.calls.every(([url]) => String(url).endsWith("/history-epoch"))).toBe(true);
  });

  it("discovers new runs with the panel closed, ignores phases and Critic, and reads only the clicked end", async () => {
    const history = vi.mocked(chatmateService.listRuns);
    history.mockResolvedValue([]);
    render(<App />); await settle();
    history.mockResolvedValue([evaluatedRun({ status: "GENERATING", final_status: null, completed_at: null })]);
    await tick(5000);
    expect(bell(1)).toBeInTheDocument();
    const panel = await open(1);
    for (const status of ["AWAITING_SELECTION", "AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING"] as const) {
      history.mockResolvedValue([evaluatedRun({ status, final_status: null, completed_at: null })]);
      await tick();
      expect(bell(1)).toBeInTheDocument();
      expect(panel).toHaveTextContent("ChatMate assessment started");
      expect(panel).not.toHaveTextContent("ready for selection");
    }
    history.mockResolvedValue([evaluatedRun({ critic_status: "RUNNING" })]);
    await tick();
    expect(bell(2)).toBeInTheDocument();
    expect(panel).not.toHaveTextContent("Critic");
    fireEvent.click(within(panel).getByRole("button", { name: /ChatMate assessment completed/ }));
    await settle();
    expect(window.location.pathname + window.location.search).toBe("/reports?chatmate=chatmate-1");
    expect(bell(1)).toBeInTheDocument();
  });

  it("retains saved history on error and reload, recovers on reconnect, and respects deletion", async () => {
    const view = render(<App />); await settle();
    vi.mocked(chatmateService.listRuns).mockRejectedValue(new Error("password=hidden"));
    await tick(5000);
    const panel = await open(2);
    expect(within(panel).getByRole("alert")).toHaveTextContent("Saved notifications may be out of date");
    expect(panel).not.toHaveTextContent("password=hidden");
    view.unmount(); render(<App />); await settle();
    expect(bell(2)).toBeInTheDocument();
    vi.mocked(chatmateService.listRuns).mockResolvedValue([]);
    await act(async () => { window.dispatchEvent(new Event("online")); });
    const recovered = await open(0);
    expect(recovered).toHaveTextContent("No notifications.");
    expect(within(recovered).getByRole("button", { name: "Mark all read" })).toBeDisabled();
  });

  it("reacts to local changes, navigation, focus and cross-tab read receipts", async () => {
    render(<App />); await settle();
    const history = vi.mocked(chatmateService.listRuns);
    history.mockResolvedValue([evaluatedRun(), evaluatedRun({ run_id: "new", status: "GENERATING", completed_at: null, final_status: null })]);
    await act(async () => { window.dispatchEvent(new Event(platformService.changeEvent)); });
    expect(bell(3)).toBeInTheDocument();
    const key = `${notificationReadKey("shell-reader")}:chatmate:new:run:start`;
    window.localStorage.setItem(key, "1");
    await act(async () => { window.dispatchEvent(new StorageEvent("storage", { key })); });
    expect(bell(2)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Findings" })); await settle();
    expect(bell(2)).toBeInTheDocument();
    history.mockResolvedValue([]);
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(bell(0)).toBeInTheDocument();
  });

  it("shows initial loading and a reachable disabled footer before histories resolve", async () => {
    let resolve!: (value: ReturnType<typeof evaluatedRun>[]) => void;
    vi.mocked(chatmateService.listRuns).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(<App />);
    await settle();
    const panel = await open(0);
    expect(within(panel).getByRole("status")).toHaveTextContent("Loading notifications");
    expect(within(panel).getByRole("button", { name: "Mark all read" })).toBeDisabled();
    await act(async () => { resolve([evaluatedRun()]); });
    expect(bell(2)).toBeInTheDocument();
  });

  it("clears history across polling/remounts, hides background loading, and still shows future events", async () => {
    const deletion = vi.spyOn(chatmateService, "deleteRun");
    const history = vi.mocked(chatmateService.listRuns);
    const view = render(<App />); await settle();
    const panel = await open(2);
    let resolve!: (value: ReturnType<typeof evaluatedRun>[]) => void;
    history.mockReturnValueOnce(new Promise(done => { resolve = done; }));
    await tick(5000);
    expect(within(panel).queryByText(/Refreshing|Loading notifications/)).not.toBeInTheDocument();
    expect(panel).toHaveTextContent("ChatMate assessment completed");
    fireEvent.click(within(panel).getByRole("button", { name: "Clear history" }));
    expect(bell(0)).toBeInTheDocument();
    expect(panel).toHaveTextContent("No notifications.");
    await act(async () => { resolve([evaluatedRun()]); });
    expect(panel).toHaveTextContent("No notifications.");
    view.unmount(); render(<App />); await settle();
    const restored = await open(0);
    expect(restored).toHaveTextContent("No notifications.");
    expect(within(restored).getByRole("button", { name: "Clear history" })).toBeDisabled();
    history.mockResolvedValue([evaluatedRun(), evaluatedRun({ run_id: "future", status: "GENERATING", completed_at: null, final_status: null })]);
    await tick(5000);
    expect(bell(1)).toBeInTheDocument();
    fireEvent.click(within(restored).getByRole("button", { name: "Clear history" }));
    history.mockResolvedValue([evaluatedRun(), evaluatedRun({ run_id: "future" })]);
    await tick(3000);
    expect(bell(1)).toBeInTheDocument(); // Its new completion is not the dismissed start.
    expect(restored).toHaveTextContent("ChatMate assessment completed");
    expect(deletion).not.toHaveBeenCalled();
  });

  it("respects a notification cleared in another tab after the next poll", async () => {
    render(<App />); await settle();
    const key = `${notificationClearedKey("shell-reader")}:chatmate:chatmate-1:run:start`;
    window.localStorage.setItem(key, "1");
    await act(async () => { window.dispatchEvent(new StorageEvent("storage", { key })); });
    expect(bell(1)).toBeInTheDocument();
    await tick(5000);
    const panel = await open(1);
    expect(panel).toHaveTextContent("ChatMate assessment completed");
    expect(panel).not.toHaveTextContent("ChatMate assessment started");
  });
});
