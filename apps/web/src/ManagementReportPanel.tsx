import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { loadManagementReport, managementReportBundle, reportSelectionKey, assessmentChains, linkedSocmateChains } from "./managementReport";
import type { ManagementReportItem, ReportNotes, ReportOutcome, ReportSelection } from "./managementReport";
import { criticDisplayText } from "./chatmateCritic";
import { EvidenceResponse, JudgeReasoning } from "./EvidencePresentation";
import { StandardRecommendationCards } from "./StandardRecommendationCards";
import "./managementReportChains.css";

const dateText = (value: string | null) => value && Number.isFinite(Date.parse(value))
  ? new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
const outcomes: ReportOutcome[] = ["Resisted", "Compromised", "Inconclusive", "Failed", "Cancelled", "Unavailable"];

function CriticReport({ item, children }: { item: ManagementReportItem; children: ManagementReportItem[] }) {
  if (!item.critic) return null;
  const { review, notice } = item.critic;
  return <section className="management-report-critic" aria-label={`Critic analysis for ${item.runId}`}>
    <h4>Adaptive analysis · Critic</h4><p>Advisory analysis; does not modify either Judge verdict.</p>
    {notice && <p className="management-report-missing">{notice}</p>}
    {review && <>
      <h5>Management summary</h5><p>{criticDisplayText(review.management_summary)}</p>
      <h5>Attack effectiveness</h5><p>{criticDisplayText(review.attack_effectiveness_analysis)}</p>
      <h5>Outcome analysis</h5><p>{criticDisplayText(review.outcome_analysis)}</p>
      <h5>Weak point · {review.weak_point_status}</h5><p>{criticDisplayText(review.observed_weak_point ?? "No weak point observed.")}</p>
      <h5>Model recommendation · {review.recommended_attack_profile_id}</h5><p>{criticDisplayText(review.recommended_follow_up_objective)}</p>
      {children.map((child) => <div key={child.runId}><h5>{child.lineage?.context?.recommended_attack_profile_id !== review.recommended_attack_profile_id ? "Policy-adjusted follow-up" : "Applied to selected follow-up"}</h5>
        <p>{child.runId} · {child.lineage?.profile}</p>{child.lineage?.context?.recommended_attack_profile_id !== review.recommended_attack_profile_id && <p>{criticDisplayText(String(child.lineage?.context?.objective ?? ""))}</p>}</div>)}
      <h5>Expected evidence</h5><ul>{review.expected_evidence.map((value, i) => <li key={i}>{criticDisplayText(value)}</li>)}</ul>
      <p><strong>Critic evidence citations:</strong> {review.evidence_references.join(" · ") || "None"}</p>
      <p><strong>Critic policy citations:</strong> {review.policy_references.join(" · ") || "None"}</p>
      <dl><div><dt>Critic review</dt><dd>{review.critic_review_id}</dd></div><div><dt>Source evaluation</dt><dd>{review.source_evaluation_id}</dd></div>
        <div><dt>Source Judge SHA-256</dt><dd>{review.source_judge_sha256}</dd></div></dl>
    </>}
  </section>;
}

export function ManagementReportPanel({ selections, title = "SecMate Report", onClose }: {
  selections: ReportSelection[]; title?: string; onClose: () => void;
}) {
  const [items, setItems] = useState<ManagementReportItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [generatedAt, setGeneratedAt] = useState("");
  const [outputError, setOutputError] = useState("");
  const [notes, setNotes] = useState<ReportNotes>({ reviewer: "", date: "", decision: "", notes: "" });
  const heading = useRef<HTMLHeadingElement>(null);
  const outputController = useRef<AbortController | null>(null);
  const outputPending = useRef(false);
  const notesRef = useRef(notes);
  notesRef.current = notes;
  const signature = JSON.stringify(selections);
  const structure = assessmentChains(items ?? []);
  const socmate = linkedSocmateChains(items ?? []);
  useEffect(() => setNotes({ reviewer: "", date: "", decision: "", notes: "" }), [signature]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setItems(null);
    setOutputError("");
    void loadManagementReport(JSON.parse(signature) as ReportSelection[], controller.signal).then((next) => {
      if (!controller.signal.aborted) { setItems(next); setGeneratedAt(new Date().toISOString()); setLoading(false); }
    }).catch(() => { if (!controller.signal.aborted) setLoading(false); });
    heading.current?.focus();
    return () => { controller.abort(); outputController.current?.abort(); };
  }, [signature, attempt]);

  const output = async (print: boolean) => {
    if (!items || outputPending.current) return;
    const controller = new AbortController();
    outputController.current = controller;
    outputPending.current = true;
    setLoading(true);
    setOutputError("");
    try {
      const latest = await loadManagementReport(JSON.parse(signature) as ReportSelection[], controller.signal);
      if (controller.signal.aborted) return;
      const issued = new Date().toISOString();
      // Commit the freshly verified document to the DOM before opening print.
      flushSync(() => { setItems(latest); setGeneratedAt(issued); setLoading(false); });
      if (print) { window.print(); return; }
      const blob = new Blob([JSON.stringify(managementReportBundle(title, issued, latest, notesRef.current), null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url; anchor.download = `secmate-report-${issued.replace(/[:.]/g, "-")}.json`; anchor.click();
      } finally { URL.revokeObjectURL(url); }
    } catch {
      if (!controller.signal.aborted) setOutputError("Export unavailable.");
    } finally {
      outputPending.current = false;
      if (!controller.signal.aborted) setLoading(false);
    }
  };
  return <section className="management-report" aria-label={title}>
    <div className="management-report-actions">
      <button type="button" className="secondary-action" onClick={onClose}>Back</button>
      <div><button type="button" className="secondary-action" disabled={loading} onClick={() => setAttempt((value) => value + 1)}>Refresh</button>
        <button type="button" className="secondary-action" disabled={!items || loading} onClick={() => void output(false)}>Export JSON</button>
        <button type="button" className="primary-action" disabled={!items || loading} onClick={() => void output(true)}>Print / Save PDF</button></div>
    </div>
    <p className="management-report-print-help">Use browser print to save as PDF.</p>
    {outputError && <p role="alert">{outputError}</p>}
    <article className="management-report-paper">
      <header className="management-report-cover"><div className="management-report-brand">SECMATE<span>Assessment intelligence</span></div>
        <div className="management-report-cover-line" /><h1 ref={heading} tabIndex={-1}>{title}</h1>
        <p>Assessment results</p><dl><div><dt>Issued</dt><dd>{dateText(generatedAt)}</dd></div>
          <div><dt>Scope</dt><dd>{selections.length} selected run{selections.length === 1 ? "" : "s"}</dd></div>
          <div><dt>Sequence</dt><dd>Selection order between chains; parent before follow-up</dd></div></dl>
      </header>
      {loading && <p role="status">Building report...</p>}
      {!loading && !items && <p role="alert">Evidence unavailable.</p>}
      {items && <>
        <section className="management-report-section"><h2><span>01</span>Summary</h2>
          <div className="management-report-metrics">{outcomes.map((label) => <div key={label} data-outcome={label}><strong>{items.filter((item) => item.outcome === label).length}</strong><span>{label}</span></div>)}</div>
          <p className="management-report-verification">{items.filter((item) => item.evidenceStatus === "Verified").length} / {items.length} evidence verified</p>
          <p>{structure.chains.length > 0 && <>{structure.chains.length} ChatMate assessment chain{structure.chains.length === 1 ? "" : "s"} · </>}{items.length} selected run{items.length === 1 ? "" : "s"}. Run and path verdicts are independent; no combined score is inferred.</p>
        </section>
        <section className="management-report-section"><h2><span>02</span>Results</h2><div className="management-report-table-wrap"><table>
          <thead><tr><th>#</th><th>Target / Method</th><th>Outcome</th><th>Score</th><th>Confidence</th><th>Completed</th></tr></thead>
          <tbody>{items.map((item, index) => <tr key={reportSelectionKey(item)}><td>{index + 1}</td><td><strong>{item.target}</strong><span>{item.method}</span>{item.lineage?.parentRunId && <small>Continuation of {item.lineage.parentRunId}</small>}</td>
            <td><span className="management-report-badge" data-outcome={item.outcome}>{item.outcome}</span></td>
             <td>{item.pathResults && item.pathResults.length > 1 ? item.pathResults.map(path => <div key={path.pathId}><small>Path {path.number}</small>{path.score === undefined ? "Not evaluated" : `${path.score}/100`}</div>) : item.score === undefined ? item.unsupported ? "Not evaluated" : "—" : `${item.score}/100`}</td>
             <td>{item.pathResults && item.pathResults.length > 1 ? item.pathResults.map(path => <div key={path.pathId}><small>Path {path.number}</small>{path.confidence === undefined ? "Not recorded" : `${Math.round(path.confidence * 100)}%`}</div>) : item.confidence === undefined ? item.unsupported ? "Not recorded" : "—" : `${Math.round(item.confidence * 100)}%`}</td><td>{dateText(item.completed)}</td></tr>)}</tbody>
        </table></div></section>
        <section className="management-report-section"><h2><span>03</span>{structure.chains.length ? "Assessment chains" : "Assessments"}</h2>
          {structure.chains.map((chain, index) => <section className="management-report-chain" key={chain.rootRunId} aria-label={`Assessment chain ${index + 1}`}>
            <h3>Assessment chain {index + 1} · {chain.rootRunId}</h3><p>Lineage: {chain.status}</p>{chain.notice && <p className="management-report-missing">{chain.notice}</p>}
            {chain.stages.map((item, stage) => <section className="management-report-stage" key={item.runId}>
              <h4>Stage {stage + 1} — {item.lineage?.parentRunId ? "Follow-up" : "Initial assessment"}</h4>
              <p>{item.runId} · {item.method}</p><p>{item.outcome} · {item.score === undefined ? "No score" : `${item.score}/100`} · {item.evidenceStatus}</p>
              <p>{item.summary}</p><small>{dateText(item.completed)}</small>
              <CriticReport item={item} children={chain.transitions.filter((edge) => edge.parentRunId === item.runId).map((edge) => chain.stages.find((value) => value.runId === edge.childRunId)!)} />
            </section>)}
          </section>)}
           {socmate.chains.map((chain, index) => <section className="management-report-chain" key={chain.rootRunId} aria-label={`Linked assessment chain ${index + 1}`}>
             <h3>Linked fresh assessments · {chain.status}</h3><p>Each linked child is a fresh assessment informed by parent evidence, not a continued conversation.</p>{chain.notice && <p>{chain.notice}</p>}
             {chain.stages.map(item => <section className="management-report-stage" key={item.runId}><h4>{item.socmateLink ? "Linked fresh assessment" : "Parent assessment"} · {item.method}</h4>
               <p>{item.runId} · {item.outcome}</p><p>{item.summary}</p></section>)}
           </section>)}
           {socmate.independentItems.length > 0 && <><h3>Independent assessments</h3>{socmate.independentItems.map((item) => <div key={reportSelectionKey(item)}><p>{item.target} · {item.method} · {item.outcome}</p><p>{item.summary}</p></div>)}</>}
        </section>
        <section className="management-report-section"><h2><span>04</span>Actions</h2>
          {items.some((item) => item.actions.length) ? items.filter((item) => item.actions.length).map((item) => <div key={reportSelectionKey(item)}><h3>{item.target} · Critic recommendation</h3>{item.actions.map((action, index) => <p key={index}>{action}</p>)}</div>) : <p>Review selected evidence.</p>}
          <div className="management-report-review"><h3>Human review</h3><div className="management-report-review-grid">{(["reviewer", "date", "decision", "notes"] as const).map((key) => <label key={key}>
            {key[0].toUpperCase() + key.slice(1)}{key === "notes" ? <textarea aria-label="Notes" value={notes[key]} maxLength={10000} onChange={(event) => setNotes({ ...notes, [key]: event.target.value })} />
              : <input aria-label={key[0].toUpperCase() + key.slice(1)} type={key === "date" ? "date" : "text"} value={notes[key]} maxLength={500} onChange={(event) => setNotes({ ...notes, [key]: event.target.value })} />}
            <span className="management-report-print-value" aria-hidden="true">{notes[key] || "—"}</span></label>)}</div></div>
        </section>
        <section className="management-report-section management-report-appendix"><h2><span>05</span>Appendix</h2>
          {items.map((item, index) => <section className="management-report-evidence" key={reportSelectionKey(item)}><header><span>Evidence {String(index + 1).padStart(2, "0")}</span><h3>{item.target} · {item.method}</h3></header>
             {item.unsupported && <p className="management-report-missing"><strong>Unsupported experimental selection.</strong> {item.unsupportedReason}</p>}
             <dl>{Object.entries(item.appendix).filter(([, value]) => value !== null && value !== "").map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
            {item.exchanges.map((exchange, exchangeIndex) => <div className="management-report-exchange" key={exchangeIndex}><h4>{exchange.label}</h4><h5>Prompt</h5><pre>{exchange.prompt || "—"}</pre><h5>Response</h5><EvidenceResponse text={exchange.response || "—"} />{exchange.tools && <><h5>Tool evidence</h5><pre>{exchange.tools}</pre></>}</div>)}
             {!item.originalAvailable && <p>{item.evidenceStatus === "Invalid" ? "Validation failed." : "Original evidence unavailable."}</p>}
             {item.standardReview && <section className="management-report-standard-review"><h4>Standard Attack Critic review</h4>
               <p>Uncalibrated recommendation priority, not a success probability or the Judge’s deviation score.</p>
               {item.standardReview.notice && <p>{item.standardReview.notice}</p>}
               {item.standardReview.status === "Verified" && item.standardReview.review && <>
                 <StandardRecommendationCards recommendations={item.standardReview.review.recommendations} />
                 <dl><div><dt>Review</dt><dd>{item.standardReview.review.review_id}</dd></div><div><dt>Source path</dt><dd>{item.standardReview.review.source_path_id}</dd></div>
                   <div><dt>Review SHA-256</dt><dd>{item.standardReview.sha256}</dd></div></dl>
               </>}
             </section>}
            {item.pathResults?.length ? <section className="management-report-path-results" aria-label={`Path evaluations ${item.runId}`}><h4>Path evaluations</h4>
              <p>Scores describe observed policy deviation, not attack quality or probability of compromise.</p>
              {item.pathResults.map(path => <section key={path.pathId} className="management-report-stage"><h5>Path {path.number} · {path.method}</h5>
                <dl><div><dt>Path outcome</dt><dd>{path.outcome}</dd></div><div><dt>Deviation score</dt><dd>{path.score === undefined ? "Not evaluated" : `${path.score}/100`}</dd></div>
                  <div><dt>Judge-reported confidence</dt><dd>{path.confidence === undefined ? "Not recorded" : `${Math.round(path.confidence * 100)}%`}</dd></div></dl>
                {path.scoreNote && <p>{path.scoreNote}</p>}{path.rationale && <JudgeReasoning reasoning={path.rationale} />}
              </section>)}
            </section> : item.rationales.length > 0 && <div className="management-report-rationale"><h4>Model rationale</h4>{item.rationales.map((rationale, rationaleIndex) => <JudgeReasoning key={rationaleIndex} reasoning={rationale} />)}</div>}
            {item.citations.length > 0 && <div className="management-report-citations"><strong>Citations</strong><ul>{item.citations.map((citation, i) => <li key={i}>{citation}</li>)}</ul></div>}
          </section>)}
        </section>
        <footer className="management-report-footer"><strong>SECMATE</strong><span>{title} · {dateText(generatedAt)}</span></footer>
      </>}
    </article>
  </section>;
}
