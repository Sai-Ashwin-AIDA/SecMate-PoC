export const ACTIVE_DEEPTEAM_RUN_KEY = "secmate.activeDeepteamRun";
export const DEEPTEAM_RUN_HISTORY_KEY = "secmate.deepteamRunHistory";

export function listSavedDeepTeamRunIds() {
  const activeRunId = window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY);
  let savedRunIds: string[] = [];

  try {
    const stored = JSON.parse(
      window.localStorage.getItem(DEEPTEAM_RUN_HISTORY_KEY) ?? "[]",
    ) as unknown;
    if (Array.isArray(stored)) {
      savedRunIds = stored.filter(
        (value): value is string => typeof value === "string" && Boolean(value),
      );
    }
  } catch {
    savedRunIds = [];
  }

  return Array.from(new Set([activeRunId, ...savedRunIds].filter(Boolean) as string[]));
}

export function saveDeepTeamRunId(runId: string) {
  const runIds = [runId, ...listSavedDeepTeamRunIds().filter((id) => id !== runId)];
  window.localStorage.setItem(ACTIVE_DEEPTEAM_RUN_KEY, runId);
  window.localStorage.setItem(DEEPTEAM_RUN_HISTORY_KEY, JSON.stringify(runIds));
}

export function removeSavedDeepTeamRunId(runId: string) {
  const runIds = listSavedDeepTeamRunIds().filter((id) => id !== runId);
  window.localStorage.setItem(DEEPTEAM_RUN_HISTORY_KEY, JSON.stringify(runIds));
  if (window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY) === runId) {
    window.localStorage.removeItem(ACTIVE_DEEPTEAM_RUN_KEY);
  }
}
