import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { chatmateService } from "./chatmateService";
import type { ChatMateCriticReview, ChatMateRunRecord } from "./chatmateService";
import { chatMateCriticSource, eligibleChatMateCritic, parseChatMateCriticReview, criticDisplayText, legacyCriticWarning, safeCriticRecommendation, effectiveCriticRecommendation } from "./chatmateCritic";
import { chatMateAttackName, chatMateDate, chatMateSafeDiagnostic } from "./chatmateDisplay";

type Props = { run: ChatMateRunRecord; audit: unknown; onRunChange?: (run: ChatMateRunRecord) => void };

export function CriticReviewPanel(props: Props) {
  if (!eligibleChatMateCritic(props.run, props.audit)) return null;
  const source = chatMateCriticSource(props.run, props.audit);
  // A different source must discard consent, cached content and in-flight responses.
  const identity = JSON.stringify([props.run.run_id, props.run.evaluation_id, props.run.selected_candidate_id,
    props.run.selected_candidate_sha256, source.candidate.prompt, props.run.manual_evidence?.correlation_sha256,
    props.run.manual_evidence?.persisted_response_sha256, props.run.manual_evidence?.redacted_response_text,
    props.run.candidate_batch?.assessment_spec, props.run.candidate_batch?.provenance, props.run.conversation_id ?? null, source.judge]);
  return <CriticReviewSession key={identity} {...props} />;
}

function CriticReviewSession({ run, audit, onRunChange }: Props) {
  const navigate = useNavigate();
  const id = useId();
  const [current, setCurrent] = useState(run);
  const [expanded, setExpanded] = useState(false);
  const [review, setReview] = useState<ChatMateCriticReview | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const alive = useRef(false);
  const pending = useRef(false);
  const callback = useRef(onRunChange);
  // The keyed session owns one validated source. Equivalent audit objects should
  // not cancel reads or restart polling while the parent refreshes its state.
  const sourceAudit = useRef(audit).current;
  const incomingCriticState = JSON.stringify([run.critic_status ?? null, run.critic_review_id ?? null,
    run.critic_review_available ?? false, run.critic_review_sha256 ?? null, run.critic_attempts ?? 0,
    run.critic_started_at ?? null, run.critic_completed_at ?? null, run.critic_error_code ?? null, run.critic_error_message ?? null]);
  const previousIncomingState = useRef(incomingCriticState);
  callback.current = onRunChange;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (previousIncomingState.current === incomingCriticState) return;
    previousIncomingState.current = incomingCriticState;
    const sameArtifact = run.critic_status === "COMPLETED" && run.critic_review_available === true
      && run.critic_review_id === current.critic_review_id && run.critic_started_at === current.critic_started_at
      && (run.critic_review_sha256 ?? null) === (current.critic_review_sha256 ?? null);
    setCurrent(run);
    if (!sameArtifact) setReview(null);
  }, [run, incomingCriticState, current.critic_review_id, current.critic_started_at, current.critic_review_sha256]);

  const accept = (next: ChatMateRunRecord) => {
    if (next.run_id !== run.run_id || !eligibleChatMateCritic(next, sourceAudit)) throw new Error("The assessment source changed. Reload the saved assessment before continuing.");
    if (alive.current) { setCurrent(next); callback.current?.(next); }
  };

  useEffect(() => {
    if (!expanded || review || (!reload && !["RUNNING", "COMPLETED"].includes(current.critic_status ?? ""))) return;
    let disposed = false;
    let timer = 0;
    const load = async () => {
      try {
        const next = await chatmateService.getRun(run.run_id);
        if (disposed) return;
        if (next.run_id !== run.run_id || !eligibleChatMateCritic(next, sourceAudit)) throw new Error("The assessment source changed. Reload the saved assessment.");
        if (next.critic_status === "COMPLETED") {
          const value = await chatmateService.getCritic(run.run_id);
          const saved = await parseChatMateCriticReview(next, sourceAudit, value);
          if (disposed) return;
          setCurrent(next);
          setReview(saved);
          setError("");
        } else if (next.critic_status === "FAILED") {
          setCurrent(next);
          setError("");
        } else if (next.critic_status === "RUNNING") {
          setCurrent(next);
          setError("");
          timer = window.setTimeout(() => void load(), 1500);
        } else if (next.critic_status == null) {
          setCurrent(next);
          setError("");
        } else throw new Error("Critic status is unavailable. Reload the saved assessment.");
      } catch (reason) {
        if (disposed) return;
        setError(chatMateSafeDiagnostic(reason instanceof Error ? reason.message : "Unable to load Critic review."));
        if (current.critic_status === "RUNNING") timer = window.setTimeout(() => void load(), 1500);
      }
    };
    if (current.critic_status === "RUNNING") timer = window.setTimeout(() => void load(), 1000);
    else void load();
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [expanded, current.critic_status, current.critic_review_id, current.critic_review_sha256, incomingCriticState, run.run_id, sourceAudit, review, reload]);

  const requestReview = async () => {
    if (pending.current || ![null, undefined, "FAILED"].includes(current.critic_status) || (current.critic_attempts ?? 0) >= 3) return;
    pending.current = true;
    setBusy("critic");
    setError("");
    try { accept(await chatmateService.requestCritic(run.run_id)); }
    catch (reason) { if (alive.current) setError(chatMateSafeDiagnostic(reason instanceof Error ? reason.message : "Unable to request Critic review.")); }
    finally { pending.current = false; if (alive.current) setBusy(""); }
  };

  const followUp = async () => {
    if (!review?.recommendation_available || pending.current) return;
    pending.current = true;
    setBusy("follow-up");
    setError("");
    try {
      const draft = await chatmateService.createFollowUp(run.run_id);
      const policy = draft.follow_up_context?.recommendation_policy;
      const expected = policy == null
        ? { profile: review.recommended_attack_profile_id, objective: review.recommended_follow_up_objective }
        : effectiveCriticRecommendation(current.attack_profile_id, String(current.candidate_batch?.assessment_spec.spec_id), String(current.final_status), review, String(policy));
      if (draft.status !== "DRAFT" || draft.authorization_attested !== false || draft.parent_run_id !== run.run_id
        || !expected || draft.follow_up_critic_review_id !== review.critic_review_id || draft.attack_profile_id !== expected.profile
        || draft.follow_up_objective !== expected.objective
        || JSON.stringify(draft.follow_up_expected_evidence) !== JSON.stringify(review.expected_evidence)
        || !draft.run_id || draft.run_id === run.run_id || draft.candidate_batch || draft.manual_evidence || draft.started_at) {
        throw new Error("The saved follow-up draft does not match this recommendation. Reload the assessment before continuing.");
      }
      if (alive.current) navigate(`/assessments/chatmate?run=${encodeURIComponent(draft.run_id)}`);
    } catch (reason) { if (alive.current) setError(chatMateSafeDiagnostic(reason instanceof Error ? reason.message : "Unable to save follow-up draft.")); }
    finally { pending.current = false; if (alive.current) setBusy(""); }
  };

  const status = current.critic_status === "RUNNING" ? "In progress" : current.critic_status === "COMPLETED" ? "Saved review"
    : current.critic_status === "FAILED" ? "Review failed" : "Not requested";
  const reloadSavedReview = () => {
    setReview(null);
    setError("");
    setReload((value) => value + 1);
  };
  return <section className="critic-review-panel" aria-label="Critic Review">
    <button className="critic-review-toggle" aria-expanded={expanded} aria-controls={id} type="button" onClick={() => setExpanded((value) => !value)}>
      <h3>Critic Review</h3><span className="chatmate-method-badge">{status}</span><span aria-hidden="true">{expanded ? "−" : "+"}</span>
    </button>
    <div className="critic-review-content" id={id} hidden={!expanded}>{expanded && <>
      <details className="chatmate-helper"><summary>How advisory review works</summary><p>Advisory analysis only. The original Judge verdict remains unchanged. Each explicitly approved attempt makes at most one provider call, with no automatic provider retries. Maximum: 3 attempts.</p></details>
      {error && <div className="inline-error" role="alert"><p>{error}</p><p>Refresh can retry reading saved status without making a provider call.</p><button className="secondary-action" type="button" disabled={Boolean(busy)} onClick={reloadSavedReview}>Reload saved review</button></div>}
      {current.critic_status === "RUNNING" && <p role="status">Attack Critic review is in progress. Attempt {current.critic_attempts} of 3. Status refreshes automatically while this panel is open.</p>}
      {current.critic_status === "COMPLETED" && !review && !error && <p role="status">Loading and verifying saved Critic review...</p>}
      {current.critic_status === "FAILED" && <div className="chatmate-validation"><strong>Critic review failed</strong><p>{chatMateSafeDiagnostic(current.critic_error_message ?? "The advisory provider did not produce a valid review.")}</p><p>The original result and evidence are preserved.</p></div>}
      {[null, undefined, "FAILED"].includes(current.critic_status) && <>
        {(current.critic_attempts ?? 0) >= 3 ? <p className="chatmate-helper">The 3-attempt Critic limit has been reached.</p> : <>
          <button className="primary-action" type="button" title="Send the redacted response and Judge summary to the configured Critic." disabled={Boolean(busy)} onClick={() => void requestReview()}>{busy === "critic" ? "Requesting review..." : current.critic_status === "FAILED" ? "Retry Critic Review" : "Request Critic Review"}</button>
        </>}
      </>}
      {review && <>
        {legacyCriticWarning(review) && <p className="chatmate-validation">{legacyCriticWarning(review)}</p>}
        <section><h3>Management summary</h3><p>{criticDisplayText(review.management_summary)}</p></section>
        <section><h3>Attack effectiveness</h3><p>Reviewed method: {chatMateAttackName(current)}</p><p>{criticDisplayText(review.attack_effectiveness_analysis)}</p></section>
        <section><h3>Outcome analysis</h3><p>{criticDisplayText(review.outcome_analysis)}</p></section>
        <section><h3>{review.weak_point_status === "NONE_OBSERVED" ? "No weak point observed" : review.weak_point_status === "HYPOTHESIS" ? "Weak-point hypothesis" : "Evidence-supported observation"}</h3><p>{criticDisplayText(review.observed_weak_point ?? "No weak point was observed in the reviewed evidence.")}</p></section>
        <section><h3>Recommended follow-up</h3><p><strong>{chatMateAttackName({ ...current, attack_profile_id: review.recommended_attack_profile_id })}</strong></p><p>{criticDisplayText(review.recommended_follow_up_objective)}</p><h4>Expected evidence</h4><ul>{review.expected_evidence.map((item, index) => <li key={index}>{criticDisplayText(item)}</li>)}</ul></section>
        <section><h3>Evidence and policy references</h3><dl className="detail-list"><div><dt>Evidence</dt><dd>{review.evidence_references.join(", ") || "None cited"}</dd></div><div><dt>Policies</dt><dd>{review.policy_references.join(", ") || "None cited"}</dd></div></dl></section>
        {!review.recommendation_available && <div className="chatmate-validation" role="status"><strong>Recommendation needs review</strong><p>Missing or invalid references prevent creating a follow-up.</p>{Boolean(review.invalid_evidence_references.length || review.invalid_policy_references.length) && <p>Invalid references: {[...review.invalid_evidence_references, ...review.invalid_policy_references].join(", ")}</p>}</div>}
        {!safeCriticRecommendation(review) && <p className="chatmate-validation">The saved recommendation has incomplete or unsafe text; follow-up creation is blocked.</p>}
        {(() => {
          const plan = effectiveCriticRecommendation(current.attack_profile_id, String(current.candidate_batch?.assessment_spec.spec_id), String(current.final_status), review);
          return <>{plan?.adjusted && <p className="chatmate-validation">Policy-adjusted follow-up: {plan.profile}. {plan.objective} The model's original recommendation is retained above.</p>}
            {!plan && <p className="chatmate-validation">Follow-up unavailable: no eligible recommendation compatible with the frozen assessment boundary.</p>}
            <button className="primary-action" type="button" disabled={!plan || !safeCriticRecommendation(review) || Boolean(busy)} onClick={() => void followUp()}>{busy === "follow-up" ? "Saving follow-up draft..." : "Start recommended follow-up"}</button></>;
        })()}
        {!error && <button className="secondary-action" type="button" disabled={Boolean(busy)} onClick={reloadSavedReview}>Reload saved review</button>}
        <details className="report-technical-details"><summary>Critic provider metadata</summary><dl className="detail-list chatmate-metadata-grid">
          <div><dt>Provider / model</dt><dd>{review.provider} / {review.model}</dd></div><div><dt>Provider call count</dt><dd>{String(review.budget.provider_calls_attempted)} · {current.critic_attempts} of 3 attempts</dd></div>
          <div><dt>Model profile</dt><dd>{review.profile_id}</dd></div><div><dt>Started / completed</dt><dd>{chatMateDate(review.created_at)} / {chatMateDate(current.critic_completed_at)}</dd></div>
          <div><dt>Review ID</dt><dd><code>{review.critic_review_id}</code></dd></div><div><dt>Source evaluation</dt><dd><code>{review.source_evaluation_id}</code></dd></div><div><dt>Source Judge SHA-256</dt><dd><code>{review.source_judge_sha256}</code></dd></div>
          <div><dt>Source candidate SHA-256</dt><dd><code>{review.source_candidate_sha256}</code></dd></div><div><dt>Source correlation SHA-256</dt><dd><code>{review.source_correlation_sha256}</code></dd></div>
          <div><dt>Source input SHA-256</dt><dd><code>{review.source_input_sha256}</code></dd></div><div><dt>System instruction SHA-256</dt><dd><code>{review.critic_system_instruction_sha256}</code></dd></div><div><dt>User prompt SHA-256</dt><dd><code>{review.critic_user_prompt_sha256}</code></dd></div>
        </dl><pre>{JSON.stringify({ budget: review.budget, model_attempts: review.model_attempts }, null, 2)}</pre></details>
      </>}
    </>}</div>
  </section>;
}
