import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { Session } from "./auth";
import { ModelConnectivitySection } from "./ModelConnectivitySection";
import { THEME_PRESETS } from "./theme";
import type { ThemeId } from "./theme";

type SettingsPageProps = {
  activeTheme: ThemeId;
  session: Session;
  onThemeChange: (theme: ThemeId) => void;
  onResetDemo: () => Promise<void>;
};

const settingsSections = [
  { id: "overview", label: "Overview", detail: "Workspace status and scope" },
  { id: "profile", label: "Profile", detail: "Identity and regional preferences" },
  { id: "appearance", label: "Appearance", detail: "Theme and presentation" },
  { id: "demo", label: "PoC workspace", detail: "Local SOCMate baseline" },
  { id: "identity", label: "Identity and access", detail: "SSO, roles, and approvals" },
  { id: "assessment", label: "Assessment policy", detail: "Budgets and safety controls" },
  { id: "models", label: "AI runtime", detail: "Providers, models, and worker health" },
  { id: "evidence", label: "Evidence and retention", detail: "Redaction and audit lifecycle" },
  { id: "notifications", label: "Notifications", detail: "Routing and escalation" },
  { id: "integrations", label: "Integrations", detail: "Pipelines and operations" },
] as const;

type SettingsSection = (typeof settingsSections)[number]["id"];

const plannedContent: Record<Exclude<SettingsSection, "overview" | "profile" | "appearance" | "demo" | "models">, { title: string; description: string; items: Array<{ title: string; detail: string }> }> = {
  identity: { title: "Identity and access", description: "Plan enterprise authentication and role boundaries without exposing identity decisions as working controls.", items: [{ title: "Identity provider", detail: "Enterprise SSO provider and session policy." }, { title: "Role matrix", detail: "Security Lead, AI Product Owner, and Executive Viewer permissions." }, { title: "Access reviews", detail: "Periodic ownership and authorization review workflow." }] },
  assessment: { title: "Assessment policy", description: "Define organization-wide execution limits and safety decisions controlled by the broker.", items: [{ title: "Default budgets", detail: "Approved turn, token, request, time, and cost limits." }, { title: "Environment policy", detail: "Allowed Targets, destinations, sandboxes, and execution tiers." }, { title: "Emergency controls", detail: "Cancellation authority and global emergency-stop ownership." }] },
  evidence: { title: "Evidence and retention", description: "Prepare immutable, reproducible, and appropriately redacted assurance evidence.", items: [{ title: "Retention", detail: "Retention periods, deletion policy, and legal requirements." }, { title: "Redaction", detail: "Credential, token, PII, and sensitive-data handling rules." }, { title: "Audit integrity", detail: "Version provenance, tamper evidence, and canonical export formats." }] },
  notifications: { title: "Notifications", description: "Route advisory events to the correct owners without creating alert fatigue.", items: [{ title: "Finding events", detail: "Target owner and security reviewer notifications." }, { title: "Operational events", detail: "Review service errors, timeouts, inconclusive runs, and worker health." }, { title: "Escalation", detail: "Critical-risk review paths and acknowledgement expectations." }] },
  integrations: { title: "Integrations", description: "Connect SecMate to internal delivery and operations platforms after architecture approval.", items: [{ title: "Advisory CI/CD", detail: "JSON, SARIF, and JUnit result publishing." }, { title: "Secrets and inference", detail: "Secrets manager and centrally reachable model services." }, { title: "Platform operations", detail: "Queues, workers, scheduling, monitoring, backup, and recovery." }] },
};

function PlannedSection({ section }: { section: keyof typeof plannedContent }) {
  const content = plannedContent[section];
  return <div className="settings-detail"><header><span className="placeholder-badge">Planned</span><h2>{content.title}</h2><p>{content.description}</p></header><div className="settings-detail-list">{content.items.map((item) => <article key={item.title}><h3>{item.title}</h3><p>{item.detail}</p></article>)}</div></div>;
}

const timeZones = ["UTC", "Asia/Kolkata", "Asia/Dubai", "Europe/London", "Europe/Paris", "America/New_York", "America/Chicago", "America/Los_Angeles", "Asia/Singapore", "Australia/Sydney"];
const TIME_ZONE_KEY = "secmate.profile.timezone";

export function SettingsPage({ activeTheme, session, onThemeChange, onResetDemo }: SettingsPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSection = searchParams.get("section");
  const activeSection = settingsSections.some((section) => section.id === requestedSection) ? requestedSection as SettingsSection : "overview";
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [savedTimeZone, setSavedTimeZone] = useState(() => window.localStorage.getItem(TIME_ZONE_KEY) ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC");
  const [timeZone, setTimeZone] = useState(savedTimeZone);
  const [timeZoneSaved, setTimeZoneSaved] = useState(false);
  const availableTimeZones = timeZones.includes(timeZone) ? timeZones : [timeZone, ...timeZones];

  const selectSection = (section: SettingsSection) => {
    setConfirmReset(false);
    setSearchParams(section === "overview" ? {} : { section });
  };
  const resetDemo = async () => {
    if (!confirmReset) { setConfirmReset(true); return; }
    setResetting(true);
    await onResetDemo();
  };
  const saveTimeZone = () => {
    window.localStorage.setItem(TIME_ZONE_KEY, timeZone);
    setSavedTimeZone(timeZone);
    setTimeZoneSaved(true);
  };

  return (
    <section className="settings-shell">
      <aside className="settings-navigation" aria-label="Settings categories">
        <div><span>SecMate</span><strong>Settings</strong><small>Local PoC workspace</small></div>
        <label className="settings-mobile-select"><span>Settings category</span><select value={activeSection} onChange={(event) => selectSection(event.target.value as SettingsSection)}>{settingsSections.map((section) => <option key={section.id} value={section.id}>{section.label}</option>)}</select></label>
        <nav>{settingsSections.map((section) => <button aria-current={activeSection === section.id ? "page" : undefined} key={section.id} type="button" onClick={() => selectSection(section.id)}><strong>{section.label}</strong><span>{section.detail}</span></button>)}</nav>
      </aside>

      <div className="settings-content">
        {activeSection === "overview" && <div className="settings-detail"><header><h2>Workspace overview</h2></header><div className="settings-overview-grid"><article><span>Current profile</span><strong>{session.displayName}</strong><button type="button" onClick={() => selectSection("profile")}>Open profile</button></article><article><span>Current theme</span><strong>{THEME_PRESETS.find((theme) => theme.id === activeTheme)?.label}</strong><button type="button" onClick={() => selectSection("appearance")}>Manage appearance</button></article><article><span>Workspace</span><strong>SOCMate baseline</strong><button type="button" onClick={() => selectSection("demo")}>Manage PoC workspace</button></article><article><span>Runtime</span><strong>AI runtime and worker health</strong><button type="button" onClick={() => selectSection("models")}>Open AI runtime</button></article></div></div>}

        {activeSection === "profile" && <div className="settings-detail"><header><span className="placeholder-badge">Available now</span><h2>Profile</h2><p>Review your current SecMate identity and regional preference for this local PoC.</p></header><article className="profile-panel"><div className="profile-identity"><span className="profile-avatar" aria-hidden="true">{session.displayName.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span><div><h3>{session.displayName}</h3><p>{session.email}</p><span>{session.role}</span></div></div><dl className="profile-facts"><div><dt>Name</dt><dd>{session.displayName}</dd></div><div><dt>Account</dt><dd>{session.email}</dd></div><div><dt>Access profile</dt><dd>{session.role}</dd></div><div><dt>Identity source</dt><dd>Local PoC access</dd></div></dl><div className="profile-time-zone"><div><span>Time zone</span><h3>Regional date and time</h3><p>SecMate uses this preference when displaying Assessment, Finding, and Report timestamps.</p></div><div className="profile-time-zone-control"><select aria-label="Time zone" value={timeZone} onChange={(event) => { setTimeZone(event.target.value); setTimeZoneSaved(false); }}>{availableTimeZones.map((zone) => <option key={zone}>{zone}</option>)}</select><button disabled={timeZone === savedTimeZone} type="button" onClick={saveTimeZone}>Save time zone</button></div><small>{timeZoneSaved ? `Saved ${savedTimeZone}` : `Current time zone: ${savedTimeZone}`}</small></div><footer>Enterprise identity, role, and access changes will remain managed by Paramount IT after SSO integration.</footer></article></div>}

        {activeSection === "appearance" && <div className="settings-detail"><header><span className="placeholder-badge">Available now</span><h2>Appearance</h2><p>Choose an approved SecMate presentation preset. The preference is stored locally in this browser.</p></header><div className="settings-theme-large">{THEME_PRESETS.map((theme) => <button aria-pressed={activeTheme === theme.id} key={theme.id} type="button" onClick={() => onThemeChange(theme.id)}><span className="theme-preview" aria-hidden="true" style={{ background: theme.swatches[0] }}><i style={{ background: theme.swatches[1] }} /><b style={{ background: theme.swatches[2] }} /></span><span><strong>{theme.label}</strong><small>{theme.description}</small></span><em>{activeTheme === theme.id ? "Selected" : "Select"}</em></button>)}</div></div>}

        {activeSection === "demo" && <div className="settings-detail"><header><h2>PoC workspace</h2></header><article className="settings-reset-panel"><div><h3>Reset PoC workspace</h3><p>Restore browser workspace data to the SOCMate baseline.</p></div><button disabled={resetting} type="button" onClick={() => void resetDemo()}>{resetting ? "Resetting..." : confirmReset ? "Confirm PoC reset" : "Reset PoC workspace"}</button>{confirmReset && !resetting && <small>Click again to confirm the reset.</small>}</article></div>}

        {activeSection === "models" && <ModelConnectivitySection />}

        {activeSection !== "overview" && activeSection !== "profile" && activeSection !== "appearance" && activeSection !== "demo" && activeSection !== "models" && <PlannedSection section={activeSection} />}
      </div>
    </section>
  );
}
