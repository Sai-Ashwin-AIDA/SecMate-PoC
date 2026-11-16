import type { ReactNode } from "react";

export function ConsoleDetails({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return <details className={`console-details ${className}`}><summary>{title}</summary><div className="console-details-content">{children}</div></details>;
}

export function HistoryFilters({ date, onDateChange, outcome, onOutcomeChange, source, onSourceChange, liveLabel = "Live assessment" }: {
  date: string; onDateChange: (value: string) => void;
  outcome: string; onOutcomeChange: (value: string) => void;
  source?: string; onSourceChange?: (value: string) => void;
  liveLabel?: string;
}) {
  return <div className="console-history-filters" role="group" aria-label="History filters">
    <label>Date<select value={date} onChange={(event) => onDateChange(event.target.value)}><option value="all">All dates</option><option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label>
    <label>Outcome<select value={outcome} onChange={(event) => onOutcomeChange(event.target.value)}><option value="all">All outcomes</option><option value="violation">Policy violation detected</option><option value="resisted">Boundary resisted</option><option value="inconclusive">Inconclusive</option><option value="incomplete">Assessment incomplete</option><option value="active">In progress</option><option value="cancelled">Cancelled</option></select></label>
    {onSourceChange && <label>Source<select value={source} onChange={(event) => onSourceChange(event.target.value)}><option value="all">All sources</option><option value="chatmate">ChatMate</option><option value="live">{liveLabel}</option><option value="summary">Summary report</option></select></label>}
  </div>;
}

export function matchesHistoryDate(value: string | null | undefined, range: string) {
  if (range === "all") return true;
  const timestamp = value ? Date.parse(value) : NaN;
  return Number.isFinite(timestamp) && timestamp >= Date.now() - Number(range) * 86400000;
}

export function outcomeKey(value: string | null | undefined) {
  if (["COMPROMISED", "CRITICAL_RISK_DETECTED"].includes(value ?? "")) return "violation";
  if (["RESISTED", "PASS"].includes(value ?? "")) return "resisted";
  if (["INCONCLUSIVE", "ASSESSMENT_INCONCLUSIVE"].includes(value ?? "")) return "inconclusive";
  if (["ERROR", "FAILED", "HARNESS_ERROR"].includes(value ?? "")) return "incomplete";
  if (value === "CANCELLED") return "cancelled";
  if (["RUNNING", "QUEUED", "CANCEL_REQUESTED"].includes(value ?? "")) return "active";
  return "other";
}
