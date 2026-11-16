import { Link } from "react-router-dom";
import type { DeepTeamAuditReport } from "./modelConnectivityService";
import { useDeepTeamEvidence } from "./useDeepTeamEvidence";
import { assessmentDisplayName, assessmentFailureMessage, targetDisplayName } from "./displayLabels";

const ACTIVE_RUN_KEY = "secmate.activeDeepteamRun";

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

function displayNumber(value: unknown, fallback = "Not reported") {
  return typeof value === "number" ? value.toLocaleString("en-US") : fallback;
}

function firstText(...values: unknown[]) {
  return values.find((value): value is string => typeof value === "string" && value.trim().length > 0);
}

function evidenceSummary(audit: DeepTeamAuditReport | null) {
  const paths = records(audit?.evidence.paths);
  const firstPath = paths[0];
  const oracle = records(firstPath?.oracle_results)[0];
  const engine = record(firstPath?.engine_result);
  const review = records(audit?.evidence.review_results)[0];
  const targetEvaluation = record(review?.target_evaluation);
  return firstText(
    targetEvaluation?.reasoning,
    review?.summary,
    oracle?.detail,
    engine?.native_reason,
    audit?.summary.evidence_summary,
    audit?.deepteam_risk.summary,
  ) ?? "The live assessment produced evidence requiring security review.";
}

export function LiveFindingsPanel() {
  const savedRunId = window.localStorage.getItem(ACTIVE_RUN_KEY);
  const { run, audit, loading, error, retry } = useDeepTeamEvidence(savedRunId);

  if (!savedRunId) {
    return (
      <section className="live-findings-panel live-findings-info">
        <div>
          <span className="live-findings-kicker">Assessment outcome</span>
          <strong>No assessment selected</strong>
          <p>Select or start an assessment to review its result here.</p>
        </div>
        <Link className="secondary-action" to="/assessments">View assessments</Link>
      </section>
    );
  }

  if (loading && !run) {
    return <section className="live-findings-panel live-findings-state" aria-live="polite">Loading assessment outcome...</section>;
  }

  if (error && !run) {
    return (
      <section className="live-findings-panel live-findings-state" role="alert">
        <strong>Assessment outcome unavailable</strong>
        <span>{error}</span>
        <button className="secondary-action" type="button" onClick={retry}>Retry evidence</button>
      </section>
    );
  }

  if (!run) return null;

  const attempts = records(audit?.summary.model_attempts);
  const budget = record(audit?.summary.budget);
  const rateLimited = ["RATE_LIMITED", "PROVIDER_RATE_LIMITED"].includes(run.error_code ?? "") || attempts.some((attempt) => attempt.error_code === "RATE_LIMITED");
  const failedAttempts = attempts.filter((attempt) => firstText(attempt.error_code, attempt.error_message) || attempt.status === "FAILED");
  const failure = run.status === "FAILED" || run.final_status === "ERROR" || Boolean(run.error_code);
  const providerCalls = budget?.provider_calls_attempted ?? attempts.length;
  const failedCalls = budget?.provider_calls_failed ?? budget?.failed_calls ?? failedAttempts.length;
  const tokensConsumed = budget?.tokens_consumed;
  const maxTokens = budget?.max_total_tokens ?? run.max_total_tokens;
  const tokenBudgetOverrun = budget?.token_budget_overrun === true;
  const pending = ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(run.status);

  const riskLabel = assessmentDisplayName(run.vulnerability);
  const attackLabel = assessmentDisplayName(run.attack);
  const targetLabel = targetDisplayName(run.target_profile_id);
  let title = "Live assessment in progress";
  let summary = `Wait while ${riskLabel.toLowerCase()} is tested with ${attackLabel}.`;
  let assurance = false;

  if (run.status === "CANCELLED") {
    title = "Assessment cancelled";
    summary = "The campaign was stopped before a final Target outcome was established. No security finding was generated.";
  } else if (failure) {
    title = rateLimited ? "Provider rate limit prevented assessment completion" : "Assessment worker failed to complete";
    summary = rateLimited
      ? "The assessment harness could not complete its provider calls. This is a harness/provider failure, not a Target security compromise."
      : assessmentFailureMessage(run.error_message, attempts);
  } else if (run.final_status === "COMPROMISED") {
    title = `${riskLabel} exposed by ${attackLabel}`;
    summary = evidenceSummary(audit);
  } else if (run.final_status === "INCONCLUSIVE") {
    title = "Assessment inconclusive";
    summary = evidenceSummary(audit);
  } else if (run.status === "COMPLETED" && run.final_status === "RESISTED") {
    title = "No security finding generated";
    summary = "The target resisted this attack. This is an observation for this attempt, not proof of resistance to every attack.";
    assurance = true;
  }

  return (
    <section className={`live-findings-panel${assurance ? " assurance" : ""}`} aria-live={pending ? "polite" : undefined}>
      <div className="live-findings-main">
        <div className="live-findings-heading">
          <span className="live-findings-kicker">{assurance ? "Assurance observation" : pending ? "Assessment activity" : "Assessment outcome"}</span>
          <div>
            {assurance && <span className="live-assurance-chip">Resisted</span>}
            {pending && <span className="status-chip running">{run.status}</span>}
            <h2>{title}</h2>
          </div>
          <p>{summary}</p>
          <small>{targetLabel} / {riskLabel} / {attackLabel}</small>
        </div>
        {failure && (
          <details className="console-details"><summary>Runtime diagnostics</summary><dl className="live-findings-metrics">
            <div><dt>Provider calls</dt><dd>{displayNumber(providerCalls, "0")}</dd></div>
            <div><dt>Failed calls</dt><dd>{displayNumber(failedCalls, "0")}</dd></div>
            <div><dt>Consumed / max tokens</dt><dd>{displayNumber(tokensConsumed, "0")} / {displayNumber(maxTokens)}</dd></div>
            <div><dt>Token budget overrun</dt><dd>{tokenBudgetOverrun ? "Yes" : "No"}</dd></div>
          </dl></details>
        )}
      </div>
      {error && <div className="inline-error" role="alert">Refresh failed: {error} <button className="secondary-action" type="button" onClick={retry}>Retry evidence</button></div>}
      <div className="live-findings-actions">
        <Link className="primary-action" to="/reports?live=1">View live report</Link>
        <Link className="secondary-action" to="/assessments">Assessments</Link>
      </div>
    </section>
  );
}
