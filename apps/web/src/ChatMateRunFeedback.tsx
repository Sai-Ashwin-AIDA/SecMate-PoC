import { useEffect, useState } from "react";
import type { ChatMateRunRecord } from "./chatmateService";
import { chatMateDate, chatMateSafeDiagnostic } from "./chatmateDisplay";

export function ChatMateConfirmation({ title, description, confirmLabel, cancelLabel, busy, onConfirm, onCancel }: {
  title: string; description: string; confirmLabel: string; cancelLabel: string; busy: boolean;
  onConfirm: () => void; onCancel: () => void;
}) {
  return <div className="chatmate-confirmation" role="group" aria-label={title}>
    <div><strong>{title}</strong><p>{description}</p></div>
    <div className="chatmate-action-group">
      <button className="secondary-action" disabled={busy} onClick={onCancel} type="button">{cancelLabel}</button>
      <button className="danger-action" disabled={busy} onClick={onConfirm} type="button">{busy ? "Working..." : confirmLabel}</button>
    </div>
  </div>;
}

export function ChatMateDiagnostics({ run }: { run: ChatMateRunRecord }) {
  const entries = run.logs.slice(-12);
  if (!entries.length) return null;
  return <details className="chatmate-diagnostics">
    <summary>Run diagnostics <span>Latest {entries.length} entries</span></summary>
    <ol>{entries.map((entry, index) => <li key={index}>
      <div><time>{chatMateDate(entry.timestamp)}</time><span>{entry.level}</span></div>
      <pre>{chatMateSafeDiagnostic(entry.message)}</pre>
    </li>)}</ol>
    {run.logs.length > entries.length && <small>Showing the latest 12 entries. Diagnostic messages are truncated and credentials are redacted.</small>}
  </details>;
}

export function ChatMatePollingMessage({ since }: { since: string | null; polling?: boolean }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [since]);
  const seconds = since ? Math.max(0, Math.floor((now - Date.parse(since)) / 1000)) : NaN;
  const elapsed = Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed` : "";
  return elapsed ? <small className="chatmate-polling">{elapsed}</small> : null;
}
