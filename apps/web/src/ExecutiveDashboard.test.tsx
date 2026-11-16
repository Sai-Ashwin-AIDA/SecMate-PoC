import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExecutiveDashboard } from "./App";
import { dashboardService } from "./dashboardService";
import type { DashboardData, DateRange } from "./dashboardService";

const data = (range: DateRange, extra: Partial<DashboardData> = {}): DashboardData => ({
  range, generatedAt: `2026-10-0${range === "7" ? "1" : range === "30" ? "2" : "3"}T12:00:00Z`, isStale: false,
  hasActiveRuns: false, hasActiveRunsInRange: false,
  metrics: [
    { id: "assessments", label: "Assessments", value: range, detail: "0 drafts", tone: "default" },
    { id: "active", label: "Active work", value: "0", detail: "0 completed in range", tone: "default" },
    { id: "pass-rate", label: "Assessment pass rate", value: "No evaluated results", detail: "0 resisted · 0 compromised · 0 inconclusive", tone: "default" },
    { id: "exceptions", label: "Lifecycle exceptions", value: "0", detail: "0 failed · 0 cancelled", tone: "default" },
  ],
  trend: [], severity: { available: false, counts: null }, targets: [], activity: [], ...extra,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function Location() { const location = useLocation(); return <output aria-label="Location">{location.pathname}{location.search}</output>; }
const show = () => render(<MemoryRouter initialEntries={["/dashboard"]}><ExecutiveDashboard /><Location /></MemoryRouter>);

describe("ExecutiveDashboard refresh behavior", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it("clears the old range and suppresses an out-of-order range response", async () => {
    const seven = deferred<DashboardData>();
    const ninety = deferred<DashboardData>();
    vi.spyOn(dashboardService, "getDashboard").mockImplementation(async range => range === "30" ? data("30") : range === "7" ? seven.promise : ninety.promise);
    show();
    await screen.findByText("30", { selector: ".metric-card > strong" });
    fireEvent.change(screen.getByLabelText("Dashboard time period"), { target: { value: "7" } });
    expect(screen.queryByText("30", { selector: ".metric-card > strong" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Dashboard time period"), { target: { value: "90" } });
    seven.resolve(data("7"));
    ninety.resolve(data("90"));
    expect(await screen.findByText("90", { selector: ".metric-card > strong" })).toBeVisible();
    expect(screen.queryByText("7", { selector: ".metric-card > strong" })).not.toBeInTheDocument();
  });

  it("queues one focus refresh received during an in-flight request", async () => {
    const first = deferred<DashboardData>();
    const service = vi.spyOn(dashboardService, "getDashboard").mockReturnValueOnce(first.promise).mockResolvedValue(data("30"));
    show();
    act(() => { window.dispatchEvent(new Event("focus")); window.dispatchEvent(new Event("focus")); });
    expect(service).toHaveBeenCalledTimes(1);
    first.resolve(data("30"));
    await waitFor(() => expect(service).toHaveBeenCalledTimes(2));
  });

  it("polls active work and stops the fast poll after it becomes terminal", async () => {
    vi.useFakeTimers();
    const service = vi.spyOn(dashboardService, "getDashboard")
      .mockResolvedValueOnce(data("30", { hasActiveRuns: true, hasActiveRunsInRange: true }))
      .mockResolvedValue(data("30"));
    show();
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(service).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(1500); await Promise.resolve(); await Promise.resolve(); });
    expect(service).toHaveBeenCalledTimes(2);
    await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); });
    expect(service).toHaveBeenCalledTimes(2);
  });

  it("hides snapshot metadata and renders a count-only activity graph with a separate legend", async () => {
    vi.spyOn(dashboardService, "getDashboard").mockResolvedValue(data("30", {
      metrics: [
        { id: "assessments", label: "Assessments", value: "19", detail: "1 draft", tone: "default" },
        { id: "active", label: "Active work", value: "0", detail: "13 completed in range", tone: "default" },
        { id: "pass-rate", label: "Assessment pass rate", value: "100%", detail: "13 resisted · 0 compromised · 0 inconclusive", tone: "positive" },
        { id: "exceptions", label: "Lifecycle exceptions", value: "6", detail: "6 failed · 0 cancelled", tone: "critical" },
      ],
      trend: [{ label: "Nov 14", passRate: 100, total: 3, assessments: 3, evaluated: 3 }, { label: "Nov 15", passRate: 100, total: 7, assessments: 7, evaluated: 7 }],
    }));
    const { container } = show();

    expect(await screen.findByRole("img", { name: "Assessments run by day" })).toBeInTheDocument();
    expect(screen.getByText("Assessments run")).toBeInTheDocument();
    expect(screen.getByText("Pass rate")).toBeInTheDocument();
    expect(container.querySelectorAll(".chart-y-axis span")).toHaveLength(3);
    expect([...container.querySelectorAll(".chart-y-axis span")].map((node) => node.textContent)).toEqual(["10", "5", "0"]);
    expect(container.querySelector(".activity-line")).toBeInTheDocument();
    expect(screen.queryByText(/Server snapshot|Generated .* UTC|dashed line is total activity/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/smoke tests|rejected|abandoned/i)).not.toBeInTheDocument();
  });

  it("shows only three recent activities and a compact four-column target table", async () => {
    vi.spyOn(dashboardService, "getDashboard").mockResolvedValue(data("30", {
      targets: [{ id: "target", name: "Synthetic ChatMate", description: "Long internal target description", owner: "AIDA", risk: "Unrated", outcomes: 7, lastAssessed: "Nov 15", status: "Completed", href: "/targets?id=target" }],
      activity: Array.from({ length: 5 }, (_, index) => ({ id: `activity-${index}`, tone: "completed" as const, title: `Activity ${index + 1}`, detail: "AIDA", occurredAt: "Nov 15", href: `/reports?live=${index}` })),
    }));
    const { container } = show();

    expect(await screen.findByRole("heading", { name: "Target activity overview" })).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual(["Target", "Evaluated outcomes", "Latest activity", "Status"]);
    expect(within(table).queryByText("Owner")).not.toBeInTheDocument();
    expect(within(table).queryByText("Risk")).not.toBeInTheDocument();
    expect(within(table).queryByText("Long internal target description")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".risk-table-card colgroup col")).toHaveLength(4);
    expect(container.querySelectorAll(".activity-list > *")).toHaveLength(3);
    expect(screen.getByText("Activity 1")).toBeInTheDocument();
    expect(screen.getByText("Activity 3")).toBeInTheDocument();
    expect(screen.queryByText("Activity 4")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open assessment history/ })).toBeInTheDocument();
  });

  it("shows stale errors, refreshes deleted data, and navigates canonical targets and mixed activity", async () => {
    const populated = data("30", {
      targets: [{ id: "canonical", name: "Canonical", description: "Authoritative", owner: "Not specified", risk: "Unrated", outcomes: 1, lastAssessed: "Oct 1, 2026", status: "Completed", href: "/targets?id=canonical" }],
      activity: [{ id: "legacy:one", tone: "completed", title: "ChatMate assessment completed", detail: "Owner not specified", occurredAt: "Oct 1", href: "/reports?chatmate=one" }],
    });
    const service = vi.spyOn(dashboardService, "getDashboard").mockResolvedValueOnce(populated).mockRejectedValueOnce(new Error("offline")).mockResolvedValue(data("30"));
    show();
    await screen.findByText("Canonical");
    act(() => window.dispatchEvent(new Event("focus")));
    expect(await screen.findByText(/Showing the last available snapshot/)).toBeVisible();
    expect(screen.queryByText("Stale snapshot")).not.toBeInTheDocument();
    act(() => window.dispatchEvent(new Event("secmate:data-changed")));
    await waitFor(() => expect(screen.queryByText("Canonical")).not.toBeInTheDocument());
    expect(screen.getByText("No targets")).toBeVisible();
    service.mockResolvedValue(populated);
    act(() => window.dispatchEvent(new Event("secmate:data-changed")));
    await screen.findByText("Canonical");
    fireEvent.click(screen.getByRole("button", { name: /ChatMate assessment completed/ }));
    expect(screen.getByLabelText("Location")).toHaveTextContent("/reports?chatmate=one");
    fireEvent.click(screen.getByRole("link", { name: "Open Canonical" }));
    expect(screen.getByLabelText("Location")).toHaveTextContent("/targets?id=canonical");
  });
});
