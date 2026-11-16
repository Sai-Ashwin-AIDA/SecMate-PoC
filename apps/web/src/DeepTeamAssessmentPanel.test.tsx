import { act, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DeepTeamAssessmentPanel } from "./DeepTeamAssessmentPanel";
import { modelConnectivityService, ModelConnectivityError } from "./modelConnectivityService";
import type { DeepTeamRunRecord } from "./modelConnectivityService";

const restoredRun: DeepTeamRunRecord = {
  run_id: "restored-run", status: "RUNNING", created_at: "2026-10-30T00:00:00Z", started_at: null, completed_at: null,
  scenario: "socmate-tier1-permission-escalation", scenario_version: "1", target_profile_id: "synthetic-socmate-tier1", target_profile_version: "1",
  catalog_schema_version: "2.1", vulnerability: "ExcessiveAgency:permissions", attack: "PermissionEscalation",
  vulnerability_profile_id: "permissions-v1", attack_profile_id: "permission-v1", vulnerability_applicability: "APPLICABLE", attack_applicability: "APPLICABLE",
  vulnerability_capability_level: "REGISTERED", attack_capability_level: "REGISTERED", max_total_tokens: 150000, execution_mode: "SINGLE", max_paths: 1,
  final_status: null, artifact_available: false, logs: [], error_code: null, error_message: null,
};

describe("DeepTeamAssessmentPanel", () => {
  afterEach(() => vi.restoreAllMocks());
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = url.endsWith("/deepteam-catalog") ? {
        schema_version: "2.3",
        scenario_id: "socmate-tier1-permission-escalation",
        scenario_version: "1",
        target_profile_id: "synthetic-socmate-tier1",
        target_profile_version: "1",
        synthetic_only: true,
        max_cases_per_run: 1,
        target_profiles: [
          { id: "synthetic-socmate-tier1", name: "SocMate", version: "1", purpose: "Synthetic SOC assistant", scenario_id: "socmate-tier1-permission-escalation", scenario_version: "1", synthetic_only: true, api_selectable: true, deterministic_vulnerable: false },
          { id: "secmate.synthetic-chatmate.fresh.v1", name: "Synthetic ChatMate", version: "0.5.0", purpose: "Fresh synthetic assistant", scenario_id: "chatmate-direct-user-prompt-injection", scenario_version: "3", synthetic_only: true, api_selectable: true, deterministic_vulnerable: false, binding_version: "2.0.0", api_registration: true, deepteam_provider: true, execution_modes: ["SINGLE", "ADAPTIVE"], max_paths: 2, attack_profile_ids: ["permission-v1", "prompt-injection-v1", "crescendo-v1", "sequential-jailbreak-v1"], vulnerability_profile_ids: ["DirectPromptInjection:direct_user_instruction"], unsupported_attack_profiles: { "tree-jailbreaking-v1": "Tree Jailbreaking requires speculative sibling histories; fresh ChatMate requires one authoritative linear conversation per path." }, experimental_catalog_projection: { schema_version: "1.0", admission: "EXPERIMENTAL", attack_profile_ids: ["permission-v1", "prompt-injection-v1", "crescendo-v1", "sequential-jailbreak-v1", "tree-jailbreaking-v1"], vulnerability_profile_ids: ["permissions-v1", "pii-v1", "pii-unreviewed-v1", "IndirectInstruction:document_embedded_instructions", "DirectPromptInjection:direct_user_instruction"] } },
          { id: "synthetic-chatmate-rag", name: "ChatMate", version: "1", purpose: "Synthetic document assistant", scenario_id: "chatmate-document-indirect-injection", scenario_version: "1", synthetic_only: true, api_selectable: true, deterministic_vulnerable: false },
          { id: "chatmate-vuln", name: "ChatMate(Vuln)", version: "1", purpose: "Synthetic vulnerable document assistant", scenario_id: "chatmate-document-indirect-injection", scenario_version: "1", synthetic_only: true, api_selectable: true, deterministic_vulnerable: true },
        ],
        attack_profiles: [
          { id: "permission-v1", name: "Permission Escalation", class_name: "PermissionEscalation", description: "Single-turn approval pressure.", turn_mode: "SINGLE", max_turns: 1, status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed.", capability_level: "APPLICABLE", target_profile_ids: ["synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1"], scenario_ids: ["socmate-tier1-permission-escalation", "chatmate-direct-user-prompt-injection"], required_target_capabilities: [], evidence_references: ["test"], target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "prompt-injection-v1", name: "Prompt Injection", class_name: "PromptInjection", description: "Direct prompt injection.", turn_mode: "SINGLE", max_turns: 1, status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed for ChatMate.", capability_level: "REGISTERED", target_profile_ids: ["synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1", "synthetic-chatmate-rag", "chatmate-vuln"], scenario_ids: ["socmate-tier1-permission-escalation", "chatmate-direct-user-prompt-injection", "chatmate-document-indirect-injection"], required_target_capabilities: ["conversation"], evidence_references: ["test"], target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "crescendo-v1", name: "Crescendo", class_name: "Crescendo", description: "Multi-turn trust escalation.", turn_mode: "MULTI", max_turns: 4, status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed.", capability_level: "OFFLINE_VERIFIED", target_profile_ids: ["synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1"], scenario_ids: ["socmate-tier1-permission-escalation", "chatmate-direct-user-prompt-injection"], required_target_capabilities: [], evidence_references: ["test"], target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "sequential-jailbreak-v1", name: "Sequential Jailbreak", class_name: "SequentialJailbreak", description: "Bounded sequential conversation.", turn_mode: "MULTI", max_turns: 4, status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed.", capability_level: "OFFLINE_VERIFIED", target_profile_ids: ["secmate.synthetic-chatmate.fresh.v1"], scenario_ids: ["chatmate-direct-user-prompt-injection"], required_target_capabilities: [], evidence_references: ["test"], target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "tree-jailbreaking-v1", name: "Tree Jailbreaking", class_name: "TreeJailbreaking", description: "Branching conversation.", turn_mode: "MULTI", max_turns: 5, status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Catalogued.", capability_level: "OFFLINE_VERIFIED", target_profile_ids: [], scenario_ids: ["chatmate-direct-user-prompt-injection"], target_applicability: { "secmate.synthetic-chatmate.fresh.v1": { applicability: "NOT_APPLICABLE", reason: "Requires speculative sibling histories." } }, target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } }, required_target_capabilities: [], evidence_references: ["test"] },
        ],
        vulnerability_profiles: [
          { id: "permissions-v1", name: "Excessive permissions", class_name: "ExcessiveAgency", subtype: "permissions", category: "Agency", description: "Tests unauthorized privileged actions.", status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed for SOCMate.", capability_level: "OFFLINE_VERIFIED", target_profile_ids: ["synthetic-socmate-tier1"], scenario_ids: ["socmate-tier1-permission-escalation"], required_target_capabilities: ["privileged_tool_boundary"], evidence_references: ["test"], target_applicability: { "secmate.synthetic-chatmate.fresh.v1": { applicability: "NOT_APPLICABLE", reason: "Requires a privileged tool boundary." } }, target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "pii-v1", name: "PII leakage", class_name: "SensitiveInformationDisclosure", subtype: "pii", category: "Privacy", description: "Tests disclosure of synthetic personal data.", status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed for SOCMate.", capability_level: "REGISTERED", target_profile_ids: ["synthetic-socmate-tier1"], scenario_ids: ["socmate-tier1-permission-escalation"], required_target_capabilities: [], evidence_references: [], target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "pii-unreviewed-v1", name: "Out-of-scope PII path", class_name: "SensitiveInformationDisclosure", subtype: "session_leak", category: "Privacy", description: "Registered for another target.", status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Scoped to another target.", capability_level: "REGISTERED", target_profile_ids: ["another-target"], scenario_ids: ["socmate-tier1-permission-escalation"], required_target_capabilities: [], evidence_references: [], target_applicability: { "secmate.synthetic-chatmate.fresh.v1": { applicability: "NOT_APPLICABLE", reason: "Established scope is another target." } }, target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "IndirectInstruction:document_embedded_instructions", name: "Indirect instruction / document", class_name: "IndirectInstruction", subtype: "document_embedded_instructions", category: "Agentic", description: "Tests document instructions.", status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Reviewed for ChatMate.", capability_level: "APPLICABLE", target_profile_ids: ["synthetic-chatmate-rag", "chatmate-vuln"], scenario_ids: ["chatmate-document-indirect-injection"], required_target_capabilities: ["untrusted_document_retrieval"], evidence_references: ["test"], target_applicability: { "secmate.synthetic-chatmate.fresh.v1": { applicability: "NOT_APPLICABLE", reason: "Fresh target has no document retrieval." } }, target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
          { id: "DirectPromptInjection:direct_user_instruction", name: "Prompt injection / direct user", class_name: "DirectPromptInjection", subtype: "direct_user_instruction", category: "Prompt injection", description: "Tests direct user instructions.", status: "AVAILABLE", applicability: "APPLICABLE", applicability_reason: "Dedicated fresh target path.", capability_level: "APPLICABLE", target_profile_ids: ["secmate.synthetic-chatmate.fresh.v1"], scenario_ids: ["chatmate-direct-user-prompt-injection"], required_target_capabilities: ["conversation"], evidence_references: ["test"], target_applicability: { "secmate.synthetic-chatmate.fresh.v1": { applicability: "APPLICABLE", reason: "Dedicated fresh direct-user path." } }, target_experimental_admission: { "secmate.synthetic-chatmate.fresh.v1": { admission: "ADMITTED", selectable: true, reason: "Experimental exact ID." } } },
        ],
      } : url.endsWith("/platform-capabilities") ? {
        schema_version: "1.0",
        mode: "POC",
        model_connectivity: { state: "AVAILABLE", live_tests_supported: true, assessment_grade: false },
        deepteam_worker: { state: "AVAILABLE", invocation: "LOCAL_SUBPROCESS", api_connected: true, api_contract_version: "2.0", supported_execution_modes: ["SINGLE", "ADAPTIVE"], max_paths: 2, cancellation_supported: true, synthetic_only: true, verified_at: "2026-09-28T12:00:00Z", deepteam_version: "1.0.9", deepteam_commit: "commit", deepeval_version: "3.6.2", scenario_id: "socmate-tier1-permission-escalation", supported_vulnerabilities: [], supported_attacks: [], max_verified_cases: 1, max_verified_turns: 4, last_verified_result: "RESISTED", target_evaluator_verified: true, last_deviation_category: "ALIGNED", last_deviation_score: 0, last_evaluator_confidence: 0.95 },
        assessment_api: { state: "NOT_AVAILABLE", lifecycle_source: "FRONTEND_SIMULATION" },
      } : url.endsWith("/deepteam-runs") && init?.method === "POST" ? {
        ...JSON.parse(String(init.body)),
        run_id: "run-selected",
        status: "COMPLETED",
        created_at: "2026-09-28T12:00:00Z",
        started_at: "2026-09-28T12:00:01Z",
        completed_at: "2026-09-28T12:00:20Z",
        scenario: JSON.parse(String(init.body)).scenario_id,
        vulnerability: "SensitiveInformationDisclosure:pii",
        attack: "Crescendo",
        vulnerability_profile_id: JSON.parse(String(init.body)).vulnerability_profile_id,
        attack_profile_id: JSON.parse(String(init.body)).attack_profile_id,
        final_status: "RESISTED",
        artifact_available: false,
        logs: [{ timestamp: "2026-09-28T12:00:00Z", level: "INFO", message: "Run completed." }],
        error_code: null,
        error_message: null,
      } : null;
      return { ok: true, status: 200, json: async () => body } as Response;
    }));
  });

  it("filters dropdowns, selects profiles, and submits both selected IDs", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Set up assessment" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Launch readiness")).not.toBeInTheDocument();
    expect(screen.queryByText(/Test selection:|Worker: Configured|Providers: Ready|Saved assessment: Resolved|Usage limit: Sufficient estimate/)).not.toBeInTheDocument();
    expect(document.querySelector(".campaign-service-availability")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Risk area" }));
    await user.click(screen.getByRole("option", { name: "Privacy" }));
    const vulnerabilitySelect = screen.getByRole("combobox", { name: "Security risk" });
    expect(vulnerabilitySelect).not.toHaveTextContent("Excessive permissions");
    await user.click(vulnerabilitySelect);
    await user.click(screen.getByRole("option", { name: "PII leakage" }));

    await user.click(screen.getByRole("combobox", { name: "Test length" }));
    await user.click(screen.getByRole("option", { name: "Multiple steps" }));
    const attackSelect = screen.getByRole("combobox", { name: "Test method" });
    expect(attackSelect).not.toHaveTextContent("Permission Escalation");
    await user.click(attackSelect);
    await user.click(screen.getByRole("option", { name: "Crescendo" }));
    await user.click(screen.getByRole("combobox", { name: "Usage limit" }));
    await user.click(screen.getByRole("option", { name: `${(150000).toLocaleString()} tokens` }));

    expect(screen.queryByText("APPLICABLE")).not.toBeInTheDocument();
    expect(screen.queryByText("REGISTERED")).not.toBeInTheDocument();
    expect(screen.queryByText("OFFLINE VERIFIED")).not.toBeInTheDocument();
    expect(screen.queryByText(/SensitiveInformationDisclosure/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Start assessment" }));
    const postCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/deepteam-runs") && init?.method === "POST");
    expect(postCall?.[1]?.body).toBe(JSON.stringify({ scenario_id: "socmate-tier1-permission-escalation", target_profile_id: "synthetic-socmate-tier1", attack_profile_id: "crescendo-v1", vulnerability_profile_id: "pii-v1", max_total_tokens: 150000, execution_mode: "ADAPTIVE", max_paths: 2 }));
    expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe("run-selected");
    expect(window.localStorage.getItem("secmate.deepteamRunHistory")).toContain("run-selected");
    expect(screen.queryByRole("heading", { name: "Assessment history" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Usage for this assessment" })).toBeInTheDocument();
    const activeConfiguration = screen.getByLabelText("Active run configuration");
    expect(activeConfiguration).toHaveTextContent("Crescendo");
    expect(activeConfiguration).toHaveTextContent("Personal data exposure");
    expect(activeConfiguration).not.toHaveTextContent("(crescendo-v1)");
    expect(activeConfiguration).not.toHaveTextContent("(pii-v1)");
  });

  it("renders local configuration while provider diagnostics remain pending", async () => {
    const providerStatus = vi.spyOn(modelConnectivityService, "getProviderStatus").mockImplementation(() => new Promise(() => {}));
    const view = render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    try {
      expect(await screen.findByRole("heading", { name: "Set up assessment" })).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Security risk" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Start assessment" })).toBeEnabled();
    } finally { view.unmount(); providerStatus.mockRestore(); }
  });

  it("hides out-of-scope profiles", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);

    await user.click(await screen.findByRole("combobox", { name: "Risk area" }));
    await user.click(screen.getByRole("option", { name: "Privacy" }));
    await user.click(screen.getByRole("combobox", { name: "Security risk" }));

    expect(screen.queryByRole("option", { name: "Out-of-scope PII path" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start assessment" })).toBeEnabled();
  });

  it("offers SocMate and fresh Synthetic ChatMate while keeping old RAG targets hidden", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);

    const target = await screen.findByRole("combobox", { name: "Target" });
    expect(target).toHaveTextContent("SocMate");
    await user.click(target);
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.getByRole("option", { name: "Synthetic ChatMate" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "ChatMate" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "SocMate" }));
    await user.click(screen.getByRole("combobox", { name: "Test coverage" }));
    await user.click(screen.getByRole("option", { name: "Standard" }));
    expect(screen.getByRole("combobox", { name: "Test coverage" })).toHaveTextContent("Standard");
    expect(screen.getByRole("combobox", { name: "Target" })).toHaveTextContent("SocMate");

    await user.click(screen.getByRole("button", { name: "Start assessment" }));
    const postCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/deepteam-runs") && init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({ scenario_id: "socmate-tier1-permission-escalation", target_profile_id: "synthetic-socmate-tier1", execution_mode: "SINGLE", max_paths: 1 });
  });

  it("guards a double launch synchronously and sends one stable idempotency key", async () => {
    const user = userEvent.setup();
    let resolve!: (run: DeepTeamRunRecord) => void;
    const start = vi.spyOn(modelConnectivityService, "startDeepTeamRun").mockImplementation(() => new Promise(done => { resolve = done; }));
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    const button = await screen.findByRole("button", { name: "Start assessment" });
    await user.dblClick(button);
    expect(start).toHaveBeenCalledTimes(1);
    expect(start.mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/i);
    const selection = start.mock.calls[0][0];
    await act(async () => resolve({ ...restoredRun, ...selection, scenario: selection.scenario_id,
      run_id: "double-click-run", status: "COMPLETED", final_status: "RESISTED" }));
    expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe("double-click-run");
  });

  it.each([320, 375, 390, 1440])("keeps catalog controls and launch actions accessible at %ipx", async width => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    expect(await screen.findByRole("combobox", { name: "Target" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Test method" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Test coverage" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Start assessment" })).toBeVisible();
    expect(document.body.scrollWidth).toBeLessThanOrEqual(width);
  });

  it("offers the complete fresh experimental catalog and allows an incompatible exact selection", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    await user.click(await screen.findByRole("combobox", { name: "Target" }));
    await user.click(screen.getByRole("option", { name: "Synthetic ChatMate" }));

    expect(screen.getByRole("combobox", { name: "Risk area" })).toHaveTextContent("Prompt injection");
    expect(screen.getByRole("combobox", { name: "Security risk" })).toHaveTextContent("Prompt injection / direct user");
    expect(screen.getByRole("combobox", { name: "Test method" })).toHaveTextContent("Prompt Injection");
    const riskArea = screen.getByRole("combobox", { name: "Risk area" });
    await user.click(riskArea);
    for (const name of ["Agency", "Privacy", "Agentic", "Prompt injection"]) expect(screen.getByRole("option", { name })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Privacy" }));
    await user.click(screen.getByRole("combobox", { name: "Security risk" }));
    expect(screen.getByRole("option", { name: "PII leakage" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Out-of-scope PII path" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Out-of-scope PII path" }));
    await user.click(screen.getByRole("combobox", { name: "Test length" }));
    await user.click(screen.getByRole("option", { name: "Multiple steps" }));
    await user.click(screen.getByRole("combobox", { name: "Test method" }));
    expect(screen.getByRole("option", { name: "Crescendo" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Sequential Jailbreak" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Tree Jailbreaking" })).toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Tree Jailbreaking" }));
    expect(screen.queryByText(/Experimental selection has a compatibility limitation/)).not.toBeInTheDocument();
    expect(screen.queryByText(/execution may return a typed unsupported or error outcome without a score/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Usage limit" }));
    await user.click(screen.getByRole("option", { name: `${(100000).toLocaleString()} tokens` }));
    const coverage = screen.getByRole("combobox", { name: "Test coverage" });
    await user.click(coverage);
    expect(screen.getByRole("option", { name: "Expanded" })).not.toHaveAttribute("aria-disabled");
    await user.click(screen.getByRole("option", { name: "Standard" }));

    await user.click(screen.getByRole("button", { name: "Start assessment" }));
    const postCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/deepteam-runs") && init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body))).toEqual({
      scenario_id: "chatmate-direct-user-prompt-injection",
      target_profile_id: "secmate.synthetic-chatmate.fresh.v1",
      attack_profile_id: "tree-jailbreaking-v1",
      vulnerability_profile_id: "pii-unreviewed-v1",
      max_total_tokens: 100000,
      execution_mode: "SINGLE",
      max_paths: 1,
    });

    await user.click(screen.getByRole("combobox", { name: "Target" }));
    await user.click(screen.getByRole("option", { name: "SocMate" }));
    expect(screen.getByRole("combobox", { name: "Risk area" })).toHaveTextContent("Agency");
    await user.click(screen.getByRole("combobox", { name: "Test coverage" }));
    expect(screen.getByRole("option", { name: "Expanded" })).not.toHaveAttribute("aria-disabled");
  });

  it.each([false, true])("reconciles setup coherently on terminal refresh (removed profiles: %s)", async removed => {
    const user = userEvent.setup();
    const initial = await modelConnectivityService.getDeepTeamCatalog();
    const catalog = vi.spyOn(modelConnectivityService, "getDeepTeamCatalog").mockResolvedValue(initial);
    let finish!: (run: DeepTeamRunRecord) => void;
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValueOnce(restoredRun)
      .mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const start = vi.spyOn(modelConnectivityService, "startDeepTeamRun").mockResolvedValue({ ...restoredRun, run_id: "next-run", status: "COMPLETED", final_status: "RESISTED" });
    window.localStorage.setItem("secmate.activeDeepteamRun", restoredRun.run_id);
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    await user.click(await screen.findByRole("combobox", { name: "Risk area" }));
    await user.click(screen.getByRole("option", { name: "Privacy" }));
    await user.click(screen.getByRole("combobox", { name: "Test length" }));
    await user.click(screen.getByRole("option", { name: "Multiple steps" }));
    await user.click(screen.getByRole("combobox", { name: "Usage limit" }));
    await user.click(screen.getByRole("option", { name: `${(150000).toLocaleString()} tokens` }));
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    if (removed) {
      catalog.mockResolvedValue({ ...initial, attack_profiles: initial.attack_profiles.filter(profile => profile.id !== "crescendo-v1"),
        vulnerability_profiles: initial.vulnerability_profiles.filter(profile => profile.category !== "Privacy") });
      vi.spyOn(modelConnectivityService, "getPlatformCapabilities").mockRejectedValue(new Error("Unavailable"));
    }
    await act(async () => finish({ ...restoredRun, status: "COMPLETED", final_status: "RESISTED" }));
    await waitFor(() => expect(catalog).toHaveBeenCalledTimes(2));
    if (removed) {
      expect(screen.getByRole("combobox", { name: "Test length" })).toHaveTextContent("One step");
      expect(screen.getByRole("combobox", { name: "Test method" })).toHaveTextContent("Permission Escalation");
      expect(screen.getByRole("combobox", { name: "Risk area" })).toHaveTextContent("Agency");
      expect(screen.getByRole("combobox", { name: "Security risk" })).toHaveTextContent("Excessive permissions");
      expect(screen.getByRole("button", { name: "Start assessment" })).toBeDisabled();
      expect(start).not.toHaveBeenCalled();
    } else {
      expect(screen.getByRole("combobox", { name: "Test length" })).toHaveTextContent("Multiple steps");
      expect(screen.getByRole("combobox", { name: "Test method" })).toHaveTextContent("Crescendo");
      expect(screen.getByRole("combobox", { name: "Risk area" })).toHaveTextContent("Privacy");
      await user.click(screen.getByRole("button", { name: "Start assessment" }));
    expect(start).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ attack_profile_id: "crescendo-v1", vulnerability_profile_id: "pii-v1", max_total_tokens: 150000 }), expect.any(String));
    }
  });

  it.each([404, 410])("silently forgets only the confirmed missing saved run (HTTP %s)", async status => {
    vi.useFakeTimers();
    try {
      window.localStorage.setItem("secmate.activeDeepteamRun", "missing");
      window.localStorage.setItem("secmate.deepteamRunHistory", '["missing","valid-other"]');
      window.localStorage.setItem("secmate.preferences", "preserved");
      window.localStorage.setItem("secmate.currentAssessment.v1", "preserved-manual-selection");
      const get = vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValue(new ModelConnectivityError("DeepTeam run not found.", status, "/deepteam-runs/missing"));
      render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
      await act(async () => {});
      await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
      expect(get).toHaveBeenCalledExactlyOnceWith("missing");
      expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBeNull();
      expect(window.localStorage.getItem("secmate.deepteamRunHistory")).toBe('["valid-other"]');
      expect(window.localStorage.getItem("secmate.preferences")).toBe("preserved");
      expect(window.localStorage.getItem("secmate.currentAssessment.v1")).toBe("preserved-manual-selection");
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Start assessment" })).toBeEnabled();
    } finally { vi.useRealTimers(); }
  });

  it.each([401, 403, 500, 502])("does not erase references based on an unrelated HTTP %s error", async status => {
    vi.useFakeTimers();
    try {
      window.localStorage.setItem("secmate.activeDeepteamRun", "saved");
      const get = vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValue(new ModelConnectivityError("DeepTeam run not found.", status, "/deepteam-runs/saved"));
      render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
      await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
      expect(get).toHaveBeenCalledTimes(5);
      expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe("saved");
      expect(screen.getByRole("alert")).toHaveTextContent("DeepTeam run not found.");
    } finally { vi.useRealTimers(); }
  });

  it("retains the pointer through a network failure and restores status on retry", async () => {
    vi.useFakeTimers();
    try {
      window.localStorage.setItem("secmate.activeDeepteamRun", restoredRun.run_id);
      const get = vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockRejectedValueOnce(new TypeError("Network unavailable"))
        .mockResolvedValue({ ...restoredRun, status: "COMPLETED", final_status: "RESISTED" });
      render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
      await act(async () => {});
      expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe(restoredRun.run_id);
      expect(screen.getByRole("alert")).toHaveTextContent("Network unavailable");
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(get).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe(restoredRun.run_id);
    } finally { vi.useRealTimers(); }
  });

  it("stops polling and restores setup if the current run disappears from the API", async () => {
    vi.useFakeTimers();
    try {
      window.localStorage.setItem("secmate.activeDeepteamRun", restoredRun.run_id);
      const get = vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValueOnce(restoredRun)
        .mockRejectedValue(new ModelConnectivityError("Missing", 404, `/deepteam-runs/${restoredRun.run_id}`));
      render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
      await act(async () => {});
      await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
      expect(get).toHaveBeenCalledTimes(2);
      expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBeNull();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Start assessment" })).toBeEnabled();
    } finally { vi.useRealTimers(); }
  });

  it("does not associate a mismatched response or missing audit with a missing source run", async () => {
    window.localStorage.setItem("secmate.activeDeepteamRun", restoredRun.run_id);
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue({ ...restoredRun, status: "COMPLETED", artifact_available: true });
    vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockRejectedValue(new ModelConnectivityError("Audit unavailable", 404, `/deepteam-runs/${restoredRun.run_id}/audit`));
    const view = render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Audit unavailable");
    expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe(restoredRun.run_id);
    view.unmount();
    vi.mocked(modelConnectivityService.getDeepTeamRun).mockResolvedValue({ ...restoredRun, run_id: "wrong-id" });
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("does not match the requested run");
    expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe(restoredRun.run_id);
  });

  it("ignores a late missing response from a disposed StrictMode recovery", async () => {
    window.localStorage.setItem("secmate.activeDeepteamRun", restoredRun.run_id);
    let reject!: (error: Error) => void;
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }))
      .mockResolvedValue({ ...restoredRun, status: "COMPLETED", final_status: "RESISTED" });
    render(<StrictMode><MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter></StrictMode>);
    await screen.findByRole("combobox", { name: "Target" });
    await act(async () => reject(new ModelConnectivityError("Missing", 404, `/deepteam-runs/${restoredRun.run_id}`)));
    expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBe(restoredRun.run_id);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("blocks launch while a saved run is unresolved and releases only after confirmed missing", async () => {
    window.localStorage.setItem("secmate.activeDeepteamRun", "old");
    let reject!: (error: Error) => void;
    vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
    const start = vi.spyOn(modelConnectivityService, "startDeepTeamRun");
    render(<MemoryRouter><DeepTeamAssessmentPanel /></MemoryRouter>);
    expect(await screen.findByRole("button", { name: "Recovering saved assessment..." })).toBeDisabled();
    expect(start).not.toHaveBeenCalled();
    await act(async () => reject(new ModelConnectivityError("Missing", 404, "/deepteam-runs/old")));
    expect(await screen.findByRole("button", { name: "Start assessment" })).toBeEnabled();
    expect(window.localStorage.getItem("secmate.activeDeepteamRun")).toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
