import { chatmateService } from "./chatmateService";
import type { ChatMateRunRecord } from "./chatmateService";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";
import { assessmentDisplayName, targetDisplayName } from "./displayLabels";
import { chatMateAttackName, chatMateGenerationFailed, chatMateSafeDiagnostic } from "./chatmateDisplay";
import { eligibleChatMateResult } from "./chatmateProjections";
import { platformService } from "./platformService";
import type { Assessment } from "./platformService";

export type Notification = {
  id: string;
  title: string;
  detail: string;
  occurredAt: string;
  href: string;
  read: boolean;
  timestamp?: number;
};

export type NotificationSnapshot = {
  notifications: Notification[];
  hasActiveRuns: boolean;
  error: string;
};

type Event = Omit<Notification, "read"> & { timestamp: number };
const syntheticActive = new Set(["QUEUED", "RUNNING", "CANCEL_REQUESTED"]);
const chatmateActive = new Set(["QUEUED", "GENERATING", "AWAITING_SELECTION", "AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING"]);
const verdicts = { RESISTED: "Boundary resisted", COMPROMISED: "Policy violation detected", INCONCLUSIVE: "Inconclusive", ERROR: "Evaluation failed" };

function event(source: string, runId: string, stage: string, status: string, title: string, detail: string, href: string, dates: Array<string | null | undefined>): Event {
  const date = dates.find((value) => value && Number.isFinite(Date.parse(value)));
  const timestamp = date ? Date.parse(date) : 0;
  return {
    id: `${source}:${encodeURIComponent(runId)}:${stage}:${status}`,
    title,
    detail: chatMateSafeDiagnostic(detail, 240).replace(/\s+/g, " ").trim(),
    occurredAt: date ? new Date(timestamp).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "Date not recorded",
    timestamp,
    href,
  };
}

function syntheticEvents(run: DeepTeamRunRecord): Event[] {
  if (run.status === "DRAFT") return [];
  const target = chatMateSafeDiagnostic(targetDisplayName(run.target_profile_id), 60);
  const failed = run.status === "FAILED" || run.final_status === "ERROR";
  const titles = { QUEUED: "assessment queued", RUNNING: "assessment running", CANCEL_REQUESTED: "assessment cancellation requested", CANCELLED: "assessment cancelled", COMPLETED: "assessment completed", FAILED: "assessment failed" };
  const outcome = failed ? "Assessment service failed; review the saved diagnostics." : run.final_status ? verdicts[run.final_status] : titles[run.status];
  const href = `/reports?live=${encodeURIComponent(run.run_id)}`;
  const events = [event("synthetic", run.run_id, "run", "start", `${target} assessment started`, `${target} · ${assessmentDisplayName(run.attack)}`, href, [run.created_at])];
  if (!syntheticActive.has(run.status)) events.push(event("synthetic", run.run_id, "run", "end",
    `${target} ${failed ? "assessment failed" : titles[run.status]}`,
    `${target} · ${assessmentDisplayName(run.attack)} · ${outcome}`,
    `/reports?live=${encodeURIComponent(run.run_id)}`,
    [run.completed_at]));
  if (run.execution_mode === "SINGLE" && run.critic_review_id && run.critic_status) {
    events.push(event("synthetic", run.run_id, `standard-review:${run.critic_review_id}`, run.critic_status,
      `${target} Critic review ${run.critic_status.toLowerCase()}`, "Advisory review; the assessment verdict is unchanged.", href,
      [run.critic_completed_at, run.critic_started_at]));
  }
  return events;
}

function chatmateEvents(run: ChatMateRunRecord): Event[] {
  const assessmentHref = `/assessments/chatmate?run=${encodeURIComponent(run.run_id)}`;
  const failed = run.status === "FAILED" || run.final_status === "ERROR";
  const generationFailed = failed && chatMateGenerationFailed(run);
  const titles: Record<ChatMateRunRecord["status"], string> = {
    DRAFT: run.parent_run_id ? "Follow-up draft saved" : "ChatMate draft saved",
    QUEUED: "Attack generation queued", GENERATING: "Generating ChatMate attacks",
    AWAITING_SELECTION: "ChatMate attacks ready for selection", AWAITING_RESPONSE: "ChatMate response awaited",
    AWAITING_EVALUATION: "ChatMate evaluation queued", EVALUATING: "ChatMate evaluation running",
    COMPLETED: "ChatMate assessment completed", FAILED: generationFailed ? "Attack generation failed" : "ChatMate evaluation failed",
    REJECTED: "ChatMate attacks rejected", ABANDONED: "ChatMate assessment abandoned",
  };
  // A report is a saved evaluation result, not merely a generated candidate batch.
  const reportEligible = eligibleChatMateResult(run) && run.artifact_available && Boolean(run.evaluation_id);
  const href = reportEligible ? `/reports?chatmate=${encodeURIComponent(run.run_id)}` : assessmentHref;
  const outcome = failed ? generationFailed ? "Generation could not be completed; open the assessment for diagnostics." : "Evaluation failed; review the saved diagnostics."
    : run.final_status ? verdicts[run.final_status] : run.status === "DRAFT" ? "Configure and generate when ready." : titles[run.status];
  // A saved follow-up draft is not an accepted generation run. Abandoning an
  // unstarted draft likewise must not invent a generation start.
  if (run.status === "DRAFT") return [];
  const events = run.status === "ABANDONED" && !run.started_at ? [] : [event("chatmate", run.run_id, "run", "start",
    "ChatMate assessment started", `${chatMateAttackName(run)} · Candidate generation accepted.`, assessmentHref, [run.started_at, run.created_at])];
  if (["COMPLETED", "FAILED", "REJECTED", "ABANDONED"].includes(run.status)) events.push(event("chatmate", run.run_id, "run", "end",
    failed ? titles.FAILED : titles[run.status], `${chatMateAttackName(run)} · ${outcome}`, href, [run.completed_at]));
  return events;
}

function browserEvents(run: Assessment): Event[] {
  if (run.status === "DRAFT") return [];
  const href = "/assessments";
  const events = [event("browser", run.id, "run", "start", `${run.targetName} assessment started`, run.name, href, [run.createdAt])];
  if (["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(run.status)) events.push(event("browser", run.id, "run", "end",
    `${run.targetName} assessment ${run.status.toLowerCase().replaceAll("_", " ")}`, `${run.name} · Browser-local assessment`, href, [run.completedAt]));
  return events;
}

export function projectNotifications(synthetic: DeepTeamRunRecord[], chatmate: ChatMateRunRecord[], browser: Assessment[] = []): Omit<NotificationSnapshot, "error"> {
  const events = [...synthetic.flatMap(syntheticEvents), ...chatmate.flatMap(chatmateEvents), ...browser.flatMap(browserEvents)].sort((a, b) => b.timestamp - a.timestamp || a.id.localeCompare(b.id));
  const unique = new Map<string, Event>();
  for (const item of events) if (!unique.has(item.id)) unique.set(item.id, item);
  return {
    notifications: [...unique.values()].slice(0, 1000).map((item) => ({ ...item, read: false })),
    hasActiveRuns: synthetic.some((run) => syntheticActive.has(run.status) || run.status !== "DRAFT" && run.execution_mode === "SINGLE" && run.critic_status === "RUNNING") || chatmate.some((run) => chatmateActive.has(run.status)) || browser.some((run) => !["DRAFT", "COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(run.status)),
  };
}

export const notificationReadKey = (user: string) => `secmate.notifications.read.v1:${encodeURIComponent(user.trim().toLowerCase())}`;
const memoryRead = new Map<string, Set<string>>();
export const notificationClearedKey = (user: string) => `secmate.notifications.cleared.v1:${encodeURIComponent(user.trim().toLowerCase())}`;
const memoryCleared = new Map<string, Set<string>>();
export const NOTIFICATION_HISTORY_CHANGED = "secmate:notification-history-changed";

function clearedNotificationIds(user: string): Set<string> {
  const key = notificationClearedKey(user);
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    return new Set([...(Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : []), ...(memoryCleared.get(key) ?? [])]);
  } catch { return new Set(memoryCleared.get(key)); }
}

export function clearNotificationHistory(user: string, ids: string[]) {
  if (!user.trim()) return;
  const key = notificationClearedKey(user);
  const cleared = clearedNotificationIds(user);
  for (const source of ["synthetic", "chatmate", "browser"]) {
    cachedNotifications(user, source).forEach(item => cleared.add(item.id));
    try { window.localStorage.removeItem(notificationHistoryKey(user, source)); } catch { /* memory fallback below */ }
  }
  ids.forEach(id => cleared.add(id));
  memoryCleared.set(key, cleared);
  try {
    // Per-event receipts prevent cleared entries returning after polling or
    // another tab's concurrent clear. Future event IDs remain unaffected.
    cleared.forEach(id => window.localStorage.setItem(`${key}:${id}`, "1"));
    window.localStorage.setItem(key, JSON.stringify([...cleared].slice(-5000)));
    memoryCleared.delete(key);
  } catch { /* Keep dismissed IDs for this session if storage is unavailable. */ }
  window.dispatchEvent(new Event(NOTIFICATION_HISTORY_CHANGED));
}

export function readNotificationIds(user: string): Set<string> {
  if (!user.trim()) return new Set();
  const key = notificationReadKey(user);
  try {
    const stored = window.localStorage.getItem(key);
    if (!stored) return new Set(memoryRead.get(key));
    const value: unknown = JSON.parse(stored);
    const persisted = Array.isArray(value) ? value.filter((id): id is string => typeof id === "string").slice(-5000) : [];
    return new Set([...persisted, ...(memoryRead.get(key) ?? [])]);
  } catch { return new Set(memoryRead.get(key)); }
}

export function markNotificationsRead(user: string, ids: string[]) {
  if (!user.trim()) return;
  const key = notificationReadKey(user);
  const read = readNotificationIds(user);
  ids.forEach((id) => read.add(id));
  // One immutable receipt per event avoids concurrent tabs overwriting another
  // tab's read operation. Keep the v1 array for existing installations.
  ids.forEach((id) => { try { window.localStorage.setItem(`${key}:${id}`, "1"); } catch { /* memory fallback below */ } });
  const bounded = [...read].slice(-5000);
  try {
    [...read].slice(0, Math.max(0, read.size - 5000)).forEach((id) => window.localStorage.removeItem(`${key}:${id}`));
    window.localStorage.setItem(key, JSON.stringify(bounded));
    memoryRead.delete(key);
  } catch { memoryRead.set(key, new Set(bounded)); }
}

export function notificationPersistenceError(user: string): string {
  return memoryRead.has(notificationReadKey(user)) ? "Browser storage unavailable. Read status may not survive reload."
    : memoryCleared.has(notificationClearedKey(user)) ? "Browser storage unavailable. Cleared notifications may return after reload." : "";
}

export function applyNotificationReadState(user: string, notifications: Notification[]): Notification[] {
  const read = readNotificationIds(user);
  const key = notificationReadKey(user);
  const cleared = clearedNotificationIds(user);
  const legacyReadPrefixes = new Set([...read]
    .filter((id) => !id.includes(":critic:") && /:(COMPLETED|FAILED|CANCELLED|REJECTED|ABANDONED)$/.test(id))
    .map((id) => `${id.split(":").slice(0, 2).join(":")}:`));
  return notifications.filter(item => {
    if (cleared.has(item.id)) return false;
    try { return !window.localStorage.getItem(`${notificationClearedKey(user)}:${item.id}`); } catch { return true; }
  }).map((item) => {
    let receipt = false;
    try { receipt = !read.has(item.id) && Boolean(user.trim()) && window.localStorage.getItem(`${key}:${item.id}`) === "1"; } catch { /* use memory */ }
    // Preserve legacy terminal reads; intermediate phase reads do not mark a
    // future completion read. Critic/draft activity is intentionally retired.
    const prefix = item.id.replace(/:run:(start|end)$/, ":");
    const legacy = item.id.endsWith(":end") && legacyReadPrefixes.has(prefix);
    return { ...item, read: receipt || read.has(item.id) || legacy };
  });
}

// Coalesce concurrent shell refreshes, including route remounts. Abort a stalled
// read so an unavailable source cannot permanently block every later refresh.
async function boundedRead<T>(read: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  let timer = 0;
  try {
    return await Promise.race([Promise.resolve().then(() => read(controller.signal)), new Promise<never>((_, reject) => {
      timer = window.setTimeout(() => { controller.abort(); reject(new Error("Notification history timeout")); }, 10000);
    })]);
  } finally { window.clearTimeout(timer); }
}
type Sources = [PromiseSettledResult<DeepTeamRunRecord[]>, PromiseSettledResult<ChatMateRunRecord[]>, PromiseSettledResult<Assessment[]>];
let inFlight: Promise<Sources> | null = null;
export const notificationHistoryKey = (user: string, source: string) => `secmate.notifications.history.v2:${encodeURIComponent(user.trim().toLowerCase())}:${source}`;

function cachedNotifications(user: string, source: string): Notification[] {
  if (!user.trim()) return [];
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(notificationHistoryKey(user, source)) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.slice(0, 1000).filter((item): item is Notification => item && typeof item === "object"
      && ["id", "title", "detail", "occurredAt", "href"].every((key) => typeof item[key] === "string" && item[key].length < 2000)
      && item.id.startsWith(`${source}:`) && (/:run:(start|end)$/.test(item.id) || /:standard-review:[^:]+:(RUNNING|COMPLETED|FAILED)$/.test(item.id))
      && !item.id.startsWith(`${source}:undefined:`) && !item.id.startsWith(`${source}:null:`)
      && typeof item.timestamp === "number" && Number.isFinite(item.timestamp)
      && (/^\/assessments$/.test(item.href) || /^\/(assessments\/chatmate|reports)\?/.test(item.href)));
  } catch { return []; }
}

function validSourceRows(value: unknown, source: number): boolean {
  if (!Array.isArray(value)) return false;
  const statuses = source === 0 ? ["QUEUED", "RUNNING", "CANCEL_REQUESTED", "COMPLETED", "FAILED", "CANCELLED"]
    : source === 1 ? ["DRAFT", ...chatmateActive, "COMPLETED", "FAILED", "REJECTED", "ABANDONED"]
    : ["DRAFT", "VALIDATING", "QUEUED", "PLANNING", "RUNNING", "VERIFYING", "FINALIZING", "CANCEL_REQUESTED", "COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"];
  const text = (field: unknown) => typeof field === "string" && field.length <= 512 && Boolean(field.trim()) && !/[\u0000-\u001f\u007f]/.test(field);
  return value.every((row: unknown) => {
    if (!row || typeof row !== "object" || Array.isArray(row)) return false;
    const run = row as Record<string, unknown>;
    const id = source === 2 ? run.id : run.run_id;
    if (!text(id) || id === "undefined" || id === "null" || id !== (id as string).trim() || !statuses.includes(run.status as string)) return false;
    if (run.final_status != null && (typeof run.final_status !== "string" || !Object.hasOwn(verdicts, run.final_status))) return false;
    const dateFields = source === 2 ? ["createdAt", "completedAt"] : ["created_at", "started_at", "completed_at"];
    if (dateFields.some((key) => run[key] != null && (typeof run[key] !== "string" || !Number.isFinite(Date.parse(run[key] as string))))) return false;
    if (source === 1 && run.artifact_available != null && typeof run.artifact_available !== "boolean") return false;
    if (source === 0) return text(run.target_profile_id) && text(run.attack);
    if (source === 1) return ["prompt-injection-v1", "system-override-v1", "prompt-probing-v1", "goal-redirection-v1", "context-poisoning-v1"].includes(run.attack_profile_id as string);
    return text(run.targetName) && text(run.name);
  });
}

export async function getLiveNotifications(user: string): Promise<NotificationSnapshot> {
  if (!inFlight) {
    inFlight = Promise.allSettled([
      boundedRead((signal) => modelConnectivityService.listDeepTeamRuns(signal)),
      boundedRead((signal) => chatmateService.listRuns(signal)),
      Promise.resolve().then(() => platformService.listAssessments()),
    ]).finally(() => { inFlight = null; });
  }
  const results = await inFlight;
  const sources = ["synthetic", "chatmate", "browser"];
  const labels = ["Synthetic assessments", "ChatMate activity", "Browser assessments"];
  const failed: string[] = [];
  const projected = results.map((result, index) => {
    try {
      if (result.status === "rejected" || !validSourceRows(result.value, index)) throw new Error("History unavailable");
      return projectNotifications(index === 0 ? result.value as DeepTeamRunRecord[] : [],
        index === 1 ? result.value as ChatMateRunRecord[] : [], index === 2 ? result.value as Assessment[] : []);
    } catch {
      failed.push(labels[index]);
      return null;
    }
  });
  let storageError = notificationPersistenceError(user);
  const notifications = projected.flatMap((snapshot, index) => {
    if (!snapshot) return cachedNotifications(user, sources[index]);
    try { if (user.trim()) window.localStorage.setItem(notificationHistoryKey(user, sources[index]), JSON.stringify(applyNotificationReadState(user, snapshot.notifications))); } catch { storageError = "Browser storage unavailable. Saved notification history may not survive reload."; }
    return snapshot.notifications;
  });
  notifications.sort((a, b) => (b.timestamp ?? 0) - (a.timestamp ?? 0) || a.id.localeCompare(b.id));
  const unique = [...new Map(notifications.map((item) => [item.id, item])).values()].slice(0, 1000);
  return { notifications: applyNotificationReadState(user, unique), hasActiveRuns: projected.some((snapshot) => snapshot?.hasActiveRuns)
      || unique.some((item) => /:standard-review:[^:]+:RUNNING$/.test(item.id)),
    error: [failed.length ? `${failed.join(" and ")} unavailable. Saved notifications may be out of date. Retry to refresh.` : "", storageError].filter(Boolean).join(" ") };
}
