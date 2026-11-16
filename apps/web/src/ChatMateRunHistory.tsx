import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { chatmateService } from "./chatmateService";
import type { ChatMateRunRecord } from "./chatmateService";
import { chatMateAttackName, chatMateDate, chatMateRunReference, chatMateStatusLabel, chatMateGenerationFailed } from "./chatmateDisplay";
import { RUNS_CHANGED } from "./assessmentSession";
import { ChatMateConfirmation } from "./ChatMateRunFeedback";
import { chatMateReportLink, eligibleChatMateResult } from "./chatmateProjections";

export function ChatMateRunHistory() {
  const [runs, setRuns] = useState<ChatMateRunRecord[]>([]);
  const [dateRange, setDateRange] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const filteredRuns = runs.filter((item) => (dateRange === "all" || Date.parse(item.created_at) >= Date.now() - Number(dateRange) * 86400000)
    && (outcome === "all" || (outcome === "active" ? !["COMPLETED", "FAILED", "REJECTED", "ABANDONED"].includes(item.status) : outcome === "FAILED" ? item.status === "FAILED" || item.final_status === "ERROR" : item.final_status === outcome)));
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const mounted = useRef(false);
  const pending = useRef(false);
  const loadVersion = useRef(0);
  const fetching = useRef(false);

  const refresh = async (silent = false) => {
    if (fetching.current) return;
    fetching.current = true;
    const version = ++loadVersion.current;
    if (!silent) setLoading(true);
    setError("");
    try {
      const items = await chatmateService.listRuns();
      if (!Array.isArray(items)) throw new Error("Invalid ChatMate history response.");
      if (mounted.current && version === loadVersion.current) setRuns([...items].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    } catch (reason) {
      if (mounted.current && version === loadVersion.current) setError(reason instanceof Error ? reason.message : "Unable to load run history.");
    } finally {
      if (version === loadVersion.current) fetching.current = false;
      if (mounted.current && version === loadVersion.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const visible = () => { if (document.visibilityState !== "hidden" && !pending.current) void refresh(true); };
    const timer = window.setInterval(visible, 3000);
    window.addEventListener("focus", visible);
    window.addEventListener(RUNS_CHANGED, visible);
    document.addEventListener("visibilitychange", visible);
    return () => { mounted.current = false; loadVersion.current += 1; fetching.current = false; window.clearInterval(timer); window.removeEventListener("focus", visible); window.removeEventListener(RUNS_CHANGED, visible); document.removeEventListener("visibilitychange", visible); };
  }, []);

  const remove = async (id: string) => {
    if (pending.current) return;
    pending.current = true;
    setDeleting(true);
    setDeleteError("");
    setNotice("");
    try {
      await chatmateService.deleteRun(id);
      if (!mounted.current) return;
      setRuns((items) => items.filter((item) => item.run_id !== id));
      setConfirmId(null);
      setNotice("Run deleted.");
      await refresh();
    } catch (reason) {
      if (mounted.current) setDeleteError(reason instanceof Error ? reason.message : "Unable to delete this run. Please try again.");
    } finally {
      pending.current = false;
      if (mounted.current) setDeleting(false);
    }
  };

  return <section className="chatmate-history report-history" aria-label="ChatMate run history">
    <button className="chatmate-history-toggle" aria-expanded={expanded} aria-controls="chatmate-history-list" onClick={() => setExpanded((value) => !value)} type="button">
      <div><span>Previous assessments</span><h3>Run history</h3><small>Resume an assessment or review a previous run.</small></div>
      <div><strong>{runs.length}</strong><svg aria-hidden="true" fill="none" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg></div>
    </button>
    <div id="chatmate-history-list" hidden={!expanded}>
      <div className="chatmate-history-filters"><label>Date<select value={dateRange} onChange={(event) => setDateRange(event.target.value)}><option value="all">All dates</option><option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select></label><label>Outcome<select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="all">All outcomes</option><option value="COMPROMISED">Policy violation detected</option><option value="RESISTED">Boundary resisted</option><option value="INCONCLUSIVE">Inconclusive</option><option value="FAILED">Failed</option><option value="active">Drafts / active</option></select></label><span>{filteredRuns.length} of {runs.length} runs</span></div>
      {loading && <p className="chatmate-history-message" role="status">Loading run history...</p>}
      {error && <div className="inline-error" role="alert">History unavailable: {error}. You can still configure a new assessment. <button className="secondary-action" onClick={() => void refresh()} type="button">Retry history</button></div>}
      {notice && <p className="chatmate-history-message" role="status">{notice}</p>}
      {!loading && !error && !runs.length && <p className="chatmate-history-message">No previous runs found.</p>}
      {!loading && !error && runs.length > 0 && !filteredRuns.length && <p className="chatmate-history-message">No runs match these filters.</p>}
      {filteredRuns.map((item) => <article className="chatmate-history-row" key={item.run_id}>
        <div className="chatmate-history-main"><strong>{chatMateAttackName(item)}</strong><small>{chatMateRunReference(item.run_id)}</small>{item.parent_run_id && item.status === "DRAFT" && <><small>Follow-up draft</small>{item.follow_up_objective && <small title={item.follow_up_objective}>{item.follow_up_objective.length > 160 ? `${item.follow_up_objective.slice(0, 160)}…` : item.follow_up_objective}</small>}</>}<details><summary>View details</summary><code>{item.run_id}</code>{item.parent_run_id && <p>Parent assessment: <Link to={`/assessments/chatmate?run=${encodeURIComponent(item.parent_run_id)}`}>{chatMateRunReference(item.parent_run_id)}</Link></p>}</details></div>
        <span className={`chatmate-status-badge ${item.status === "FAILED" || item.final_status === "ERROR" ? "failed" : (item.final_status ?? item.status).toLowerCase()}`}>{item.status === "FAILED" ? chatMateStatusLabel(item) : item.final_status === "COMPROMISED" ? "Policy violation detected" : item.final_status === "RESISTED" ? "Boundary resisted" : item.final_status === "INCONCLUSIVE" ? "Inconclusive" : chatMateStatusLabel(item)}</span>
        <time dateTime={item.created_at}>{chatMateDate(item.created_at)}</time>
        <div className="chatmate-action-group">
          <Link className="secondary-action" aria-label={`${item.status === "DRAFT" && item.parent_run_id ? "Configure follow-up" : ["COMPLETED", "FAILED", "REJECTED", "ABANDONED"].includes(item.status) ? "View assessment" : "Resume assessment"} ${chatMateAttackName(item)} ${chatMateRunReference(item.run_id)}`} to={`/assessments/chatmate?run=${encodeURIComponent(item.run_id)}`}>{item.status === "DRAFT" && item.parent_run_id ? "Configure follow-up" : ["COMPLETED", "FAILED", "REJECTED", "ABANDONED"].includes(item.status) ? "View assessment" : "Resume assessment"}</Link>
          {(eligibleChatMateResult(item) || chatMateGenerationFailed(item)) && <Link className="secondary-action" to={chatMateReportLink(item.run_id)}>View report</Link>}
          <button className="chatmate-tertiary-action" aria-label={`Delete ${chatMateAttackName(item)} ${chatMateRunReference(item.run_id)}`} disabled={deleting} onClick={() => { setConfirmId(item.run_id); setDeleteError(""); setNotice(""); }} type="button"><svg aria-hidden="true" fill="none" viewBox="0 0 24 24"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6m4-6v6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>Delete</button>
        </div>
        {confirmId === item.run_id && <div className="chatmate-history-confirm">
          <ChatMateConfirmation title="Delete this run?" description={`Permanently delete ${chatMateRunReference(item.run_id)} and its saved evidence. Active runs must finish or be ended before they can be deleted.`} confirmLabel="Confirm delete run" cancelLabel="Cancel delete" busy={deleting} onConfirm={() => void remove(item.run_id)} onCancel={() => { setConfirmId(null); setDeleteError(""); }} />
          {deleteError && <div className="inline-error" role="alert">{deleteError}</div>}
        </div>}
      </article>)}
    </div>
  </section>;
}
