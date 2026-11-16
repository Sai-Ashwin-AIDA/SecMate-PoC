import { clearLocalAssessmentHistory } from "./platformService";
// Store identifiers only. Evidence, form drafts and consent remain server-owned
// or transient. A separate key avoids resurrecting obsolete legacy browser state.
const KEY = "secmate.currentAssessment.v1";
export const RUNS_CHANGED = "secmate:runs-changed";
export function currentAssessment(): string | null {
  try { return window.localStorage.getItem(KEY); } catch { return null; }
}
export function rememberAssessment(id: string) {
  try { window.localStorage.setItem(KEY, id); } catch { /* URL restoration still works. */ }
}
export function forgetAssessment(id?: string) {
  try { if (!id || currentAssessment() === id) window.localStorage.removeItem(KEY); } catch { /* Storage may be disabled. */ }
}
export function assessmentUrl(id: string) { return `/assessments/chatmate?run=${encodeURIComponent(id)}`; }

export async function syncHistoryEpoch() {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/history-epoch`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
  if (!response.ok) return;
  const { epoch } = await response.json();
  if (typeof epoch !== "string" || !/^[a-f0-9]{32}$/.test(epoch)) return;
  if (window.localStorage.getItem("secmate.historyEpoch") === epoch) return;
  clearLocalAssessmentHistory();
  for (const key of [KEY, "secmate.activeChatMateRun", "secmate.activeDeepteamRun", "secmate.deepteamRunHistory"]) window.localStorage.removeItem(key);
  const notificationKeys = Array.from({ length: window.localStorage.length }, (_, index) => window.localStorage.key(index))
    .filter((key): key is string => Boolean(key?.startsWith("secmate.notifications.")));
  notificationKeys.forEach(key => window.localStorage.removeItem(key));
  window.localStorage.setItem("secmate.historyEpoch", epoch);
  window.dispatchEvent(new Event(RUNS_CHANGED));
  window.dispatchEvent(new Event("secmate:data-changed"));
}
