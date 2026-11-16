import { useEffect, useRef, useState } from "react";
import { AssessmentSelect } from "./AssessmentSelect";
import { StandardReviewPanel } from "./StandardReviewPanel";
import { SocMateScoreSummary } from "./SocMateScoreSummary";
import { Link } from "react-router-dom";
import { modelConnectivityService, ModelConnectivityError } from "./modelConnectivityService";
import type {
  DeepTeamAuditReport,
  DeepTeamCatalog,
  DeepTeamRunRecord,
  PlatformCapabilities,
  ProviderStatus,
} from "./modelConnectivityService";
import {
  ACTIVE_DEEPTEAM_RUN_KEY,
  saveDeepTeamRunId,
  removeSavedDeepTeamRunId,
} from "./deepTeamRunStorage";
import { assessmentDisplayName, assessmentFailureMessage, targetDisplayName } from "./displayLabels";
import { operationKey } from "./standardReview";

const TOKEN_BUDGET_OPTIONS = [25_000, 50_000, 75_000, 100_000, 150_000, 250_000];
const SOCMATE_TARGET_ID = "synthetic-socmate-tier1";
const SYNTHETIC_CHATMATE_TARGET_ID = "secmate.synthetic-chatmate.fresh.v1";

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function records(value: unknown) {
  return Array.isArray(value)
    ? value.map(record).filter((item): item is Record<string, unknown> => Boolean(item))
    : [];
}

function isApplicableProfile(
  profile: { id: string; applicability: string; target_profile_ids: string[]; scenario_ids: string[]; target_applicability?: Record<string, { applicability: string }> },
  target: DeepTeamCatalog["target_profiles"][number] | undefined,
) {
  const targetDetail = target && profile.target_applicability?.[target.id];
  const registered = target && ("turn_mode" in profile
    ? !target.attack_profile_ids || target.attack_profile_ids.includes(profile.id)
    : !target.vulnerability_profile_ids || target.vulnerability_profile_ids.includes(profile.id));
  return Boolean(
    target &&
    registered &&
    profile.applicability === "APPLICABLE" &&
    profile.target_profile_ids.includes(target.id) &&
    profile.scenario_ids.includes(target.scenario_id) &&
    targetDetail?.applicability !== "NOT_APPLICABLE",
  );
}

function isSelectableProfile(
  catalog: DeepTeamCatalog,
  profile: DeepTeamCatalog["attack_profiles"][number] | DeepTeamCatalog["vulnerability_profiles"][number],
  target: DeepTeamCatalog["target_profiles"][number] | undefined,
) {
  if (target?.id !== SYNTHETIC_CHATMATE_TARGET_ID) return isApplicableProfile(profile, target);
  const projection = target.experimental_catalog_projection;
  const projectedIds = "turn_mode" in profile
    ? projection?.attack_profile_ids
    : projection?.vulnerability_profile_ids;
  const admission = profile.target_experimental_admission?.[target.id];
  return catalog.schema_version === "2.3" && projection?.admission === "EXPERIMENTAL"
    && projectedIds?.includes(profile.id) === true
    && admission?.admission === "ADMITTED" && admission.selectable === true;
}

function assessmentStatusLabel(run: DeepTeamRunRecord) {
  if (run.status === "QUEUED") return "Waiting to start";
  if (run.status === "RUNNING") return "Assessment in progress";
  if (run.status === "CANCEL_REQUESTED") return "Stopping assessment";
  if (run.status === "CANCELLED") return "Assessment cancelled";
  if (run.status === "FAILED" || run.final_status === "ERROR") return "Assessment incomplete";
  if (run.final_status === "COMPROMISED") return "Policy violation found";
  if (run.final_status === "INCONCLUSIVE") return "Inconclusive";
  if (run.final_status === "RESISTED") return "No policy violation found";
  return run.status.replaceAll("_", " ").toLowerCase();
}

export function DeepTeamAssessmentPanel() {
  const [catalog, setCatalog] = useState<DeepTeamCatalog | null>(null);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [selectedTargetId, setSelectedTargetId] = useState("");
  const [selectedAttackId, setSelectedAttackId] = useState("");
  const [selectedVulnerabilityId, setSelectedVulnerabilityId] = useState("");
  const [category, setCategory] = useState("");
  const [turnMode, setTurnMode] = useState<"SINGLE" | "MULTI">("SINGLE");
  const [executionMode, setExecutionMode] = useState<"SINGLE" | "ADAPTIVE">("ADAPTIVE");
  const [maxTotalTokens, setMaxTotalTokens] = useState(75_000);
  const [run, setRun] = useState<DeepTeamRunRecord | null>(null);
  const [audit, setAudit] = useState<DeepTeamAuditReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [recovering, setRecovering] = useState(() => Boolean(window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY)));
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const [recoveryError, setRecoveryError] = useState("");
  const mountedRef = useRef(true);
  const activeRunIdRef = useRef<string | null>(null);
  const catalogVersionRef = useRef(0);
  const launchPendingRef = useRef(false);
  const restoredConfigurationRef = useRef(false);
  // Async refreshes must reconcile the latest operator selection, not the
  // render that originally started polling a run.
  const selectionRef = useRef({ selectedTargetId, selectedAttackId, selectedVulnerabilityId, category, turnMode });
  selectionRef.current = { selectedTargetId, selectedAttackId, selectedVulnerabilityId, category, turnMode };

  const forgetMissingRun = (runId: string, reason: unknown) => {
    if (!(reason instanceof ModelConnectivityError) || ![404, 410].includes(reason.status)
        || reason.path !== `/deepteam-runs/${encodeURIComponent(runId)}`
        || activeRunIdRef.current !== runId || window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY) !== runId) return false;
    removeSavedDeepTeamRunId(runId);
    activeRunIdRef.current = null;
    setRun(null);
    setAudit(null);
    setRecovering(false);
    setRecoveryError("");
    return true;
  };

  const loadCatalog = async () => {
    const version = ++catalogVersionRef.current;
    setLoading(true);
    setError("");
    // Quota diagnostics may time out; they must not hold the local catalog hostage.
    setProviders([]);
    void modelConnectivityService.getProviderStatus().then((status) => {
      if (mountedRef.current && version === catalogVersionRef.current) setProviders(Array.isArray(status) ? status : []);
    }).catch(() => {
      if (mountedRef.current && version === catalogVersionRef.current) setProviders([]);
    });
    const [catalogResult, capabilityResult] = await Promise.allSettled([
      modelConnectivityService.getDeepTeamCatalog(),
      modelConnectivityService.getPlatformCapabilities(),
    ]);
    if (!mountedRef.current || version !== catalogVersionRef.current) return;
    if (catalogResult.status === "fulfilled") {
      const nextCatalog = catalogResult.value;
      const current = selectionRef.current;
      const defaultTarget = nextCatalog.target_profiles.find(target => target.id === current.selectedTargetId) ?? nextCatalog.target_profiles.find(
        (target) => target.id === SOCMATE_TARGET_ID,
      );
       const defaultVulnerability = nextCatalog.vulnerability_profiles.find(profile => profile.id === current.selectedVulnerabilityId && isSelectableProfile(nextCatalog, profile, defaultTarget))
        ?? nextCatalog.vulnerability_profiles.find(profile => profile.category === current.category && isSelectableProfile(nextCatalog, profile, defaultTarget))
        ?? nextCatalog.vulnerability_profiles.find(
          (profile) => profile.id === "ExcessiveAgency:permissions" && isSelectableProfile(nextCatalog, profile, defaultTarget),
        ) ?? nextCatalog.vulnerability_profiles.find((profile) => isSelectableProfile(nextCatalog, profile, defaultTarget));
      const defaultAttack = nextCatalog.attack_profiles.find(profile => profile.id === current.selectedAttackId && isSelectableProfile(nextCatalog, profile, defaultTarget))
        ?? (current.selectedAttackId ? nextCatalog.attack_profiles.find(profile => profile.turn_mode === current.turnMode && isSelectableProfile(nextCatalog, profile, defaultTarget)) : undefined)
        ?? nextCatalog.attack_profiles.find(
          (profile) => profile.id === "permission-escalation-v1" && isSelectableProfile(nextCatalog, profile, defaultTarget),
        ) ?? nextCatalog.attack_profiles.find((profile) => isSelectableProfile(nextCatalog, profile, defaultTarget));
      setCatalog(nextCatalog);
      setSelectedTargetId(defaultTarget?.id ?? "");
      setSelectedVulnerabilityId(defaultVulnerability?.id ?? "");
      setSelectedAttackId(defaultAttack?.id ?? "");
      setCategory(defaultVulnerability?.category ?? "");
      setTurnMode(defaultAttack?.turn_mode ?? "SINGLE");
    } else {
      setCatalog(null);
      setError(
        catalogResult.reason instanceof Error
          ? catalogResult.reason.message
          : "Assessment catalog is unavailable.",
      );
    }
    const nextCapabilities = capabilityResult.status === "fulfilled" ? capabilityResult.value : null;
    setCapabilities(nextCapabilities);
    if (!nextCapabilities?.deepteam_worker.supported_execution_modes?.includes("ADAPTIVE")) {
      setExecutionMode("SINGLE");
    }
    setLoading(false);
  };

  useEffect(() => {
    let disposed = false;
    mountedRef.current = true;
    void loadCatalog();
    const savedRunId = window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY);
    let recoveryTimer = 0;
    let recoveryAttempts = 0;
    if (savedRunId) {
      activeRunIdRef.current = savedRunId;
      const recover = async () => {
        try {
          const record = await modelConnectivityService.getDeepTeamRun(savedRunId);
          if (disposed || !mountedRef.current || activeRunIdRef.current !== savedRunId
              || window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY) !== savedRunId) return;
          if (record.run_id !== savedRunId) throw new Error("The saved assessment response does not match the requested run.");
          setRun(record);
          setRecovering(false);
          setRecoveryError("");
          if (record.artifact_available) {
            const report = await modelConnectivityService.getDeepTeamAudit(savedRunId);
            if (!disposed && mountedRef.current && activeRunIdRef.current === savedRunId
                && window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY) === savedRunId) {
              if (report.run_id !== savedRunId) throw new Error("The saved assessment evidence does not match the requested run.");
              setAudit(report);
            }
          }
        } catch (reason) {
          if (disposed || !mountedRef.current || activeRunIdRef.current !== savedRunId
              || window.localStorage.getItem(ACTIVE_DEEPTEAM_RUN_KEY) !== savedRunId) return;
          if (forgetMissingRun(savedRunId, reason)) return;
          setRecoveryError(
            reason instanceof Error
              ? reason.message
              : "Unable to reconnect to the saved assessment run.",
          );
          recoveryAttempts += 1;
          if (recoveryAttempts < 5) {
            recoveryTimer = window.setTimeout(() => void recover(), 1000);
          }
        }
      };
      void recover();
    }
    else setRecovering(false);
    return () => {
      disposed = true;
      mountedRef.current = false;
      catalogVersionRef.current += 1;
      window.clearTimeout(recoveryTimer);
    };
  }, []);

  useEffect(() => {
    if (!catalog || !run || restoredConfigurationRef.current || activeRunIdRef.current !== run.run_id) return;
    const target = catalog.target_profiles.find(item => item.id === run.target_profile_id);
    const vulnerability = catalog.vulnerability_profiles.find(profile => profile.id === run.vulnerability_profile_id && isSelectableProfile(catalog, profile, target));
    const attack = catalog.attack_profiles.find(profile => profile.id === run.attack_profile_id && isSelectableProfile(catalog, profile, target));
    restoredConfigurationRef.current = true;
    if (!target || !vulnerability || !attack) return;
    setSelectedTargetId(target.id);
    setSelectedVulnerabilityId(vulnerability.id);
    setCategory(vulnerability.category);
    setSelectedAttackId(attack.id);
    setTurnMode(attack.turn_mode);
    setExecutionMode(run.execution_mode);
    setMaxTotalTokens(run.max_total_tokens);
  }, [catalog, run?.run_id]);

  useEffect(() => {
    if (!run || !["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(run.status)) return;
    let disposed = false;
    let timer = 0;
    const runId = run.run_id;
    const poll = async () => {
      try {
        const next = await modelConnectivityService.getDeepTeamRun(runId);
        if (disposed || activeRunIdRef.current !== runId) return;
        if (next.run_id !== runId) throw new Error("The assessment response does not match the requested run.");
        setRun(next);
        setRecoveryError("");
        if (["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(next.status)) {
          timer = window.setTimeout(() => void poll(), 500);
        } else if (next.artifact_available) {
          const report = await modelConnectivityService.getDeepTeamAudit(next.run_id);
          if (!disposed && activeRunIdRef.current === runId) {
            if (report.run_id !== runId) throw new Error("The assessment evidence does not match the requested run.");
            setAudit(report);
            void loadCatalog();
          }
        } else {
          void loadCatalog();
        }
      } catch (reason) {
        if (!disposed && activeRunIdRef.current === runId) {
          if (forgetMissingRun(runId, reason)) return;
          setRecoveryError(
            reason instanceof Error
              ? reason.message
              : "Unable to refresh the assessment run.",
          );
          timer = window.setTimeout(() => void poll(), 1000);
        }
      }
    };
    timer = window.setTimeout(() => void poll(), 500);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [run?.run_id]);

  const selectedTarget = catalog?.target_profiles.find(
    (target) => target.id === selectedTargetId,
  );
  const applicableVulnerabilities = catalog?.vulnerability_profiles.filter(
    (profile) => isSelectableProfile(catalog, profile, selectedTarget),
  ) ?? [];
  const categories = [...new Set(applicableVulnerabilities.map((profile) => profile.category))];
  const vulnerabilities = applicableVulnerabilities.filter(
    (profile) => profile.category === category,
  );
  const attacks = catalog?.attack_profiles.filter(
    (profile) => profile.turn_mode === turnMode && isSelectableProfile(catalog, profile, selectedTarget),
  ) ?? [];
  const availableTurnModes = new Set(
    catalog?.attack_profiles
      .filter((profile) => isSelectableProfile(catalog, profile, selectedTarget))
      .map((profile) => profile.turn_mode) ?? [],
  );
  const selectedAttack = attacks.find(
    (profile) => profile.id === selectedAttackId,
  );
  const selectedVulnerability = vulnerabilities.find(
    (profile) => profile.id === selectedVulnerabilityId,
  );
  const selectionKnown = Boolean(catalog && selectedAttack && selectedVulnerability
    && isSelectableProfile(catalog, selectedAttack, selectedTarget)
    && isSelectableProfile(catalog, selectedVulnerability, selectedTarget));
  const runActive = Boolean(run && ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(run.status));
  const backendAvailable =
    capabilities?.deepteam_worker.state === "AVAILABLE" &&
    capabilities.deepteam_worker.api_connected;
  const providerReady = capabilities?.model_connectivity.state === "AVAILABLE"
    && capabilities.model_connectivity.live_tests_supported;
  const targetModes = selectedTarget?.execution_modes ?? capabilities?.deepteam_worker.supported_execution_modes ?? ["SINGLE"];
  const expandedVisible = targetModes.includes("ADAPTIVE");
  const adaptiveSupported = expandedVisible && (selectedTarget?.max_paths ?? capabilities?.deepteam_worker.max_paths ?? 0) >= 2
    && capabilities?.deepteam_worker.supported_execution_modes?.includes("ADAPTIVE");
  const cancellationSupported = capabilities?.deepteam_worker.cancellation_supported === true;
  const groqQuota = providers.find((provider) => provider.provider === "GROQ")?.quota;
  const openRouterQuota = providers.find(
    (provider) => provider.provider === "OPENROUTER",
  )?.quota;
  const quotaValue = (value: number | null | undefined) =>
    value === null || value === undefined ? "Not reported" : value.toLocaleString();
  const baseEstimatedTokens = selectedAttack
    ? selectedAttack.turn_mode === "SINGLE"
      ? 12_000
      : Math.max(50_000, selectedAttack.max_turns * 17_000)
    : 0;
  const baseEstimatedGroqCalls = selectedAttack
    ? selectedAttack.turn_mode === "SINGLE"
      ? 6
      : selectedAttack.max_turns * 6 + 3
    : 0;
  const baseEstimatedOpenRouterCalls = selectedAttack
    ? selectedAttack.turn_mode === "SINGLE"
      ? selectedTarget?.id === SOCMATE_TARGET_ID ? 2 : 1
      : selectedAttack.max_turns
    : 0;
  const effectiveExecutionMode = targetModes.includes(executionMode) ? executionMode : "SINGLE";
  const maxPaths = effectiveExecutionMode === "ADAPTIVE" ? 2 : 1;
  const estimatedTokens = effectiveExecutionMode === "ADAPTIVE"
    ? baseEstimatedTokens * 2 + 4_000
    : baseEstimatedTokens;
  const estimatedGroqCalls = effectiveExecutionMode === "ADAPTIVE"
    ? baseEstimatedGroqCalls * 2 + 1
    : baseEstimatedGroqCalls;
  const estimatedOpenRouterCalls = effectiveExecutionMode === "ADAPTIVE"
    ? baseEstimatedOpenRouterCalls * 2
    : baseEstimatedOpenRouterCalls;
  const budgetLikelySufficient = maxTotalTokens >= estimatedTokens;
  const possibleRuns = [
    groqQuota?.requests_remaining == null || !estimatedGroqCalls
      ? null
      : Math.floor(groqQuota.requests_remaining / estimatedGroqCalls),
    openRouterQuota?.requests_remaining == null || !estimatedOpenRouterCalls
      ? null
      : Math.floor(openRouterQuota.requests_remaining / estimatedOpenRouterCalls),
    groqQuota?.tokens_remaining == null || !estimatedTokens
      ? null
      : Math.floor(groqQuota.tokens_remaining / Math.ceil(estimatedTokens * 0.8)),
  ].filter((value): value is number => value !== null);
  const estimatedRunsRemaining = possibleRuns.length
    ? Math.max(0, Math.min(...possibleRuns))
    : null;
  const canLaunch = Boolean(
    catalog &&
      selectedAttack &&
      selectedVulnerability &&
      selectionKnown &&
      backendAvailable &&
      providerReady &&
      budgetLikelySufficient &&
      (effectiveExecutionMode === "SINGLE" || adaptiveSupported) &&
      !loading && !starting &&
      !runActive && !recovering,
  );
  const auditBudget = record(audit?.summary.budget);
  const actualTokens = typeof auditBudget?.tokens_consumed === "number"
    ? auditBudget.tokens_consumed
    : null;
  const runTokenLimit = typeof auditBudget?.max_total_tokens === "number"
    ? auditBudget.max_total_tokens
    : run?.max_total_tokens ?? maxTotalTokens;
  const tokensRemaining = actualTokens === null
    ? null
    : Math.max(0, runTokenLimit - actualTokens);
  const tokenUsagePercent = actualTokens === null || runTokenLimit === 0
    ? 0
    : Math.min(100, Math.round((actualTokens / runTokenLimit) * 100));
  const providerCallsAttempted = typeof auditBudget?.provider_calls_attempted === "number"
    ? auditBudget.provider_calls_attempted
    : null;
  const maxProviderCalls = typeof auditBudget?.max_provider_calls === "number"
    ? auditBudget.max_provider_calls
    : null;
  const callsWithMissingUsage = typeof auditBudget?.calls_with_missing_usage === "number"
    ? auditBudget.calls_with_missing_usage
    : null;
  const tokenBudgetOverrun = auditBudget?.token_budget_overrun === true;
  const rateLimitFailures = records(audit?.summary.model_attempts).filter(
    (attempt) => attempt.error_code === "RATE_LIMITED",
  ).length;
  const modelAttempts = records(audit?.summary.model_attempts);

  const selectCategory = (nextCategory: string) => {
    setCategory(nextCategory);
    const profiles = catalog?.vulnerability_profiles.filter(
      (profile) => profile.category === nextCategory && catalog && isSelectableProfile(catalog, profile, selectedTarget),
    ) ?? [];
    const first = profiles[0];
    setSelectedVulnerabilityId(first?.id ?? "");
  };

  const selectTurnMode = (nextMode: "SINGLE" | "MULTI") => {
    setTurnMode(nextMode);
    const profiles = catalog?.attack_profiles.filter(
      (profile) => profile.turn_mode === nextMode && catalog && isSelectableProfile(catalog, profile, selectedTarget),
    ) ?? [];
    const first = profiles[0];
    setSelectedAttackId(first?.id ?? "");
  };

  const selectTarget = (targetId: string) => {
    if (!catalog) return;
    const target = catalog.target_profiles.find((item) => item.id === targetId);
    if (!target) return;
    const preferredVulnerabilityId = target.id === SOCMATE_TARGET_ID
      ? "ExcessiveAgency:permissions"
      : target.id === SYNTHETIC_CHATMATE_TARGET_ID
        ? "DirectPromptInjection:direct_user_instruction"
        : undefined;
    const preferredAttackId = target.id === SOCMATE_TARGET_ID
      ? "permission-escalation-v1"
      : "prompt-injection-v1";
    const vulnerability = catalog.vulnerability_profiles.find(
      (profile) => profile.id === preferredVulnerabilityId && isSelectableProfile(catalog, profile, target),
    ) ?? catalog.vulnerability_profiles.find((profile) => isSelectableProfile(catalog, profile, target));
    const attack = catalog.attack_profiles.find(
      (profile) => profile.id === preferredAttackId && isSelectableProfile(catalog, profile, target),
    ) ?? catalog.attack_profiles.find((profile) => isSelectableProfile(catalog, profile, target));
    setSelectedTargetId(target.id);
    setSelectedVulnerabilityId(vulnerability?.id ?? "");
    setCategory(vulnerability?.category ?? "");
    setSelectedAttackId(attack?.id ?? "");
    setTurnMode(attack?.turn_mode ?? "SINGLE");
    const modes = target.execution_modes ?? capabilities?.deepteam_worker.supported_execution_modes ?? ["SINGLE"];
    setExecutionMode(current => modes.includes(current) ? current : "SINGLE");
  };

  const launch = async () => {
    if (launchPendingRef.current || !canLaunch || !catalog || !selectedTarget || !selectedAttack || !selectedVulnerability) return;
    launchPendingRef.current = true;
    setStarting(true);
    setError("");
    setRecoveryError("");
    setAudit(null);
    try {
      const selection = {
        scenario_id: selectedTarget.scenario_id,
        target_profile_id: selectedTarget.id,
        attack_profile_id: selectedAttack.id,
        vulnerability_profile_id: selectedVulnerability.id,
        max_total_tokens: maxTotalTokens,
        execution_mode: effectiveExecutionMode,
        max_paths: maxPaths,
      } as const;
      const operation = operationKey(`launch.${selectedTarget.id}.${selectedAttack.id}.${selectedVulnerability.id}.${effectiveExecutionMode}.${maxPaths}.${maxTotalTokens}`);
      const next = await modelConnectivityService.startDeepTeamRun(selection, operation.key);
      if (next.scenario !== selection.scenario_id || next.target_profile_id !== selection.target_profile_id
          || next.attack_profile_id !== selection.attack_profile_id || next.vulnerability_profile_id !== selection.vulnerability_profile_id
          || next.max_total_tokens !== selection.max_total_tokens || next.execution_mode !== selection.execution_mode
          || next.max_paths !== selection.max_paths) {
        throw new Error("The started assessment response does not match the requested configuration.");
      }
      operation.clear();
      activeRunIdRef.current = next.run_id;
      restoredConfigurationRef.current = true;
      saveDeepTeamRunId(next.run_id);
      if (mountedRef.current) {
        setRun(next);
      }
      if (next.artifact_available) {
        const report = await modelConnectivityService.getDeepTeamAudit(next.run_id);
        if (mountedRef.current && activeRunIdRef.current === next.run_id) {
          setAudit(report);
        }
      }
    } catch (reason) {
      if (mountedRef.current) {
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to start the assessment run.",
        );
      }
    } finally {
      launchPendingRef.current = false;
      if (mountedRef.current) setStarting(false);
    }
  };

  const cancel = async () => {
    if (!run || !["QUEUED", "RUNNING"].includes(run.status)) return;
    setCancelling(true);
    setError("");
    try {
      const next = await modelConnectivityService.cancelDeepTeamRun(run.run_id);
      if (mountedRef.current) setRun(next);
    } catch (reason) {
      if (mountedRef.current) setError(reason instanceof Error ? reason.message : "Unable to cancel the assessment.");
    } finally {
      if (mountedRef.current) setCancelling(false);
    }
  };

  return (
    <section className="deepteam-assessment" aria-labelledby="live-assessment-heading">
      <header className="deepteam-header">
        <div>
          <h2 id="live-assessment-heading">Set up assessment</h2>
          <p>Choose what to test and how thoroughly to test it.</p>
        </div>
        <div
          className={`deepteam-availability ${backendAvailable ? "available" : "unavailable"}`}
          role="status"
        >
          <i aria-hidden="true" />
          <span>Service</span>
          <strong>{loading ? "Checking" : backendAvailable ? "Configured" : "Unavailable"}</strong>
        </div>
      </header>
      <div className="deepteam-boundary" role="note">
        <strong>Safe test environment</strong>
      </div>
      {loading && !catalog && (
        <div className="deepteam-state" aria-live="polite">
          Loading live assessment catalog...
        </div>
      )}
      {(error || recoveryError) && (
        <div className="inline-error" role="alert">
          {error || recoveryError}{" "}
          {!catalog && (
            <button type="button" onClick={() => void loadCatalog()}>
              Retry
            </button>
          )}
        </div>
      )}
      {catalog && (
        <>
          <div className="deepteam-selector-grid">
            <fieldset className="console-config-group"><legend>Target and policy boundary</legend>
            <AssessmentSelect label="Target" value={selectedTargetId} onChange={selectTarget}
              options={catalog.target_profiles.filter(target => [SOCMATE_TARGET_ID, SYNTHETIC_CHATMATE_TARGET_ID].includes(target.id)).map(target => ({ value: target.id, label: target.id === SYNTHETIC_CHATMATE_TARGET_ID ? targetDisplayName(target.id) : target.name }))} />
            <AssessmentSelect label="Risk area" value={category} onChange={selectCategory}
              options={categories.map(item => ({ value: item, label: item }))} />
            <AssessmentSelect label="Security risk" value={selectedVulnerabilityId} onChange={setSelectedVulnerabilityId}
              options={vulnerabilities.map(profile => ({ value: profile.id, label: profile.name }))} />
            <AssessmentSelect label="Test length" value={turnMode} onChange={value => selectTurnMode(value as "SINGLE" | "MULTI")}
              options={[...(availableTurnModes.has("SINGLE") ? [{ value: "SINGLE", label: "One step" }] : []),
                ...(availableTurnModes.has("MULTI") ? [{ value: "MULTI", label: "Multiple steps" }] : [])]} />
            </fieldset>
            <fieldset className="console-config-group"><legend>Test method and usage</legend>
            <AssessmentSelect label="Test method" value={selectedAttackId} onChange={setSelectedAttackId}
              options={attacks.map(profile => ({ value: profile.id, label: profile.name }))} />
            <AssessmentSelect label="Test coverage" value={effectiveExecutionMode} onChange={value => setExecutionMode(value as "SINGLE" | "ADAPTIVE")}
              options={[{ value: "SINGLE", label: "Standard" }, ...(expandedVisible ? [{ value: "ADAPTIVE", label: "Expanded", disabled: !adaptiveSupported }] : [])]} />
            <AssessmentSelect label="Usage limit" value={String(maxTotalTokens)} onChange={value => setMaxTotalTokens(Number(value))}
              options={TOKEN_BUDGET_OPTIONS.map(value => ({ value: String(value), label: `${value.toLocaleString()} tokens` }))} />
            </fieldset>
          </div>
           {expandedVisible && !adaptiveSupported && capabilities && <div className="campaign-budget-warning" role="status"><strong>Expanded coverage is temporarily unavailable.</strong><span>Use Standard coverage for this assessment.</span></div>}
           {effectiveExecutionMode === "ADAPTIVE" && adaptiveSupported && <div className="campaign-budget-warning" role="note"><strong>Expanded runs two independent fresh paths.</strong><span>Attack Critic guidance selects path 2 automatically. Each path starts fresh; no conversation continues between paths.</span></div>}
          {(selectedAttack || selectedVulnerability) && <details className="console-details"><summary>About the selected test</summary><div className="console-details-content"><h3>{selectedVulnerability?.name}</h3><p>{selectedVulnerability?.description}</p><h3>{selectedAttack?.name}</h3><p>{selectedAttack?.description}</p></div></details>}
          <section className="campaign-summary" aria-labelledby="campaign-summary-heading">
            <header>
              <div>
                <span>{canLaunch ? "Ready to start" : "Review setup"}</span>
                <h3 id="campaign-summary-heading">Review and start</h3>
              </div>
              <button
                className="primary-action"
                disabled={!canLaunch}
                type="button"
                onClick={() => void launch()}
              >
                 {starting
                   ? "Starting assessment..."
                   : recovering
                     ? "Recovering saved assessment..."
                  : runActive
                    ? "Assessment in progress..."
                    : "Start assessment"}
              </button>
            </header>
             <div className="campaign-summary-groups">
               <article>
                <span>Assessment</span>
                <dl>
                  <div><dt>Target</dt><dd>{selectedTarget ? targetDisplayName(selectedTarget.id) : "Not selected"}</dd></div>
                  <div><dt>Risk</dt><dd>{selectedVulnerability?.name ?? "Not selected"}</dd></div>
                  <div><dt>Method</dt><dd>{selectedAttack?.name ?? "Not selected"}</dd></div>
                  <div><dt>Coverage</dt><dd>{effectiveExecutionMode === "ADAPTIVE" ? "Expanded / up to 2 paths" : "Standard / 1 path"}</dd></div>
                  <div><dt>Test scope</dt><dd>1 case / up to {selectedAttack?.max_turns ?? 0} interaction{selectedAttack?.max_turns === 1 ? "" : "s"}</dd></div>
                </dl>
              </article>
               <article>
                 <span>Estimated usage</span>
                <strong>About {estimatedTokens.toLocaleString()} tokens</strong>
                <div className="campaign-budget-meter" role="progressbar" aria-label="Estimated usage" aria-valuemin={0} aria-valuemax={maxTotalTokens} aria-valuenow={Math.min(maxTotalTokens, estimatedTokens)}><i style={{ width: `${Math.min(100, Math.round((estimatedTokens / maxTotalTokens) * 100))}%` }} /></div>
                <p>{maxTotalTokens.toLocaleString()}-token maximum · {budgetLikelySufficient ? "Enough capacity" : "Choose a higher limit"}</p>
              </article>
               <article className="campaign-service-availability">
                 <span>Service availability</span>
                <dl>
                  <div><dt>Estimated AI requests</dt><dd>About {estimatedGroqCalls + estimatedOpenRouterCalls}</dd></div>
                  <div><dt>Assessments available</dt><dd>{estimatedRunsRemaining === null ? "Not reported" : `About ${estimatedRunsRemaining}`}</dd></div>
                </dl>
                <details className="campaign-service-details"><summary>Service details</summary><dl><div><dt>Attacker requests available</dt><dd>{quotaValue(groqQuota?.requests_remaining)}</dd></div><div><dt>Target and review requests available</dt><dd>{quotaValue(openRouterQuota?.requests_remaining)}</dd></div></dl></details>
              </article>
            </div>
            {!budgetLikelySufficient && <div className="campaign-budget-warning" role="alert"><strong>Choose a higher usage limit.</strong><span>This assessment needs about {estimatedTokens.toLocaleString()} tokens.</span></div>}
             {!selectionKnown && selectedAttackId && selectedVulnerabilityId && <div className="campaign-budget-warning" role="alert"><strong>This selection is no longer in the current catalog.</strong><span>Choose current risk and method IDs before starting.</span></div>}
          </section>
        </>
      )}
      {run && (
        <section className="assessment-run-panel" aria-labelledby="current-run-heading">
           <header aria-live="polite">
            <div>
              <h3 id="current-run-heading">{assessmentStatusLabel(run)}</h3>
              <small>{assessmentDisplayName(run.attack)} · {assessmentDisplayName(run.vulnerability)}</small>
            </div>
            {cancellationSupported && ["QUEUED", "RUNNING"].includes(run.status) && <button className="secondary-action" disabled={cancelling} type="button" onClick={() => void cancel()}>{cancelling ? "Stopping assessment..." : "Cancel assessment"}</button>}
           </header>
            <dl className="assessment-active-run-config" aria-label="Active run configuration"><div><dt>Target</dt><dd>{targetDisplayName(run.target_profile_id ?? selectedTarget?.id ?? SOCMATE_TARGET_ID)} v{run.target_profile_version ?? selectedTarget?.version ?? "Not reported"}</dd></div><div><dt>Scenario</dt><dd>{run.scenario} v{run.scenario_version ?? "Not reported"}</dd></div><div><dt>Method</dt><dd>{assessmentDisplayName(run.attack)}</dd></div><div><dt>Risk</dt><dd>{assessmentDisplayName(run.vulnerability)}</dd></div><div><dt>Coverage</dt><dd>{run.execution_mode === "ADAPTIVE" ? "Expanded" : "Standard"} / {run.max_paths} path{run.max_paths === 1 ? "" : "s"}</dd></div><div><dt>Usage limit</dt><dd>{run.max_total_tokens.toLocaleString()} tokens</dd></div></dl>
          {run.error_message && (
            <div className="inline-error" role="alert">
              <strong>Assessment issue</strong> {assessmentFailureMessage(run.error_message, modelAttempts)}
            </div>
          )}
          <section className="assessment-live-usage" aria-labelledby="live-usage-heading">
            <header>
              <div><span>Assessment usage</span><h4 id="live-usage-heading">Usage for this assessment</h4></div>
              <strong>{actualTokens === null ? (runActive ? "In progress" : "Waiting for usage") : `${tokenUsagePercent}% of limit used`}</strong>
            </header>
            <div className="assessment-token-meter" role="progressbar" aria-label="Assessment usage" aria-valuemin={0} aria-valuemax={runTokenLimit} aria-valuenow={actualTokens ?? 0}>
              <i style={{ width: `${tokenUsagePercent}%` }} />
            </div>
            <details className="assessment-run-details"><summary>Usage breakdown</summary>
            <dl>
              <div><dt>Tokens used</dt><dd>{actualTokens === null ? "Pending" : actualTokens.toLocaleString()}</dd></div>
              <div><dt>Assessment limit left</dt><dd>{tokenBudgetOverrun ? "Exceeded" : tokensRemaining === null ? runTokenLimit.toLocaleString() : tokensRemaining.toLocaleString()}</dd></div>
              <div><dt>AI requests</dt><dd>{providerCallsAttempted === null ? "Pending" : `${providerCallsAttempted}${maxProviderCalls === null ? "" : ` of ${maxProviderCalls} maximum`}`}</dd></div>
              <div><dt>Usage quality</dt><dd>{callsWithMissingUsage === null ? "Pending" : callsWithMissingUsage === 0 ? "Provider reported" : `Includes reserved-token estimates for ${callsWithMissingUsage} call${callsWithMissingUsage === 1 ? "" : "s"}`}</dd></div>
            </dl>
            <p className="assessment-pacing-note">Remaining usage applies only to this assessment. It is not your provider account balance.</p>
            {runActive && <p className="assessment-pacing-note">The assessment may pause briefly to stay within service limits.</p>}
            </details>
          </section>
          {rateLimitFailures > 0 && (
            <div className="assessment-failure-diagnosis" role="note">
              <strong>Why this run failed</strong>
              <p>
                The assessment could not be completed because an AI service limit was reached. No policy violation was confirmed.
              </p>
            </div>
          )}
          <details className="assessment-run-details"><summary>Activity log</summary><ol className="assessment-run-logs">{run.logs.map((entry) => (<li key={`${entry.timestamp}-${entry.message}`}><time>{new Date(entry.timestamp).toLocaleTimeString()}</time><span>{entry.message}</span></li>))}</ol></details>
          {audit && (
            <div className="assessment-complete-banner" role="status">
              <div className="assessment-complete-summary">
                <SocMateScoreSummary audit={audit} />
                <strong className="assessment-complete-outcome">{assessmentStatusLabel(run)}</strong>
              </div>
              <Link className="primary-action" to={`/reports?live=${encodeURIComponent(run.run_id)}`}>
                View results
              </Link>
            </div>
          )}
           {audit && <StandardReviewPanel key={run.run_id} run={run} />}
        </section>
      )}
    </section>
  );
}
