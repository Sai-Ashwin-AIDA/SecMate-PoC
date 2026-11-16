import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { chatmateService } from "./chatmateService";
import type { ChatMateCriticReview, ChatMateRunRecord } from "./chatmateService";
import { chatMateCandidate, chatMateExport, chatMateResultLabel, eligibleChatMateResult, parseChatMateAudit } from "./chatmateProjections";
import { chatMateAttackName, chatMateDate, chatMateErrorMessage, chatMateRunReference, chatMateSafeDiagnostic, chatMateStatusLabel, chatMateGenerationFailed } from "./chatmateDisplay";
import { ChatMateDiagnostics } from "./ChatMateRunFeedback";
import { Link } from "react-router-dom";
import { CriticReviewPanel } from "./CriticReviewPanel";
import { chatMateNextStep, parseChatMateCriticReview, legacyCriticWarning } from "./chatmateCritic";
import { CHATMATE_SCORE_GUIDANCE, ChatMateJudgeRationale, chatMateScoreCategory, chatMateGradedResult } from "./ChatMateJudgeDetails";
import { ManagementReportPanel } from "./ManagementReportPanel";
import { BaselineMethodReview } from "./BaselineMethodReview";
import { EvidenceResponse } from "./EvidencePresentation";

export function useChatMateAudit(runId: string) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    id: string; run?: ChatMateRunRecord; parsed?: ReturnType<typeof parseChatMateAudit>; error?: string;
  }>({ id: runId });
  useEffect(() => {
    let disposed = false;
    setState({ id: runId });
    const load = async () => {
      let run: ChatMateRunRecord | undefined;
      try {
        run = await chatmateService.getRun(runId);
        if (run.run_id === runId && chatMateGenerationFailed(run)) {
          if (!disposed) setState({ id: runId, run });
          return;
        }
        if (run.run_id !== runId || !eligibleChatMateResult(run)) throw new Error("The requested run has no eligible evaluated report.");
        if (!run.artifact_available) throw new Error("Validated audit unavailable. No Judge conclusion or download is available.");
        const audit = await chatmateService.getAudit(runId);
        const parsed = parseChatMateAudit(run, audit);
        if (!disposed) setState({ id: runId, run, parsed });
      } catch (reason) {
        if (!disposed) setState({ id: runId, run: run?.run_id === runId && eligibleChatMateResult(run) ? run : undefined,
          error: reason instanceof Error ? reason.message : "ChatMate report unavailable." });
      }
    };
    void load();
    return () => { disposed = true; };
  }, [runId, attempt]);
  return { ...(state.id === runId ? state : { id: runId }), retry: () => setAttempt((current) => current + 1) };
}

export function ChatMateRunError({ run }: { run: ChatMateRunRecord }) {
  const message = chatMateErrorMessage(run);
  const diagnostic = run.error_message ? chatMateSafeDiagnostic(run.error_message, 4000) : "";
  return <div className="chatmate-failure-reason" role="alert">
    <strong>Failure reason</strong><p>{message}</p>
    {(run.error_code || (diagnostic && diagnostic !== message)) && <details className="chatmate-diagnostics">
      <summary>Error details</summary>
      {run.error_code && <p>Error code: <code>{chatMateSafeDiagnostic(run.error_code, 128)}</code></p>}
      {diagnostic && diagnostic !== message && <pre>{diagnostic}</pre>}
    </details>}
  </div>;
}

export function ChatMateReportPanel({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { run, parsed, error, retry } = useChatMateAudit(runId);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [managementOpen, setManagementOpen] = useState(false);
  const exportVersion = useRef(0);
  const exportPending = useRef(false);
  useLayoutEffect(() => {
    exportVersion.current += 1;
    exportPending.current = false;
    setExporting(false);
    setExportError("");
    setManagementOpen(false);
    return () => { exportVersion.current += 1; };
  }, [runId]);

  const download = async () => {
    if (!parsed || exportPending.current) return;
    exportPending.current = true;
    const version = exportVersion.current;
    const current = () => version === exportVersion.current;
    setExporting(true);
    setExportError("");
    try {
      // Export a fresh saved snapshot; the child Critic panel may have completed
      // a review after the report hook loaded. These requests never start work.
      const latest = await chatmateService.getRun(runId);
      if (!current()) return;
      if (latest.run_id !== runId || !eligibleChatMateResult(latest)) throw new Error("The latest saved report does not match the requested assessment.");
      const latestAudit = await chatmateService.getAudit(runId);
      if (!current()) return;
      const bundle = chatMateExport(latest, latestAudit);
      let criticReview: ChatMateCriticReview | undefined;
      if (latest.critic_status === "COMPLETED") {
        const savedReview = await chatmateService.getCritic(runId);
        if (!current()) return;
        criticReview = await parseChatMateCriticReview(latest, latestAudit, savedReview);
      }
      if (!current()) return;
      // Preserve canonical historical evidence; JSON escapes controls rather than
      // silently rewriting hashed review text. The notice travels with the export.
      const completeBundle = { ...bundle, ...(criticReview ? { critic_review: criticReview,
        ...(legacyCriticWarning(criticReview) ? { critic_review_notice: legacyCriticWarning(criticReview) } : {}) } : {}) };
      const blob = new Blob([JSON.stringify(completeBundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `chatmate-${encodeURIComponent(runId)}.redacted.json`;
        anchor.click();
      } finally { URL.revokeObjectURL(url); }
    } catch (reason) {
      if (current()) setExportError(chatMateSafeDiagnostic(reason instanceof Error ? reason.message : "Unable to validate the latest saved report."));
    } finally {
      if (current()) { exportPending.current = false; setExporting(false); }
    }
  };
  const manual = run?.manual_evidence;
  const failed = run?.status === "FAILED" || run?.final_status === "ERROR";
  const generationFailed = run ? chatMateGenerationFailed(run) : false;
  if (managementOpen) return <ManagementReportPanel title="ChatMate Report" selections={[{ source: "ChatMate", runId }]} onClose={() => setManagementOpen(false)} />;
  return <article className="report-preview chatmate-report" aria-label="ChatMate report">
    <div className="report-actions"><button className="secondary-action" type="button" onClick={onClose}>Back to history</button><button className="secondary-action" type="button" disabled={!run || generationFailed} onClick={() => setManagementOpen(true)}>Report</button><button className="primary-action" type="button" disabled={!parsed || exporting} aria-busy={exporting} onClick={() => void download()}>{exporting ? "Exporting..." : "Export JSON"}</button></div>
    <header className="chatmate-report-header">
      <div><span className="report-kicker">ChatMate report</span><h2>{generationFailed ? "Generation Failed" : parsed && run ? parsed.judge && !failed ? chatMateGradedResult(parsed.judge) : chatMateResultLabel(run) : failed ? "Evaluation failed" : error ? "Report unavailable" : "Loading report"}</h2>
        {run?.parent_run_id && <p>Recorded continuation of <Link to={`/reports?chatmate=${encodeURIComponent(run.parent_run_id)}`}>{chatMateRunReference(run.parent_run_id)}</Link> · Critic review {run.follow_up_critic_review_id}</p>}</div>
      <dl className="console-context-grid">
        {run && <><div><dt>{chatMateCandidate(run)?.generation_mode === "BASELINE_METHOD_REVIEWED" ? "Requested method" : "Test method"}</dt><dd>{chatMateAttackName(run)}</dd></div><div><dt>Target</dt><dd>{run.target_name}</dd></div><div><dt>Status</dt><dd><span className={`chatmate-status-badge ${failed ? "failed" : "complete"}`}>{chatMateStatusLabel(run)}</span></dd></div><div><dt>Completed</dt><dd><time dateTime={run.completed_at ?? undefined}>{chatMateDate(run.completed_at)}</time></dd></div></>}
        <div><dt>Reference</dt><dd>{chatMateRunReference(runId)}</dd></div>
      </dl>
    </header>
    {run && chatMateCandidate(run)?.generation_mode === "BASELINE_METHOD_ALIGNED" && <p>Method-aligned baseline prompt.</p>}
    <BaselineMethodReview candidate={run ? chatMateCandidate(run) : null} />
    {!run && !error && <div className="chatmate-report-state" role="status">Loading assessment evidence...</div>}
    {error && <div className="inline-error" role="alert"><strong>Report unavailable</strong><p>{error}</p><button className="secondary-action" type="button" onClick={retry}>Retry report</button></div>}
    {exportError && <div className="inline-error" role="alert"><strong>Export unavailable</strong><p>{exportError}</p><p>No file was downloaded. Reload the report or try exporting again.</p></div>}
    {generationFailed && run && <><ChatMateRunError run={run} /><ChatMateDiagnostics run={run} /><Link className="secondary-action" to={`/assessments/chatmate?run=${encodeURIComponent(run.run_id)}`}>View assessment</Link></>}
    {parsed && run && manual && <>
        <section className="chatmate-outcome-summary"><h3>Outcome summary</h3><p>{failed ? "Evaluation could not be completed." : run.final_status === "COMPROMISED" ? "Policy violation found." : run.final_status === "RESISTED" ? "No policy violation found." : "Evidence is inconclusive."}</p></section>
      <dl className="chatmate-report-metrics" aria-label="Evaluation metrics">
         {parsed.judge && <><div><dt>Deviation score</dt><dd>{parsed.judge.deviation_score}<span>/100</span></dd></div><div><dt>Score category</dt><dd className="chatmate-score-category">{chatMateScoreCategory(parsed.judge)}</dd></div><div><dt>Judge-reported confidence</dt><dd>{Math.round(parsed.judge.confidence * 100)}<span>%</span></dd></div></>}
         <div><dt>Evidence-qualified verdict</dt><dd>{run.final_status}</dd></div><div><dt>Evaluation attempts</dt><dd>{run.evaluation_attempts}</dd></div>
      </dl>
        {parsed.judge && <details><summary>Score details</summary><p>{CHATMATE_SCORE_GUIDANCE}</p></details>}
       <details className="assessment-conversation chatmate-conversation"><summary><strong>Test conversation</strong><span>1 captured exchange · exact prompt and response</span></summary><div className="chatmate-evidence-comparison"><section aria-label="Selected attack"><h3>Exact selected attack</h3><pre className="chatmate-captured-response" tabIndex={0}>{chatMateCandidate(run)?.prompt}</pre></section>
        <section aria-label="Captured response"><h3>Captured response · redacted</h3>{manual.outcome === "VISIBLE_FAILURE" ? <p className="chatmate-report-state">Response could not be completed.</p> : <div aria-label="Captured response text"><EvidenceResponse text={manual.redacted_response_text ?? ""} /></div>}</section></div></details>
       <section className="chatmate-report-rationale" aria-label="Judge rationale"><h3>Judge rationale</h3>{parsed.judge ? <ChatMateJudgeRationale judge={parsed.judge} /> : <p>{failed ? "The evaluation could not be completed. No Judge rationale is available." : "No Judge evaluation was produced for this observation."}</p>}</section>
       <section className="chatmate-report-next-step" aria-label="Next step"><div><h3>Next step</h3><p>{chatMateNextStep(run, parsed.audit)}</p></div><a className="secondary-action" href={`/assessments/chatmate?run=${encodeURIComponent(run.run_id)}`}>View assessment</a></section>
    </>}
    {run && failed && <><ChatMateRunError run={run} />{!parsed && <p>Submitted evidence is retained.</p>}</>}
    {run && parsed && <CriticReviewPanel run={run} audit={parsed.audit} />}
    {run && <>
      <details className="report-technical-details"><summary>Lifecycle timestamps</summary><dl className="detail-list chatmate-metadata-grid">
        {([ ["Created", run.created_at], ["Started", run.started_at], ["Generated", run.generated_at], ["Selected", run.selected_at], ["Response submitted", run.response_submitted_at], ["Evaluation started", run.evaluation_started_at], ["Completed", run.completed_at] ]).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{chatMateDate(value)}</dd></div>)}
      </dl></details>
      <details className="report-technical-details"><summary>Evidence and evaluation metadata</summary><dl className="detail-list chatmate-metadata-grid">
        <div><dt>Run ID</dt><dd><code>{run.run_id}</code></dd></div>
        <div><dt>Selected candidate</dt><dd><code>{run.selected_candidate_id}</code></dd></div>
        <div><dt>Selected SHA-256</dt><dd><code>{run.selected_candidate_sha256}</code></dd></div>
        <div><dt>Collection</dt><dd>Copy and paste</dd></div>
        <div><dt>Correlation SHA-256</dt><dd><code>{manual?.correlation_sha256}</code></dd></div>
        <div><dt>Persisted response SHA-256</dt><dd>{manual?.persisted_response_sha256 ? <code>{manual.persisted_response_sha256}</code> : "No response"}</dd></div>
        <div><dt>Redaction</dt><dd>{manual?.redaction_applied ? "Applied" : "Not required"}</dd></div>
        <div><dt>Evidence submitted (server)</dt><dd>{chatMateDate(manual?.submitted_at)}</dd></div>
        <div><dt>Evaluation ID</dt><dd>{run.evaluation_id ? <code>{run.evaluation_id}</code> : "Not recorded"}</dd></div>
        <div><dt>Evaluation attempts</dt><dd>{run.evaluation_attempts}</dd></div>
        {run.conversation_id && <div><dt>Conversation ID</dt><dd>{run.conversation_id}</dd></div>}
        {run.parent_run_id && <><div><dt>Parent assessment</dt><dd><Link to={`/assessments/chatmate?run=${encodeURIComponent(run.parent_run_id)}`}>View parent assessment</Link><code>{run.parent_run_id}</code></dd></div><div><dt>Follow-up Critic review</dt><dd><code>{run.follow_up_critic_review_id}</code></dd></div><div><dt>Follow-up objective</dt><dd>{run.follow_up_objective}</dd></div><div><dt>Expected evidence</dt><dd>{run.follow_up_expected_evidence?.join("; ")}</dd></div></>}
        {run.error_code && <div><dt>Operational error code</dt><dd>{run.error_code}</dd></div>}
        {manual?.prompt_sent_at && <div><dt>Legacy operator prompt time</dt><dd>{chatMateDate(manual.prompt_sent_at)}</dd></div>}
        {manual?.response_observed_at && <div><dt>Legacy operator observation time</dt><dd>{chatMateDate(manual.response_observed_at)}</dd></div>}
      </dl></details>
      {failed && <ChatMateDiagnostics run={run} />}
    </>}
    {parsed && <details className="report-technical-details"><summary>Raw audit</summary><p>Validated audit with the selected attack and redacted observation.</p><pre>{JSON.stringify(parsed.audit, null, 2)}</pre></details>}
  </article>;
}
