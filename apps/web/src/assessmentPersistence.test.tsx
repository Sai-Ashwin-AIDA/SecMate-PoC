import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ChatMatePage } from "./ChatMatePage";
import { AssessmentsPage } from "./ModulePages";
import { ChatMateReportPanel } from "./ChatMateReportPanel";
import { chatmateService } from "./chatmateService";
import { evaluatedRun } from "./chatmateTestFixtures";
import { currentAssessment, rememberAssessment, syncHistoryEpoch } from "./assessmentSession";
import { chatMateTextHash } from "./chatmateCritic";

function Location() { const location = useLocation(); return <output>{location.pathname}{location.search}</output>; }
function app(path = "/assessments") {
  return render(<MemoryRouter initialEntries={[path]}><Link to="/other">Other page</Link><Link to="/assessments">Assessments tab</Link><Location /><Routes>
    <Route path="/assessments" element={<AssessmentsPage />} /><Route path="/assessments/chatmate" element={<ChatMatePage />} /><Route path="/other" element={<p>Elsewhere</p>} />
  </Routes></MemoryRouter>);
}
beforeEach(() => { window.localStorage.clear(); vi.spyOn(chatmateService, "listRuns").mockResolvedValue([]); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("clears deleted history references once while preserving browser target configuration", async () => {
  const state = { schemaVersion: 2, targets: [{ id: "my-target", name: "My target" }], modelProfiles: [], assessments: [], findings: [], reports: [], deletedReportAssessmentIds: [] };
  window.localStorage.setItem("secmate.poc.platform.v2", JSON.stringify(state));
  window.localStorage.setItem("secmate.deepteamRunHistory", '["deleted"]');
  rememberAssessment("deleted");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ epoch: "a".repeat(32) }) }));
  await syncHistoryEpoch();
  expect(currentAssessment()).toBeNull();
  expect(window.localStorage.getItem("secmate.deepteamRunHistory")).toBeNull();
  expect(JSON.parse(window.localStorage.getItem("secmate.poc.platform.v2")!).targets[0].id).toBe("my-target");
  rememberAssessment("new-run");
  await syncHistoryEpoch();
  expect(currentAssessment()).toBe("new-run");
});

it("restores the active generation after navigation without creating or replaying work", async () => {
  const user = userEvent.setup();
  const run = { ...evaluatedRun(), status: "GENERATING" as const, candidate_batch: null, manual_evidence: null, evaluation_attempts: 0, artifact_available: false };
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(run);
  const create = vi.spyOn(chatmateService, "createRun");
  rememberAssessment(run.run_id);
  app();
  await screen.findByRole("heading", { name: "Generating two attack prompts" });
  await user.click(screen.getByText("Other page"));
  expect(screen.getByText("Elsewhere")).toBeVisible();
  await user.click(screen.getByText("Assessments tab"));
  await screen.findByRole("heading", { name: "Generating two attack prompts" });
  expect(screen.getByText(`/assessments/chatmate?run=${run.run_id}`)).toBeVisible();
  expect(create).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Return to new assessment" }));
  await screen.findByRole("heading", { name: "Choose an attack method" });
  expect(currentAssessment()).toBeNull();
});

it("retains the current identifier on transient recovery errors and clears confirmed missing runs", async () => {
  const run = evaluatedRun();
  rememberAssessment(run.run_id);
  const get = vi.spyOn(chatmateService, "getRun").mockRejectedValue(new Error("Temporarily offline"));
  app();
  await screen.findByText("Temporarily offline");
  expect(currentAssessment()).toBe(run.run_id);
  get.mockRejectedValue(Object.assign(new Error("Run missing"), { missingRun: true }));
  await userEvent.click(screen.getByRole("button", { name: "Retry recovery" }));
  await waitFor(() => expect(currentAssessment()).toBeNull());
});

it("shows generation failures in the existing report detail without fetching Judge evidence", async () => {
  const run = { ...evaluatedRun(), status: "FAILED" as const, final_status: null, manual_evidence: null, evaluation_attempts: 0, candidate_batch: null, artifact_available: false, error_message: "Provider rate limit." };
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(run);
  const audit = vi.spyOn(chatmateService, "getAudit");
  render(<MemoryRouter><ChatMateReportPanel runId={run.run_id} onClose={() => {}} /></MemoryRouter>);
  await screen.findByRole("heading", { name: "Generation Failed" });
  expect(screen.queryByText("Deviation score")).not.toBeInTheDocument();
  expect(audit).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Export JSON" })).toBeDisabled();
});

it.each(["NOT_ALIGNED", "UNCERTAIN"] as const)("keeps %s candidates selectable and displays the actual advisory verdict", async verdict => {
  const run = evaluatedRun();
  run.status = "AWAITING_SELECTION";
  run.artifact_available = false;
  run.manual_evidence = null;
  run.evaluation_attempts = 0;
  const first = run.candidate_batch!.candidates[0];
  const secondPrompt = `${first.prompt} Alternative baseline.`;
  const secondHash = await chatMateTextHash(secondPrompt);
  run.candidate_batch!.candidates = [first, { ...first, ordinal: 2, candidate_id: `${first.candidate_id}-second`,
    prompt: secondPrompt, prompt_sha256: secondHash }].map(candidate => ({ ...candidate,
    source_prompt: candidate.prompt, source_prompt_sha256: candidate.prompt_sha256,
    generation_mode: "BASELINE_METHOD_REVIEWED", method_review: { candidate_id: candidate.candidate_id,
      prompt_sha256: candidate.prompt_sha256, verdict, reviewer_instruction_version: "baseline-method-review-v1",
      reviewer_instruction_sha256: "a".repeat(64) } }));
  vi.spyOn(chatmateService, "getRun").mockResolvedValue(run);
  const select = vi.spyOn(chatmateService, "selectCandidate").mockResolvedValue({ ...run, status: "AWAITING_RESPONSE" });
  app(`/assessments/chatmate?run=${run.run_id}`);
  await screen.findByRole("heading", { name: "Select one generated attack" });
  expect(screen.getAllByText(verdict === "NOT_ALIGNED" ? "Not aligned" : "Uncertain")).toHaveLength(2);
  expect(screen.queryByText(/Method-aligned baseline/)).not.toBeInTheDocument();
  expect(screen.queryByText(/This review does not block selection or establish attack effectiveness/)).not.toBeInTheDocument();
  const button = screen.getByRole("button", { name: "Select candidate 1" });
  expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(select).toHaveBeenCalledWith(run.run_id, run.candidate_batch!.candidates[0].candidate_id);
  expect(await screen.findByText(verdict === "NOT_ALIGNED" ? "Not aligned" : "Uncertain")).toBeVisible();
});
