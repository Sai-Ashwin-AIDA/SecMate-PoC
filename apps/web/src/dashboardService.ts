import { platformService } from "./platformService";
import { getLiveNotifications, markNotificationsRead } from "./notificationService";
import type { NotificationSnapshot } from "./notificationService";
import { targetProjectionService } from "./targetProjectionService";
export type { Notification, NotificationSnapshot } from "./notificationService";

export type DateRange = "7" | "30" | "90";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type TargetRisk = "Critical" | "High" | "Medium" | "Low" | "Unrated";
export type AssessmentStatus = "Running" | "Completed" | "Failed" | "Cancelled" | "Rejected" | "Abandoned" | "Draft" | "Inconclusive" | "Not assessed";
export type DashboardMetric = { id: "assessments" | "active" | "pass-rate" | "exceptions"; label: string; value: string; detail: string; tone: "critical" | "default" | "positive" | "warning" };
export type TrendPoint = { label: string; passRate: number | null; total: number; assessments: number; evaluated: number };
export type TargetRiskRow = { id: string; name: string; description: string; owner: string; risk: TargetRisk; outcomes: number; lastAssessed: string; status: AssessmentStatus; href: string };
export type ActivityItem = { id: string; tone: "critical" | "completed" | "onboarded"; title: string; detail: string; occurredAt: string; href: string | null };
export type SeverityData = { available: false; counts: null } | { available: true; counts: Record<Severity, number> };
export type DashboardData = { range: DateRange; generatedAt: string; isStale: boolean; metrics: DashboardMetric[]; trend: TrendPoint[]; severity: SeverityData; targets: TargetRiskRow[]; activity: ActivityItem[]; hasActiveRuns: boolean; hasActiveRunsInRange: boolean };
export type SearchResult = { id: string; type: "Target" | "Finding"; title: string; description: string; href: string };
export interface DashboardService {
  getDashboard(range: DateRange, signal?: AbortSignal): Promise<DashboardData>;
  search(query: string): Promise<SearchResult[]>;
  getNotifications(user: string): Promise<NotificationSnapshot>;
  markNotificationRead(user: string, id: string): void;
  markAllNotificationsRead(user: string, ids: string[]): void;
}

type Counts = {
  total: number; assessments: number; drafts: number; smoke_tests: number; active: number; completed: number; evaluated: number;
  conclusive: number; resisted: number; compromised: number; inconclusive: number; failed: number; cancelled: number; rejected: number; abandoned: number;
};
type RunSummary = {
  id: string; run_id: string; kind: "ASSESSMENT" | "DRAFT" | "SMOKE_TEST"; family: "DEEPTEAM" | "LEGACY_CHATMATE" | "SYNTHETIC_CHATMATE_SMOKE";
  target_id: string | null; target_name: string; target_owner: string | null; status: string; outcome: string | null; evaluated: boolean; timestamp: string;
};
type TargetSummary = { target_id: string; target_name: string; target_owner: string | null; counts: Counts; latest: RunSummary | null };
type ConsoleTrend = Counts & { label: string; pass_rate: number | null };
type ConsoleSnapshot = {
  schema_version: string; generated_at: string; range: { days: number; start: string; end: string; timezone: string };
  has_active_runs: boolean; has_active_runs_in_range: boolean; counts: Counts; pass_rate: number | null;
  finding_severity: SeverityData; targets: Record<string, TargetSummary>; trend: ConsoleTrend[]; activity: RunSummary[];
};

const ACTIVE = new Set(["VALIDATING", "QUEUED", "PLANNING", "RUNNING", "VERIFYING", "FINALIZING", "CANCEL_REQUESTED", "GENERATING", "AWAITING_SELECTION", "AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING"]);
const terminalStatus = (value: string): AssessmentStatus => {
  if (ACTIVE.has(value)) return "Running";
  if (value === "DRAFT") return "Draft";
  if (value === "FAILED" || value === "TIMED_OUT") return "Failed";
  if (value === "CANCELLED") return "Cancelled";
  if (value === "REJECTED") return "Rejected";
  if (value === "ABANDONED") return "Abandoned";
  return "Completed";
};
const formatUtcDay = (value: string) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(match[2]) - 1] ?? match[2]} ${Number(match[3])}`;
};
const formatTimestamp = (value: string) => Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString(undefined, { timeZone: "UTC", year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })
  : "Date not recorded";
const activityHref = (run: RunSummary): string | null => {
  if (run.family === "DEEPTEAM" && run.kind === "ASSESSMENT") return `/reports?live=${encodeURIComponent(run.run_id)}`;
  if (run.family === "DEEPTEAM" && run.kind === "DRAFT") return `/assessments?linked=${encodeURIComponent(run.run_id)}`;
  if (run.family === "LEGACY_CHATMATE") return run.evaluated
    ? `/reports?chatmate=${encodeURIComponent(run.run_id)}`
    : `/assessments/chatmate?run=${encodeURIComponent(run.run_id)}`;
  if (run.kind === "SMOKE_TEST" && run.target_id) return `/targets?id=${encodeURIComponent(run.target_id)}`;
  return null;
};

function normalizeActivity(value: Record<string, unknown>): RunSummary {
  return {
    id: String(value.id ?? value.activity_id ?? ""), run_id: String(value.run_id ?? ""), kind: value.kind as RunSummary["kind"], family: value.family as RunSummary["family"],
    target_id: value.target_id == null ? null : String(value.target_id), target_name: String(value.target_name ?? value.target_id ?? "Unknown target"),
    target_owner: value.target_owner == null ? null : String(value.target_owner), status: String(value.status ?? ""), outcome: value.outcome == null ? null : String(value.outcome),
    evaluated: value.evaluated === true, timestamp: String(value.timestamp ?? value.occurred_at ?? ""),
  };
}

function normalizeSeverity(value: unknown): SeverityData {
  if (!value || typeof value !== "object" || (value as { available?: unknown }).available !== true) return { available: false, counts: null };
  const raw = (value as { counts?: unknown }).counts;
  if (!raw || typeof raw !== "object") return { available: false, counts: null };
  const counts = raw as Record<string, unknown>;
  const read = (name: Severity) => Number(counts[name] ?? counts[name.toLowerCase()]);
  const normalized = { CRITICAL: read("CRITICAL"), HIGH: read("HIGH"), MEDIUM: read("MEDIUM"), LOW: read("LOW") };
  return Object.values(normalized).every(count => Number.isFinite(count) && count >= 0)
    ? { available: true, counts: normalized }
    : { available: false, counts: null };
}

function normalizeSnapshot(value: ConsoleSnapshot & Record<string, unknown>): ConsoleSnapshot {
  if (!value || value.schema_version !== "console-summary-v2" || !value.counts || !value.targets || !Array.isArray(value.trend) || !Array.isArray(value.activity)) {
    throw new Error("The dashboard service returned an unsupported console summary.");
  }
  const targets = Object.fromEntries(Object.entries(value.targets).map(([id, item]) => {
    const wire = item as TargetSummary & { latest_activity?: Record<string, unknown> };
    const latest = wire.latest ?? wire.latest_activity;
    return [id, { ...wire, target_id: wire.target_id || id, latest: latest ? normalizeActivity(latest as unknown as Record<string, unknown>) : null }];
  }));
  const trend = value.trend.map(item => {
    const wire = item as unknown as { label?: string; date?: string; counts?: Counts; pass_rate: number | null };
    return { ...(wire.counts ?? item), label: wire.label ?? wire.date ?? "", pass_rate: wire.pass_rate } as ConsoleTrend;
  });
  return {
    ...value,
    has_active_runs: value.has_active_runs ?? value.has_active_runs_global === true,
    finding_severity: normalizeSeverity(value.finding_severity),
    targets,
    trend,
    activity: value.activity.map(item => normalizeActivity(item as unknown as Record<string, unknown>)),
  };
}

export const dashboardService: DashboardService = {
  async getDashboard(range, signal) {
    const [projectedTargets, response] = await Promise.all([
      targetProjectionService.list(signal),
      fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/console-summary?days=${range}`, { cache: "no-store", signal }),
    ]);
    if (!response.ok) throw new Error(`Unable to refresh assessment metrics (HTTP ${response.status}).`);
    const snapshot = normalizeSnapshot(await response.json() as ConsoleSnapshot & Record<string, unknown>);
    const counts = snapshot.counts;
    const passRate = snapshot.pass_rate;
    const exceptions = counts.failed + counts.cancelled;
    const assessmentDetail = [`${counts.drafts} draft${counts.drafts === 1 ? "" : "s"}`, ...(counts.smoke_tests ? [`${counts.smoke_tests} smoke test${counts.smoke_tests === 1 ? "" : "s"}`] : [])].join(" · ");

    const summaries = new Map<string, TargetSummary>();
    Object.entries(snapshot.targets).forEach(([key, summary]) => summaries.set(summary.target_id || key, summary));
    const rows = new Map<string, { id: string; name: string; owner: string | null; purpose: string; projected: boolean }>();
    projectedTargets.forEach(target => rows.set(target.id, { id: target.id, name: target.name, owner: target.owner, purpose: target.purpose, projected: true }));
    summaries.forEach((summary, id) => {
      if (!rows.has(id)) rows.set(id, { id, name: summary.target_name || id, owner: summary.target_owner, purpose: "Legacy non-projected assessment scope", projected: false });
    });

    return {
      range, generatedAt: snapshot.generated_at, isStale: false, hasActiveRuns: snapshot.has_active_runs,
      hasActiveRunsInRange: snapshot.has_active_runs_in_range,
      metrics: [
        { id: "assessments", label: "Assessments", value: String(counts.assessments), detail: assessmentDetail, tone: "default" },
        { id: "active", label: "Active work", value: String(counts.active), detail: `${counts.completed} completed in range`, tone: counts.active ? "warning" : "default" },
        { id: "pass-rate", label: "Assessment pass rate", value: passRate == null ? "No evaluated results" : `${passRate}%`, detail: `${counts.resisted} resisted · ${counts.compromised} compromised · ${counts.inconclusive} inconclusive`, tone: passRate == null ? "default" : "positive" },
        { id: "exceptions", label: "Lifecycle exceptions", value: String(exceptions), detail: `${counts.failed} failed · ${counts.cancelled} cancelled`, tone: exceptions ? "critical" : "default" },
      ],
      trend: counts.total === 0 ? [] : snapshot.trend.map(point => ({ label: formatUtcDay(point.label), passRate: point.pass_rate, total: point.total, assessments: point.assessments, evaluated: point.evaluated })),
      severity: snapshot.finding_severity,
      targets: [...rows.values()].map(target => {
        const summary = summaries.get(target.id);
        return {
          id: target.id, name: target.name, description: target.projected ? target.purpose : `${target.purpose}.`, owner: target.owner?.trim() || "Not specified",
          risk: "Unrated" as const, outcomes: summary?.counts.evaluated ?? 0, lastAssessed: summary?.latest ? formatTimestamp(summary.latest.timestamp) : "Not assessed in period",
           status: summary?.latest ? terminalStatus(summary.latest.status) : "Not assessed",
           href: target.projected ? `/targets?id=${encodeURIComponent(target.id)}` : target.id === "legacy-chatmate-manual" ? "/assessments/chatmate" : "/assessments",
        };
      }).sort((a, b) => b.outcomes - a.outcomes || a.name.localeCompare(b.name)),
      activity: snapshot.activity.slice(0, 3).map(run => ({
        id: run.id,
        tone: run.status === "FAILED" || run.status === "TIMED_OUT" ? "critical" : ACTIVE.has(run.status) ? "onboarded" : "completed",
        title: run.kind === "DRAFT" ? `${run.target_name} linked assessment draft` : `${run.target_name} ${run.kind === "SMOKE_TEST" ? "smoke test" : "assessment"} ${run.status.toLowerCase().replaceAll("_", " ")}`,
        detail: `${run.target_owner?.trim() || "Owner not specified"}${run.evaluated && run.outcome ? ` · ${run.outcome.toLowerCase().replaceAll("_", " ")}` : ""}`,
        occurredAt: formatTimestamp(run.timestamp), href: activityHref(run),
      })),
    };
  },
  async search(query) {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return [];
    const [targets, findings] = await Promise.all([targetProjectionService.list(), platformService.listFindings()]);
    const items: SearchResult[] = [
      ...targets.map(target => ({ id: `target:${target.id}`, type: "Target" as const, title: target.name, description: `${target.purpose} / ${target.owner?.trim() || "Not specified"}`, href: `/targets?id=${encodeURIComponent(target.id)}` })),
      ...findings.map(finding => ({ id: `finding:${finding.id}`, type: "Finding" as const, title: finding.title, description: `${finding.targetName} / ${finding.severity}`, href: `/findings?id=${encodeURIComponent(finding.id)}` })),
    ];
    return items.filter(item => `${item.title} ${item.description} ${item.type}`.toLowerCase().includes(normalized));
  },
  getNotifications: getLiveNotifications,
  markNotificationRead: (user, id) => markNotificationsRead(user, [id]),
  markAllNotificationsRead: markNotificationsRead,
};
