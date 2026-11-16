import { useCallback, useEffect, useRef, useState } from "react";
import { dashboardService } from "./dashboardService";
import type { Notification } from "./notificationService";
import { applyNotificationReadState, notificationReadKey, notificationPersistenceError, clearNotificationHistory, notificationClearedKey, NOTIFICATION_HISTORY_CHANGED } from "./notificationService";
import { platformService } from "./platformService";

type State = { user: string; notifications: Notification[]; loading: boolean; error: string };

export function useNotifications(user: string, navigationKey: string, open: boolean) {
  const [state, setState] = useState<State>(() => ({ user, notifications: [], loading: true, error: "" }));
  const refreshRef = useRef<() => void>(() => {});
  const triggers = useRef({ navigationKey, open });
  const refresh = useCallback(() => refreshRef.current(), []);

  useEffect(() => {
    let alive = true;
    let inFlight = false;
    let queued = false;
    let activeRuns = false;
    let timer = 0;
    let initialized = false;
    setState({ user, notifications: [], loading: true, error: "" });
    const visible = () => document.visibilityState !== "hidden";
    const schedule = () => {
      window.clearTimeout(timer);
      if (alive && visible()) timer = window.setTimeout(() => void load(false), activeRuns ? 3000 : 5000);
    };
    const load = async (immediate: boolean) => {
      if (!alive || !visible()) return;
      if (inFlight) { if (immediate) queued = true; return; }
      queued = false;
      inFlight = true;
      window.clearTimeout(timer);
      if (!initialized) setState((current) => current.user === user ? { ...current, loading: true } : current);
      try {
        const result = await dashboardService.getNotifications(user);
        if (!alive) return;
        activeRuns = result.hasActiveRuns;
        initialized = true;
        setState({ user, notifications: applyNotificationReadState(user, result.notifications), loading: false, error: result.error });
      } catch {
        initialized = true;
        if (alive) setState((current) => current.user === user ? { ...current, loading: false, error: "Notifications unavailable. Saved notifications may be out of date. Retry to refresh." } : current);
      } finally {
        inFlight = false;
        if (alive) {
          if (queued && visible()) { queued = false; void load(true); }
          else schedule();
        }
      }
    };
    const refreshNow = () => void load(true);
    const onVisibility = () => {
      window.clearTimeout(timer);
      if (visible()) refreshNow();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key?.startsWith(notificationReadKey(user)) || event.key?.startsWith(notificationClearedKey(user)) || event.key === null) {
        setState((current) => current.user === user ? { ...current, notifications: applyNotificationReadState(user, current.notifications) } : current);
      }
      if (event.key === "secmate.poc.platform.v2" || event.key === null) refreshNow();
    };
    const onClear = () => setState(current => current.user === user ? { ...current,
      notifications: applyNotificationReadState(user, current.notifications), error: notificationPersistenceError(user) || current.error } : current);
    refreshRef.current = refreshNow;
    refreshNow();
    window.addEventListener("focus", refreshNow);
    window.addEventListener("online", refreshNow);
    window.addEventListener(platformService.changeEvent, refreshNow);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("storage", onStorage);
    window.addEventListener(NOTIFICATION_HISTORY_CHANGED, onClear);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      refreshRef.current = () => {};
      window.removeEventListener("focus", refreshNow);
      window.removeEventListener("online", refreshNow);
      window.removeEventListener(platformService.changeEvent, refreshNow);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(NOTIFICATION_HISTORY_CHANGED, onClear);
    };
  }, [user]);

  useEffect(() => {
    const previous = triggers.current;
    triggers.current = { navigationKey, open };
    if (navigationKey !== previous.navigationKey || (open && !previous.open)) refresh();
  }, [navigationKey, open, refresh]);

  const notifications = state.user === user ? state.notifications : [];
  const markRead = (id: string) => {
    dashboardService.markNotificationRead(user, id);
    setState((current) => current.user === user ? { ...current, notifications: applyNotificationReadState(user, current.notifications), error: notificationPersistenceError(user) || current.error } : current);
  };
  const markAllRead = () => {
    dashboardService.markAllNotificationsRead(user, notifications.map((item) => item.id));
    setState((current) => current.user === user ? { ...current, notifications: applyNotificationReadState(user, current.notifications), error: notificationPersistenceError(user) || current.error } : current);
  };
  const clearHistory = () => clearNotificationHistory(user, notifications.map(item => item.id));
  return { notifications, loading: state.user !== user || state.loading, error: state.user === user ? state.error : "", unreadCount: notifications.filter((item) => !item.read).length, refresh, markRead, markAllRead, clearHistory };
}
