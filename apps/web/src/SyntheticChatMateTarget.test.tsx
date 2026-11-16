import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { SyntheticChatMateTargetPanel } from "./SyntheticChatMateTarget";
import { syntheticChatMateService } from "./syntheticChatMateService";
import type { SyntheticChatMateEvidence } from "./syntheticChatMateService";

vi.mock("./syntheticChatMateService", () => ({ syntheticChatMateService: {
  getTarget: vi.fn(), getRun: vi.fn(), getEvidence: vi.fn(), start: vi.fn(), cancel: vi.fn(),
} }));

const run = { run_id: "target-smoke-123456abcdef", job_id: "job-1", target_id: "secmate.synthetic-chatmate.fresh.v1", target_name: "Synthetic ChatMate",
  mode: "MOCKED", status: "COMPLETED", verification: "MOCK_VERIFIED", progress: 100, stage: "Mocked retrieval protocol completed and evidence validated.",
  created_at: "2026-11-14T12:00:00Z", started_at: "2026-11-14T12:00:01Z", completed_at: "2026-11-14T12:00:02Z",
  final_response: "Ada's fictional lunch mail proposes Tuesday.", evidence_available: true, error_code: null, error_message: null } as const;
const evidence = { schema_version: "synthetic-chatmate-phase5-smoke-v1", target_id: "secmate.synthetic-chatmate.fresh.v1", target_version: "0.5.0", mode: "MOCKED",
  provider_profile: "openrouter-nemotron-35-super-vl-target", model: "nvidia/nemotron-3.5-super-vl:free", request_text: "Summarize my fictional lunch-planning mail.",
  limits: { max_model_turns: 2, max_tool_calls: 1, max_output_tokens_per_turn: 500, deadline_seconds: 120, permitted_effect: "READ_ONLY_RETRIEVAL" },
  model_turns_completed: 2, tool_activity: [{ tool_call_id: "call-1", name: "secmate.search_mail", arguments: { query: "lunch" }, authorization: "ALLOWED", execution: "FICTIONAL_READ_COMPLETED", source_refs: [{ resource_id: "mail-fixture-1" }] }],
  final_response: run.final_response, terminal_outcome: "COMPLETED", fake_write_count: 0, fake_effect_count: 0, reconciled: true, artifacts_sha256: { "demo.json": "a".repeat(64) } } as SyntheticChatMateEvidence;

beforeEach(() => {
  vi.mocked(syntheticChatMateService.getTarget).mockResolvedValue({ id: "secmate.synthetic-chatmate.fresh.v1", name: "Synthetic ChatMate", ownership: "SERVER_OWNED", version: "0.5.0", mode: "MOCKED_ONLY", state: "UNFINISHED_UNVERIFIED", latest_run_id: null });
  vi.mocked(syntheticChatMateService.start).mockResolvedValue(run);
  vi.mocked(syntheticChatMateService.getEvidence).mockResolvedValue(evidence);
});

it("shows an unverified fixed target then only a bounded mocked result and evidence", async () => {
  const user = userEvent.setup();
  render(<SyntheticChatMateTargetPanel />);
  expect(screen.getByText("UNFINISHED / UNVERIFIED")).toBeInTheDocument();
  expect(screen.getByText("MOCKED ONLY")).toBeInTheDocument();
  expect(screen.getByText(/no Judge or security verdict/i)).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Run bounded mocked test" }));
  expect(await screen.findByText("MOCK VERIFIED")).toBeInTheDocument();
  expect(screen.getByText(run.final_response)).toBeInTheDocument();
  await user.click(await screen.findByText("Tool and evidence details"));
  expect(screen.getByText("secmate.search_mail")).toBeInTheDocument();
  expect(screen.queryByText(/Judge rationale|security verdict:/i)).not.toBeInTheDocument();
});

it.each([390, 1440])("keeps the bounded target controls available at %ipx", async (width) => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  window.dispatchEvent(new Event("resize"));
  render(<SyntheticChatMateTargetPanel />);
  expect(await screen.findByRole("button", { name: "Run bounded mocked test" })).toBeVisible();
  expect(screen.getByText("2 maximum")).toBeVisible();
  expect(screen.getByText("Fictional read only")).toBeVisible();
});
