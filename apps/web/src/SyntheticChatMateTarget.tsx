import { useEffect, useRef, useState } from "react";
import { syntheticChatMateService } from "./syntheticChatMateService";
import type { SyntheticChatMateEvidence, SyntheticChatMateRun, SyntheticChatMateTarget } from "./syntheticChatMateService";

const active = (run: SyntheticChatMateRun | null) => Boolean(run && ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(run.status));
const requestKey = (action: string) => `${action}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

export function SyntheticChatMateTargetPanel() {
  const [target, setTarget] = useState<SyntheticChatMateTarget | null>(null);
  const [run, setRun] = useState<SyntheticChatMateRun | null>(null);
  const [evidence, setEvidence] = useState<SyntheticChatMateEvidence | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const disposed = useRef(false);

  useEffect(() => {
    disposed.current = false;
    syntheticChatMateService.getTarget().then(async (next) => {
      if (disposed.current) return;
      setTarget(next);
      if (next.latest_run_id) {
        const saved = await syntheticChatMateService.getRun(next.latest_run_id);
        if (!disposed.current) setRun(saved);
      }
    }).catch((reason) => { if (!disposed.current) setError(reason instanceof Error ? reason.message : "Smoke-test API unavailable."); });
    return () => { disposed.current = true; };
  }, []);

  useEffect(() => {
    if (!active(run)) return;
    const timer = window.setInterval(() => {
      syntheticChatMateService.getRun(run!.run_id).then((next) => {
        if (!disposed.current) setRun(next);
      }).catch((reason) => { if (!disposed.current) setError(reason instanceof Error ? reason.message : "Unable to refresh smoke test."); });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [run?.run_id, run?.status]);

  useEffect(() => {
    if (run?.status !== "COMPLETED" || !run.evidence_available || evidence) return;
    let current = true;
    void syntheticChatMateService.getEvidence(run.run_id).then((saved) => { if (current && !disposed.current) setEvidence(saved); })
      .catch((reason) => { if (current && !disposed.current) setError(reason instanceof Error ? reason.message : "Evidence unavailable."); });
    return () => { current = false; };
  }, [run?.run_id, run?.status, run?.evidence_available, evidence]);

  const start = async () => {
    setBusy(true); setError(""); setEvidence(null);
    try { setRun(await syntheticChatMateService.start(requestKey("target-smoke"))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start smoke test."); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!run) return;
    setBusy(true); setError("");
    try { setRun(await syntheticChatMateService.cancel(run.run_id, requestKey("target-smoke-cancel"))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to cancel smoke test."); }
    finally { setBusy(false); }
  };

  const verified = run?.verification === "MOCK_VERIFIED";
  return <article className="synthetic-chatmate-target" aria-labelledby="synthetic-chatmate-heading">
    <header><div><span>Server-owned target / Phase 5</span><h2 id="synthetic-chatmate-heading">Synthetic ChatMate</h2><p>One bounded read-only retrieval protocol check. This is not a DeepTeam assessment and produces no Judge or security verdict.</p></div><strong className={`smoke-mode ${verified ? "verified" : "unverified"}`}>{verified ? "MOCK VERIFIED" : "UNFINISHED / UNVERIFIED"}</strong></header>
    <div className="smoke-boundary"><strong>MOCKED ONLY</strong><span>No live provider, real mail, Teams, writes, findings, or security scoring.</span></div>
    <dl className="smoke-limits"><div><dt>Model turns</dt><dd>2 maximum</dd></div><div><dt>Tool calls</dt><dd>1 maximum</dd></div><div><dt>Effect</dt><dd>Fictional read only</dd></div><div><dt>Deadline</dt><dd>120 seconds</dd></div></dl>
    {run && <section className="smoke-run" aria-live="polite"><div className="smoke-run-heading"><div><span>{run.status.replaceAll("_", " ")}</span><strong>{run.stage}</strong></div><b>{run.progress}%</b></div><div className="smoke-progress" role="progressbar" aria-label="Synthetic ChatMate test progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={run.progress}><i style={{ width: `${run.progress}%` }} /></div>
      {run.error_message && <div className="inline-error" role="alert"><strong>{run.error_code}</strong> {run.error_message}</div>}
      {run.final_response && <div className="smoke-final"><span>Mocked final response</span><p>{run.final_response}</p></div>}
      {evidence && <details className="smoke-evidence"><summary>Tool and evidence details</summary><dl><div><dt>Profile-shaped model</dt><dd>{evidence.model}</dd></div><div><dt>Request</dt><dd>{evidence.request_text}</dd></div><div><dt>Reconciled</dt><dd>Yes, mocked evidence only</dd></div><div><dt>Writes / effects</dt><dd>0 / 0</dd></div><div><dt>Sealed artifacts</dt><dd>{Object.keys(evidence.artifacts_sha256).length}</dd></div></dl>{evidence.tool_activity.map((tool) => <article key={tool.tool_call_id}><strong>{tool.name}</strong><span>{tool.authorization} / {tool.execution.replaceAll("_", " ")}</span><pre>{JSON.stringify({ arguments: tool.arguments, source_refs: tool.source_refs }, null, 2)}</pre></article>)}</details>}
    </section>}
    {error && <div className="inline-error" role="alert">{error}</div>}
    <footer>{active(run) ? <button className="danger-action" disabled={busy || run?.status === "CANCEL_REQUESTED"} type="button" onClick={() => void cancel()}>{run?.status === "CANCEL_REQUESTED" ? "Cancellation requested" : "Cancel bounded test"}</button> : <button className="primary-action" disabled={busy || target === null} type="button" onClick={() => void start()}>{busy ? "Starting..." : "Run bounded mocked test"}</button>}<span>Version {target?.version ?? "0.5.0"} / fixed server configuration</span></footer>
  </article>;
}
