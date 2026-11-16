import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TargetsPage } from "./ModulePages";
import type { TargetDetail, TargetSummary, TargetTool } from "./targetProjectionService";

const productionStyles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

const model = { profile_id: "openrouter-nemotron-35-super-vl-target", provider: "OPENROUTER", model: "nvidia/nemotron-3.5-super-vl:free" } as const;
const summary = (chatmate: boolean): TargetSummary => ({
  schema_version: "target-projection-v1",
  id: chatmate ? "secmate.synthetic-chatmate.fresh.v1" : "synthetic-socmate-tier1",
  name: chatmate ? "Synthetic ChatMate" : "SocMate",
  version: chatmate ? "0.5.0" : "1",
  purpose: chatmate
    ? "A fresh synthetic company chat assistant for bounded direct-user conversations with fictional collaboration data and isolated assessment state."
    : "A synthetic Tier-1 SOC assistant that searches synthetic alerts and explains findings while privileged actions remain approval-gated simulations.",
  environment: "SYNTHETIC", ownership: "SERVER_OWNED", owner: chatmate ? "AIDA" : null, synthetic: true, selectable: true, model_profile: model,
  tool_count: chatmate ? 7 : 3, tool_count_basis: "TOTAL_INVENTORY",
  profile: { profile_schema_version: "2.3", profile_id: chatmate ? "secmate.synthetic-chatmate.fresh.v1" : "synthetic-socmate-tier1", profile_version: chatmate ? "0.5.0" : "1", scenario_id: chatmate ? "chatmate-direct-user-prompt-injection" : "socmate-tier1-permission-escalation", scenario_version: chatmate ? "3" : "1", binding_version: chatmate ? "2.0.0" : null },
});

const displayNames: Record<string, string> = {
  "secmate.conversation.history.read": "Read conversation history", "secmate.search_mail": "Search mail", "secmate.read_teams": "Read Teams conversations",
  "secmate.search_directory": "Search directory", "secmate.propose_message": "Propose a message", "secmate.read_calendar": "Read calendar", "secmate.propose_meeting": "Propose a meeting",
  search_alerts: "Search alerts", isolate_host: "Isolate host", disable_user: "Disable user",
};
const tool = (name: string, status: "AVAILABLE" | "REQUIRES_APPROVAL" | "NOT_ENABLED", effect: "READ" | "WRITE" = "READ"): TargetTool => ({
  canonical_name: name, display_name: displayNames[name], native_names: name.includes("search") ? ["native_search"] : [], native_details: `Native detail for ${name}.`, description: `Purpose for ${displayNames[name]}.`, effect,
  effect_scope: name.startsWith("secmate.") ? "FICTIONAL_DATA" : "SIMULATED", model_exposure: "EXPOSED", implementation_status: "IMPLEMENTED", execution_status: status,
  execution_details: status === "AVAILABLE" ? "Available as a read-only capability." : "A proposal requiring approval.",
});

const detail = (chatmate: boolean): TargetDetail => {
  const base = summary(chatmate);
  const tools = chatmate
    ? [tool("secmate.search_mail", "AVAILABLE"), tool("secmate.read_teams", "AVAILABLE"), tool("secmate.conversation.history.read", "AVAILABLE"), tool("secmate.search_directory", "AVAILABLE"), tool("secmate.propose_message", "REQUIRES_APPROVAL", "WRITE"), tool("secmate.read_calendar", "AVAILABLE"), tool("secmate.propose_meeting", "REQUIRES_APPROVAL", "WRITE")]
    : [tool("search_alerts", "AVAILABLE"), tool("isolate_host", "REQUIRES_APPROVAL", "WRITE"), tool("disable_user", "REQUIRES_APPROVAL", "WRITE")];
  return {
    ...base, tools,
    guardrails: chatmate
      ? [{ id: "direct-user-untrusted", name: "Untrusted direct-user instructions", description: "Direct user instructions cannot override the trusted target safety boundary.", enforcement: "TARGET_RUNTIME" }, { id: "profile-governed-access", name: "Profile-governed access", description: "Reads are available while proposals require approval.", enforcement: "ASSESSMENT_DISPATCH" }, { id: "fresh-path-state", name: "Fresh assessment path state", description: "Each assessment path starts from isolated synthetic state without caller history authority.", enforcement: "ASSESSMENT_DISPATCH" }]
      : [{ id: "trusted-app-approval", name: "Trusted application approval", description: "Privileged actions require trusted application approval that user text cannot provide.", enforcement: "TRUSTED_APPLICATION" }, { id: "simulated-effects-only", name: "No real effects", description: "Containment attempts are intercepted simulations and never affect real systems.", enforcement: "TARGET_RUNTIME" }],
    data_memory: chatmate
      ? { data_environment: "SYNTHETIC", data_sources: ["Fictional mail", "Fictional Teams", "Fictional calendar", "Fictional directory"], production_data: false, memory_kind: "SEEDED_FACTS_ONLY", facts_only_seeded_memory: true, natural_learning: false, cross_run_memory: "DISABLED", assessment_state: "FRESH_ISOLATED_PER_PATH", details: ["Seeded memory contains synthetic facts only.", "Natural learning is disabled.", "Assessment state is fresh and isolated for each path."] }
      : { data_environment: "SYNTHETIC", data_sources: ["Synthetic security alerts"], production_data: false, memory_kind: "NONE_CLAIMED", facts_only_seeded_memory: null, natural_learning: null, cross_run_memory: "NOT_CLAIMED", assessment_state: "RUN_SCOPED", details: ["The profile makes no persistent or cross-run memory claim."] },
    execution: { supported: true, channels: chatmate ? ["TEXT", "MODEL_TOOLS", "DEEPTEAM", "BOUNDED_SMOKE"] : ["TEXT", "MODEL_TOOLS", "DEEPTEAM"], limits: [{ id: "deepteam-profile", description: "Current assessment profile bounds.", execution_modes: ["SINGLE", "ADAPTIVE"], max_paths: 2, max_conversation_turns: chatmate ? 4 : null, max_model_turns: null, max_tool_calls: null, max_output_tokens_per_turn: null, max_provider_attempts: null, deadline_seconds: null }], limitations: chatmate ? ["All data is fictional and proposals cannot take effect without approval."] : ["All target data and tool effects are synthetic."] },
    references: [{ path: "services/deepteam-worker/src/secmate_worker/target_profiles.py", kind: "SOURCE", description: "Target profile source." }],
  };
};

const summaries = [summary(false), summary(true)];
const details = new Map<string, TargetDetail>(summaries.map((item) => [item.id, detail(item.name === "Synthetic ChatMate")]));

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.search}</output>;
}

function mockTargetsApi() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = url.endsWith("/targets") ? summaries : details.get(decodeURIComponent(url.split("/targets/")[1]));
    return { ok: Boolean(body), status: body ? 200 : 404, json: async () => body ?? { detail: "Target not found." }, requestMethod: init?.method } as unknown as Response;
  });
}

describe("TargetsPage projection", () => {
  beforeEach(() => vi.stubGlobal("fetch", mockTargetsApi()));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("renders exactly one shared card per API summary and filters the combined list without a false empty state", async () => {
    const user = userEvent.setup();
    const { container } = render(<MemoryRouter><TargetsPage /></MemoryRouter>);
    expect(await screen.findByText("2 of 2 Targets")).toBeInTheDocument();
    expect(container.querySelectorAll(".target-grid")).toHaveLength(1);
    expect(container.querySelectorAll(".target-card")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /SocMate/ })).toHaveTextContent("3");
    expect(screen.getByRole("button", { name: /Synthetic ChatMate/ })).toHaveTextContent("7");
    await user.type(screen.getByRole("searchbox", { name: "Find a target" }), "company chat");
    expect(screen.getByText("1 of 2 Targets")).toBeInTheDocument();
    expect(container.querySelectorAll(".target-card")).toHaveLength(1);
    expect(screen.queryByText("No matching targets")).not.toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox", { name: "Find a target" }));
    await user.type(screen.getByRole("searchbox", { name: "Find a target" }), "not present");
    expect(screen.getByText("0 of 2 Targets")).toBeInTheDocument();
    expect(screen.getByText("No matching targets")).toBeInTheDocument();
  });

  it.each(["SocMate", "Synthetic ChatMate"] as const)("opens %s through the same accessible dialog and restores focus", async (name) => {
    const user = userEvent.setup();
    const { container } = render(<MemoryRouter><TargetsPage /></MemoryRouter>);
    const card = await screen.findByRole("button", { name: new RegExp(name) });
    await user.click(card);
    const dialog = await screen.findByRole("dialog", { name });
    expect(dialog).toHaveClass("target-detail-dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus());
    await user.tab();
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(card).toHaveFocus();
    expect(container.querySelector(".target-grid")).toBeInTheDocument();
  });

  it("shows compact authoritative identity, guardrails, memory and a full-width tool inventory", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><TargetsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: /Synthetic ChatMate/ }));
    const dialog = await screen.findByRole("dialog", { name: "Synthetic ChatMate" });
    expect(within(dialog).getByText("nvidia/nemotron-3.5-super-vl:free")).toBeInTheDocument();
    expect(within(dialog).getByText("OpenRouter")).toBeInTheDocument();
    expect(within(dialog).getByText("AIDA")).toBeInTheDocument();
    expect(within(dialog).getByText("5 read-only capabilities are available. 2 proposals require approval.")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Available")).toHaveLength(5);
    expect(within(dialog).getAllByText("Requires approval")).toHaveLength(2);
    expect(within(dialog).getAllByText("Read-only")).toHaveLength(5);
    expect(within(dialog).getAllByText("Proposes an action")).toHaveLength(2);
    expect(within(dialog).getByText("User instructions are untrusted")).toBeInTheDocument();
    expect(within(dialog).getByText("Reads available; proposals require approval")).toBeInTheDocument();
    expect(within(dialog).getByText("Synthetic only; no production data")).toBeInTheDocument();
    expect(within(dialog).getByText("Mail, Teams, Calendar, Directory")).toBeInTheDocument();
    expect(within(dialog).getByText("Seeded facts only; reset each assessment")).toBeInTheDocument();
    expect(within(dialog).queryByText("Natural learning is disabled.")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Fresh assessment path state")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("assessment dispatch")).not.toBeInTheDocument();
    expect(dialog.querySelectorAll(".target-compact-facts")).toHaveLength(2);
    expect(dialog.querySelectorAll(".target-compact-facts > div")).toHaveLength(5);
    expect(dialog.querySelectorAll(".target-summary-grid > section")).toHaveLength(3);
    expect(dialog.querySelectorAll(".target-tools-section")).toHaveLength(1);
    expect(dialog.querySelectorAll(".target-tool")).toHaveLength(7);
    expect(within(dialog).queryByText("Execution support and limitations")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Technical details")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Limitations")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("secmate.search_mail")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("native_search")).not.toBeInTheDocument();
    expect(dialog).not.toHaveTextContent(/Phase5|dispatch allowlist|fixture|schema exposure|canonical|native|EXPOSED|IMPLEMENTED|binding/i);
    expect(dialog.querySelector("table")).not.toBeInTheDocument();
  });

  it("keeps capability names and statuses readable with the previous projection shape", async () => {
    const legacy = detail(true);
    legacy.tools = legacy.tools.map((item) => ({
      ...item,
      display_name: undefined,
      execution_status: ["secmate.search_mail", "secmate.read_teams"].includes(item.canonical_name)
        ? "EXECUTABLE"
        : "DEFERRED",
    }));
    legacy.execution.limitations = [
      "Only secmate.search_mail and secmate.read_teams execute in current Phase5 assessment dispatch.",
      "All data is fictional and all write-capable schemas are deferred.",
      "Tree-style speculative sibling histories are not supported.",
    ];
    details.set(legacy.id, legacy);

    try {
      render(<MemoryRouter initialEntries={["/targets?id=secmate.synthetic-chatmate.fresh.v1"]}><TargetsPage /></MemoryRouter>);
      const dialog = await screen.findByRole("dialog", { name: "Synthetic ChatMate" });
      expect(await within(dialog).findByText("Read conversation history")).toBeInTheDocument();
      expect(within(dialog).getByText("Propose a meeting")).toBeInTheDocument();
      expect(within(dialog).getByText("2 read-only capabilities are available. 0 proposals require approval. 5 not enabled for this assessment.")).toBeInTheDocument();
      expect(within(dialog).getAllByText("Available")).toHaveLength(2);
      expect(within(dialog).getAllByText("Not enabled for this assessment")).toHaveLength(5);
      expect(within(dialog).queryByText("Limitations")).not.toBeInTheDocument();
      expect(within(dialog).queryByText(/Phase5 assessment dispatch/)).not.toBeInTheDocument();
    } finally {
      details.set(legacy.id, detail(true));
    }
  });

  it("keeps the dialog body below the header with one vertical content scroller", async () => {
    render(<MemoryRouter initialEntries={["/targets?id=secmate.synthetic-chatmate.fresh.v1"]}><TargetsPage /></MemoryRouter>);
    const dialog = await screen.findByRole("dialog", { name: "Synthetic ChatMate" });
    await within(dialog).findByRole("heading", { name: "Identity" });
    const body = dialog.querySelector<HTMLElement>(".target-detail-body");
    expect(body).not.toBeNull();
    expect(productionStyles).toMatch(/\.target-detail-dialog\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;[^}]*overflow:\s*hidden;/s);
    expect(productionStyles).toMatch(/\.target-detail-body\s*\{[^}]*overflow-x:\s*hidden;[^}]*overflow-y:\s*auto;/s);
    expect(productionStyles).toMatch(/\.target-compact-facts\s*>\s*div\s*\{[^}]*grid-template-columns:\s*88px minmax\(0, 1fr\);/s);
  });

  it("supports direct links, unknown IDs, safe Close and Escape while preserving unrelated query parameters", async () => {
    const user = userEvent.setup();
    const linked = render(<MemoryRouter initialEntries={["/targets?tab=all&id=synthetic-socmate-tier1"]}><TargetsPage /><LocationProbe /></MemoryRouter>);
    const dialog = await screen.findByRole("dialog", { name: "SocMate" });
    expect(await within(dialog).findByText("Trusted application approval required")).toBeInTheDocument();
    expect(within(dialog).getByText("Simulated only; no real-world changes")).toBeInTheDocument();
    expect(within(dialog).getByText("No persistent or cross-run memory claimed")).toBeInTheDocument();
    expect(screen.getByLabelText("location")).toHaveTextContent("tab=all&id=synthetic-socmate-tier1");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("location")).toHaveTextContent("?tab=all");
    linked.unmount();

    render(<MemoryRouter initialEntries={["/targets?id=unknown&tab=all"]}><TargetsPage /><LocationProbe /></MemoryRouter>);
    expect(await screen.findByText("Target not found")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to Targets" }));
    expect(screen.getByLabelText("location")).toHaveTextContent("?tab=all");
  });

  it("makes only GET projection requests and renders no smoke or onboarding controls", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    render(<MemoryRouter><TargetsPage /></MemoryRouter>);
    await user.click(await screen.findByRole("button", { name: /Synthetic ChatMate/ }));
    await screen.findByRole("dialog", { name: "Synthetic ChatMate" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    for (const [input, init] of fetchMock.mock.calls) {
      expect(String(input)).toMatch(/^\/api\/v1\/targets(?:\/|$)/);
      expect(init?.method).toBe("GET");
    }
    expect(screen.queryByText(/MOCKED ONLY|UNFINISHED|MOCK VERIFIED/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Onboard|Run bounded|Cancel bounded|Select Synthetic/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("keeps responsive content structurally stackable at a 390px jsdom viewport", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    const { container } = render(<MemoryRouter initialEntries={["/targets?id=secmate.synthetic-chatmate.fresh.v1"]}><TargetsPage /></MemoryRouter>);
    const dialog = await screen.findByRole("dialog", { name: "Synthetic ChatMate" });
    await within(dialog).findByRole("heading", { name: "Identity" });
    expect(dialog).toHaveClass("target-detail-dialog");
    expect(container.querySelectorAll(".target-summary-grid > section")).toHaveLength(3);
    expect(container.querySelectorAll(".target-tool")).toHaveLength(7);
    expect(container.querySelectorAll(".target-card")).toHaveLength(2);
    expect([...dialog.querySelectorAll<HTMLElement>("*")].some((element) => /width\s*:\s*\d+px/.test(element.getAttribute("style") ?? ""))).toBe(false);
    expect(within(dialog).queryByText("Technical details")).not.toBeInTheDocument();
  });
});
