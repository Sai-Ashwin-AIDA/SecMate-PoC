import { Fragment, useEffect, useId, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { chatmateService } from "./chatmateService";
import type { ChatMateRunRecord } from "./chatmateService";
import { chatMateClassification, chatMateReportLink } from "./chatmateProjections";
import { useChatMateAudit } from "./ChatMateReportPanel";
import { chatMateAttackName, chatMateDate, chatMateRunReference, chatMateStatusLabel } from "./chatmateDisplay";
import { RUNS_CHANGED } from "./assessmentSession";
import { ChatMateJudgeRationale } from "./ChatMateJudgeDetails";

function ChatMateFindingDetail({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { run, parsed, error, retry } = useChatMateAudit(runId);
  return <article className="chatmate-panel" aria-label="ChatMate source finding detail">
    <header><h3>{parsed && run ? chatMateClassification(run)?.label : "Assessment details"}</h3><button className="secondary-action" type="button" onClick={onClose}>Close details</button></header>
    {!parsed && !error && <p role="status">Loading validated Judge details...</p>}
    {error && <div className="inline-error" role="alert"><p>{error}</p><button className="secondary-action" type="button" onClick={retry}>Retry details</button></div>}
    {parsed && <>{parsed.judge ? <><p>Judge-reported confidence: {Math.round(parsed.judge.confidence * 100)}%</p><ChatMateJudgeRationale judge={parsed.judge} /></> : <p>No Judge confidence or rationale is available.</p>}</>}
    <Link className="secondary-action" to={chatMateReportLink(runId)}>View report</Link>
  </article>;
}

export function useChatMateFindings() {
  const [runs, setRuns] = useState<ChatMateRunRecord[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let disposed = false;
    let inFlight = false;
    setError("");
    const load = () => {
      if (inFlight || disposed) return;
      inFlight = true;
      void chatmateService.listRuns().then((items) => {
      if (!Array.isArray(items)) throw new Error("Invalid ChatMate history response.");
      if (!disposed) { setRuns(items); setError(""); }
    }).catch((reason) => { if (!disposed) setError(reason instanceof Error ? reason.message : "ChatMate findings unavailable."); }).finally(() => { inFlight = false; });
    };
    const visible = () => { if (document.visibilityState !== "hidden") load(); };
    load();
    const timer = window.setInterval(visible, 3000);
    window.addEventListener("focus", visible);
    window.addEventListener(RUNS_CHANGED, visible);
    document.addEventListener("visibilitychange", visible);
    return () => { disposed = true; window.clearInterval(timer); window.removeEventListener("focus", visible); window.removeEventListener(RUNS_CHANGED, visible); document.removeEventListener("visibilitychange", visible); };
  }, [attempt]);
  const projections = (runs ?? []).flatMap((run) => {
    const classification = chatMateClassification(run);
    return classification ? [{ run, ...classification }] : [];
  });
  return { runs, projections, error, retry: () => setAttempt((value) => value + 1) };
}

export function ChatMateFindingsPanel({ history }: {
  history: ReturnType<typeof useChatMateFindings>;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = searchParams.get("chatmate");
  const disclosureId = useId();
  const triggers = useRef(new Map<string, HTMLButtonElement>());
  const close = (runId: string) => {
    const next = new URLSearchParams(searchParams);
    next.delete("chatmate");
    setSearchParams(next);
    triggers.current.get(runId)?.focus();
  };
  const { runs, projections, error, retry } = history;
   const filtered = projections;
  if (runs && !projections.length && !error && !selected) return null;
  return <section className="chatmate-results" aria-label="ChatMate results">
     <header><h2>ChatMate results</h2><span>{filtered.filter((item) => item.open).length} policy violations · {filtered.filter((item) => item.run.final_status === "RESISTED").length} boundary resisted</span></header>
    {error && <div className="inline-error" role="alert">ChatMate history unavailable: {error} <button className="secondary-action" type="button" onClick={retry}>Retry ChatMate history</button></div>}
    {!runs && !error && <p role="status">Loading ChatMate results...</p>}
    {filtered.length > 0 && <div className="records-table"><table aria-label="ChatMate results">
       <thead><tr><th>Source / Target</th><th>Result</th><th>Attack</th><th>Date</th><th>Actions</th></tr></thead>
       <tbody>{filtered.map((item, index) => <Fragment key={item.run.run_id}><tr className="chatmate-finding-row">
        <td><strong>ChatMate</strong><small className="chatmate-result-reference">{chatMateRunReference(item.run.run_id)}</small></td>
        <td><strong>{item.label}</strong><small className="chatmate-result-reference">{chatMateStatusLabel(item.run)}</small></td>
        <td>{chatMateAttackName(item.run)}</td>
        <td><time dateTime={item.run.completed_at ?? item.run.created_at}>{chatMateDate(item.run.completed_at ?? item.run.created_at)}</time></td>
        <td><div className="chatmate-finding-actions"><button className="secondary-action" ref={(node) => { if (node) triggers.current.set(item.run.run_id, node); else triggers.current.delete(item.run.run_id); }} id={`${disclosureId}-trigger-${index}`} aria-expanded={selected === item.run.run_id} aria-controls={`${disclosureId}-detail-${index}`} aria-label={`View details ${chatMateRunReference(item.run.run_id)}`} type="button" onClick={() => {
          if (selected === item.run.run_id) close(item.run.run_id);
          else { const next = new URLSearchParams(searchParams); next.delete("id"); next.set("chatmate", item.run.run_id); setSearchParams(next); }
        }}>{selected === item.run.run_id ? "Hide details" : "View details"}</button>
          <Link className="secondary-action" to={chatMateReportLink(item.run.run_id)}>View report</Link></div></td>
      </tr><tr hidden={selected !== item.run.run_id} className="chatmate-inline-detail"><td colSpan={5}><div id={`${disclosureId}-detail-${index}`} role="region" aria-labelledby={`${disclosureId}-trigger-${index}`}>
        {selected === item.run.run_id && <ChatMateFindingDetail key={item.run.run_id} runId={item.run.run_id} onClose={() => close(item.run.run_id)} />}
      </div></td></tr></Fragment>)}</tbody>
    </table></div>}
    {selected && runs && !error && !filtered.some((item) => item.run.run_id === selected) && <div className="inline-error" role="status">ChatMate result unavailable. <button className="secondary-action" type="button" onClick={() => close(selected)}>Clear selection</button></div>}
  </section>;
}
