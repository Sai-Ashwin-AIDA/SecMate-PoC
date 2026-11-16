import { afterEach, describe, expect, it, vi } from "vitest";
import { chatmateService } from "./chatmateService";

describe("chatmateService", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses guarded lifecycle routes and immutable candidate IDs", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return {
        ok: true,
        status: 200,
        json: async () => ({ run_id: "chatmate-run-1" }),
      } as Response;
    }));

    await chatmateService.createRun({
      attack_profile_id: "prompt-injection-v1",
      max_total_tokens: 100000,
      authorization_attested: true,
    });
    await chatmateService.selectCandidate("chatmate-run-1", "candidate-2");
    await chatmateService.retryEvaluation("chatmate-run-1");
    await chatmateService.abandonRun("run/1");

    expect(requests[0].url.endsWith("/api/v1/chatmate-runs")).toBe(true);
    expect(requests[0].init?.headers).toMatchObject({ "X-SecMate-Local-Run": "confirmed" });
    expect(requests[1].init?.body).toBe(JSON.stringify({ candidate_id: "candidate-2", reject_all: false }));
    expect(requests[2].url.endsWith("/chatmate-runs/chatmate-run-1/evaluation")).toBe(true);
    expect(requests[3].url.endsWith("/chatmate-runs/run%2F1/abandon")).toBe(true);
    expect(requests[3].init).toMatchObject({ method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" } });
  });

  it("submits explicit Judge consent with manual response evidence", async () => {
    let captured: RequestInit | undefined;
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      captured = init;
      return { ok: true, status: 202, json: async () => ({ run_id: "chatmate-run-1" }) } as Response;
    }));

    await chatmateService.submitResponse("chatmate-run-1", {
      candidate_id: "candidate-1",
      candidate_sha256: "a".repeat(64),
      outcome: "RESPONSE",
      response_text: "ChatMate refused.",
      prompt_submitted_unchanged: true,
      observation_captured_verbatim: true,
      judge_data_collection_attested: true,
    });

    expect(JSON.parse(String(captured?.body))).toMatchObject({
      outcome: "RESPONSE",
      response_text: "ChatMate refused.",
      judge_data_collection_attested: true,
    });
    expect(JSON.parse(String(captured?.body))).not.toHaveProperty("prompt_sent_at");
    expect(JSON.parse(String(captured?.body))).not.toHaveProperty("response_observed_at");
  });

  it("explains that a generic ChatMate 404 is a stale API process", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not Found" }),
    }) as Response));

    await expect(chatmateService.createRun({
      attack_profile_id: "prompt-injection-v1",
      max_total_tokens: 50000,
      authorization_attested: true,
    })).rejects.toThrow("Restart SecMate with npm run dev");
  });

  it("deletes through the guarded encoded route and does not parse a 204 body", async () => {
    const json = vi.fn(async () => { throw new Error("No JSON body"); });
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 204, json }) as unknown as Response));
    const deletion: Promise<void> = chatmateService.deleteRun("run/1");
    await expect(deletion).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith("/api/v1/chatmate-runs/run%2F1", expect.objectContaining({
      method: "DELETE", headers: { "Content-Type": "application/json", "X-SecMate-Local-Run": "confirmed" },
    }));
    expect(json).not.toHaveBeenCalled();
  });

  it("uses exact confirmed Critic, bodyless follow-up and draft generation contracts", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return { ok: true, status: init?.method === "POST" ? 202 : 200, json: async () => ({}) } as Response;
    }));
    await chatmateService.requestCritic("source/1");
    await chatmateService.getCritic("source/1");
    await chatmateService.createFollowUp("source/1");
    await chatmateService.generateDraft("draft/1", { max_total_tokens: 50000, authorization_attested: true });
    expect(requests.map(({ url }) => url)).toEqual([
      "/api/v1/chatmate-runs/source%2F1/critic", "/api/v1/chatmate-runs/source%2F1/critic",
      "/api/v1/chatmate-runs/source%2F1/follow-up", "/api/v1/chatmate-runs/draft%2F1/generation",
    ]);
    for (const index of [0, 2, 3]) expect(requests[index].init).toMatchObject({ method: "POST", headers: { "X-SecMate-Local-Run": "confirmed" } });
    expect(JSON.parse(String(requests[0].init?.body))).toEqual({ critic_data_collection_attested: true });
    expect(requests[1].init?.method).toBeUndefined();
    expect(requests[2].init?.body).toBeUndefined();
    expect(JSON.parse(String(requests[3].init?.body))).toEqual({ max_total_tokens: 50000, authorization_attested: true });
  });

  it("preserves the actionable backend reason for a rejected active-run delete", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409,
      json: async () => ({ detail: "Cannot delete an active run. Wait for generation to finish, then end the run." }),
    }) as Response));
    await expect(chatmateService.deleteRun("active")).rejects.toThrow("Wait for generation to finish, then end the run.");
  });
});
