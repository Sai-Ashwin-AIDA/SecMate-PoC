import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";

const session = { email: "sai.ashwin@paramount.test", displayName: "Sai Ashwin", role: "Local Preview" };
let profileTestStatus: "PASS" | "FAIL";
let openRouterConfigured: boolean;
let capabilityAvailable: boolean;
let connectivityState: "AVAILABLE" | "DEGRADED";
let workerApiConnected: boolean;

const workerRun = (status: "QUEUED" | "COMPLETED") => ({
  run_id: "api-run-test",
  status,
  created_at: "2026-09-28T12:00:00Z",
  started_at: status === "COMPLETED" ? "2026-09-28T12:00:01Z" : null,
  completed_at: status === "COMPLETED" ? "2026-09-28T12:00:20Z" : null,
  scenario: "socmate-tier1-permission-escalation",
  vulnerability: "ExcessiveAgency:permissions",
  attack: "PermissionEscalation",
  vulnerability_profile_id: "excessive-agency-permissions-v1",
  attack_profile_id: "permission-escalation-v1",
  final_status: status === "COMPLETED" ? "RESISTED" : null,
  artifact_available: status === "COMPLETED",
  logs: [{ timestamp: "2026-09-28T12:00:00Z", level: "INFO", message: status === "COMPLETED" ? "Worker finished with 8 provider calls and 8197 tokens." : "Run accepted by the local FastAPI control boundary." }],
  error_code: null,
  error_message: null,
});

describe("SettingsPage", () => {
  afterEach(() => { vi.useRealTimers(); });
  beforeEach(() => {
    window.localStorage.clear();
    profileTestStatus = "PASS";
    openRouterConfigured = true;
    capabilityAvailable = true;
    connectivityState = "AVAILABLE";
    workerApiConnected = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/platform-capabilities") && !capabilityAvailable) {
        return { ok: false, status: 404, json: async () => ({ detail: "Not available" }) } as Response;
      }
      const body = url.endsWith("/deepteam-catalog") ? {
        schema_version: "1.0",
        scenario_id: "socmate-tier1-permission-escalation",
        target_profile_id: "synthetic-socmate-tier1",
        vulnerability_profile_id: "excessive-agency-permissions-v1",
        vulnerability: "ExcessiveAgency:permissions",
        synthetic_only: true,
        max_cases_per_run: 1,
        max_turns_per_case: 1,
        attack_profiles: [
          { id: "permission-escalation-v1", name: "Permission Escalation", class_name: "PermissionEscalation", description: "Approval test", turn_mode: "SINGLE", status: "AVAILABLE" },
          { id: "base64-v1", name: "Base64", class_name: "Base64", description: "Encoding test", turn_mode: "SINGLE", status: "AVAILABLE" },
        ],
      } : url.endsWith("/deepteam-runs/api-run-test/audit") ? {
        run_id: "api-run-test",
        manifest: { run_id: "worker-run" },
        evidence: { paths: [{ status: "RESISTED" }] },
        deepteam_risk: { test_cases: [{}] },
        summary: { final_status: "RESISTED", budget: { provider_calls_attempted: 8, tokens_consumed: 8197 } },
      } : url.endsWith("/deepteam-runs/api-run-test") ? workerRun("COMPLETED")
      : url.endsWith("/deepteam-runs") && init?.method === "POST" ? workerRun("QUEUED")
      : url.endsWith("/platform-capabilities") ? {
        schema_version: "1.0",
        mode: "POC",
        model_connectivity: { state: connectivityState, live_tests_supported: connectivityState === "AVAILABLE", assessment_grade: false },
        deepteam_worker: { state: workerApiConnected ? "AVAILABLE" : "VERIFIED_OFFLINE", invocation: workerApiConnected ? "LOCAL_SUBPROCESS" : "CLI_ONLY", api_connected: workerApiConnected, synthetic_only: true, verified_at: "2026-09-28T12:35:09.135416Z", deepteam_version: "1.0.9", deepteam_commit: "2fd3445c5bb2070ce09834f66f1622eb914f6f46", deepeval_version: "3.6.2", scenario_id: "socmate-tier1-permission-escalation", supported_vulnerabilities: ["ExcessiveAgency:permissions"], supported_attacks: ["PermissionEscalation"], max_verified_cases: 1, max_verified_turns: 1, last_verified_result: "RESISTED", target_evaluator_verified: true, last_deviation_category: "ALIGNED", last_deviation_score: 0, last_evaluator_confidence: 0.95 },
        assessment_api: { state: "NOT_AVAILABLE", lifecycle_source: "FRONTEND_SIMULATION" },
      } : url.endsWith("/model-profiles") ? [
        { id: "groq-qwen-attacker", role: "ATTACKER", provider: "GROQ", name: "Qwen 3.8 Attack Planner", model: "qwen/qwen3.8-27b", description: "Test attacker", capabilities: ["structured_output"] },
        { id: "openrouter-nemotron-target", role: "TARGET", provider: "OPENROUTER", name: "Nemotron Target", model: "nvidia/nemotron-3-ultra-550b-a55b:free", description: "Test target", capabilities: ["tool_calling"] },
      ] : url.endsWith("/providers/status") ? [
        { provider: "GROQ", configured: true, reachable: true, detail: "Groq model catalog is reachable.", quota: { requests_limit: 1000, requests_remaining: 999, tokens_limit: 8000, tokens_remaining: 7900, reset_requests: null, reset_tokens: null } },
        { provider: "OPENROUTER", configured: openRouterConfigured, reachable: openRouterConfigured, detail: openRouterConfigured ? "OpenRouter key is valid." : "OpenRouter key is not configured.", quota: openRouterConfigured ? { requests_limit: 50, requests_remaining: 49, tokens_limit: null, tokens_remaining: null, reset_requests: null, reset_tokens: null } : null },
      ] : url.endsWith("/model-workflows/adaptive-handoff/test") ? {
        scenario: "Synthetic SOCMate approval-boundary handoff",
        max_turns: 3,
        turns_completed: 3,
        stop_reason: "TURN_BUDGET_EXHAUSTED",
        turns: [1, 2, 3].map((turn) => ({
          turn,
          attacker: { objective: "Test boundary", strategy: `Strategy ${turn}`, probe: `Probe ${turn}`, success_condition: "Target requests approval" },
          target: { response_text: "Approval required", tool_attempts: [] },
          deterministic_check: { outcome: "NO_HARD_VIOLATION", rule_id: "NO_TOOL", detail: "No restricted tool attempt." },
          judge: { verdict: "RESISTED", confidence: 0.9, expected_behavior: "Request approval", observed_behavior: "Requested approval", evidence: ["No tool call"], concise_rationale: "Boundary preserved." },
          critic: turn < 3 ? { attack_quality_score: 60, weaknesses: ["Weak context"], unexplored_boundaries: ["Approval validation"], recommended_adaptation: `Adaptation ${turn}`, must_not_repeat: ["Repeat probe"] } : null,
        })),
      } : {
        profile_id: "groq-qwen-attacker", provider: "GROQ", model: "qwen/qwen3.8-27b", status: profileTestStatus, latency_ms: 420, summary: profileTestStatus === "PASS" ? "Attacker returned a valid structured test plan." : "Attacker diagnostic failed.", output: profileTestStatus === "PASS" ? { objective: "Test approval boundary" } : null, usage: { prompt_tokens: 20, completion_tokens: 30, total_tokens: 50 }, quota: null,
      };
      return { ok: true, status: 200, json: async () => body } as Response;
    }));
  });

  it("opens on Overview and renders one selected section at a time", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/settings"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Workspace overview" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "AI runtime and provider health" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^AI runtime/ }));
    expect(await screen.findByRole("heading", { name: "AI runtime and provider health" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Workspace overview" })).not.toBeInTheDocument();
  });

  it("runs a role-specific model connectivity test", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Attacker" })).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Test model" })[0]);
    expect(await screen.findByText("Attacker returned a valid structured test plan.")).toBeInTheDocument();
    expect(screen.getByText(/Test approval boundary/)).toBeInTheDocument();
  });

  it("shows the three-turn adaptive handoff timeline", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);
    await screen.findByText("Run fixed three-turn routing check");
    await user.click(screen.getByText("Routing diagnostics", { selector: "summary" }));
    await user.click(screen.getByRole("button", { name: "Run diagnostic handoff" }));
    expect(await screen.findByText("3 / 3 turns")).toBeInTheDocument();
    expect(screen.getByText("TURN BUDGET EXHAUSTED")).toBeInTheDocument();
    expect(screen.getByText("Adaptation 1")).toBeInTheDocument();
    expect(screen.getByText("Turn 3")).toBeInTheDocument();
  });

  it("separates live API diagnostics from verified offline worker evidence", async () => {
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);

    expect(await screen.findByText("VERIFIED OFFLINE")).toBeInTheDocument();
    expect(screen.getByText("Worker is not connected.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Worker details", { selector: "summary" }));
    expect(screen.getByText(/ALIGNED \/ 0 score \/ 95% confidence/)).toBeInTheDocument();
    expect(screen.queryByText(/arbitrary prompts.*remain prohibited/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run deepteam/i })).not.toBeInTheDocument();
  });

  it("renders an HTTP PASS or FAIL result accurately", async () => {
    profileTestStatus = "FAIL";
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);

    await screen.findByRole("heading", { name: "Attacker" });
    await user.click(screen.getAllByRole("button", { name: "Test model" })[0]);
    expect(await screen.findByText("Diagnostic failed")).toBeInTheDocument();
    expect(screen.queryByText("Diagnostic passed")).not.toBeInTheDocument();
  });

  it("distinguishes an unconfigured provider from an outage", async () => {
    openRouterConfigured = false;
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);

    expect(await screen.findByText("Not configured")).toBeInTheDocument();
  });

  it("keeps live diagnostics usable when capability metadata is unavailable", async () => {
    capabilityAvailable = false;
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);

    expect(await screen.findByText("Capability metadata unavailable")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Test model" })[0]).toBeEnabled();
  });

  it("disables live controls when the capability state is degraded", async () => {
    connectivityState = "DEGRADED";
    render(<MemoryRouter initialEntries={["/settings?section=models"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);

    expect(await screen.findByText("DEGRADED")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Test model" })[0]).toBeDisabled();
    await userEvent.click(screen.getByText("Routing diagnostics", { selector: "summary" }));
    expect(screen.getByRole("button", { name: "Run diagnostic handoff" })).toBeDisabled();
  });

  it("supports direct section links", () => {
    render(<MemoryRouter initialEntries={["/settings?section=appearance"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /White/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows session-backed profile details and persists time zone", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/settings?section=profile"]}><SettingsPage activeTheme="white" session={session} onResetDemo={vi.fn()} onThemeChange={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getAllByText("Sai Ashwin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("sai.ashwin@paramount.test").length).toBeGreaterThan(0);
    await user.selectOptions(screen.getByRole("combobox", { name: "Time zone" }), "Asia/Kolkata");
    await user.click(screen.getByRole("button", { name: "Save time zone" }));
    expect(window.localStorage.getItem("secmate.profile.timezone")).toBe("Asia/Kolkata");
  });
});
