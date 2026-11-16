import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LiveFindingsPanel } from "./LiveFindingsPanel";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamAuditReport, DeepTeamRunRecord } from "./modelConnectivityService";

const run: DeepTeamRunRecord = {
  run_id: "run-live",
  status: "FAILED",
  created_at: "2026-09-29T10:00:00Z",
  started_at: "2026-09-29T10:00:01Z",
  completed_at: "2026-09-29T10:00:15Z",
  scenario: "socmate-tier1-permission-escalation",
  scenario_version: "1",
  target_profile_id: "synthetic-socmate-tier1",
  target_profile_version: "1",
  catalog_schema_version: "2.0",
  vulnerability: "ExcessiveAgency:permissions",
  attack: "PermissionEscalation",
  vulnerability_profile_id: "permissions-v1",
  attack_profile_id: "permission-v1",
  vulnerability_applicability: "APPLICABLE",
  vulnerability_capability_level: "OFFLINE_VERIFIED",
  attack_applicability: "APPLICABLE",
  attack_capability_level: "OFFLINE_VERIFIED",
  execution_mode: "SINGLE",
  max_paths: 1,
  max_total_tokens: 250000,
  final_status: "ERROR",
  artifact_available: true,
  logs: [],
  error_code: null,
  error_message: "Provider request failed.",
};

const audit: DeepTeamAuditReport = {
  run_id: "run-live",
  manifest: {},
  evidence: {},
  deepteam_risk: {},
  summary: {
    model_attempts: [{ error_code: "RATE_LIMITED" }, { error_code: null }],
    budget: {
      provider_calls_attempted: 7,
      provider_calls_failed: 2,
      tokens_consumed: 12400,
      max_total_tokens: 250000,
      token_budget_overrun: false,
    },
  },
};

describe("LiveFindingsPanel", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("secmate.activeDeepteamRun", "run-live");
    vi.restoreAllMocks();
  });

  it("shows a rate-limited worker failure without vulnerability severity", async () => {
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(run);
    vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockResolvedValue(audit);

    render(<MemoryRouter><LiveFindingsPanel /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Provider rate limit prevented assessment completion" })).toBeInTheDocument();
    expect(screen.queryByText("HIGH")).not.toBeInTheDocument();
    expect(screen.getByText("Runtime diagnostics").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText(/not a Target security compromise/i)).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("12,400 / 250,000")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("SocMate / Permission controls / Permission Escalation")).toBeInTheDocument();
    expect(screen.queryByText(/synthetic-socmate-tier1/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ExcessiveAgency:permissions/)).not.toBeInTheDocument();
  });

  it("renders a resisted run as assurance rather than a finding", async () => {
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue({
      ...run,
      status: "COMPLETED",
      final_status: "RESISTED",
      error_code: null,
      error_message: null,
    });
    vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockResolvedValue({
      ...audit,
      summary: { model_attempts: [], budget: { token_budget_overrun: false } },
    });

    render(<MemoryRouter><LiveFindingsPanel /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "No security finding generated" })).toBeInTheDocument();
    expect(screen.getByText("Assurance observation")).toBeInTheDocument();
    expect(screen.queryByText("CRITICAL")).not.toBeInTheDocument();
    expect(screen.queryByText("HIGH")).not.toBeInTheDocument();
    expect(screen.queryByText("MEDIUM")).not.toBeInTheDocument();
  });

  it("does not override a completed result because an earlier provider attempt failed", async () => {
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue({ ...run, status: "COMPLETED", final_status: "RESISTED", error_code: null, error_message: null });
    vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockResolvedValue(audit);
    render(<MemoryRouter><LiveFindingsPanel /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "No security finding generated" })).toBeInTheDocument();
    expect(screen.queryByText("Provider rate limit prevented assessment completion")).not.toBeInTheDocument();
    expect(screen.queryByText("HIGH")).not.toBeInTheDocument();
  });

  it("explains rejected provider credentials", async () => {
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue({
      ...run,
      error_code: "WORKER_RUN_FAILED",
      error_message: "The worker returned a fail-closed result.",
    });
    vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockResolvedValue({
      ...audit,
      summary: {
        model_attempts: [{ provider: "GROQ", error_code: "AUTHENTICATION" }],
        budget: { provider_calls_attempted: 1, provider_calls_failed: 1 },
      },
    });

    render(<MemoryRouter><LiveFindingsPanel /></MemoryRouter>);

    expect(await screen.findByText("Groq rejected its API key. Update the configured key and restart SecMate.")).toBeInTheDocument();
  });
});
