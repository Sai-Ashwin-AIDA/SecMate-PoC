import { webcrypto } from "node:crypto";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ChatMatePage } from "./ChatMatePage";
import { parseChatMateAudit } from "./chatmateProjections";
import { canonicalJudgeJson, chatMateCriticSource, chatMateTextHash, parseChatMateCriticReview } from "./chatmateCritic";
import { offlineChatMateContractFixture } from "./chatmateOfflineContractFixture";

const fixture = offlineChatMateContractFixture();

beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => vi.unstubAllGlobals());

it("accepts the actual offline worker/API audit and review with API-validated Unicode/redaction hashes", async () => {
  expect(fixture.offline).toBe(true);
  expect(fixture.provider_calls).toEqual({ judge: 1, critic: 1 });
  expect(parseChatMateAudit(fixture.record, fixture.audit).judge).toMatchObject({ confidence: .94, deviation_score: 10 });
  const source = chatMateCriticSource(fixture.record, fixture.audit);
  expect(source.judge).toEqual(fixture.canonical_judge);
  expect(await chatMateTextHash(source.candidate.prompt)).toBe(fixture.review.source_candidate_sha256);
  expect(await chatMateTextHash(fixture.record.manual_evidence!.redacted_response_text!)).toBe(fixture.record.manual_evidence!.persisted_response_sha256);
  expect(await chatMateTextHash(canonicalJudgeJson(source.judge))).toBe(fixture.review.source_judge_sha256);
  expect(await parseChatMateCriticReview(fixture.record, fixture.audit, fixture.review)).toEqual(fixture.review);
  expect(fixture.review.budget).toMatchObject({ provider_calls_attempted: 1, max_retries_per_call: 0 });
});

it("renders the actual saved review and draft, then sends only the confirmed draft generation payload after fresh authorization", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const draft = fixture.follow_up_draft;
  const queued = { ...draft, status: "QUEUED", authorization_attested: true };
  let generationStarted = false;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push({ url, init });
    let body: unknown;
    if (url.endsWith("/generation")) { generationStarted = true; body = queued; }
    else if (url.endsWith("/follow-up")) body = draft;
    else if (url.endsWith("/critic")) body = fixture.review;
    else if (url.endsWith("/audit")) body = fixture.audit;
    else if (url.endsWith(draft.run_id)) body = generationStarted ? queued : draft;
    else if (url.endsWith(fixture.record.run_id)) body = fixture.record;
    else throw new Error(`Unexpected request: ${url}`);
    return { ok: true, status: init?.method === "POST" ? url.endsWith("/follow-up") ? 201 : 202 : 200, json: async () => body } as Response;
  }));
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={[`/assessments/chatmate?run=${fixture.record.run_id}`]}><ChatMatePage /></MemoryRouter>);
  await user.click(await screen.findByRole("button", { name: /Critic Review/ }));
  expect(await screen.findByText(fixture.review.management_summary)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Start recommended follow-up" }));
  expect(await screen.findByRole("heading", { name: "Choose an attack method" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View parent assessment" })).toHaveAttribute("href", `/assessments/chatmate?run=${fixture.record.run_id}`);
  expect(screen.getByText(draft.follow_up_objective!)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /System Override/ })).toBeDisabled();
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(requests.filter(({ init }) => init?.method === "POST")).toHaveLength(1);
  expect(requests.find(({ url }) => url.endsWith("/follow-up"))?.init).toMatchObject({ method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" } });
  expect(requests.find(({ url }) => url.endsWith("/follow-up"))?.init?.body).toBeUndefined();
  await user.click(screen.getByRole("button", { name: "Generate 2 attacks" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "Generating two attack prompts" })).toBeInTheDocument());
  const generation = requests.find(({ url }) => url.endsWith("/generation"))!;
  expect(generation.url).toBe(`/api/v1/chatmate-runs/${draft.run_id}/generation`);
  expect(generation.init).toMatchObject({ method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" } });
  expect(JSON.parse(String(generation.init?.body))).toEqual({ max_total_tokens: 100000, authorization_attested: true });
  expect(requests.filter(({ init }) => init?.method === "POST")).toHaveLength(2);
});
