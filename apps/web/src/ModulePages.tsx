import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { assessmentUrl, currentAssessment, RUNS_CHANGED, forgetAssessment } from "./assessmentSession";
import { AssessmentResultsPanel } from "./AssessmentResultsPanel";
import { DeepTeamAssessmentPanel } from "./DeepTeamAssessmentPanel";
import { LinkedAssessmentDraft, LinkedAssessmentDraftList } from "./LinkedAssessmentDraft";
import { assessmentDisplayName, targetDisplayName } from "./displayLabels";
import { LiveFindingsPanel } from "./LiveFindingsPanel";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { ChatMateConfirmation } from "./ChatMateRunFeedback";
import { ManagementReportPanel } from "./ManagementReportPanel";
import { reportSelectionKey } from "./managementReport";
import type { ReportSelection } from "./managementReport";
import { ChatMateFindingsPanel, useChatMateFindings } from "./ChatMateFindingsPanel";
import { chatmateService } from "./chatmateService";
import { chatMateResultLabel, eligibleChatMateResult } from "./chatmateProjections";
import { chatMateAttackName, chatMateDate, chatMateRunReference, chatMateGenerationFailed } from "./chatmateDisplay";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";
import { ConsoleDetails, HistoryFilters, matchesHistoryDate, outcomeKey } from "./ConsoleUI";
import {
  ACTIVE_DEEPTEAM_RUN_KEY,
  listSavedDeepTeamRunIds,
  removeSavedDeepTeamRunId,
} from "./deepTeamRunStorage";
import { platformService } from "./platformService";
import { targetProjectionService } from "./targetProjectionService";
import type { TargetDetail as ProjectedTargetDetail, TargetSummary } from "./targetProjectionService";
import type {
  Assessment,
  AssessmentStatus,
  Finding,
  FindingSeverity,
  FindingStatus,
  Report,
  Target,
} from "./platformService";

const activeAssessmentStatuses: AssessmentStatus[] = [
  "VALIDATING",
  "QUEUED",
  "PLANNING",
  "RUNNING",
  "VERIFYING",
  "FINALIZING",
  "CANCEL_REQUESTED",
];

type ResourceOptions<T> = {
  pollMs?: number;
  shouldPoll?: (data: T) => boolean;
};

function useResource<T>(
  loader: () => Promise<T>,
  options: ResourceOptions<T> = {},
) {
  const [data, setData] = useState<T | null>(null);
  const dataRef = useRef<T | null>(null);
  const dataSignatureRef = useRef("");
  const inFlightRef = useRef<Promise<void> | null>(null);
  const requestVersionRef = useRef(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = async (silent = false) => {
    if (inFlightRef.current) return inFlightRef.current;
    const requestVersion = ++requestVersionRef.current;
    if (!silent || dataRef.current === null) {
      setLoading(true);
      setError("");
    }
    const request = (async () => {
      try {
        const nextData = await loader();
        if (requestVersion !== requestVersionRef.current) return;
        setError("");
        const signature = JSON.stringify(nextData);
        if (signature !== dataSignatureRef.current) {
          dataSignatureRef.current = signature;
          dataRef.current = nextData;
          setData(nextData);
        }
      } catch (reason) {
        if (requestVersion === requestVersionRef.current)
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load this page.",
          );
      } finally {
        if (requestVersion === requestVersionRef.current) setLoading(false);
        if (requestVersion === requestVersionRef.current) inFlightRef.current = null;
      }
    })();
    inFlightRef.current = request;
    return request;
  };

  useEffect(() => {
    void refresh();
    const onChange = () => void refresh(true);
    window.addEventListener(platformService.changeEvent, onChange);
    window.addEventListener(RUNS_CHANGED, onChange);
    window.addEventListener("focus", onChange);
    const onVisible = () => { if (document.visibilityState === "visible") onChange(); };
    document.addEventListener("visibilitychange", onVisible);
    const discovery = window.setInterval(() => { if (document.visibilityState !== "hidden") onChange(); }, 15000);
    const poll = options.pollMs
      ? window.setInterval(() => {
          if (document.visibilityState === "hidden") return;
          if (
            dataRef.current !== null &&
            options.shouldPoll &&
            !options.shouldPoll(dataRef.current)
          )
            return;
          void refresh(true);
        }, options.pollMs)
      : null;
    return () => {
      window.removeEventListener(platformService.changeEvent, onChange);
      window.removeEventListener(RUNS_CHANGED, onChange);
      window.removeEventListener("focus", onChange);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearInterval(discovery);
      requestVersionRef.current += 1;
      inFlightRef.current = null;
      if (poll) window.clearInterval(poll);
    };
  }, []);

  return { data, loading, error, refresh };
}

function ModuleLoading({ label }: { label: string }) {
  return (
    <section className="module-loading" aria-live="polite">
      <div className="loading-spinner" />
      <p>Loading {label}...</p>
    </section>
  );
}

function ModuleError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <section className="module-empty" role="alert">
      <strong>Unable to load this page</strong>
      <span>{message}</span>
      <button className="primary-action" type="button" onClick={onRetry}>
        Retry
      </button>
    </section>
  );
}

function EmptyModule({
  title,
  detail,
  action,
  compact = false,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`module-empty${compact ? " compact" : ""}`}>
      <strong>{title}</strong>
      <span>{detail}</span>
      {action}
    </div>
  );
}

function RefreshNotice({ error }: { error: string }) {
  if (error)
    return (
      <div className="inline-error" role="alert">
        Refresh failed. Showing the last available data.
      </div>
    );
  return null;
}

function DialogFrame({
  backdropClassName,
  children,
  className,
  labelledBy,
  locked = false,
  onClose,
}: {
  backdropClassName?: string;
  children: ReactNode;
  className: string;
  labelledBy: string;
  locked?: boolean;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  const lockedRef = useRef(locked);
  useEffect(() => {
    closeRef.current = onClose;
    lockedRef.current = locked;
  }, [locked, onClose]);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const focusFrame = window.requestAnimationFrame(() =>
      dialogRef.current
        ?.querySelector<HTMLElement>(
          "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href]",
        )
        ?.focus(),
    );
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !lockedRef.current) closeRef.current();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [
        ...dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ];
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, []);

  return (
    <div
      className={`modal-backdrop${backdropClassName ? ` ${backdropClassName}` : ""}`}
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !locked) onClose();
      }}
    >
      <section
        aria-labelledby={labelledBy}
        aria-modal="true"
        className={className}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        {children}
      </section>
    </div>
  );
}

export function TargetsPage() {
  const [targets, setTargets] = useState<TargetSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadVersion, setLoadVersion] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();
  const [targetSearch, setTargetSearch] = useState("");
  const requestedId = searchParams.get("id");
  const selected = targets?.find((target) => target.id === requestedId) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    targetProjectionService.list(controller.signal)
      .then(setTargets)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load Targets.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [loadVersion]);

  const updateTargetId = (id?: string) => setSearchParams((current) => {
    const next = new URLSearchParams(current);
    if (id) next.set("id", id); else next.delete("id");
    return next;
  });

  if (loading && !targets) return <ModuleLoading label="Targets" />;
  if (error && !targets)
    return <ModuleError message={error} onRetry={() => setLoadVersion((value) => value + 1)} />;
  if (!targets) return null;
  const query = targetSearch.trim().toLowerCase();
  const visibleTargets = targets.filter((target) =>
    `${target.name} ${target.purpose} ${target.environment} ${target.profile.profile_version}`.toLowerCase().includes(query),
  );

  return (
    <section className="module-page targets-page">
      <RefreshNotice error={error} />
      <div className="module-toolbar">
        <div>
          <span className="record-count">
            {visibleTargets.length} of {targets.length} Targets
          </span>
          <p>Review available test systems, data boundaries, and capabilities.</p>
        </div>
      </div>
      <label className="console-search-field"><span>Find a target</span><input type="search" value={targetSearch} onChange={(event) => setTargetSearch(event.target.value)} placeholder="Search by name, purpose or environment" /></label>
      {requestedId && !selected && (
        <EmptyModule
          title="Target not found"
          detail="The requested Target does not exist or is no longer available."
          action={
            <button
              className="secondary-action"
              type="button"
              onClick={() => updateTargetId()}
            >
              Return to Targets
            </button>
          }
        />
      )}
      {targets.length > 0 && (
        <div className="target-grid">
          {visibleTargets.map((target) => (
            <TargetCard key={target.id} target={target} onSelect={() => updateTargetId(target.id)} />
          ))}
        </div>
      )}
      {targets.length === 0 && <EmptyModule compact title="No targets available" detail="The server returned no target profiles." />}
      {targets.length > 0 && visibleTargets.length === 0 && <EmptyModule compact title="No matching targets" detail="Try a different name, purpose or environment." />}
      {selected && (
        <ProjectedTargetDialog key={selected.id} summary={selected} onClose={() => updateTargetId()} />
      )}
    </section>
  );
}

function TargetCard({ target, onSelect }: { target: TargetSummary; onSelect: () => void }) {
  return (
    <button className="target-card" type="button" onClick={onSelect}>
      <div className="target-card-top"><span className="target-chip">Synthetic test system</span></div>
      <strong>{target.name}</strong>
      <p>{target.purpose}</p>
      <dl>
        <div><dt>Version</dt><dd>{target.profile.profile_version}</dd></div>
        <div><dt>Capabilities</dt><dd>{target.tool_count}</dd></div>
        <div><dt>Managed by</dt><dd>{target.owner ?? "SecMate"}</dd></div>
      </dl>
    </button>
  );
}

function compactGuardrail(guardrail: ProjectedTargetDetail["guardrails"][number]) {
  switch (guardrail.id) {
    case "direct-user-untrusted":
      return { label: "Trust boundary", value: "User instructions are untrusted" };
    case "phase5-read-only-dispatch":
    case "read-only-dispatch":
      return { label: "Access", value: "Read-only mail search and Teams read" };
    case "profile-governed-access":
      return { label: "Access", value: "Reads available; proposals require approval" };
    case "fresh-path-state":
      return null;
    case "trusted-app-approval":
      return { label: "Approval", value: "Trusted application approval required" };
    case "simulated-effects-only":
      return { label: "Effects", value: "Simulated only; no real-world changes" };
    default:
      return { label: guardrail.name, value: guardrail.description };
  }
}

function toolStatusLabel(status: ProjectedTargetDetail["tools"][number]["execution_status"]) {
  if (status === "REQUIRES_APPROVAL") return "Requires approval";
  if (status === "NOT_ENABLED" || status === "DEFERRED") return "Not enabled for this assessment";
  return "Available";
}

const capabilityNames: Record<string, string> = {
  "secmate.conversation.history.read": "Read conversation history",
  "secmate.search_mail": "Search mail",
  "secmate.read_teams": "Read Teams conversations",
  "secmate.search_directory": "Search directory",
  "secmate.propose_message": "Propose a message",
  "secmate.read_calendar": "Read calendar",
  "secmate.propose_meeting": "Propose a meeting",
  search_alerts: "Search alerts",
  isolate_host: "Isolate host",
  disable_user: "Disable user",
};

function capabilityName(tool: ProjectedTargetDetail["tools"][number]) {
  const projected = tool.display_name?.trim();
  if (projected) return projected;
  const known = capabilityNames[tool.canonical_name];
  if (known) return known;
  const words = tool.canonical_name.split(".").at(-1)?.replaceAll("_", " ") || "Capability";
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function capabilitySummary(target: ProjectedTargetDetail) {
  const reads = target.tools.filter((tool) => tool.effect === "READ" && ["AVAILABLE", "EXECUTABLE"].includes(tool.execution_status)).length;
  const proposals = target.tools.filter((tool) => tool.effect === "WRITE" && tool.execution_status === "REQUIRES_APPROVAL").length;
  const unavailable = target.tools.filter((tool) => ["NOT_ENABLED", "DEFERRED"].includes(tool.execution_status)).length;
  const readNoun = reads === 1 ? "capability is" : "capabilities are";
  const proposalNoun = proposals === 1 ? "proposal requires" : "proposals require";
  return `${reads} read-only ${readNoun} available. ${proposals} ${proposalNoun} approval.${unavailable ? ` ${unavailable} not enabled for this assessment.` : ""}`;
}

function compactDataSource(source: string) {
  const value = source.replace(/^(fictional|synthetic)\s+/i, "");
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function compactMemory(target: ProjectedTargetDetail) {
  if (target.data_memory.memory_kind === "SEEDED_FACTS_ONLY") {
    return "Seeded facts only; reset each assessment";
  }
  return "No persistent or cross-run memory claimed";
}

function ProjectedTargetDialog({ summary, onClose }: { summary: TargetSummary; onClose: () => void }) {
  const headingId = useId();
  const [target, setTarget] = useState<ProjectedTargetDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    targetProjectionService.get(summary.id, controller.signal)
      .then(setTarget)
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load target details.");
      });
    return () => controller.abort();
  }, [summary.id]);

  return (
    <DialogFrame backdropClassName="target-detail-backdrop" className="detail-dialog target-detail-dialog" labelledBy={headingId} onClose={onClose}>
      <header><div><span>Version {summary.profile.profile_version}</span><h2 id={headingId}>{summary.name}</h2><p>{summary.purpose}</p></div><button type="button" onClick={onClose}>Close</button></header>
      {!target && !error && <div className="target-detail-state" role="status">Loading target details...</div>}
      {error && <div className="target-detail-state inline-error" role="alert">{error}</div>}
      {target && <div className="target-detail-body">
        <div className="target-summary-grid">
          <section><h3>Identity</h3><dl className="target-facts">
            <div><dt>Environment</dt><dd>Synthetic test system</dd></div><div><dt>Managed by</dt><dd>{target.owner ?? "SecMate"}</dd></div><div><dt>AI provider</dt><dd>OpenRouter</dd></div><div><dt>Model</dt><dd>{target.model_profile.model}</dd></div><div><dt>Version</dt><dd>{target.version}</dd></div>
          </dl></section>
          <section><h3>Guardrails and access</h3><dl className="target-facts target-compact-facts">{target.guardrails.map((guardrail) => {
            const fact = compactGuardrail(guardrail);
            return fact && <div key={guardrail.id}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>;
          })}</dl></section>
          <section><h3>Data and memory</h3><dl className="target-facts target-compact-facts">
            <div><dt>Data</dt><dd>Synthetic only; no production data</dd></div>
            <div><dt>Sources</dt><dd>{target.data_memory.data_sources.map(compactDataSource).join(", ")}</dd></div>
            <div><dt>Memory</dt><dd>{compactMemory(target)}</dd></div>
          </dl></section>
        </div>
        <section className="target-tools-section"><h3>Capabilities</h3><p className="target-section-intro">{capabilitySummary(target)}</p><div className="target-tools">
          {target.tools.map((tool) => <article className="target-tool" key={tool.canonical_name}>
            <div className="target-tool-heading"><div><strong>{capabilityName(tool)}</strong><span className="tool-access">{tool.effect === "READ" ? "Read-only" : "Proposes an action"}</span></div><span className={`tool-status ${tool.execution_status.toLowerCase()}`}>{toolStatusLabel(tool.execution_status)}</span></div>
            <p>{tool.description}</p>
          </article>)}
        </div></section>
      </div>}
    </DialogFrame>
  );
}

function OnboardTargetDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (target: Target) => void;
}) {
  const headingId = useId();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    try {
      onCreated(
        await platformService.createTarget({
          name: String(form.get("name") ?? "").trim(),
          description: String(form.get("description") ?? "").trim(),
          owner: String(form.get("owner") ?? "").trim(),
          environment: String(form.get("environment")) as
            | "Development"
            | "Test"
            | "Staging",
          criticality: String(form.get("criticality")) as
            | "Tier 1"
            | "Tier 2"
            | "Tier 3",
          modelProvider: "OpenRouter",
          modelName: String(form.get("modelName")),
          tools: String(form.get("tools") ?? "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
          guardrails: String(form.get("guardrails") ?? "")
            .split("\n")
            .map((item) => item.trim())
            .filter(Boolean),
          dataClasses: String(form.get("dataClasses") ?? "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        }),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to create Target.",
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <DialogFrame
      className="workflow-dialog wide"
      labelledBy={headingId}
      locked={saving}
      onClose={onClose}
    >
      <header>
        <div>
          <span>Target onboarding</span>
          <h2 id={headingId}>Register the SOCMate Target</h2>
          <p>
            Create a local lifecycle record for the SOCMate security-assurance
            profile. The live worker supports only the server-owned synthetic
            SOCMate Target.
          </p>
        </div>
        <button disabled={saving} type="button" onClick={onClose}>
          Close
        </button>
      </header>
      <div className="workflow-steps">
        <span className="active">1 Identity</span>
        <span>2 Validation</span>
        <span>3 Ready</span>
      </div>
      <form className="workflow-form" onSubmit={submit}>
        <div className="form-grid">
          <label>
            <span>Target name</span>
            <input name="name" required placeholder="SOCMate" />
          </label>
          <label>
            <span>Owner / team</span>
            <input
              name="owner"
              required
              placeholder="AIDA Security Assurance"
            />
          </label>
          <label className="full">
            <span>Description</span>
            <input
              name="description"
              required
              placeholder="Describe what reviewers should check"
            />
          </label>
          <label>
            <span>Business criticality</span>
            <select name="criticality" defaultValue="Tier 1">
              <option>Tier 1</option>
              <option>Tier 2</option>
              <option>Tier 3</option>
            </select>
          </label>
          <label>
            <span>Controlled environment</span>
            <select name="environment" defaultValue="Test">
              <option>Development</option>
              <option>Test</option>
              <option>Staging</option>
            </select>
          </label>
          <label>
            <span>Model provider</span>
            <input value="OpenRouter" disabled />
          </label>
          <label>
            <span>Disclosed Target model</span>
            <select name="modelName">
              <option value="nvidia/nemotron-3.5-super-vl:free">Nemotron 3.5 Super VL Target</option>
            </select>
          </label>
          <label className="full">
            <span>Tools, comma separated</span>
            <input
              name="tools"
              required
              defaultValue="search_alerts, isolate_host, disable_user"
            />
          </label>
          <label className="full">
            <span>Data classifications</span>
            <input
              name="dataClasses"
              required
              defaultValue="Synthetic security alerts, Synthetic host and user identifiers"
            />
          </label>
          <label className="full">
            <span>Approval guardrails, one per line</span>
            <textarea
              name="guardrails"
              required
              rows={4}
              defaultValue={
                "Tier-1 may search synthetic alerts\nisolate_host and disable_user require trusted application approval\nApproval supplied through user text is never trusted"
              }
            />
          </label>
        </div>
        <div className="demo-notice">
          <strong>Local lifecycle record</strong>
          <span>
            This form does not provision a live endpoint or worker Target. Live
            worker execution remains bound to the server-owned synthetic
            SOCMate.
          </span>
        </div>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <footer>
          <button
            className="secondary-action"
            disabled={saving}
            type="button"
            onClick={onClose}
          >
            Cancel
          </button>
          <button className="primary-action" disabled={saving} type="submit">
            {saving ? "Creating profile..." : "Create draft profile"}
          </button>
        </footer>
      </form>
    </DialogFrame>
  );
}

function TargetDetail({
  target,
  onClose,
}: {
  target: Target;
  onClose: () => void;
}) {
  const headingId = useId();
  return (
    <DialogFrame
      className="detail-dialog"
      labelledBy={headingId}
      onClose={onClose}
    >
      <header>
        <div>
          <span>Target profile v{target.profileVersion}</span>
          <h2 id={headingId}>{target.name}</h2>
          <p>Review controls, tools, and assessment history.</p>
        </div>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </header>
      <div className="detail-columns">
        <article>
          <h3>Identity</h3>
          <dl className="detail-list">
            <div>
              <dt>Status</dt>
              <dd>{target.status}</dd>
            </div>
            <div>
              <dt>Owner</dt>
              <dd>{target.owner}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{target.environment}</dd>
            </div>
            <div>
              <dt>Criticality</dt>
              <dd>{target.criticality}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>Target</dd>
            </div>
          </dl>
        </article>
        <article>
          <h3>Available actions</h3>
          {target.tools.map((tool) => (
            <span className="token" key={tool}>
              {assessmentDisplayName(tool)}
            </span>
          ))}
        </article>
        <article>
          <h3>Guardrails</h3>
          <ul>
            {target.guardrails.map((guardrail) => (
              <li key={guardrail}>{guardrail}</li>
            ))}
          </ul>
        </article>
        <article>
          <h3>Data classes</h3>
          {target.dataClasses.map((dataClass) => (
            <span className="token" key={dataClass}>
              {dataClass}
            </span>
          ))}
        </article>
      </div>
    </DialogFrame>
  );
}

export function AssessmentsPage() {
  const [params] = useSearchParams();
  const linkedId = params.get("linked");
  if (linkedId) return <section className="module-page"><LinkedAssessmentDraft key={linkedId} runId={linkedId} /></section>;
  const current = currentAssessment();
  if (current && params.get("workflow") !== "socmate") return <Navigate to={assessmentUrl(current)} replace />;
  return (
    <section className="module-page">
      <article className="chatmate-entry">
        <div><span>Real-target workflow</span><h2>ChatMate</h2><p>Generate two DeepTeam attacks, copy one into ChatMate, and evaluate the captured response with the independent Judge.</p></div>
        <Link className="primary-action" to="/assessments/chatmate">Start assessment</Link>
      </article>
      <DeepTeamAssessmentPanel />
      <LinkedAssessmentDraftList />
    </section>
  );
}

const findingTransitions: Record<FindingStatus, FindingStatus[]> = {
  OPEN: ["TRIAGED", "FALSE_POSITIVE"],
  TRIAGED: ["IN_REMEDIATION", "ACCEPTED_RISK", "FALSE_POSITIVE"],
  IN_REMEDIATION: ["READY_FOR_RETEST", "ACCEPTED_RISK"],
  READY_FOR_RETEST: ["RESOLVED", "IN_REMEDIATION"],
  RESOLVED: ["READY_FOR_RETEST"],
  ACCEPTED_RISK: ["OPEN"],
  FALSE_POSITIVE: ["OPEN"],
};

export function FindingsPage() {
  const chatmateHistory = useChatMateFindings();
  const {
    data: allFindings,
    loading,
    error,
    refresh,
  } = useResource(platformService.listFindings);
  const [searchParams, setSearchParams] = useSearchParams();
  const [severity, setSeverity] = useState<FindingSeverity | "ALL">("ALL");
  const activeLiveRunId = window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY);
  if (loading && !allFindings) return <ModuleLoading label="Findings" />;
  if (error && !allFindings)
    return <ModuleError message={error} onRetry={() => void refresh()} />;
  if (!allFindings) return null;
  const findings =
    severity === "ALL"
      ? allFindings
      : allFindings.filter((finding) => finding.severity === severity);
  const requestedId = searchParams.get("id");
  const selected =
    allFindings.find((finding) => finding.id === requestedId) ?? null;
  const openChatMateCount = chatmateHistory.projections.filter((item) => item.open).length;
  const completedChatMateCount = chatmateHistory.projections.filter((item) => !item.open).length;
  const hasResults = allFindings.length > 0 || chatmateHistory.projections.length > 0 || Boolean(activeLiveRunId);
  const historyLoaded = chatmateHistory.runs !== null && !chatmateHistory.error;
  return (
    <section className="module-page">
      <RefreshNotice error={error} />
      <div className="module-toolbar filters">
        <div>
          <span className="record-count">
            {findings.length + openChatMateCount} Findings
            {completedChatMateCount > 0 && ` · ${completedChatMateCount} completed result${completedChatMateCount === 1 ? "" : "s"}`}
          </span>
        </div>
        <div className="filter-pills">
          {(["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map(
            (item) => (
              <button
                className={severity === item ? "active" : ""}
                key={item}
                type="button"
                onClick={() => setSeverity(item)}
              >
                {item}
              </button>
            ),
          )}
        </div>
      </div>
      {activeLiveRunId && <LiveFindingsPanel key={activeLiveRunId} />}
      {requestedId && !selected && (
        <EmptyModule
          title="Finding not found"
          detail="The requested Finding does not exist or is no longer available."
          action={
            <button
              className="secondary-action"
              type="button"
              onClick={() => setSearchParams({})}
            >
              Return to Findings
            </button>
          }
        />
      )}
      {!hasResults && historyLoaded ? (
        <EmptyModule compact title="No findings or results yet" detail="Complete an assessment to review its evidence and results." action={<Link className="primary-action" to="/assessments">Start assessment</Link>} />
      ) : allFindings.length > 0 && findings.length === 0 && !chatmateHistory.projections.length ? (
        <EmptyModule
          title="No findings in this severity"
          detail="Change the filter or complete another Assessment."
        />
      ) : findings.length > 0 ? (
        <div className="records-table">
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Finding</th>
                <th>Target</th>
                <th>Status</th>
                <th>Review confidence</th>
                <th>Regression</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((finding) => (
                <tr key={finding.id}>
                  <td>
                    <span
                      className={`severity-chip ${finding.severity.toLowerCase()}`}
                    >
                      {finding.severity}
                    </span>
                  </td>
                  <td>
                    <button
                      className="record-link"
                      type="button"
                      onClick={() => setSearchParams({ id: finding.id })}
                    >
                      <strong>{finding.title}</strong>
                      <span>
                        {finding.id} / {finding.assessmentId}
                      </span>
                    </button>
                  </td>
                  <td>{finding.targetName}</td>
                  <td>{finding.status.replaceAll("_", " ")}</td>
                  <td>{Math.round(finding.confidence * 100)}%</td>
                  <td>{finding.regressionPinned ? "Pinned" : "Not pinned"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <ChatMateFindingsPanel history={chatmateHistory} />
      {selected && (
        <FindingDetail
          finding={selected}
          onClose={() => setSearchParams({})}
          onChanged={refresh}
        />
      )}
    </section>
  );
}

function FindingDetail({
  finding,
  onClose,
  onChanged,
}: {
  finding: Finding;
  onClose: () => void;
  onChanged: (silent?: boolean) => Promise<void>;
}) {
  const headingId = useId();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const updateStatus = async (status: FindingStatus) => {
    setSaving(true);
    setError("");
    try {
      await platformService.updateFindingStatus(finding.id, status);
      await onChanged(true);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to update Finding status.",
      );
    } finally {
      setSaving(false);
    }
  };
  const toggleRegression = async () => {
    setSaving(true);
    setError("");
    try {
      await platformService.toggleRegression(finding.id);
      await onChanged(true);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to update the regression case.",
      );
    } finally {
      setSaving(false);
    }
  };
  const statusOptions = [finding.status, ...findingTransitions[finding.status]];
  return (
    <DialogFrame
      className="detail-dialog finding-detail"
      labelledBy={headingId}
      locked={saving}
      onClose={onClose}
    >
      <header>
        <div>
          <span>
            {finding.id} / {finding.assessmentId}
          </span>
          <h2 id={headingId}>{finding.title}</h2>
          <p>{finding.targetName} / evidence-backed advisory Finding</p>
        </div>
        <button disabled={saving} type="button" onClick={onClose}>
          Close
        </button>
      </header>
      <div className="finding-actions">
        <span className={`severity-chip ${finding.severity.toLowerCase()}`}>
          {finding.severity}
        </span>
        <select
          aria-label="Finding status"
          disabled={saving}
          value={finding.status}
          onChange={(event) =>
            void updateStatus(event.target.value as FindingStatus)
          }
        >
          {statusOptions.map((status) => (
            <option key={status} value={status}>{status.replaceAll("_", " ")}</option>
          ))}
        </select>
        <button
          className="secondary-action"
          disabled={saving}
          type="button"
          onClick={() => void toggleRegression()}
        >
          {finding.regressionPinned
            ? "Unpin regression"
            : "Pin regression case"}
        </button>
      </div>
      {error && (
        <div className="dialog-error form-error" role="alert">
          {error}
        </div>
      )}
      <div className="evidence-grid">
        <article>
          <span>Expected boundary</span>
          <p>{finding.expectedBehavior}</p>
        </article>
        <article>
          <span>Observed behavior</span>
          <p>{finding.observedBehavior}</p>
        </article>
        <article className="full">
          <span>Evidence</span>
          <p>{finding.evidence}</p>
          <code>{finding.toolAttempt}</code>
        </article>
        <article>
          <ConsoleDetails title="Automated policy check">
          <p>{finding.oracleResult}</p>
          </ConsoleDetails>
        </article>
        <article>
          <ConsoleDetails title="Judge rationale">
          <p>{finding.judgeRationale}</p>
          </ConsoleDetails>
        </article>
        <article>
          <ConsoleDetails title="Standards mappings">
          {finding.standards.map((standard) => (
            <span className="token" key={standard}>
              {standard}
            </span>
          ))}
          </ConsoleDetails>
        </article>
        <article className="full">
          <span>Recommended remediation</span>
          <p>{finding.remediation}</p>
        </article>
      </div>
    </DialogFrame>
  );
}

type ReportPageData = {
  reports: Report[];
  assessments: Assessment[];
  findings: Finding[];
};
const loadReportPage = async (): Promise<ReportPageData> => {
  const [reports, assessments, findings] = await Promise.all([
    platformService.listReports(),
    platformService.listAssessments(),
    platformService.listFindings(),
  ]);
  return { reports, assessments, findings };
};

function reportResultLabel(value: string | null) {
  if (value === "RESISTED" || value === "PASS") return "No policy violation found";
  if (value === "COMPROMISED" || value === "CRITICAL_RISK_DETECTED") return "Policy violation found";
  if (value === "INCONCLUSIVE" || value === "ASSESSMENT_INCONCLUSIVE") return "Inconclusive";
  if (value === "ERROR" || value === "FAILED" || value === "HARNESS_ERROR") return "Assessment incomplete";
  if (value === "CANCELLED") return "Assessment cancelled";
  if (value === "RUNNING" || value === "QUEUED" || value === "CANCEL_REQUESTED") return "Assessment in progress";
  return value?.replaceAll("_", " ").toLowerCase() ?? "Result pending";
}

export function ReportsPage() {
  const [selectionOrder, setSelectionOrder] = useState<ReportSelection[]>([]);
  const [activeManagementReport, setActiveManagementReport] = useState<ReportSelection[] | null>(null);
  const chatmateHistory = useResource(async () => {
    const runs = await chatmateService.listRuns();
    if (!Array.isArray(runs)) throw new Error("Invalid ChatMate history response.");
    return runs.sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, { pollMs: 1500, shouldPoll: runs => runs.some(run => ["QUEUED", "GENERATING", "EVALUATING"].includes(run.status)) });
  const { data, loading, error, refresh } = useResource(loadReportPage, {
    pollMs: 1500,
    shouldPoll: (page) =>
      page.assessments.some((assessment) =>
        activeAssessmentStatuses.includes(assessment.status),
      ) ||
      page.reports.some((report) =>
        ["REQUESTED", "GENERATING"].includes(report.status),
      ),
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const [liveRuns, setLiveRuns] = useState<DeepTeamRunRecord[]>([]);
  const [historyDate, setHistoryDate] = useState("all");
  const [historyOutcome, setHistoryOutcome] = useState("all");
  const [historySource, setHistorySource] = useState("all");
  const [savedLiveRunIds, setSavedLiveRunIds] = useState(() => listSavedDeepTeamRunIds());
  const [liveHistoryLoading, setLiveHistoryLoading] = useState(true);
  const [liveHistoryAttempt, setLiveHistoryAttempt] = useState(0);
  const [removal, setRemoval] = useState<{ key: string; id: string; source: string } | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removalError, setRemovalError] = useState("");
  const [removedKeys, setRemovedKeys] = useState<string[]>([]);
  const removalPending = useRef(false);
  const historyHeadingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!removedKeys.length) return;
    const frame = window.requestAnimationFrame(() => historyHeadingRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [removedKeys]);
  const reportDetailRef = useRef<HTMLDivElement>(null);
  const focusReportOnSelectionRef = useRef(false);
  const selectedReportKey = searchParams.get("chatmate") ?? searchParams.get("live") ?? searchParams.get("id");

  useEffect(() => {
    if (!focusReportOnSelectionRef.current || (!selectedReportKey && !activeManagementReport)) return;
    focusReportOnSelectionRef.current = false;
    const frame = window.requestAnimationFrame(() => {
      reportDetailRef.current?.focus();
      reportDetailRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [selectedReportKey, activeManagementReport]);

  useEffect(() => {
    let disposed = false;
    let timer = 0;
    const onFocus = () => setLiveHistoryAttempt((value) => value + 1);
    const loadLiveRuns = async () => {
      const runIds = listSavedDeepTeamRunIds();
      setSavedLiveRunIds(runIds);
      const results = await Promise.allSettled(
        runIds.map((runId) => modelConnectivityService.getDeepTeamRun(runId)),
      );
      if (disposed) return;
      const loaded = results.flatMap((result, index) => result.status === "fulfilled" && result.value.run_id === runIds[index] ? [result.value] : [])
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
      setLiveRuns(loaded);
      setLiveHistoryLoading(false);
      if (loaded.some((run) => ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(run.status))) {
        timer = window.setTimeout(() => void loadLiveRuns(), 2000);
      }
    };
    void loadLiveRuns();
    window.addEventListener("focus", onFocus);
    return () => { disposed = true; window.clearTimeout(timer); window.removeEventListener("focus", onFocus); };
  }, [liveHistoryAttempt]);

  if (loading && !data) return <ModuleLoading label="Reports" />;
  if (error && !data)
    return <ModuleError message={error} onRetry={() => void refresh()} />;
  if (!data) return null;
  const requestedId = searchParams.get("id");
  const requestedChatMateId = searchParams.get("chatmate");
  const requestedLiveId = searchParams.get("live");
  const selectedLiveId = requestedLiveId === "1"
    ? window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY)
    : requestedLiveId;
  const selected = requestedId
    ? data.reports.find((report) => report.id === requestedId)
    : undefined;
  const downloadJson = (report: Report) => {
    const assessment = data.assessments.find(
      (item) => item.id === report.assessmentId,
    );
    const findings = data.findings.filter((finding) =>
      report.findingIds.includes(finding.id),
    );
    const blob = new Blob(
      [
        JSON.stringify(
          {
            report,
            assessment,
            findings,
            exportType: "SECMATE_POC_BASELINE",
            generatedAt: new Date().toISOString(),
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.id.toLowerCase()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const requestRemoval = (source: string, id: string) => {
    setRemovalError("");
    setRemoval({ source, id, key: `${source}-${id}` });
  };
  const removeLiveReport = (runId: string) => requestRemoval("live", runId);
  const confirmRemoval = async () => {
    if (!removal || removalPending.current) return;
    removalPending.current = true;
    setRemoving(true);
    setRemovalError("");
    try {
      const { source, id, key } = removal;
      if (source === "chatmate") {
        const latest = await chatmateService.getRun(id);
        if (latest.run_id !== id || !["COMPLETED", "FAILED", "ABANDONED", "REJECTED"].includes(latest.status) || latest.critic_status === "RUNNING")
          throw new Error("This run is active. Wait for its work to finish before deleting it.");
        await chatmateService.deleteRun(id);
        forgetAssessment(id);
      } else if (source === "summary") await platformService.deleteReport(id);
      else {
        removeSavedDeepTeamRunId(id);
        setSavedLiveRunIds((current) => current.filter((entry) => entry !== id));
        setLiveRuns((current) => current.filter((run) => run.run_id !== id));
        setLiveHistoryAttempt((value) => value + 1);
      }
      setRemovedKeys((current) => [...current, key]);
      const selectionKey = source === "summary" ? null : reportSelectionKey({ source: source === "chatmate" ? "ChatMate" : "SocMate", runId: id });
      setSelectionOrder((current) => current.filter((entry) => reportSelectionKey(entry) !== selectionKey));
      setActiveManagementReport((current) => current?.some((entry) => reportSelectionKey(entry) === selectionKey) ? null : current);
      // Read the current URL: navigation may have changed during the request.
      setSearchParams((current) => {
        const next = new URLSearchParams(current);
        const param = source === "chatmate" ? "chatmate" : source === "live" ? "live" : "id";
        if (next.get(param) === id || (source === "live" && next.get(param) === "1" && selectedLiveId === id)) {
          next.delete(param); next.delete("management");
        }
        return next;
      }, { replace: true });
      setRemoval(null);
      if (source === "summary") await refresh(true);
      if (source === "chatmate") await chatmateHistory.refresh(true);
    } catch (reason) {
      setRemovalError(reason instanceof Error ? reason.message : "Unable to remove this report.");
    } finally { removalPending.current = false; setRemoving(false); }
  };
  const selectLiveReport = (runId: string) => {
    setActiveManagementReport(null);
    focusReportOnSelectionRef.current = true;
    setSearchParams({ live: runId });
  };
  const selectGeneratedReport = (reportId: string) => {
    setActiveManagementReport(null);
    focusReportOnSelectionRef.current = true;
    setSearchParams({ id: reportId });
  };
  const historyEntries = [
    ...(!liveHistoryLoading ? savedLiveRunIds.filter((id) => !liveRuns.some((run) => run.run_id === id)).map((id) => ({ source: "live", id, date: "", outcome: "unavailable", key: `live-${id}`, selection: { source: "SocMate" as const, runId: id }, selectionLabel: "Managed / DeepTeam",
      content: <div className="inline-error" role="group" aria-label={`Unavailable saved assessment ${id}`} key={`unavailable-${id}`}><strong>Saved assessment unavailable</strong><p>{id}</p><button className="secondary-action" type="button" onClick={() => setLiveHistoryAttempt((value) => value + 1)}>Retry saved assessment</button><button className="secondary-action" type="button" onClick={() => removeLiveReport(id)}>Remove saved reference</button></div> })) : []),
    ...(chatmateHistory.data ?? []).filter(run => eligibleChatMateResult(run) || chatMateGenerationFailed(run)).map((run) => ({ source: "chatmate", id: run.run_id, date: run.completed_at ?? run.created_at, key: `chatmate-${run.run_id}`, selection: eligibleChatMateResult(run) ? { source: "ChatMate" as const, runId: run.run_id } : null,
      outcome: outcomeKey(run.status === "FAILED" ? "FAILED" : run.final_status),
      content: <button aria-current={requestedChatMateId === run.run_id ? "true" : undefined} className={requestedChatMateId === run.run_id ? "active" : ""} key={`chatmate-${run.run_id}`} type="button" onClick={() => { setActiveManagementReport(null); focusReportOnSelectionRef.current = true; setSearchParams({ chatmate: run.run_id }); }}>
        <div><span>ChatMate</span><strong>{chatMateAttackName(run)}</strong><small>{chatMateRunReference(run.run_id)}</small>{run.parent_run_id && <small>Continuation of {chatMateRunReference(run.parent_run_id)}</small>}</div><b>{chatMateGenerationFailed(run) ? "Generation Failed" : chatMateResultLabel(run)}</b><time>{chatMateDate(run.completed_at ?? run.created_at)}</time><em>View report</em></button> })),
    ...liveRuns.map((run) => ({ source: "live", id: run.run_id, date: run.completed_at ?? run.created_at, key: `live-${run.run_id}`, selection: { source: "SocMate" as const, runId: run.run_id }, selectionLabel: run.target_profile_id === "secmate.synthetic-chatmate.fresh.v1" ? targetDisplayName(run.target_profile_id) : "SocMate",
      outcome: outcomeKey(run.status === "FAILED" || run.status === "CANCELLED" ? run.status : run.final_status ?? run.status),
      content: <button aria-current={selectedLiveId === run.run_id ? "true" : undefined} className={selectedLiveId === run.run_id ? "active" : ""} key={`live-${run.run_id}`} type="button" onClick={() => selectLiveReport(run.run_id)}>
        <div><span>{run.target_profile_id === "secmate.synthetic-chatmate.fresh.v1" ? targetDisplayName(run.target_profile_id) : "SocMate"}</span><strong>{assessmentDisplayName(run.attack)}</strong><small>{assessmentDisplayName(run.vulnerability)}</small></div><b>{reportResultLabel(run.status === "FAILED" || run.status === "CANCELLED" ? run.status : run.final_status ?? run.status)}</b><time>{chatMateDate(run.completed_at ?? run.created_at)}</time><em>View report</em></button> })),
    ...data.reports.map((report) => ({ source: "summary", id: report.id, date: report.generatedAt, outcome: outcomeKey(report.advisoryResult), key: `summary-${report.id}`, selection: null,
      content: <button aria-current={selected?.id === report.id ? "true" : undefined} className={selected?.id === report.id ? "active" : ""} key={`summary-${report.id}`} type="button" onClick={() => selectGeneratedReport(report.id)}>
        <div><span>Summary report</span><strong>{report.title}</strong><small>{report.targetName}</small></div><b>{reportResultLabel(report.advisoryResult)}</b><time>{chatMateDate(report.generatedAt)}</time><em>View report</em></button> })),
  ].filter((item) => !removedKeys.includes(item.key)).sort((a, b) => (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0));
  const totalReports = historyEntries.length + (liveHistoryLoading ? savedLiveRunIds.length : 0);
  const filteredHistory = historyEntries.filter((item) => matchesHistoryDate(item.date, historyDate)
    && (historyOutcome === "all" || item.outcome === historyOutcome)
    && (historySource === "all" || item.source === historySource));
  return (
    <section className="module-page reports-layout">
      <RefreshNotice error={error} />
      {(activeManagementReport || requestedChatMateId !== null || selectedLiveId || requestedId) && <div className="report-detail" ref={reportDetailRef} tabIndex={-1}>
        {activeManagementReport || (searchParams.get("management") === "1" && requestedChatMateId) ? <ManagementReportPanel
          selections={activeManagementReport ?? [{ source: "ChatMate", runId: requestedChatMateId! }]}
          title={activeManagementReport ? "SecMate Report" : "ChatMate Report"}
          onClose={() => { setActiveManagementReport(null); if (searchParams.has("management")) setSearchParams(requestedChatMateId ? { chatmate: requestedChatMateId } : {}); }} /> : requestedChatMateId !== null ? (
          requestedChatMateId ? <ChatMateReportPanel key={requestedChatMateId} runId={requestedChatMateId} onClose={() => setSearchParams({})} />
            : <EmptyModule title="ChatMate report unavailable" detail="A ChatMate run ID is required." />
        ) : selectedLiveId ? (
          <AssessmentResultsPanel
            runId={selectedLiveId}
            onClose={() => setSearchParams({})}
            onRemove={() => removeLiveReport(selectedLiveId)}
          />
        ) : requestedId && !selected ? (
          <EmptyModule
            title="Report not found"
            detail="The requested report does not exist or is no longer available."
            action={<button className="secondary-action" type="button" onClick={() => setSearchParams({})}>Back to history</button>}
          />
        ) : selected ? (
          <article className="report-preview">
            <div className="report-actions">
              <div>
                <button className="secondary-action" type="button" onClick={() => setSearchParams({})}>Back to history</button>
                <button className="danger-action" type="button" disabled={["REQUESTED", "GENERATING"].includes(selected.status)} onClick={() => requestRemoval("summary", selected.id)}>Delete report</button>
                <button className="secondary-action" type="button" onClick={() => window.print()}>Print</button>
                <button className="primary-action" disabled={selected.status !== "AVAILABLE"} type="button" onClick={() => downloadJson(selected)}>Export JSON</button>
              </div>
            </div>
            <span className="report-kicker">Summary report</span>
            <h2>{selected.title}</h2>
            <p className="report-meta">Generated {new Date(selected.generatedAt).toLocaleString()}</p>
            <div className="report-result">
              <span>Result</span>
              <strong>{reportResultLabel(selected.advisoryResult)}</strong>
            </div>
            <section><h3>Summary</h3><p>{selected.summary}</p></section>
            <section><h3>Recommendation</h3><p>{selected.recommendation}</p></section>
            <ConsoleDetails title={`Linked findings (${selected.findingIds.length})`}>
              {data.findings.filter((finding) => selected.findingIds.includes(finding.id)).map((finding) => <article className="console-linked-finding" key={finding.id}><strong>{finding.title}</strong><p>{finding.observedBehavior}</p><Link className="secondary-action" to={`/findings?id=${encodeURIComponent(finding.id)}`}>Review finding</Link></article>)}
              {!selected.findingIds.length && <p>No findings linked to this report.</p>}
            </ConsoleDetails>
            <details className="report-technical-details"><summary>View details</summary><p>{selected.id} · {selected.status.toLowerCase()} · {selected.findingIds.length} linked finding{selected.findingIds.length === 1 ? "" : "s"}</p></details>
          </article>
        ) : null}
      </div>}
      <section className="report-history" aria-labelledby="report-history-heading">
        <header><div><span>Saved results</span><h2 id="report-history-heading" ref={historyHeadingRef} tabIndex={-1}>Report history</h2></div><div className="management-report-selection-actions"><strong>{totalReports}</strong><span>{selectionOrder.length} selected</span><button className="secondary-action" type="button" disabled={!selectionOrder.length} onClick={() => setSelectionOrder([])}>Clear</button><button className="primary-action" type="button" disabled={!selectionOrder.length} onClick={() => { focusReportOnSelectionRef.current = true; setActiveManagementReport([...selectionOrder]); }}>Create report</button></div></header>
        <HistoryFilters date={historyDate} onDateChange={setHistoryDate} outcome={historyOutcome} onOutcomeChange={setHistoryOutcome} source={historySource} onSourceChange={setHistorySource} liveLabel="Managed / DeepTeam" />
        <div className="report-history-list">
          {liveHistoryLoading && savedLiveRunIds.length > 0 && <p role="status">Loading saved assessment history...</p>}
          {chatmateHistory.loading && !chatmateHistory.data && <p role="status">Loading ChatMate report history...</p>}
           {chatmateHistory.error && <div className="inline-error" role="alert">ChatMate history unavailable: {chatmateHistory.error} <button className="secondary-action" type="button" onClick={() => void chatmateHistory.refresh()}>Retry ChatMate history</button></div>}
           {filteredHistory.map((item) => <div className="report-history-entry" key={item.key}>{item.selection ? <div className="management-report-selection-row">
             <label><span className="visually-hidden">Select {"selectionLabel" in item ? String(item.selectionLabel) : item.selection.source} {item.selection.runId}</span><input type="checkbox"
              checked={selectionOrder.some((selection) => reportSelectionKey(selection) === reportSelectionKey(item.selection!))}
              onChange={(event) => { const selection = item.selection!; setSelectionOrder((current) => event.target.checked
                ? current.some((entry) => reportSelectionKey(entry) === reportSelectionKey(selection)) ? current : [...current, selection]
                : current.filter((entry) => reportSelectionKey(entry) !== reportSelectionKey(selection))); }} /></label>
            {item.content}</div> : <div className="management-report-selection-row summary-history-row">{item.content}</div>}
            <button className="danger-action history-remove" type="button" aria-label={`${item.source === "chatmate" ? "Delete source run" : "Remove report"} ${item.id}`}
              disabled={item.source === "chatmate" ? chatmateHistory.data?.find((run) => `chatmate-${run.run_id}` === item.key)?.critic_status === "RUNNING" : item.source === "summary" ? data.reports.some((report) => `summary-${report.id}` === item.key && ["REQUESTED", "GENERATING"].includes(report.status)) : false}
              onClick={() => requestRemoval(item.source, item.id)}>{item.source === "chatmate" ? "Delete source run" : "Remove report"}</button>
            </div>)}
          {historyEntries.length > 0 && filteredHistory.length === 0 && <p className="report-list-empty">No reports match these filters.</p>}
          {totalReports === 0 && !chatmateHistory.loading && !chatmateHistory.error && !liveHistoryLoading && <p className="report-list-empty">No reports yet.</p>}
        </div>
      </section>
      {removal && <DialogFrame className="workflow-dialog" labelledBy="report-removal-heading" locked={removing} onClose={() => setRemoval(null)}>
        <h2 id="report-removal-heading">{removal.source === "chatmate" ? "Delete ChatMate source run?" : "Remove browser-local report?"}</h2>
        <ChatMateConfirmation title="Confirm report removal" description={removal.source === "chatmate" ? `Permanently delete ${removal.id} and its saved evidence from the API. This also removes the source assessment from ChatMate history. Active or unresolved workers cannot be deleted.` : removal.source === "live" ? `Remove the saved reference ${removal.id} from this browser. The API source run and its original evidence are retained.` : `Remove ${removal.id} from this browser. Its assessment and original findings are retained.`} confirmLabel="Confirm removal" cancelLabel="Cancel removal" busy={removing} onConfirm={() => void confirmRemoval()} onCancel={() => setRemoval(null)} />
        {removalError && <div className="inline-error" role="alert">{removalError}</div>}
      </DialogFrame>}
    </section>
  );
}
