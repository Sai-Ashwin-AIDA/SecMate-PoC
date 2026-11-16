import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { modelConnectivityService, ModelConnectivityError } from "./modelConnectivityService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";
import { saveDeepTeamRunId } from "./deepTeamRunStorage";
import { AssessmentSelect } from "./AssessmentSelect";
import { operationKey } from "./standardReview";
import { assessmentDisplayName, targetDisplayName } from "./displayLabels";

export function LinkedAssessmentDraft({ runId }: { runId: string }) {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DeepTeamRunRecord | null>(null);
  const [budget, setBudget] = useState(75000);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [estimate, setEstimate] = useState<number | null>(null);
  const pending = useRef(false);
  const alive = useRef(true);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    alive.current = true;
    let disposed = false;
    setDraft(null); setEstimate(null); setError("");
    void modelConnectivityService.getDeepTeamRun(runId).then(async record => {
      if (disposed) return;
       if (record.run_id !== runId || !record.linked_context) throw new Error("Linked draft does not match the requested assessment.");
       const context = record.linked_context;
       if (context.target_profile_id !== record.target_profile_id || context.target_profile_version !== record.target_profile_version
           || context.vulnerability_profile_id !== record.vulnerability_profile_id || context.attack_profile_id !== record.attack_profile_id
           || context.schema_version === "secmate-target-linked-assessment-v1" && (context.scenario_id !== record.scenario
             || context.scenario_version !== record.scenario_version || !context.redacted_parent_context_sha256)) {
         throw new Error("Linked draft target or evidence context does not match its frozen assessment scope.");
       }
       if (record.status !== "DRAFT") { saveDeepTeamRunId(runId); navigate("/assessments?workflow=socmate", { replace: true }); return; }
      setDraft(record); setBudget(record.max_total_tokens);
      const catalog = await modelConnectivityService.getDeepTeamCatalog();
      if (disposed) return;
      const method = catalog.attack_profiles.find(method => method.id === record.attack_profile_id);
      if (!method) throw new Error("The recommended method is no longer in the current catalog.");
      setEstimate(method.turn_mode === "SINGLE" ? 12000 : Math.max(50000, method.max_turns * 17000));
    }).catch(reason => { if (!disposed) setError(reason instanceof Error ? reason.message : "Draft unavailable."); });
    return () => { disposed = true; alive.current = false; };
  }, [runId, version, navigate]);
  const start = async () => {
    if (!draft || pending.current || estimate === null || budget < estimate) return;
    pending.current = true; setBusy(true); setError("");
    const operation = operationKey(`start.${runId}.${budget}`);
    try {
      const record = await modelConnectivityService.startLinkedAssessment(runId, budget, operation.key);
      if (record.run_id !== runId || record.status === "DRAFT") throw new Error("Start acknowledgment does not match this draft.");
      operation.clear(); saveDeepTeamRunId(runId);
      if (alive.current) navigate("/assessments?workflow=socmate", { replace: true });
    } catch (reason) {
      if (reason instanceof ModelConnectivityError && reason.status >= 400 && reason.status < 500) operation.clear();
      if (alive.current) setError(reason instanceof Error ? reason.message : "Start could not be confirmed. Reload saved status before retrying.");
    } finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  return <section className="linked-assessment-draft" aria-label="Linked fresh assessment draft"><header><h2>Linked fresh assessment</h2><p>A new assessment informed by parent evidence. It starts a fresh path and never continues the parent conversation.</p></header>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!draft && !error && <p role="status">Loading saved draft…</p>}
    {draft && <><dl className="linked-draft-details"><div><dt>Target</dt><dd>{targetDisplayName(draft.target_profile_id)} v{draft.target_profile_version}</dd></div><div><dt>Scenario</dt><dd>{draft.scenario} v{draft.scenario_version}</dd></div><div><dt>Security risk</dt><dd>{assessmentDisplayName(draft.vulnerability)}</dd></div>
      <div><dt>Method</dt><dd>{assessmentDisplayName(draft.attack)}</dd></div></dl>
      <div className="linked-draft-budget">
      <AssessmentSelect label="Usage limit" value={String(budget)} onChange={value => setBudget(Number(value))} disabled={busy}
        options={[...new Set([draft.max_total_tokens, 25000, 50000, 75000, 100000, 150000, 250000])].sort((a, b) => a - b).map(value => ({ value: String(value), label: `${value.toLocaleString()} tokens` }))} />
      {estimate !== null && <p className="linked-draft-estimate">Planning estimate: about {estimate.toLocaleString()} tokens.{budget < estimate && " Choose a higher usage limit."}</p>}
      </div></>}
    <footer className="linked-draft-actions">
      {draft && <button className="primary-action" type="button" disabled={busy || estimate === null || budget < estimate} onClick={() => void start()}>{busy ? "Starting…" : "Start linked assessment"}</button>}
      <div className="linked-draft-secondary-actions"><button className="secondary-action" type="button" disabled={busy} onClick={() => setVersion(value => value + 1)}>Reload saved draft</button><Link className="secondary-action" to="/assessments?workflow=socmate">Back to assessments</Link></div>
    </footer>
  </section>;
}

export function LinkedAssessmentDraftList() {
  const [drafts, setDrafts] = useState<DeepTeamRunRecord[]>([]);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let disposed = false;
    const load = () => { void modelConnectivityService.listLinkedDrafts().then(records => {
      if (!Array.isArray(records)) throw new Error("Invalid saved draft response.");
      if (!disposed) { setDrafts(records); setError(""); }
    }).catch(() => { if (!disposed) setError("Linked drafts could not be loaded."); }); };
    load(); window.addEventListener("focus", load);
    return () => { disposed = true; window.removeEventListener("focus", load); };
  }, [version]);
  if (!drafts.length && !error) return null;
  return <section className="linked-assessment-drafts" aria-label="Linked assessment drafts"><header><span>Saved follow-ups</span><h3>Linked assessment drafts</h3></header>
    {error && <p role="alert">{error} <button className="secondary-action" type="button" onClick={() => setVersion(value => value + 1)}>Reload saved drafts</button></p>}
    <div className="linked-draft-list">{drafts.map(draft => <article key={draft.run_id}><dl><div><dt>Test method</dt><dd>{assessmentDisplayName(draft.attack)}</dd></div><div><dt>Security risk</dt><dd>{assessmentDisplayName(draft.vulnerability)}</dd></div></dl><Link className="secondary-action" to={`/assessments?linked=${encodeURIComponent(draft.run_id)}`}>Review draft</Link></article>)}</div>
  </section>;
}
