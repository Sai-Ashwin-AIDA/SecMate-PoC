import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { clearSession, createSession, readSession, saveSession } from "./auth";
import type { Session } from "./auth";
import { dashboardService } from "./dashboardService";
import type { DashboardData, DateRange, Notification, SearchResult } from "./dashboardService";
import { useNotifications } from "./useNotifications";
import { LoginPage } from "./LoginPage";
import { platformService } from "./platformService";
import { readTheme, saveTheme, THEME_PRESETS } from "./theme";
import type { ThemeId } from "./theme";
import { PageBoundary } from "./PageBoundary";
import { syncHistoryEpoch } from "./assessmentSession";

const ChatMatePage = lazy(() => import("./ChatMatePage").then((module) => ({ default: module.ChatMatePage })));
const AssessmentsPage = lazy(() => import("./ModulePages").then((module) => ({ default: module.AssessmentsPage })));
const FindingsPage = lazy(() => import("./ModulePages").then((module) => ({ default: module.FindingsPage })));
const ReportsPage = lazy(() => import("./ModulePages").then((module) => ({ default: module.ReportsPage })));
const TargetsPage = lazy(() => import("./ModulePages").then((module) => ({ default: module.TargetsPage })));
const SettingsPage = lazy(() => import("./SettingsPage").then((module) => ({ default: module.SettingsPage })));

type PageKey = "dashboard" | "targets" | "assessments" | "findings" | "reports" | "settings";

const primaryPages: Exclude<PageKey, "settings">[] = ["dashboard", "targets", "assessments", "findings", "reports"];

const pageLabels: Record<PageKey, string> = {
  dashboard: "Executive Dashboard",
  targets: "Targets",
  assessments: "Assessments",
  findings: "Findings",
  reports: "Reports",
  settings: "Settings",
};

const pageDescriptions: Record<PageKey, string> = {
  dashboard: "Monitor target activity, assessment coverage, and evaluated outcomes.",
  targets: "Review the AI systems available for assessment.",
  assessments: "Plan and review controlled adversarial assessments.",
  findings: "Triage evidence-backed policy and security findings.",
  reports: "Review assessment evidence and create management reports.",
  settings: "Review planned workspace, governance, and integration controls.",
};

export function App() {
  return <BrowserRouter><AppRoutes /></BrowserRouter>;
}

function AppRoutes() {
  const [session, setSession] = useState<Session | null>(readSession);
  const [historyReady, setHistoryReady] = useState(false);
  useEffect(() => {
    let active = true;
    void syncHistoryEpoch().catch(() => { /* Offline restoration still uses the saved identifier. */ }).finally(() => { if (active) setHistoryReady(true); });
    return () => { active = false; };
  }, []);

  const login = async (email: string, password: string) => {
    const nextSession = createSession(email, password);
    if (!nextSession) return null;
    saveSession(nextSession);
    setSession(nextSession);
    return nextSession;
  };

  const logout = () => {
    clearSession();
    setSession(null);
  };

  if (!historyReady) return <DashboardLoading />;
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute session={session} onLogin={login} />} />
      <Route
        path="/assessments/chatmate"
        element={session ? <AuthenticatedShell activePage="assessments" content={<ChatMatePage />} session={session} onLogout={logout} /> : <RequireLogin />}
      />
      {(Object.keys(pageLabels) as PageKey[]).map((page) => (
        <Route
          key={page}
          path={`/${page}`}
          element={session ? <AuthenticatedRoute page={page} session={session} onLogout={logout} /> : <RequireLogin />}
        />
      ))}
      <Route path="*" element={<Navigate replace to={session ? "/dashboard" : "/login"} />} />
    </Routes>
  );
}

function LoginRoute({ session, onLogin }: { session: Session | null; onLogin: (email: string, password: string) => Promise<Session | null> }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedPath = searchParams.get("returnTo");
  const returnTo = requestedPath?.startsWith("/") && !requestedPath.startsWith("//") ? requestedPath : "/dashboard";
  if (session) return <Navigate replace to={returnTo} />;

  const loginAndNavigate = async (email: string, password: string) => {
    const nextSession = await onLogin(email, password);
    if (nextSession) navigate(returnTo, { replace: true });
    return nextSession;
  };

  return <LoginPage onLogin={loginAndNavigate} />;
}

function RequireLogin() {
  const location = useLocation();
  return <Navigate replace to={`/login?returnTo=${encodeURIComponent(`${location.pathname}${location.search}`)}`} />;
}

function AuthenticatedRoute({ page, session, onLogout }: { page: PageKey; session: Session; onLogout: () => void }) {
  return <AuthenticatedShell activePage={page} session={session} onLogout={onLogout} />;
}

type IconName = PageKey | "bell" | "search" | "arrow" | "shield" | "activity" | "check" | "close";

function AppIcon({ name, className = "" }: { name: IconName; className?: string }) {
  const paths: Record<IconName, ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
    targets: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
    assessments: <><path d="M9 11 12 14 22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>,
    findings: <><path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
    reports: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1 1.55V21h-4v-.08A1.7 1.7 0 0 0 9 19.37a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15a1.7 1.7 0 0 0-1.55-1H3v-4h.08A1.7 1.7 0 0 0 4.63 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63a1.7 1.7 0 0 0 1-1.55V3h4v.08a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9a1.7 1.7 0 0 0 1.55 1H21v4h-.08a1.7 1.7 0 0 0-1.52 1Z" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></>,
    activity: <path d="M3 12h4l2.5-7 5 14 2.5-7h4" />,
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };
  return <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8">{paths[name]}</g></svg>;
}

function AidaMark() {
  return (
    <svg aria-hidden="true" className="aida-mark" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="1" width="46" height="46" rx="14" fill="currentColor" opacity=".12" />
      <path d="M13 34 23.8 11 35 34M17.2 27h13.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.2" />
      <circle cx="24" cy="11" r="2.6" fill="currentColor" /><circle cx="13" cy="34" r="2.6" fill="currentColor" /><circle cx="35" cy="34" r="2.6" fill="currentColor" />
    </svg>
  );
}

function AuthenticatedShell({ activePage, session, onLogout, content }: { activePage: PageKey; session: Session; onLogout: () => void; content?: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const accountAreaRef = useRef<HTMLDivElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const accountTriggerRef = useRef<HTMLButtonElement>(null);
  const searchTriggerRef = useRef<HTMLButtonElement>(null);
  const notificationTriggerRef = useRef<HTMLButtonElement>(null);
  const [theme, setTheme] = useState<ThemeId>(readTheme);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [resetConfirmation, setResetConfirmation] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const { notifications, loading: notificationsLoading, error: notificationsError, unreadCount, refresh: refreshNotifications, markRead, markAllRead, clearHistory } = useNotifications(session.email, location.key, notificationsOpen);
  const initials = session.displayName.split(" ").map((part) => part[0]).join("").slice(0, 2);

  useEffect(() => { setAccountMenuOpen(false); setResetConfirmation(false); }, [location.pathname]);

  useEffect(() => {
    if (!accountMenuOpen) return;

    const focusFrame = window.requestAnimationFrame(() => {
      accountMenuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    });

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!accountAreaRef.current?.contains(event.target as Node)) setAccountMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setAccountMenuOpen(false);
        accountTriggerRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [accountMenuOpen]);

  const selectTheme = (nextTheme: ThemeId) => {
    saveTheme(nextTheme);
    setTheme(nextTheme);
  };

  const openNotification = (notification: Notification) => {
    markRead(notification.id);
    setNotificationsOpen(false);
    navigate(notification.href);
  };

  return (
    <main className="app-shell" data-theme={theme}>
      <aside className="sidebar">
        <div className="mini-brand"><AidaMark /><div><strong>AIDA</strong><span>SecMate Console</span></div></div>
        <div className="workspace-label">Workspace</div>
        <nav aria-label="Primary navigation">
          {primaryPages.map((page) => <NavLink aria-label={pageLabels[page]} key={page} to={`/${page}`}><AppIcon name={page} /><span>{pageLabels[page]}</span></NavLink>)}
        </nav>
        <div className="sidebar-footer" ref={accountAreaRef}>
          {accountMenuOpen && (
            <div aria-label="Profile and workspace menu" className="account-popover" ref={accountMenuRef} role="dialog">
              <header>
                <strong>{session.displayName}</strong>
                <span title={session.email}>{session.email}</span>
              </header>
              <fieldset className="theme-picker">
                <legend>Appearance</legend>
                {THEME_PRESETS.map((preset) => (
                  <button aria-pressed={theme === preset.id} key={preset.id} type="button" onClick={() => selectTheme(preset.id)}>
                    <span className="theme-swatches" aria-hidden="true">
                      {preset.swatches.map((color) => <i key={color} style={{ background: color }} />)}
                    </span>
                    <span>{preset.label}</span>
                    <i className="theme-check" aria-hidden="true">{theme === preset.id ? "✓" : ""}</i>
                  </button>
                ))}
              </fieldset>
              <div className="account-actions">
                <button className="reset-demo-button" type="button" onClick={async () => { if (!resetConfirmation) { setResetConfirmation(true); return; } await platformService.resetDemo(); window.location.reload(); }}>{resetConfirmation ? "Confirm PoC reset" : "Reset PoC workspace"}</button>
                <button className="sign-out-button" type="button" onClick={onLogout}>Sign out</button>
              </div>
            </div>
          )}
          <div className="account-block">
            <button aria-expanded={accountMenuOpen} aria-label="Open profile and workspace menu" className="account-menu-button" ref={accountTriggerRef} type="button" onClick={() => setAccountMenuOpen((isOpen) => !isOpen)}>
              <span className="account-avatar">{initials}</span>
              <span className="account-copy"><strong>{session.displayName}</strong><span>{session.role}</span></span>
              <span className="account-caret" aria-hidden="true">⌃</span>
            </button>
            <button aria-label="Open Settings page" className={`settings-button${activePage === "settings" ? " active" : ""}`} type="button" onClick={() => navigate("/settings")}><AppIcon name="settings" /></button>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="page-title"><span className="eyebrow">Paramount Computer Systems <i /> AIDA</span><h1>{pageLabels[activePage]}</h1><p>{pageDescriptions[activePage]}</p></div>
          <div className="topbar-actions">
            <button aria-label="Search Targets and Findings" className="utility-button" ref={searchTriggerRef} type="button" onClick={() => setSearchOpen(true)}><AppIcon name="search" /></button>
            <div className="panel-anchor">
              <button aria-controls={notificationsOpen ? "notifications-panel" : undefined} aria-haspopup="dialog" aria-expanded={notificationsOpen} aria-label={`Notifications, ${unreadCount} unread`} className="utility-button notification-button" ref={notificationTriggerRef} type="button" onClick={() => setNotificationsOpen((open) => !open)}><AppIcon name="bell" />{unreadCount > 0 && <span>{unreadCount}</span>}</button>
              <span className="visually-hidden" role="status" aria-label="Notification updates" aria-live="polite" aria-atomic="true">{unreadCount} unread run notifications</span>
              {notificationsOpen && <NotificationPanel error={notificationsError} loading={notificationsLoading} notifications={notifications} onClose={() => setNotificationsOpen(false)} onOpen={openNotification} onMarkAllRead={markAllRead} onClearHistory={clearHistory} onRefresh={refreshNotifications} returnFocusRef={notificationTriggerRef} />}
            </div>
            <button className="new-assessment-button" type="button" onClick={() => navigate("/assessments")}>Launch assessment <AppIcon name="arrow" /></button>
          </div>
        </header>

        <PageBoundary key={location.pathname}><Suspense fallback={<p role="status">Loading page...</p>}>{content ?? <>
          {activePage === "dashboard" && <ExecutiveDashboard />}
          {activePage === "targets" && <TargetsPage />}
          {activePage === "assessments" && <AssessmentsPage />}
          {activePage === "findings" && <FindingsPage />}
          {activePage === "reports" && <ReportsPage />}
          {activePage === "settings" && <SettingsPage activeTheme={theme} session={session} onResetDemo={async () => { await platformService.resetDemo(); window.location.reload(); }} onThemeChange={selectTheme} />}
        </>}</Suspense></PageBoundary>
      </section>
      {searchOpen && <GlobalSearch onClose={() => setSearchOpen(false)} returnFocusRef={searchTriggerRef} />}
    </main>
  );
}

function GlobalSearch({ onClose, returnFocusRef }: { onClose: () => void; returnFocusRef: RefObject<HTMLButtonElement | null> }) {
  const navigate = useNavigate();
  const dialogRef = useRef<HTMLElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex="-1"])')];
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); returnFocusRef.current?.focus(); };
  }, []);

  useEffect(() => {
    let active = true;
    setResults([]);
    setError("");
    const timeout = window.setTimeout(async () => {
      setLoading(true);
      try {
        const nextResults = await dashboardService.search(query);
        if (active) setResults(nextResults);
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Search is unavailable.");
      } finally {
        if (active) setLoading(false);
      }
    }, 180);
    return () => { active = false; window.clearTimeout(timeout); };
  }, [query]);

  const openResult = (result: SearchResult) => {
    onClose();
    navigate(result.href);
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section aria-label="Global search" aria-modal="true" className="search-dialog" ref={dialogRef} role="dialog" onMouseDown={(event) => event.stopPropagation()}>
        <div className="search-field"><AppIcon name="search" /><input autoFocus aria-label="Search" placeholder="Search Targets and Findings" value={query} onChange={(event) => setQuery(event.target.value)} /><button aria-label="Close search" type="button" onClick={onClose}><AppIcon name="close" /></button></div>
        <div className="search-results" aria-live="polite">
          {!query.trim() && <p>Start typing to search across the assurance workspace.</p>}
          {loading && <p>Searching...</p>}
          {!loading && error && <p role="alert">{error}</p>}
          {!loading && !error && query.trim() && results.length === 0 && <p>No matching records found.</p>}
          {!loading && !error && results.map((result) => <button key={result.id} type="button" onClick={() => openResult(result)}><span className="console-source-badge">{result.type}</span><strong>{result.title}</strong><small>{result.description}</small><em>Open {result.type.toLowerCase()}</em></button>)}
        </div>
      </section>
    </div>
  );
}

function NotificationPanel({ error, loading, notifications, onClose, onOpen, onMarkAllRead, onClearHistory, onRefresh, returnFocusRef }: { error: string; loading: boolean; notifications: Notification[]; onClose: () => void; onOpen: (notification: Notification) => void; onMarkAllRead: () => void; onClearHistory: () => void; onRefresh: () => void; returnFocusRef: RefObject<HTMLButtonElement | null> }) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    panelRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    const outside = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node) && !returnFocusRef.current?.contains(event.target as Node)) closeRef.current();
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeRef.current(); }
      if (event.key !== "Tab" || !panelRef.current) return;
      const buttons = [...panelRef.current.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
      const first = buttons[0], last = buttons.at(-1);
      if (!buttons.includes(document.activeElement as HTMLButtonElement)) { event.preventDefault(); first?.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", keyboard);
      returnFocusRef.current?.focus();
    };
  }, [returnFocusRef]);
  return (
    <section aria-label="Notifications" className="notification-panel" id="notifications-panel" ref={panelRef} role="dialog">
      <header><div><strong>Notifications</strong><span>Run starts and ends · Read status saved in this browser</span></div><button aria-label="Close notifications" type="button" onClick={onClose}><AppIcon name="close" /></button></header>
      <div className="notification-scroll" aria-busy={loading}>
        {loading && !notifications.length && <p className="panel-empty" role="status">Loading notifications...</p>}
        {error && <p className="panel-empty" role="alert">{error} <button disabled={loading} type="button" onClick={onRefresh}>Retry</button></p>}
        {!loading && !error && notifications.length === 0 && <p className="panel-empty">No notifications.</p>}
        {notifications.map((notification) => <button className={notification.read ? "read" : ""} key={notification.id} type="button" onClick={() => onOpen(notification)}><i /><span><strong>{notification.title}</strong><small>{notification.detail}</small><em>{notification.occurredAt}</em></span></button>)}
      </div>
      <footer className="notification-actions" aria-label="Notification actions"><span>{notifications.some((item) => !item.read) ? `${notifications.filter((item) => !item.read).length} unread` : "No unread notifications"}</span><button className="secondary-action" disabled={!notifications.some((item) => !item.read)} type="button" onClick={onMarkAllRead}>Mark all read</button><button className="secondary-action" disabled={!notifications.length} type="button" onClick={onClearHistory}>Clear history</button></footer>
    </section>
  );
}

export function ExecutiveDashboard() {
  const navigate = useNavigate();
  const [range, setRange] = useState<DateRange>("30");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const rangeCache = useRef(new Map<DateRange, DashboardData>());
  const changeRange = (nextRange: DateRange) => {
    setRange(nextRange);
    setError("");
    setData(rangeCache.current.get(nextRange) ?? null);
    setLoading(true);
  };

  useEffect(() => {
    let active = true;
    let timer = 0;
    let inFlight = false;
    let refreshQueued = false;
    let requestNumber = 0;
    let controller: AbortController | null = null;
    const load = async () => {
      if (inFlight) { refreshQueued = true; return; }
      inFlight = true;
      refreshQueued = false;
      const currentRequest = ++requestNumber;
      controller = new AbortController();
      window.clearTimeout(timer);
      timer = 0;
      setLoading(true);
      setError("");
      try {
        const nextData = await dashboardService.getDashboard(range, controller.signal);
        if (!active || currentRequest !== requestNumber) return;
        rangeCache.current.set(range, nextData);
        setData(nextData);
        if (nextData.hasActiveRuns) timer = window.setTimeout(() => { if (document.visibilityState === "visible") void load(); }, 1500);
      } catch (reason) {
        if (active && currentRequest === requestNumber && !(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "Unable to load dashboard data.");
          setData(current => current ? { ...current, isStale: true } : null);
        }
      } finally {
        inFlight = false;
        if (active && currentRequest === requestNumber) {
          setLoading(false);
          if (refreshQueued) void load();
        }
      }
    };
    const refresh = () => void load();
    const onVisible = () => { if (document.visibilityState === "visible") void load(); };
    void load();
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    window.addEventListener("secmate:runs-changed", refresh);
    window.addEventListener("secmate:data-changed", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      requestNumber += 1;
      controller?.abort();
      window.clearTimeout(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
      window.removeEventListener("secmate:runs-changed", refresh);
      window.removeEventListener("secmate:data-changed", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [range, reloadKey]);

  if (loading && !data) return <section className="executive-dashboard"><div className="dashboard-toolbar"><select aria-label="Dashboard time period" value={range} onChange={(event) => changeRange(event.target.value as DateRange)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></div><DashboardLoading /></section>;
  if (error && !data) return <DashboardError message={error} onRetry={() => setReloadKey((key) => key + 1)} />;
  if (!data) return null;

  const severityCounts = data.severity.available ? data.severity.counts : null;
  const totalSeverity = severityCounts ? Object.values(severityCounts).reduce((total, count) => total + count, 0) : 0;
  const metricIcons = { assessments: "assessments", active: "activity", "pass-rate": "check", exceptions: "shield" } as const;
  const activityMaximum = Math.max(5, Math.ceil(Math.max(...data.trend.map((point) => point.assessments), 0) / 5) * 5);
  const activityTicks = Array.from({ length: activityMaximum / 5 + 1 }, (_, index) => activityMaximum - index * 5);
  const activityPath = data.trend.map((point, index) => {
    const x = data.trend.length === 1 ? 38 : 38 + (index / (data.trend.length - 1)) * 672;
    const y = 18 + (1 - point.assessments / activityMaximum) * 150;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const severitySegments = (["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((severity) => !severityCounts || totalSeverity === 0 ? 0 : (severityCounts[severity] / totalSeverity) * 100);
  const severityStops = [severitySegments[0], severitySegments[0] + severitySegments[1], severitySegments[0] + severitySegments[1] + severitySegments[2]];
  const severityGradient = `conic-gradient(#e43f55 0 ${severityStops[0]}%, #f2a21b ${severityStops[0]}% ${severityStops[1]}%, #168fff ${severityStops[1]}% ${severityStops[2]}%, #6f8ba8 ${severityStops[2]}% 100%)`;
  const openTarget = (href: string) => navigate(href);

  return (
    <section className="executive-dashboard" aria-busy={loading}>
      <div className="dashboard-toolbar">
        <select aria-label="Dashboard time period" value={range} onChange={(event) => changeRange(event.target.value as DateRange)}><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select>
      </div>
      {error && <div className="inline-error" role="alert">Latest refresh failed. Showing the last available snapshot. <button type="button" onClick={() => setReloadKey((key) => key + 1)}>Retry</button></div>}

      <div className="metrics-grid">
        {data.metrics.map((metric) => <article className={`metric-card ${metric.tone}`} key={metric.id}><div className="metric-card-header"><span>{metric.label}</span><span className="metric-icon"><AppIcon name={metricIcons[metric.id]} /></span></div><strong>{metric.value}</strong><small title={metric.detail}>{metric.detail}</small></article>)}
      </div>

      <div className="insights-grid">
        <article className="dashboard-card trend-card">
          <div className="section-heading"><h2>Assessment Activity</h2></div>
          {data.trend.length === 0 ? <DashboardCardEmpty title="No trend data" detail="No assessment activity was recorded in this period." /> : <><div className="trend-header-row"><div className="trend-summary"><strong>{data.metrics.find((metric) => metric.id === "pass-rate")?.value}</strong><span>Pass rate</span></div><div className="chart-legend"><i />Assessments run</div></div><div className="trend-chart-shell"><div className="chart-y-axis" aria-hidden="true">{activityTicks.map((tick) => <span key={tick}>{tick}</span>)}</div><svg className="trend-chart" role="img" aria-label="Assessments run by day" viewBox="0 0 720 190" preserveAspectRatio="none">{activityTicks.map((tick) => { const y = 18 + (1 - tick / activityMaximum) * 150; return <line className="chart-y-gridline" key={tick} x1="38" x2="720" y1={y} y2={y} />; })}<path className="chart-line activity-line" d={activityPath} /></svg></div><div className="chart-labels" style={{ gridTemplateColumns: `repeat(${data.trend.length}, minmax(0, 1fr))` }}>{data.trend.map((point, index) => <span className={index % Math.ceil(data.trend.length / 6) && index !== data.trend.length - 1 ? "sampled-label" : ""} key={`${point.label}-${index}`}>{point.label}</span>)}</div></>}
        </article>

        <article className="dashboard-card severity-card">
          <div className="section-heading"><div><span>Recorded findings</span><h2>Severity mix</h2></div><button type="button" onClick={() => navigate("/findings")}>View all</button></div>
          {!severityCounts ? <DashboardCardEmpty title="Severity unavailable" detail="The service did not provide finding severity facts for this period." /> : totalSeverity === 0 ? <DashboardCardEmpty title="No recorded finding severity" detail="No severity-classified findings were recorded for this period." /> : <div className="severity-content"><div className="severity-donut" style={{ background: severityGradient }}><div><strong>{totalSeverity}</strong><span>Total</span></div></div><div className="severity-list"><div><span><i className="critical-dot" />Critical</span><strong>{severityCounts.CRITICAL}</strong></div><div><span><i className="high-dot" />High</span><strong>{severityCounts.HIGH}</strong></div><div><span><i className="medium-dot" />Medium</span><strong>{severityCounts.MEDIUM}</strong></div><div><span><i className="low-dot" />Low</span><strong>{severityCounts.LOW}</strong></div></div></div>}
        </article>
      </div>

      <div className="operations-grid">
        <article className="dashboard-card risk-table-card">
          <div className="section-heading"><div><span>Assessment coverage</span><h2>Target activity overview</h2></div><button type="button" onClick={() => navigate("/targets")}>View targets <AppIcon name="arrow" /></button></div>
          {data.targets.length === 0 ? <DashboardCardEmpty title="No targets" detail="No authoritative or assessed target scopes are available." /> : <div className="table-scroll"><table><colgroup><col className="target-activity-name" /><col className="target-activity-outcomes" /><col className="target-activity-latest" /><col className="target-activity-status" /></colgroup><thead><tr><th>Target</th><th>Evaluated outcomes</th><th>Latest activity</th><th>Status</th></tr></thead><tbody>{data.targets.map((target) => <tr aria-label={`Open ${target.name}`} key={target.id} role="link" tabIndex={0} onClick={() => openTarget(target.href)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openTarget(target.href); } }}><td><strong>{target.name}</strong></td><td>{target.outcomes}</td><td>{target.lastAssessed}</td><td><span className={`gate ${target.status.toLowerCase().replaceAll(" ", "-")}`}>{target.status}</span></td></tr>)}</tbody></table></div>}
        </article>

        <article className="dashboard-card activity-card">
          <div className="section-heading"><div><span>Audit feed</span><h2>Recent activity</h2></div><AppIcon name="activity" /></div>
          {data.activity.length === 0 ? <DashboardCardEmpty title="No recent activity" detail="No lifecycle activity was recorded in this period." /> : <div className="activity-list">{data.activity.slice(0, 3).map((item) => item.href ? <button className="activity-entry" key={item.id} type="button" onClick={() => navigate(item.href!)}><i className={`activity-status ${item.tone}`} /><p><strong>{item.title}</strong><span>{item.detail}</span><small>{item.occurredAt}</small></p></button> : <div key={item.id}><i className={`activity-status ${item.tone}`} /><p><strong>{item.title}</strong><span>{item.detail}</span><small>{item.occurredAt}</small></p></div>)}</div>}
          <button className="activity-link" type="button" onClick={() => navigate("/assessments")}>Open assessment history <AppIcon name="arrow" /></button>
        </article>
      </div>
    </section>
  );
}

function DashboardLoading() {
  return <section className="dashboard-state" aria-live="polite"><div className="loading-spinner" /><h2>Loading assurance posture</h2><p>Retrieving dashboard data from the local PoC service contract.</p></section>;
}

function DashboardError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <section className="dashboard-state error-state" role="alert"><AppIcon name="shield" /><h2>Dashboard unavailable</h2><p>{message}</p><button type="button" onClick={onRetry}>Retry</button></section>;
}

function DashboardCardEmpty({ title, detail }: { title: string; detail: string }) {
  return <div className="card-empty"><strong>{title}</strong><span>{detail}</span></div>;
}
