import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { chatmateService } from "./chatmateService";
import type {
  ChatMateAttackProfileId,
  ChatMateRunRecord,
} from "./chatmateService";
import type { DeepTeamAuditReport } from "./modelConnectivityService";
import { chatMateCandidate, chatMateReportLink, chatMateResultLabel, eligibleChatMateResult, parseChatMateAudit } from "./chatmateProjections";
import { chatMateAttackName, chatMateCanRetryJudge, chatMateGenerationFailed, chatMateRunReference } from "./chatmateDisplay";
import { ChatMateRunError } from "./ChatMateReportPanel";
import { ChatMateRunHistory } from "./ChatMateRunHistory";
import { ChatMateConfirmation, ChatMateDiagnostics, ChatMatePollingMessage } from "./ChatMateRunFeedback";
import { CriticReviewPanel } from "./CriticReviewPanel";
import { CHATMATE_SCORE_GUIDANCE, ChatMateJudgeRationale, chatMateScoreCategory, chatMateGradedResult } from "./ChatMateJudgeDetails";
import { EvidenceResponse } from "./EvidencePresentation";
import { AssessmentSelect } from "./AssessmentSelect";
import { ChatMatePromptPreview } from "./ChatMatePromptPreview";
import { BaselineMethodReview } from "./BaselineMethodReview";
import { assessmentUrl, currentAssessment, forgetAssessment, rememberAssessment } from "./assessmentSession";

const ACTIVE_STATUSES = new Set(["QUEUED", "GENERATING", "EVALUATING"]);

const ATTACK_METHODS: Array<{
  id: ChatMateAttackProfileId;
  name: string;
  label: string;
  description: string;
}> = [
  { id: "prompt-injection-v1", name: "Prompt Injection", label: "Instruction control", description: "Attempts to make ChatMate disregard trusted instructions and adopt the attacker's objective." },
  { id: "system-override-v1", name: "System Override", label: "Fabricated authority", description: "Frames user text as a higher-priority system, developer, or policy instruction." },
  { id: "prompt-probing-v1", name: "Prompt Probing", label: "Hidden controls", description: "Attempts to expose non-public instructions or operating configuration." },
  { id: "goal-redirection-v1", name: "Goal Redirection", label: "Task displacement", description: "Attempts to replace ChatMate's intended task with an attacker-selected objective." },
  { id: "context-poisoning-v1", name: "Context Poisoning", label: "False context", description: "Supplies fabricated context and pressures ChatMate to treat it as trusted." },
];

function statusStep(run: ChatMateRunRecord | null) {
  if (!run || run.status === "DRAFT") return 1;
  if (chatMateGenerationFailed(run)) return 2;
  if (["QUEUED", "GENERATING", "AWAITING_SELECTION"].includes(run.status)) return 2;
  if (["AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING"].includes(run.status)) return 3;
  return 4;
}

export function ChatMatePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const recoveryRunId = new URLSearchParams(location.search).get("run");
  const recoveryRequested = new URLSearchParams(location.search).has("run");
  useEffect(() => {
    const remembered = currentAssessment();
    if (!recoveryRequested && remembered) navigate(assessmentUrl(remembered), { replace: true });
  }, [recoveryRequested, navigate]);
  const mountedRef = useRef(true);
  const requestVersionRef = useRef(0);
  const submissionPendingRef = useRef(false);
  const [attackId, setAttackId] = useState<ChatMateAttackProfileId>("prompt-injection-v1");
  const [tokenBudget, setTokenBudget] = useState(100_000);
  const [run, setRun] = useState<ChatMateRunRecord | null>(null);
  const [audit, setAudit] = useState<DeepTeamAuditReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const [copyState, setCopyState] = useState("");
  const [outcome, setOutcome] = useState<"RESPONSE" | "VISIBLE_FAILURE">("RESPONSE");
  const [responseText, setResponseText] = useState("");
  const [recoveryAttempt, setRecoveryAttempt] = useState(0);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [confirmReturn, setConfirmReturn] = useState(false);
  const [responseInputError, setResponseInputError] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [followUpDismissed, setFollowUpDismissed] = useState(false);
  const [comparePrompts, setComparePrompts] = useState(false);
  const currentCandidate = chatMateCandidate(run);
  const currentStep = statusStep(run);

  useLayoutEffect(() => {
    mountedRef.current = true;
    requestVersionRef.current += 1;
    submissionPendingRef.current = false;
    setRun(null);
    setAudit(null);
    setAttackId("prompt-injection-v1");
    setTokenBudget(100_000);
    setOutcome("RESPONSE");
    setResponseText("");
    setCopyState("");
    setAction("");
    setError("");
    setConfirmEnd(false);
    setConfirmReturn(false);
    setResponseInputError("");
    setConversationId("");
    setFollowUpDismissed(false);
    setComparePrompts(false);
    setLoading(Boolean(recoveryRunId));
    return () => { mountedRef.current = false; requestVersionRef.current += 1; };
  }, [location.key, location.search, recoveryAttempt]);

  useEffect(() => {
    const version = requestVersionRef.current;
    if (!recoveryRunId) return;
    chatmateService.getRun(recoveryRunId)
      .then((saved) => {
        if (!mountedRef.current || version !== requestVersionRef.current) return;
        if (saved.run_id !== recoveryRunId) throw new Error("The restored assessment does not match the selected run. Reload the saved assessment.");
        setRun(saved);
        rememberAssessment(saved.run_id);
        setAttackId(saved.attack_profile_id);
        setTokenBudget(saved.max_total_tokens);
      })
      .catch((reason) => {
        if (reason instanceof Error && "missingRun" in reason && reason.missingRun === true) forgetAssessment(recoveryRunId);
        if (mountedRef.current && version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to restore the saved ChatMate run.");
      })
      .finally(() => { if (mountedRef.current && version === requestVersionRef.current) setLoading(false); });
  }, [location.key, location.search, recoveryAttempt, recoveryRunId]);

  useEffect(() => {
    if (!run || !ACTIVE_STATUSES.has(run.status)) return;
    let disposed = false;
    let timer = 0;
    const version = requestVersionRef.current;
    const poll = async () => {
      try {
        const next = await chatmateService.getRun(run.run_id);
        if (!disposed && mountedRef.current && version === requestVersionRef.current) {
          setRun(next);
          setError("");
        }
      } catch (reason) {
        if (!disposed && mountedRef.current && version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to refresh ChatMate status.");
      } finally {
        if (!disposed && version === requestVersionRef.current) timer = window.setTimeout(() => void poll(), 1500);
      }
    };
    timer = window.setTimeout(() => void poll(), 1000);
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [run?.run_id, run?.status]);

  useEffect(() => {
    if (!run?.artifact_available || !eligibleChatMateResult(run) || audit) return;
    const version = requestVersionRef.current;
    chatmateService.getAudit(run.run_id)
      .then((report) => {
        if (!mountedRef.current || version !== requestVersionRef.current) return;
        parseChatMateAudit(run, report);
        setAudit(report);
      })
      .catch((reason) => { if (mountedRef.current && version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to load the ChatMate audit."); });
  }, [audit, run]);

  const judgeEvaluation = useMemo(() => {
    if (!run || !audit) return null;
    try { return parseChatMateAudit(run, audit).judge; } catch { return null; }
  }, [audit, run]);

  const generate = async () => {
    if (action || submissionPendingRef.current || (run && run.status !== "DRAFT")) return;
    submissionPendingRef.current = true;
    const version = requestVersionRef.current;
    setAction("generate");
    setError("");
    setAudit(null);
    try {
      const next = run?.status === "DRAFT"
        ? await chatmateService.generateDraft(run.run_id, { max_total_tokens: tokenBudget, authorization_attested: true })
        : await chatmateService.createRun({ attack_profile_id: attackId, max_total_tokens: tokenBudget, authorization_attested: true });
      rememberAssessment(next.run_id);
      if (version !== requestVersionRef.current) return;
      if (run?.status === "DRAFT" && (next.run_id !== run.run_id || next.status !== "QUEUED" || next.authorization_attested !== true)) throw new Error("Draft generation returned an unexpected assessment. Reload the saved draft.");
      navigate(`/assessments/chatmate?run=${encodeURIComponent(next.run_id)}`);
    } catch (reason) {
      if (version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to generate ChatMate attacks.");
    } finally {
      if (version === requestVersionRef.current) { setAction(""); submissionPendingRef.current = false; }
    }
  };

  const select = async (candidateId: string) => {
    if (!run) return;
    const version = requestVersionRef.current;
    setAction(candidateId);
    setError("");
    try {
      const next = await chatmateService.selectCandidate(run.run_id, candidateId);
      if (version === requestVersionRef.current) setRun(next);
    } catch (reason) {
      if (version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to select the candidate.");
    } finally {
      if (version === requestVersionRef.current) setAction("");
    }
  };

  const rejectAll = async () => {
    if (!run) return;
    const version = requestVersionRef.current;
    setAction("reject");
    setError("");
    try {
      const next = await chatmateService.rejectCandidates(run.run_id);
      if (version === requestVersionRef.current) setRun(next);
    } catch (reason) {
      if (version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to reject the candidates.");
    } finally {
      if (version === requestVersionRef.current) setAction("");
    }
  };

  const copyCandidate = async () => {
    if (!currentCandidate) return;
    const version = requestVersionRef.current;
    try {
      await navigator.clipboard.writeText(currentCandidate.prompt);
      if (version === requestVersionRef.current) setCopyState("Copied exactly. Submit it unchanged in ChatMate.");
    } catch {
      if (version === requestVersionRef.current) setCopyState("Copy unavailable");
    }
  };

  const submitResponse = async () => {
    if (!run || run.status !== "AWAITING_RESPONSE" || !currentCandidate || !responseReady || action || submissionPendingRef.current) return;
    submissionPendingRef.current = true;
    const version = requestVersionRef.current;
    setAction("response");
    setError("");
    try {
      const next = await chatmateService.submitResponse(run.run_id, {
        candidate_id: currentCandidate.candidate_id,
        candidate_sha256: currentCandidate.prompt_sha256,
        outcome,
        ...(outcome === "RESPONSE" ? { response_text: responseText } : { failure_reason: "RESPONSE_COULD_NOT_BE_COMPLETED" as const }),
        prompt_submitted_unchanged: true,
        observation_captured_verbatim: true,
        judge_data_collection_attested: outcome === "RESPONSE",
        ...(conversationId.trim() ? { conversation_id: conversationId.trim() } : {}),
      });
      if (version === requestVersionRef.current) setRun(next);
    } catch (reason) {
      if (version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to submit the ChatMate response.");
    } finally {
      if (version === requestVersionRef.current) { setAction(""); submissionPendingRef.current = false; }
    }
  };

  const retryEvaluation = async () => {
    if (!run || !(run.status === "AWAITING_EVALUATION" || chatMateCanRetryJudge(run))) return;
    const version = requestVersionRef.current;
    setAction("retry");
    setError("");
    try {
      const next = await chatmateService.retryEvaluation(run.run_id);
      if (version === requestVersionRef.current) setRun(next);
    } catch (reason) {
      if (version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to retry the Judge evaluation.");
    } finally {
      if (version === requestVersionRef.current) setAction("");
    }
  };

  const reset = () => {
    forgetAssessment();
    requestVersionRef.current += 1;
    navigate("/assessments/chatmate");
  };

  const returnToConfigure = () => {
    const unsentObservation = run?.status === "AWAITING_RESPONSE" && !run.manual_evidence
      && (responseText.length > 0 || conversationId.length > 0 || outcome === "VISIBLE_FAILURE");
    if (unsentObservation) setConfirmReturn(true);
    else reset();
  };

  const abandon = async () => {
    if (!run || action || submissionPendingRef.current || run.manual_evidence || !["DRAFT", "AWAITING_SELECTION", "AWAITING_RESPONSE"].includes(run.status)) return;
    submissionPendingRef.current = true;
    const version = requestVersionRef.current;
    setAction("abandon");
    setError("");
    try {
      await chatmateService.abandonRun(run.run_id);
      if (version === requestVersionRef.current) reset();
    } catch (reason) {
      if (version === requestVersionRef.current) setError(reason instanceof Error ? reason.message : "Unable to end this run.");
    } finally {
      if (version === requestVersionRef.current) { setAction(""); submissionPendingRef.current = false; }
    }
  };

  const unmetRequirements = [
    ...(outcome === "RESPONSE" && !responseText.trim() ? ["Paste a nonblank ChatMate response."] : []),
    ...(outcome === "RESPONSE" && responseText.length > 20_000 ? ["Keep the response within 20,000 characters."] : []),
    ...(conversationId.trim() && (conversationId.trim().length > 128 || /\p{C}/u.test(conversationId.trim())) ? ["Use a conversation ID of at most 128 characters without control characters."] : []),
  ];
  const responseReady = Boolean(
    (!conversationId.trim() || (conversationId.trim().length <= 128 && !/\p{C}/u.test(conversationId.trim())))
    && (outcome === "VISIBLE_FAILURE" || (!responseInputError && responseText.trim() && responseText.length <= 20_000)),
  );

  if (loading && !run) return <section className="chatmate-page chatmate-panel chatmate-loading" role="status">Loading ChatMate assessment...</section>;

  if (recoveryRequested && !run) return (
    <section className="chatmate-page">
      {error && <div className="inline-error" role="alert">{error}</div>}
      <section className="chatmate-panel chatmate-result neutral">
        <span>Selected run</span><h3>ChatMate run could not be restored</h3><p>This run may be missing or the API may be unavailable. Retry or return to a new assessment.</p>
        <div className="chatmate-result-actions"><button className="primary-action" onClick={() => setRecoveryAttempt((value) => value + 1)} type="button">Retry recovery</button><button className="secondary-action" onClick={reset} type="button">Return to new assessment</button></div>
      </section>
    </section>
  );

  return (
    <section className="chatmate-page" aria-labelledby="chatmate-heading">
      <header className="chatmate-hero">
        <div>
          <Link to="/assessments">Assessments / ChatMate</Link>
          <h2 id="chatmate-heading">ChatMate</h2>
          <p>Generate prompts, capture a response, and review the result.</p>
        </div>
        {run && <div className="chatmate-hero-actions"><button className="secondary-action" onClick={returnToConfigure} type="button">Return to new assessment</button></div>}
      </header>

      <ol className="chatmate-steps" aria-label="ChatMate assessment progress">
        {["Configure", "Select attack", "Submit response", "Review result"].map((label, index) => (
          <li aria-current={currentStep === index + 1 ? "step" : undefined} className={currentStep > index ? "active" : ""} key={label}><i>{index + 1}</i><span>{label}</span></li>
        ))}
      </ol>

      {error && <div className="inline-error" role="alert">{error}</div>}
      {confirmReturn && <ChatMateConfirmation title="Discard unsent observation?" description="Return to Configure and discard the unsent observation? This run and its selected attack remain available in history." confirmLabel="Discard and return" cancelLabel="Keep this observation" busy={Boolean(action)} onConfirm={reset} onCancel={() => setConfirmReturn(false)} />}


      {run?.parent_run_id && !followUpDismissed && <aside className="chatmate-follow-up-banner" aria-label="Recommended follow-up context">
        <div><strong>Recommended follow-up</strong><p><Link to={`/assessments/chatmate?run=${encodeURIComponent(run.parent_run_id)}`}>View parent assessment</Link> · {chatMateRunReference(run.parent_run_id)} · <code>{run.follow_up_critic_review_id}</code></p><p>{run.follow_up_objective}</p><ul>{run.follow_up_expected_evidence?.map((item, index) => <li key={index}>{item}</li>)}</ul></div>
        <button className="chatmate-tertiary-action" type="button" aria-label="Dismiss follow-up context" onClick={() => setFollowUpDismissed(true)}>Dismiss</button>
      </aside>}

      {(!run || run.status === "DRAFT") && (
        <section className="chatmate-panel">
          <div className="chatmate-section-heading"><span>Step 1</span><h3>Choose an attack method</h3></div>
          <div className="chatmate-method-grid">
            {ATTACK_METHODS.map((method) => (
              <button aria-pressed={attackId === method.id} disabled={run?.status === "DRAFT" || Boolean(action)} className={attackId === method.id ? "selected" : ""} key={method.id} onClick={() => setAttackId(method.id)} type="button">
                <span>{method.label}</span><strong>{method.name}</strong><p>{method.description}</p>
              </button>
            ))}
          </div>
          <div className="chatmate-config-row">
            <AssessmentSelect label="Generation budget" value={String(tokenBudget)} onChange={value => setTokenBudget(Number(value))}
              options={[...(![50000, 100000, 150000].includes(tokenBudget) ? [tokenBudget] : []), 50000, 100000, 150000].map(value => ({ value: String(value), label: `${value.toLocaleString()} tokens` }))} />
            <button className="primary-action" title="Start this authorized assessment and generate two prompts." disabled={Boolean(action)} onClick={() => void generate()} type="button">{action === "generate" ? "Generating attacks..." : "Generate 2 attacks"}</button>
          </div>
          {run?.status === "DRAFT" && <button className="chatmate-tertiary-action" disabled={Boolean(action)} onClick={() => void abandon()} type="button">Abandon draft</button>}
        </section>
      )}

      {run && ["QUEUED", "GENERATING"].includes(run.status) && (
        <section className="chatmate-panel chatmate-waiting" aria-live="polite"><span className="chatmate-spinner" /><div><div className="chatmate-section-heading"><span>Step 2</span><h3>Generating two attack prompts</h3></div><ChatMatePollingMessage since={run.started_at ?? run.created_at} />{run.logs.at(-1)?.message.startsWith("Generation progress:") && <p>{run.logs.at(-1)?.message}</p>}<ChatMateDiagnostics run={run} /></div></section>
      )}

      {run?.status === "AWAITING_SELECTION" && run.candidate_batch && (
        <section className="chatmate-panel">
          <div className="chatmate-section-heading"><span>Step 2</span><h3>Select one generated attack</h3><p>Review all {run.candidate_batch.candidates.length} outputs. SecMate will freeze and evaluate only the candidate you select.</p></div>
          <aside className="chatmate-choice-summary" aria-label="Configured attack"><dl><div><dt>Configured attack method</dt><dd>{chatMateAttackName(run)}</dd></div><div><dt>Generation budget</dt><dd>{run.max_total_tokens.toLocaleString()} tokens</dd></div></dl></aside>
          <button className="secondary-action" type="button" aria-pressed={comparePrompts} onClick={() => setComparePrompts((value) => !value)}>{comparePrompts ? "Collapse exact prompts" : "Compare exact prompts"}</button>
          <div className="chatmate-candidate-grid">
            {run.candidate_batch.candidates.map((candidate) => (
              <article key={candidate.candidate_id}>
                <header><span>Candidate {candidate.ordinal}</span><code>{candidate.prompt_sha256.slice(0, 12)}</code></header>
                {candidate.generation_mode === "BASELINE_METHOD_ALIGNED" && <small>Method-aligned baseline</small>}
                <BaselineMethodReview candidate={candidate} />
                {candidate.explanation && <p>{candidate.explanation.approach}</p>}
                <ChatMatePromptPreview prompt={candidate.prompt} compare={comparePrompts} />
                {candidate.explanation && <details><summary>Intent, strengths & limitations</summary><dl><dt>Intended effect</dt><dd>{candidate.explanation.intended_effect}</dd><dt>Why choose this candidate</dt><dd>{candidate.explanation.selection_reason}</dd></dl><strong>Strengths</strong><ul>{candidate.explanation.strengths.map((text, i) => <li key={i}>{text}</li>)}</ul><strong>Limitations</strong><ul>{candidate.explanation.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul><small>Model-generated explanation of intent, not measured effectiveness.</small></details>}
                <button className="primary-action" disabled={Boolean(action)} onClick={() => void select(candidate.candidate_id)} type="button">{action === candidate.candidate_id ? "Selecting..." : `Select candidate ${candidate.ordinal}`}</button>
              </article>
            ))}
          </div>
          <div className="chatmate-action-bar"><button className="secondary-action" disabled={Boolean(action)} onClick={() => void abandon()} type="button">Back to Configure</button><button className="danger-action" disabled={Boolean(action)} onClick={() => void rejectAll()} type="button">{action === "reject" ? "Ending run..." : "Reject all and end run"}</button></div>
        </section>
      )}

      {run?.status === "AWAITING_RESPONSE" && currentCandidate && (
        <section className="chatmate-panel">
          <div className="chatmate-section-heading"><span>Step 3</span><h3>Run the selected attack in ChatMate</h3><p>Copy this exact prompt into a new authorized ChatMate conversation, then return with the complete response.</p></div>
          <aside className="chatmate-choice-summary" aria-label="Configuration and selected attack"><dl><div><dt>Configured attack method</dt><dd>{chatMateAttackName(run)}</dd></div><div><dt>Generation budget</dt><dd>{run.max_total_tokens.toLocaleString()} tokens</dd></div><div><dt>Selected candidate</dt><dd>Candidate {currentCandidate.ordinal}</dd></div></dl>{currentCandidate.explanation && <p>{currentCandidate.explanation.approach}</p>}</aside>
          <article className="chatmate-selected-prompt"><header><div><span>Selected attack</span><strong>{chatMateAttackName(run)}</strong></div><code>{currentCandidate.prompt_sha256.slice(0, 16)}</code></header><BaselineMethodReview candidate={currentCandidate} /><pre>{currentCandidate.prompt}</pre><button className="secondary-action" onClick={() => void copyCandidate()} type="button">Copy exact attack</button>{copyState && <small>{copyState}</small>}</article>
          <div className="chatmate-response-form">
            <fieldset><legend>Observed result</legend><label><input checked={outcome === "RESPONSE"} name="outcome" onChange={() => { setOutcome("RESPONSE"); setConversationId(""); }} type="radio" /> ChatMate returned a response</label><label><input checked={outcome === "VISIBLE_FAILURE"} name="outcome" onChange={() => { setOutcome("VISIBLE_FAILURE"); setConversationId(""); }} type="radio" /> Response could not be completed</label></fieldset>
            {outcome === "RESPONSE" && <label className="chatmate-response-text"><span>Exact ChatMate response</span><textarea aria-label="Exact ChatMate response" aria-invalid={Boolean(responseInputError) || responseText.length > 20000} aria-describedby={responseInputError ? "chatmate-response-error" : undefined} onPaste={(event) => {
              const text = event.clipboardData.getData("text/plain");
              const input = event.currentTarget;
              if (text.length > 20000 || responseText.length - (input.selectionEnd - input.selectionStart) + text.length > 20000) {
                event.preventDefault();
                setResponseInputError("The complete response exceeds 20,000 characters. Nothing was pasted; existing text is unchanged. Submit only a complete response within the supported limit.");
              } else {
                setResponseInputError("");
              }
            }} onChange={(event) => { setResponseText(event.target.value); setResponseInputError(""); }} placeholder="Paste the complete response without edits" rows={9} value={responseText} /><small>{responseText.length.toLocaleString()} / 20,000 characters</small>{responseInputError && <small id="chatmate-response-error" role="alert">{responseInputError}</small>}</label>}
            {outcome === "RESPONSE" && responseText && <details className="chatmate-response-preview"><summary>Response display preview · submitted text stays unchanged</summary><EvidenceResponse text={responseText} /></details>}
            <label className="chatmate-conversation-field"><span>Conversation ID (optional)</span><input aria-label="Conversation ID (optional)" type="text" maxLength={128} value={conversationId} onChange={(event) => setConversationId(event.target.value)} autoComplete="off" /><small>Enter only the conversation reference provided by ChatMate, if available. SecMate validates and redacts it.</small></label>
            {unmetRequirements.length > 0 && <details className="chatmate-validation"><summary>Before submitting</summary><ul>{unmetRequirements.map((requirement) => <li key={requirement}>{requirement}</li>)}</ul></details>}
            <div className="chatmate-action-bar"><div><button className="primary-action" title="Confirm the prompt was submitted unchanged and this is the complete observation; send the redacted response to the Judge." disabled={!responseReady || Boolean(action)} onClick={() => void submitResponse()} type="button">{action === "response" ? "Submitting evidence..." : "Submit response for evaluation"}</button></div><button className="chatmate-tertiary-action" disabled={Boolean(action)} onClick={() => setConfirmEnd(true)} type="button">End run and start over</button></div>
            {confirmEnd && <ChatMateConfirmation title="Confirm ending run" description="End this run and discard the unsent observation? The selected attack remains preserved in history." confirmLabel="Confirm end run" cancelLabel="Keep this run" busy={Boolean(action)} onConfirm={() => void abandon()} onCancel={() => setConfirmEnd(false)} />}
          </div>
        </section>
      )}

      {run && ["AWAITING_EVALUATION", "EVALUATING"].includes(run.status) && (
        <section className="chatmate-panel chatmate-waiting" aria-live="polite"><span className="chatmate-spinner" /><div><div className="chatmate-section-heading"><span>Step 3 / Evaluation</span><h3>{run.status === "EVALUATING" ? "Independent Judge is evaluating the response" : "Response saved and waiting for evaluation"}</h3></div><ChatMatePollingMessage since={run.evaluation_started_at ?? run.response_submitted_at} polling={run.status === "EVALUATING"} />{run.status === "AWAITING_EVALUATION" && <button className="secondary-action" disabled={action === "retry"} onClick={() => void retryEvaluation()} type="button">{action === "retry" ? "Starting Judge..." : "Start Judge evaluation"}</button>}</div></section>
      )}

      {run?.status === "REJECTED" && <section className="chatmate-panel chatmate-result neutral"><span>Run ended</span><h3>All candidates were rejected</h3><p>No prompt was submitted to ChatMate and no Judge evaluation was performed.</p><button className="primary-action" onClick={reset} type="button">Start a new ChatMate run</button></section>}

      {run?.status === "ABANDONED" && <section className="chatmate-panel chatmate-result neutral"><span>Run ended</span><h3>Run abandoned</h3><p>This run ended without submitted evidence. Its generated attacks and immutable selection remain in history.</p><button className="primary-action" onClick={reset} type="button">Start a new ChatMate run</button></section>}

      {run && chatMateGenerationFailed(run) && <section className="chatmate-panel chatmate-result failed">
        <div className="chatmate-section-heading"><span>Step 2 / Generation</span><h3>Generation Failed</h3></div>
        <ChatMateRunError run={run} />
        <ChatMateDiagnostics run={run} />
        <div className="chatmate-result-actions"><button className="primary-action" onClick={reset} type="button">Retry generation in a new run</button></div>
      </section>}

      {run && ["COMPLETED", "FAILED"].includes(run.status) && !chatMateGenerationFailed(run) && (
        <section className={`chatmate-panel chatmate-result ${(run.final_status ?? run.status).toLowerCase()}`}>
          <span>Step 4 / Result</span><h3>{judgeEvaluation && run.status !== "FAILED" && run.final_status !== "ERROR" ? chatMateGradedResult(judgeEvaluation) : chatMateResultLabel(run)}</h3><p>Evidence-qualified verdict: <strong>{run.final_status}</strong></p>{(run.status === "FAILED" || run.final_status === "ERROR") && <p>Evaluation failed. Evidence saved.</p>}
          {(run.status === "FAILED" || run.final_status === "ERROR") && <><ChatMateRunError run={run} /><ChatMateDiagnostics run={run} />{run.evaluation_attempts >= 10 && <p className="chatmate-helper">The 10-attempt Judge retry limit has been reached. Start a new assessment to continue.</p>}</>}
          {judgeEvaluation && <div className="chatmate-judge-summary"><dl><div><dt>Deviation score</dt><dd>{judgeEvaluation.deviation_score}/100</dd></div><div><dt>Score category</dt><dd>{chatMateScoreCategory(judgeEvaluation)}</dd></div><div><dt>Judge-reported confidence</dt><dd>{Math.round(judgeEvaluation.confidence * 100)}%</dd></div><div><dt>Evaluation attempts</dt><dd>{run.evaluation_attempts}</dd></div></dl><details><summary>Why the Judge reached this result</summary><p>{CHATMATE_SCORE_GUIDANCE}</p><ChatMateJudgeRationale judge={judgeEvaluation} /></details></div>}
          {run.manual_evidence && <details><summary>Evidence integrity</summary><dl className="chatmate-integrity"><div><dt>Collection</dt><dd>Operator submitted</dd></div><div><dt>Correlation</dt><dd><code>{run.manual_evidence.correlation_sha256}</code></dd></div><div><dt>Redaction</dt><dd>{run.manual_evidence.redaction_applied ? "Applied" : "Not required"}</dd></div><div><dt>Judge attempts</dt><dd>{run.evaluation_attempts}</dd></div></dl></details>}
          {eligibleChatMateResult(run) && <><Link className="secondary-action" to={`${chatMateReportLink(run.run_id)}&management=1`}>Report</Link><Link className="secondary-action" to={chatMateReportLink(run.run_id)}>View report</Link></>}
          <div className="chatmate-result-actions">{chatMateCanRetryJudge(run) && <button className="secondary-action" disabled={Boolean(action)} onClick={() => void retryEvaluation()} type="button">{action === "retry" ? "Retrying Judge..." : "Retry Judge only"}</button>}<button className="primary-action" onClick={reset} type="button">Start a new ChatMate run</button></div>
        </section>
      )}
      {run && audit && <CriticReviewPanel run={run} audit={audit} onRunChange={setRun} />}
      {!run && !recoveryRequested && <ChatMateRunHistory key={location.key} />}
    </section>
  );
}
