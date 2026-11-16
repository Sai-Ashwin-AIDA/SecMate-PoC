import { useEffect, useState } from "react";
import { modelConnectivityService } from "./modelConnectivityService";
import type {
  AdaptiveHandoffResult,
  ModelProfile,
  ModelTestResult,
  PlatformCapabilities,
  ProviderStatus,
} from "./modelConnectivityService";

const roleLabels: Record<ModelProfile["role"], string> = {
  ATTACKER: "Attacker",
  ATTACK_CRITIC: "Attack Critique",
  OUTCOME_JUDGE: "Judge",
  TARGET: "Target",
};

function quotaText(status: ProviderStatus) {
  if (!status.quota) return "Quota details unavailable";
  const requests = status.quota.requests_remaining === null
    ? "Requests unavailable"
    : `${status.quota.requests_remaining.toLocaleString()} requests remaining`;
  const tokens = status.quota.tokens_remaining === null
    ? null
    : `${status.quota.tokens_remaining.toLocaleString()} tokens remaining`;
  return [requests, tokens].filter(Boolean).join(" / ");
}

function providerState(status: ProviderStatus) {
  if (!status.configured) return "Not configured";
  return status.reachable ? "Reachable" : "Configured, unreachable";
}

export function ModelConnectivitySection() {
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [results, setResults] = useState<Record<string, ModelTestResult>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [capabilityError, setCapabilityError] = useState("");
  const [workflowTesting, setWorkflowTesting] = useState(false);
  const [workflowResult, setWorkflowResult] = useState<AdaptiveHandoffResult | null>(null);
  const [workflowError, setWorkflowError] = useState("");

  const load = async () => {
    setLoading(true);
    setLoadError("");
    setCapabilityError("");
    const [capabilityResult, profileResult, providerResult] = await Promise.allSettled([
        modelConnectivityService.getPlatformCapabilities(),
        modelConnectivityService.listProfiles(),
        modelConnectivityService.getProviderStatus(),
    ]);
    if (capabilityResult.status === "fulfilled") setCapabilities(capabilityResult.value);
    else { setCapabilities(null); setCapabilityError("Capability metadata is unavailable. Live diagnostics may still work."); }
    if (profileResult.status === "fulfilled") setProfiles(profileResult.value);
    else setProfiles([]);
    if (providerResult.status === "fulfilled") setProviders(providerResult.value);
    else setProviders([]);
    if (profileResult.status === "rejected" || providerResult.status === "rejected") {
      const reason = profileResult.status === "rejected" ? profileResult.reason : providerResult.status === "rejected" ? providerResult.reason : null;
      const scope = profileResult.status === "rejected" && providerResult.status === "rejected"
        ? "Live model diagnostics are unavailable."
        : "Some live diagnostic data is unavailable.";
      setLoadError(`${scope} ${reason instanceof Error ? reason.message : "Retry the local API."}`);
    }
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const testProfile = async (profile: ModelProfile) => {
    setTesting((current) => [...current, profile.id]);
    setErrors((current) => ({ ...current, [profile.id]: "" }));
    setResults((current) => { const next = { ...current }; delete next[profile.id]; return next; });
    try {
      const result = await modelConnectivityService.testProfile(profile.id);
      setResults((current) => ({ ...current, [profile.id]: result }));
      if (result.quota) {
        setProviders((current) => current.map((provider) => provider.provider === result.provider ? { ...provider, quota: result.quota } : provider));
      }
    } catch (reason) {
      setErrors((current) => ({ ...current, [profile.id]: reason instanceof Error ? reason.message : "Model test failed." }));
    } finally {
      setTesting((current) => current.filter((id) => id !== profile.id));
    }
  };

  const diagnosticsAvailable = capabilities
    ? capabilities.model_connectivity.state === "AVAILABLE" && capabilities.model_connectivity.live_tests_supported
    : profiles.length > 0 && providers.length > 0 && !loadError;

  const testAll = async () => {
    for (const profile of profiles) await testProfile(profile);
    void load();
  };

  const testAdaptiveHandoff = async () => {
    setWorkflowTesting(true);
    setWorkflowError("");
    setWorkflowResult(null);
    try {
      setWorkflowResult(await modelConnectivityService.testAdaptiveHandoff());
      void load();
    } catch (reason) {
      setWorkflowError(reason instanceof Error ? reason.message : "Adaptive handoff test failed.");
    } finally {
      setWorkflowTesting(false);
    }
  };

  return (
    <div className="settings-detail model-connectivity">
      <header>
        <span className="placeholder-badge">Enterprise administration</span>
        <h2>AI runtime and provider health</h2>
        <p>Inspect provider reachability, approved model profiles, worker capability metadata, and adaptive routing diagnostics.</p>
      </header>

      {loading && profiles.length === 0 && <div className="model-connectivity-state" aria-live="polite">Connecting to the local SecMate API...</div>}
      {loadError && <div className="model-connectivity-state warning" role="alert"><strong>Diagnostics partially unavailable</strong><span>{loadError}</span><button type="button" onClick={() => void load()}>Retry</button></div>}
      {capabilityError && <div className="model-connectivity-state warning" role="status"><strong>Capability metadata unavailable</strong><span>{capabilityError}</span></div>}

      {capabilities && <section className="capability-status-grid" aria-label="Platform capability status">
        <article>
          <span>Live API response</span>
          <strong>Model connectivity</strong>
          <b className={`capability-state ${capabilities.model_connectivity.state.toLowerCase()}`}>{capabilities.model_connectivity.state.replaceAll("_", " ")}</b>
        </article>
        <article>
          <span>Worker</span>
          <strong>Assessment runtime</strong>
          <b className={`capability-state ${capabilities.deepteam_worker.state.toLowerCase()}`}>{capabilities.deepteam_worker.state.replaceAll("_", " ")}</b>
          {!capabilities.deepteam_worker.api_connected && <p>Worker is not connected.</p>}
        </article>
      </section>}

      {capabilities && <details><summary>Worker details</summary><section className="worker-verification-card" aria-label="DeepTeam worker health">
        <header><div><span>Worker capability summary</span><h3>DeepTeam assessment runtime</h3><p>Review the installed engine, verified bounds, and last known outcome. Campaign selection and launch controls are available in Assessments.</p></div><strong className={`worker-result ${capabilities.deepteam_worker.last_verified_result.toLowerCase()}`}>{capabilities.deepteam_worker.last_verified_result}</strong></header>
        <dl>
          <div><dt>Verified</dt><dd>{new Date(capabilities.deepteam_worker.verified_at).toLocaleString()}</dd></div>
          <div><dt>Engine</dt><dd>DeepTeam {capabilities.deepteam_worker.deepteam_version} / DeepEval {capabilities.deepteam_worker.deepeval_version}</dd></div>
          <div><dt>Revision</dt><dd>{capabilities.deepteam_worker.deepteam_commit.slice(0, 12)}</dd></div>
          <div><dt>Coverage</dt><dd>{capabilities.deepteam_worker.supported_vulnerabilities.join(", ")} / {capabilities.deepteam_worker.supported_attacks.length} attack profiles</dd></div>
          <div><dt>Verified bounds</dt><dd>{capabilities.deepteam_worker.max_verified_cases} case / {capabilities.deepteam_worker.max_verified_turns} turn</dd></div>
          <div><dt>Judge</dt><dd>{capabilities.deepteam_worker.last_deviation_category.replaceAll("_", " ")} / {capabilities.deepteam_worker.last_deviation_score} score / {Math.round(capabilities.deepteam_worker.last_evaluator_confidence * 100)}% confidence</dd></div>
          <div><dt>Invocation</dt><dd>{capabilities.deepteam_worker.invocation.replaceAll("_", " ")}</dd></div>
        </dl>
      </section></details>}

      <div className="settings-subsection-heading"><h3>Provider and model health</h3></div>

      {providers.length > 0 && <section className="provider-status-grid" aria-label="Provider status">{providers.map((provider) => <article key={provider.provider}><div><span className={`connection-dot ${provider.reachable ? "online" : "offline"}`} aria-hidden="true" /><strong>{provider.provider === "GROQ" ? "Groq Cloud" : "OpenRouter"}</strong><em>{providerState(provider)}</em></div><p>{provider.detail}</p><small>{quotaText(provider)}</small></article>)}</section>}

      {profiles.length > 0 && <div className="model-connectivity-actions"><button disabled={!diagnosticsAvailable || testing.length > 0} type="button" onClick={() => void testAll()}>{testing.length > 0 ? `Testing ${testing.length} model${testing.length === 1 ? "" : "s"}...` : "Test all API profiles"}</button><span>Live API response / sequential to respect provider quotas</span></div>}
      <details><summary>Routing diagnostics</summary>

      {profiles.length > 0 && <section className="adaptive-handoff-panel"><header><div><span>Diagnostic adaptive handoff</span><h3>Run fixed three-turn routing check</h3><p>The connectivity API routes synthetic Attacker, Target, Judge, and Critic outputs in memory. This is not the durable worker broker or a DeepTeam Assessment.</p></div><button disabled={!diagnosticsAvailable || workflowTesting || testing.length > 0} type="button" onClick={() => void testAdaptiveHandoff()}>{workflowTesting ? "Running handoff..." : "Run diagnostic handoff"}</button></header>{workflowError && <div className="inline-error" role="alert">{workflowError}</div>}{workflowResult && <div className="adaptive-handoff-result" role="status"><div className="adaptive-handoff-summary"><span>{workflowResult.turns_completed} / {workflowResult.max_turns} turns</span><strong>{workflowResult.stop_reason.replaceAll("_", " ")}</strong></div><div className="adaptive-turn-list">{workflowResult.turns.map((turn) => <article key={turn.turn}><header><span>Turn {turn.turn}</span><strong>{turn.judge?.verdict.replaceAll("_", " ") ?? turn.deterministic_check.outcome.replaceAll("_", " ")}</strong></header><dl><div><dt>Attacker probe</dt><dd>{turn.attacker.probe}</dd></div><div><dt>Target response</dt><dd>{turn.target.response_text ?? (turn.target.tool_attempts.length ? "Structured tool attempt captured" : "No text response")}</dd></div><div><dt>Deterministic check</dt><dd>{turn.deterministic_check.detail}</dd></div>{turn.judge && <div><dt>Judge</dt><dd>{turn.judge.concise_rationale} ({Math.round(turn.judge.confidence * 100)}% confidence)</dd></div>}{turn.critic && <div><dt>Critic adaptation</dt><dd>{turn.critic.recommended_adaptation}</dd></div>}</dl>{turn.target.tool_attempts.length > 0 && <pre>{JSON.stringify(turn.target.tool_attempts, null, 2)}</pre>}</article>)}</div></div>}</section>}

      </details>
      <section className="model-profile-grid" aria-label="Connectivity API profiles">{profiles.map((profile) => {
        const result = results[profile.id];
        const error = errors[profile.id];
        const isTesting = testing.includes(profile.id);
        const failed = Boolean(error) || result?.status === "FAIL";
        const passed = result?.status === "PASS";
        return <article className="model-profile-card" key={profile.id}><header><div><span>Model role</span><h3>{roleLabels[profile.role]}</h3></div><span aria-live="polite" className={`model-test-status ${failed ? "failed" : passed ? "passed" : "untested"}`}>{failed ? "Diagnostic failed" : passed ? "Diagnostic passed" : "Not tested"}</span></header><dl><div><dt>Provider</dt><dd>{profile.provider === "GROQ" ? "Groq Cloud" : "OpenRouter"}</dd></div><div><dt>Model</dt><dd>{roleLabels[profile.role]}</dd></div><div><dt>Capabilities</dt><dd>{profile.capabilities.map((capability) => capability.replaceAll("_", " ")).join(", ")}</dd></div></dl><p>{profile.description}</p>{result && <div className="model-test-result"><div><strong>{result.summary}</strong><span>{result.latency_ms.toLocaleString()} ms{result.usage?.total_tokens ? ` / ${result.usage.total_tokens.toLocaleString()} tokens` : ""}</span></div><pre>{JSON.stringify(result.output, null, 2)}</pre></div>}{error && <div className="inline-error" role="alert">{error}</div>}<button disabled={!diagnosticsAvailable || isTesting || testing.length > 0} type="button" onClick={() => void testProfile(profile)}>{isTesting ? "Testing model..." : "Test model"}</button></article>;
      })}</section>
    </div>
  );
}
