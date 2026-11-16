import { useEffect, useState } from "react";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamAuditReport, DeepTeamRunRecord } from "./modelConnectivityService";

const active = new Set(["QUEUED", "RUNNING", "CANCEL_REQUESTED"]);

// Saved evidence reads never launch work. Retry transient failures, then expose
// manual recovery while keeping the last successfully loaded record visible.
export function useDeepTeamEvidence(runId: string | null) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ id: string | null; run: DeepTeamRunRecord | null;
    audit: DeepTeamAuditReport | null; loading: boolean; error: string }>({ id: runId, run: null, audit: null, loading: Boolean(runId), error: "" });
  useEffect(() => {
    if (!runId) return;
    let disposed = false;
    let timer = 0;
    let failures = 0;
    setState((previous) => ({ ...previous, ...(previous.id !== runId ? { run: null, audit: null } : {}), id: runId, loading: true, error: "" }));
    const load = async () => {
      let shouldPoll = false;
      try {
        const run = await modelConnectivityService.getDeepTeamRun(runId);
        if (disposed) return;
        if (run.run_id !== runId) throw new Error("The saved assessment does not match the requested run.");
        shouldPoll = active.has(run.status);
        setState((previous) => ({ ...previous, run }));
        if (run.artifact_available) {
          const audit = await modelConnectivityService.getDeepTeamAudit(runId);
          if (disposed) return;
          if (audit.run_id !== runId) throw new Error("Saved evidence does not match the requested assessment.");
          setState((previous) => ({ ...previous, audit }));
        }
        failures = 0;
        setState((previous) => ({ ...previous, error: "" }));
      } catch (reason) {
        failures += 1;
        shouldPoll = failures <= 3;
        if (!disposed) setState((previous) => ({ ...previous,
          error: reason instanceof Error ? reason.message : "Unable to load the saved assessment evidence." }));
      } finally {
        if (!disposed) {
          setState((previous) => ({ ...previous, loading: false }));
          if (shouldPoll) timer = window.setTimeout(() => void load(), failures ? 1000 * 2 ** (failures - 1) : 1000);
        }
      }
    };
    void load();
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [runId, attempt]);
  return { ...(state.id === runId ? state : { run: null, audit: null, loading: Boolean(runId), error: "" }),
    retry: () => setAttempt((value) => value + 1) };
}
