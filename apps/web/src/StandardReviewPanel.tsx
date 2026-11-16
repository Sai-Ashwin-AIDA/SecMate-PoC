import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { modelConnectivityService, ModelConnectivityError } from "./modelConnectivityService";
import type { DeepTeamRunRecord, StandardReviewView } from "./modelConnectivityService";
import { operationKey, validateStandardReview } from "./standardReview";
import { StandardRecommendationCards } from "./StandardRecommendationCards";

export function StandardReviewPanel({ run }: { run: DeepTeamRunRecord }) {
  if (!["synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1"].includes(run.target_profile_id)
      || run.execution_mode !== "SINGLE" || run.max_paths !== 1 || run.status !== "COMPLETED" || !run.artifact_available) return null;
  return <ReviewContent key={run.run_id} run={run} />;
}

function ReviewContent({ run }: { run: DeepTeamRunRecord }) {
  const navigate = useNavigate();
  const [view, setView] = useState<StandardReviewView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const pending = useRef(false);
  const alive = useRef(true);
  const eligible = ["synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1"].includes(run.target_profile_id)
    && run.execution_mode === "SINGLE" && run.max_paths === 1 && run.status === "COMPLETED" && run.artifact_available;
  useEffect(() => {
    alive.current = true;
    let disposed = false, timer = 0, failures = 0;
    setView(null); setError("");
    if (eligible) {
      const load = async () => {
        try {
          const next = await validateStandardReview(run.run_id, await modelConnectivityService.getStandardReview(run.run_id));
          if (disposed) return;
          setView(next); setError("");
          failures = 0;
          if (next.status === "RUNNING") timer = window.setTimeout(() => void load(), 1000);
        } catch (reason) {
          if (!disposed) {
            setError(reason instanceof Error ? reason.message : "Saved review unavailable.");
            if (++failures <= 3) timer = window.setTimeout(() => void load(), 1000 * 2 ** (failures - 1));
          }
        }
      };
      void load();
    }
    return () => { alive.current = false; disposed = true; window.clearTimeout(timer); };
  }, [run.run_id, eligible, version]);

  const act = async (action: () => Promise<unknown>, operation?: ReturnType<typeof operationKey>) => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const result = await action(); operation?.clear();
      if (alive.current) setVersion(value => value + 1);
      return result;
    } catch (reason) {
      // A received HTTP rejection is distinct from an unacknowledged request.
      // New explicit actions still pass the server's state/attempt/slot guards.
      if (reason instanceof ModelConnectivityError && reason.status >= 400 && reason.status < 500) operation?.clear();
      if (alive.current) setError(reason instanceof Error ? reason.message : "Action acceptance could not be confirmed. Check saved status before retrying.");
    } finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  if (!eligible) return null;
  const statusMessage = view?.status === "FAILED"
    ? view.can_retry ? "Review failed. Retry available." : "Review unavailable."
    : view?.message;
  return <section className="standard-review-panel" aria-label="Standard Attack Critic review">
    <header><div><span>Optional follow-up</span><h3>Attack Critic review</h3></div>
      <button type="button" className="secondary-action" disabled={busy} onClick={() => setVersion(value => value + 1)}>Refresh</button></header>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!view && !error && <p className="standard-review-status" role="status">Loading review status…</p>}
    <p className="standard-review-intro">Recommend a different method for a fresh follow-up assessment.</p>
    {statusMessage && <p className="standard-review-status">{statusMessage}</p>}
    {view?.status === "RUNNING" && <p className="standard-review-status" role="status">{view.cancel_requested ? "Stopping review…" : "Review in progress…"}</p>}
    {view && (view.can_request || view.can_retry) && <button type="button" className="primary-action" disabled={busy} onClick={() => {
      const operation = operationKey(`review.${run.run_id}.${view.attempts}`);
      void act(() => modelConnectivityService.requestStandardReview(run.run_id, view.can_retry, operation.key), operation);
    }}>{busy ? "Requesting…" : view.can_retry ? "Retry review · final attempt" : "Generate recommendations"}</button>}
    {view?.status === "RUNNING" && view.job_id && <button type="button" className="secondary-action" disabled={busy || view.cancel_requested}
      onClick={() => void act(() => modelConnectivityService.cancelReviewJob(view.job_id!))}>Cancel review</button>}
    {view?.status === "UNCERTAIN" && view.job_id && <button type="button" className="secondary-action" disabled={busy}
      onClick={() => void act(() => modelConnectivityService.resolveReviewJob(view.job_id!))}>Accept uncertainty and release stopped job</button>}
    {view?.status === "COMPLETED" && view.review && <>
      <p className="standard-review-intro">Priority is advisory, not a probability or score.</p>
      {view.review.recommendations.length > 0 && <StandardRecommendationCards recommendations={view.review.recommendations} disabled={busy} onChoose={async method => {
          const operation = operationKey(`draft.${run.run_id}.${view.review!.review_id}.${method}`);
          const draft = await act(() => modelConnectivityService.createLinkedAssessment(run.run_id, view.review!.review_id, method, operation.key), operation) as DeepTeamRunRecord | undefined;
          if (draft && alive.current) {
            if (draft.linked_context?.parent_run_id !== run.run_id || draft.linked_context.review_id !== view.review!.review_id
                || draft.linked_context.attack_profile_id !== method || draft.attack_profile_id !== method
                || draft.target_profile_id !== run.target_profile_id || draft.target_profile_version !== run.target_profile_version
                || draft.scenario !== run.scenario || draft.scenario_version !== run.scenario_version
                || draft.vulnerability_profile_id !== run.vulnerability_profile_id
                || draft.run_id === run.run_id) {
              setError("Linked draft acknowledgment does not match this recommendation."); return;
            }
            navigate(`/assessments?linked=${encodeURIComponent(draft.run_id)}`);
          }
        }} />}
      {!view.review.recommendations.length && <p className="standard-review-status">This legacy review has no recommendation.</p>}
      <details className="standard-review-details"><summary>Review details</summary><dl><div><dt>Review</dt><dd>{view.review.review_id}</dd></div><div><dt>Source path</dt><dd>{view.review.source_path_id}</dd></div>
        <div><dt>Critic model</dt><dd>{view.review.model}</dd></div><div><dt>Tokens accounted</dt><dd>{String(view.review.budget.tokens_consumed ?? "Not reported")}</dd></div>
        <div><dt>Input estimate</dt><dd>{view.review.input_tokens_estimate} / 4,000</dd></div><div className="standard-review-evidence-binding"><dt>Evidence binding</dt><dd>{view.review.source_audit_sha256}</dd></div></dl></details>
    </>}
  </section>;
}
