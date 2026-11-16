import type { DeepTeamRunRecord } from "./modelConnectivityService";
import { useEffect, useState } from "react";
import { ManagementReportPanel } from "./ManagementReportPanel";
import { useDeepTeamEvidence } from "./useDeepTeamEvidence";
import { ACTIVE_DEEPTEAM_RUN_KEY } from "./deepTeamRunStorage";
import { assessmentDisplayName, assessmentFailureMessage, targetDisplayName } from "./displayLabels";
import { JudgeReasoning } from "./EvidencePresentation";
import { StandardReviewPanel } from "./StandardReviewPanel";
import { SocMateScoreSummary } from "./SocMateScoreSummary";

type AssessmentResultsPanelProps = {
  runId?: string | null;
  onClose?: () => void;
  onRemove?: () => void;
};

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.map(record).filter((item): item is Record<string, unknown> => Boolean(item))
    : [];
}

function text(value: unknown, fallback = "Not available") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function numberText(value: unknown, fallback = "Not available") {
  return typeof value === "number" ? value.toLocaleString() : text(value, fallback);
}

function roleLabel(value: unknown) {
  const labels: Record<string, string> = {
    ATTACKER: "Attacker",
    DEEPTEAM_EVALUATOR: "DeepTeam Evaluator",
    ATTACK_CRITIC: "Attack Critique",
    TARGET: "Target",
    TARGET_EVALUATOR: "Judge",
  };
  return typeof value === "string" ? labels[value] ?? value.replaceAll("_", " ") : "Unattributed";
}

function resultLabel(run: DeepTeamRunRecord) {
  if (run.status === "FAILED" || run.final_status === "ERROR") return "Assessment incomplete";
  if (run.status === "CANCELLED") return "Assessment cancelled";
  if (["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(run.status)) return "Assessment in progress";
  if (run.final_status === "COMPROMISED") return "Policy violation found";
  if (run.final_status === "INCONCLUSIVE") return "Inconclusive";
  if (run.final_status === "RESISTED") return "No policy violation found";
  return "Result pending";
}

function resultExplanation(run: DeepTeamRunRecord) {
  if (run.status === "FAILED" || run.final_status === "ERROR") return "The assessment did not complete, so no security conclusion was reached.";
  if (run.status === "CANCELLED") return "The assessment was stopped before a conclusion was reached.";
  if (run.final_status === "COMPROMISED") return "Captured evidence shows that the tested policy boundary was violated.";
  if (run.final_status === "INCONCLUSIVE") return "The available evidence was not strong enough to reach a conclusion.";
  if (run.final_status === "RESISTED") return "The system preserved the tested policy boundary in this assessment.";
  return "The assessment is still processing.";
}

function reviewLabel(value: unknown, fallback: string) {
  const labels: Record<string, string> = {
    ALIGNED: "Behavior matched policy",
    MINOR_DEVIATION: "Minor concerns found",
    CONCERNING_DEVIATION: "Concerns found",
    MAJOR_DEVIATION: "Major concerns found",
    COMPROMISED: "Policy violation found",
  };
  return typeof value === "string" ? labels[value] ?? fallback : fallback;
}

export function AssessmentResultsPanel({ runId, onClose, onRemove }: AssessmentResultsPanelProps = {}) {
  const savedRunId = runId ?? window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY);
  const { run, audit, loading, error, retry } = useDeepTeamEvidence(savedRunId);
  const [managementOpen, setManagementOpen] = useState(false);
  useEffect(() => setManagementOpen(false), [savedRunId]);

  if (!savedRunId) return null;

  if (loading && !run) {
    return (
      <section className="assessment-results-panel assessment-results-state" aria-live="polite">
        Loading saved live assessment results...
      </section>
    );
  }

  if (error && !run) {
    return (
      <section className="assessment-results-panel assessment-results-state" role="alert">
        <strong>Live assessment results unavailable</strong>
        <span>{error}</span>
        <div className="assessment-results-state-actions">
          <button className="secondary-action" type="button" onClick={retry}>Retry evidence</button>
          {onClose && <button className="secondary-action" type="button" onClick={onClose}>Back to history</button>}
          {onRemove && <button className="danger-action" type="button" onClick={onRemove}>Remove unavailable report</button>}
        </div>
      </section>
    );
  }

  if (!run) return null;
  const targetLabel = targetDisplayName(run.target_profile_id ?? "synthetic-socmate-tier1");
  if (managementOpen) return <ManagementReportPanel selections={[{ source: "SocMate", runId: run.run_id }]} onClose={() => setManagementOpen(false)} />;

  const paths = records(audit?.evidence.paths);
  const reviews = records(audit?.evidence.review_results);
  const pathViews = paths.map((path, pathIndex) => {
    const pathId = text(path.path_id, `path-${pathIndex + 1}`);
    const pathReview = reviews.find((review) => review.path_id === path.path_id);
    return {
      id: pathId,
      number: text(path.sequence_number, String(pathIndex + 1)),
      method: text(path.attack_method),
      objective: text(path.objective),
      status: text(path.status),
      turns: records(path.turns).map((turn, index) => ({
        id: text(turn.turn_id, `${pathId}-turn-${index + 1}`),
        turn: text(turn.turn_number, String(index + 1)),
        probe: text(turn.probe),
        response: text(turn.target_response),
        toolAttempts: records(turn.tool_attempts),
        retrievalEvidence: records(turn.retrieval_evidence),
        retrievalDecisions: records(turn.retrieval_decisions),
      })),
      oracles: records(path.oracle_results),
      engine: record(path.engine_result),
      review: pathReview,
      targetEvaluation: record(pathReview?.target_evaluation),
      critic: record(pathReview?.critic_review),
    };
  });
  const conversations = pathViews.flatMap((path) => path.turns);
  const toolAttempts = pathViews.flatMap((path) => path.turns.flatMap((turn) =>
    turn.toolAttempts.map((attempt) => ({ path: path.number, turn: turn.turn, attempt })),
  ));
  const targetEvaluation = pathViews.length === 1 ? pathViews[0].targetEvaluation : null;
  const criticReview = pathViews.map((path) => path.critic).find(Boolean) ?? null;
  const allOracles = pathViews.flatMap((path) => path.oracles);
  const policyOutcome = allOracles.some((oracle) => oracle.outcome === "CONFIRMED_VIOLATION")
    ? "CONFIRMED_VIOLATION"
    : allOracles.some((oracle) => oracle.outcome === "ERROR")
      ? "ERROR"
      : allOracles.some((oracle) => oracle.outcome === "INSUFFICIENT_EVIDENCE")
        ? "INSUFFICIENT_EVIDENCE"
        : "NO_HARD_VIOLATION";
  const policyDetail = allOracles.length
    ? allOracles.map((oracle) => text(oracle.detail)).join(" ")
    : "No policy result was reported.";
  const budget = record(audit?.summary.budget);
  const executionProvenance = record(audit?.manifest.execution_provenance);
  const unsupported = run.execution_capability === "UNSUPPORTED";
  const executionMode = unsupported
    ? "Not executed / unsupported"
    : executionProvenance?.execution_mode === "BASELINE_UNENHANCED"
    && executionProvenance.enhancement_applied === false
    ? "Baseline / unenhanced"
    : "DeepTeam transformed";
  const tokenBudgetOverrun = budget?.token_budget_overrun === true;
  const modelAttempts = records(audit?.summary.model_attempts);
  const rateLimited = modelAttempts.some(
    (attempt) => attempt.error_code === "RATE_LIMITED",
  );
  const roleUsage = Array.from(modelAttempts.reduce((usage, attempt) => {
    const role = roleLabel(attempt.role);
    const current = usage.get(role) ?? { role, attempts: 0, succeeded: 0, failed: 0, tokens: 0 };
    current.attempts += 1;
    if (attempt.outcome === "SUCCESS") current.succeeded += 1;
    if (attempt.outcome === "FAILURE") current.failed += 1;
    const attemptUsage = record(attempt.usage);
    if (typeof attemptUsage?.total_tokens === "number") current.tokens += attemptUsage.total_tokens;
    usage.set(role, current);
    return usage;
  }, new Map<string, { role: string; attempts: number; succeeded: number; failed: number; tokens: number }>()).values());
  const failureMessage = rateLimited
    ? "The assessment could not be completed because an AI service limit was reached. No policy violation was confirmed."
    : run.status === "FAILED" || run.final_status === "ERROR"
      ? assessmentFailureMessage(run.error_message, modelAttempts)
      : null;
  const failed = run.status === "FAILED" || run.final_status === "ERROR";
  const callsWithMissingUsage = typeof budget?.calls_with_missing_usage === "number" ? budget.calls_with_missing_usage : null;
  const policyLabel = unsupported
    ? "Not evaluated"
    : policyOutcome === "CONFIRMED_VIOLATION"
    ? "Policy violation confirmed"
    : policyOutcome === "ERROR"
      ? "Policy check failed"
      : policyOutcome === "INSUFFICIENT_EVIDENCE"
        ? "Not enough evidence"
        : "No restricted action detected";
  const displayedPolicyDetail = unsupported
    ? run.execution_capability_reason ?? run.error_message ?? "The selected combination is not executable for this target."
    : policyDetail;

  const downloadAudit = () => {
    if (!audit) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(audit, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${audit.run_id}-audit.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return (
    <section className="assessment-results-panel" aria-labelledby="assessment-results-heading">
      <header className="assessment-results-header">
        <div>
          <h2 id="assessment-results-heading">Assessment results</h2>
          <p>{new Date(run.created_at).toLocaleString()}</p>
        </div>
        <div className="assessment-results-header-actions">
          <strong className={`worker-result ${(run.final_status ?? run.status).toLowerCase()}`}>
            {resultLabel(run)}
          </strong>
          {onClose && <button className="secondary-action" type="button" onClick={onClose}>Back to history</button>}
          {["COMPLETED", "FAILED", "CANCELLED"].includes(run.status) && <button className="secondary-action" type="button" onClick={() => setManagementOpen(true)}>Report</button>}
          {onRemove && <button className="danger-action" type="button" onClick={onRemove}>Remove report</button>}
        </div>
      </header>
      {!failed && <div className={`assessment-result-hero ${(run.final_status ?? run.status).toLowerCase()}`}>
        <SocMateScoreSummary audit={audit} />
        <span>Result</span>
        <strong>{resultLabel(run)}</strong>
        <p>{resultExplanation(run)}</p>
      </div>}
      {failed && <SocMateScoreSummary audit={audit} />}
      <div className="assessment-results-overview">
        <article>
          <span>What was tested</span>
           <dl><div><dt>Target</dt><dd>{targetLabel}</dd></div><div><dt>Security risk</dt><dd>{assessmentDisplayName(run.vulnerability)}</dd></div><div><dt>Test method</dt><dd>{assessmentDisplayName(run.attack)}</dd></div><div><dt>Coverage</dt><dd>{run.execution_mode === "ADAPTIVE" ? "Expanded" : "Standard"}</dd></div><div><dt>Test paths</dt><dd>{paths.length} of {run.max_paths}</dd></div></dl>
        </article>
      </div>
      {error && <div className="inline-error" role="alert">{error} <button className="secondary-action" type="button" onClick={retry}>Retry evidence</button></div>}
      {failureMessage && <div className="assessment-result-explanation" role="alert"><strong>Assessment incomplete</strong><span>{failureMessage}</span></div>}
      {unsupported && <div className="assessment-result-explanation" role="note"><strong>Unsupported experimental selection</strong><span>{run.execution_capability_reason ?? run.error_message ?? "The selected combination is not executable for this target."}</span><small>{run.execution_capability_code ?? "UNSUPPORTED"} · {run.selection_admission ?? "EXPERIMENTAL"}</small></div>}
      {tokenBudgetOverrun && <div className="assessment-result-explanation" role="alert"><strong>Usage limit exceeded</strong><span>The assessment used more tokens than its configured maximum before it stopped.</span></div>}
      {!audit ? (
        <div className="assessment-results-state" aria-live="polite">
          <strong>{run.artifact_available ? error ? "Saved audit could not be loaded" : "Loading saved audit" : run.status === "CANCELLED" ? "Assessment cancelled" : run.status === "FAILED" ? "Assessment did not produce an audit" : "Audit not ready"}</strong>
          <span>
            {run.artifact_available ? error ? "The run has saved evidence. Retry loading it without restarting the assessment." : "Reading the saved assessment evidence." : run.status === "CANCELLED" ? "The worker was stopped before a complete audit was produced." : run.error_message ??
              "The run is still processing. Results will appear here when the audit artifact is available."}
          </span>
        </div>
      ) : (
        <>
          <details className="assessment-conversation">
            <summary>
              <div className="assessment-section-heading">
                <span>Captured exchange</span>
                <h3 id="conversation-heading">Test conversation</h3>
              </div>
              <strong>{conversations.length} turn{conversations.length === 1 ? "" : "s"}</strong>
            </summary>
            <div className="assessment-conversation-content" aria-labelledby="conversation-heading">
              {pathViews.length > 0 ? pathViews.map((path) => (
                <section className="assessment-path" key={path.id}>
                  <header><div><span>Path {path.number}</span><strong>{path.method}</strong></div><b>{path.status}</b></header>
                  <p>{path.objective}</p>
                  {path.turns.map((turn) => (
                    <details className="assessment-conversation-turn" key={turn.id}>
                       <summary><span>Turn {turn.turn}</span><strong>Test prompt and system response</strong></summary>
                        <div className="assessment-turn-messages">
                          <div className="assessment-message attacker-message"><strong>Test prompt</strong><p>{turn.probe}</p></div>
                          {turn.retrievalEvidence.map((evidence, evidenceIndex) => (
                            <div className="assessment-message attacker-message" key={text(evidence.evidence_id, `${turn.id}-retrieval-${evidenceIndex + 1}`)}>
                              <strong>Retrieved evidence</strong>
                              <p>{text(evidence.redacted_content)}</p>
                              <span>{text(evidence.channel)} / {text(evidence.trust_classification)}</span>
                            </div>
                          ))}
                          <div className="assessment-message target-message"><strong>System response</strong><p>{turn.response}</p></div>
                          {turn.retrievalDecisions.map((decision, decisionIndex) => (
                            <div className="assessment-message target-message" key={text(decision.evidence_id, `${turn.id}-retrieval-decision-${decisionIndex + 1}`)}>
                              <strong>Retrieval decision</strong>
                              <p>{text(decision.detail)}</p>
                              <span>{text(decision.decision).replaceAll("_", " ")}</span>
                            </div>
                          ))}
                       </div>
                    </details>
                  ))}
                </section>
              )) : <p className="assessment-results-empty">No conversation turns were captured.</p>}
            </div>
          </details>
          <section className="assessment-evaluation" aria-labelledby="evaluator-heading">
            <div className="assessment-section-heading">
              <span>Evidence</span>
              <h3 id="evaluator-heading">Why this result</h3>
            </div>
            <div className="assessment-evaluator-grid">
              <article className="judge-evaluation">
                <span>Automated review</span>
                {pathViews.map(path => {
                  const evaluation = path.targetEvaluation;
                  const score = evaluation?.deviation_score, confidence = evaluation?.confidence;
                  const validScore = typeof score === "number" && Number.isInteger(score) && score >= 0 && score <= 100;
                  const validConfidence = typeof confidence === "number" && Number.isFinite(confidence) && confidence >= 0 && confidence <= 1;
                  return <section className="assessment-path-evaluation" key={path.id} aria-label={`Path ${path.number} evaluation`}>
                    {pathViews.length > 1 && <h4>Path {path.number} · {assessmentDisplayName(path.method)}</h4>}
                    <strong>{reviewLabel(evaluation?.category, path.status)}</strong>
                    <dl><div><dt>Deviation score</dt><dd>{validScore ? `${score}/100` : "Not evaluated"}</dd></div>
                      <div><dt>Judge-reported confidence</dt><dd>{validConfidence ? `${Math.round(confidence * 100)}%` : "Not recorded"}</dd></div></dl>
                    {evaluation ? <JudgeReasoning reasoning={text(evaluation.reasoning)} /> : <p>No Judge score was recorded for this path. Review its policy checks and outcome.</p>}
                  </section>;
                })}
                <small>Scores describe observed deviation, not attack quality or probability of compromise.</small>
              </article>
              <article>
                <span>Policy result</span>
                <strong>{policyLabel}</strong>
                 <p>{displayedPolicyDetail}</p>
              </article>
            </div>
          </section>
           {run.execution_mode === "ADAPTIVE" && <div className="assessment-result-explanation" role="note"><strong>Automatic Attack Critic</strong><span>Critic guidance selected the second independent path. Paths used fresh target state; this was not a continued conversation.</span></div>}
           <StandardReviewPanel key={run.run_id} run={run} />
          {toolAttempts.length > 0 && (
            <section aria-labelledby="tool-attempts-heading">
              <div className="assessment-section-heading">
                <span>Actions</span>
                <h3 id="tool-attempts-heading">Attempted actions</h3>
              </div>
              <div className="assessment-tool-table">
                <table>
                  <caption className="visually-hidden">Attempted actions captured during the assessment</caption><thead><tr><th scope="col">Step</th><th scope="col">Action</th><th scope="col">Result</th><th scope="col">Details</th></tr></thead>
                  <tbody>
                    {toolAttempts.map(({ path, turn, attempt }, index) => (
                      <tr key={`${path}-${turn}-${text(attempt.name, "tool")}-${index}`}>
                        <td>{path}.{turn}</td>
                        <td>{text(attempt.name ?? attempt.tool_name)}</td>
                        <td>{text(attempt.execution ?? attempt.disposition ?? attempt.status)}</td>
                        <td><code>{JSON.stringify(attempt.arguments ?? attempt.redacted_arguments ?? {})}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <details className="assessment-technical-details">
            <summary>Technical details</summary>
            <div>
               <dl className="assessment-technical-usage"><div><dt>Run ID</dt><dd>{run.run_id}</dd></div><div><dt>Completed</dt><dd>{run.completed_at ? new Date(run.completed_at).toLocaleString() : "Not completed"}</dd></div><div><dt>Target</dt><dd>{targetLabel}</dd></div><div><dt>Target profile</dt><dd>{run.target_profile_id} v{run.target_profile_version}</dd></div><div><dt>Scenario</dt><dd>{run.scenario} v{run.scenario_version}</dd></div><div><dt>Method ID</dt><dd>{run.attack_profile_id}</dd></div><div><dt>Risk ID</dt><dd>{run.vulnerability_profile_id}</dd></div><div><dt>Selection admission</dt><dd>{run.selection_admission ?? "Not reported"}</dd></div><div><dt>Execution capability</dt><dd>{run.execution_capability ?? "Not reported"}{run.execution_capability_code ? ` / ${run.execution_capability_code}` : ""}</dd></div><div><dt>Execution mode</dt><dd>{executionMode}</dd></div><div><dt>Coverage</dt><dd>{run.execution_mode === "ADAPTIVE" ? "Expanded" : "Standard"} / {run.max_paths} path{run.max_paths === 1 ? "" : "s"}</dd></div><div><dt>Captured turns</dt><dd>{conversations.length}</dd></div><div><dt>AI requests</dt><dd>{numberText(budget?.provider_calls_attempted, audit ? "0" : "Pending")}</dd></div><div><dt>Tokens accounted</dt><dd>{numberText(budget?.tokens_consumed, audit ? "0" : "Pending")} of {numberText(budget?.max_total_tokens, String(run.max_total_tokens))}</dd></div><div><dt>Usage quality</dt><dd>{callsWithMissingUsage === null ? "Not reported" : callsWithMissingUsage === 0 ? "Provider reported" : `Includes reserved-token estimates for ${callsWithMissingUsage} calls`}</dd></div><div><dt>Limit status</dt><dd>{tokenBudgetOverrun ? "Exceeded" : "Within limit"}</dd></div><div><dt>Judge-reported confidence</dt><dd>{pathViews.length > 1 ? "See per-path evaluations" : typeof targetEvaluation?.confidence === "number" ? `${Math.round(targetEvaluation.confidence * 100)}%` : "Not recorded"}</dd></div></dl>
              {criticReview && <article className="assessment-critic-detail"><strong>Automatic guidance used to select path 2</strong><p>{text(criticReview.failure_analysis)}</p><small>Recommended method: {text(criticReview.recommended_attack_method)}</small></article>}
              {roleUsage.length > 0 && <section className="assessment-role-usage" aria-labelledby="role-usage-heading"><div className="assessment-section-heading"><span>Provider telemetry</span><h3 id="role-usage-heading">Usage by role</h3></div><div>{roleUsage.map((item) => <article key={item.role}><span>{item.role}</span><strong>{item.attempts} request{item.attempts === 1 ? "" : "s"}</strong><small>{item.tokens.toLocaleString()} reported tokens / {item.failed} failed</small></article>)}</div></section>}
              <button className="secondary-action" type="button" onClick={downloadAudit}>Export JSON</button>
              <pre>{JSON.stringify(audit, null, 2)}</pre>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
