import { afterEach, describe, expect, it, vi } from "vitest";
import { formatApiErrorDetail, ModelConnectivityError, modelConnectivityService } from "./modelConnectivityService";

afterEach(() => vi.unstubAllGlobals());

it.each([404, 410, 401, 403, 500, 502])("preserves HTTP %s and the requested path", async status => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({ detail: "Saved run unavailable" }) }));
  const error = await modelConnectivityService.getDeepTeamRun("run/1").catch(error => error);
  expect(error).toBeInstanceOf(ModelConnectivityError);
  expect(error).toMatchObject({ status, path: "/deepteam-runs/run%2F1", message: "Saved run unavailable" });
  expect(fetch).toHaveBeenCalledWith("/api/v1/deepteam-runs/run%2F1", expect.objectContaining({ cache: "no-store" }));
});

it("keeps transport failures distinct from a missing API record", async () => {
  const failure = new TypeError("Network unavailable");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(failure));
  await expect(modelConnectivityService.getDeepTeamRun("saved")).rejects.toBe(failure);
});

it("sends the caller's stable idempotency key when launching", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, status: 202, json: async () => ({ run_id: "run-1" }) });
  vi.stubGlobal("fetch", fetcher);
  const selection = { scenario_id: "chatmate-direct-user-prompt-injection", target_profile_id: "secmate.synthetic-chatmate.fresh.v1",
    attack_profile_id: "crescendo-v1", vulnerability_profile_id: "DirectPromptInjection:direct_user_instruction",
    max_total_tokens: 75000, execution_mode: "SINGLE" as const, max_paths: 1 as const };
  await modelConnectivityService.startDeepTeamRun(selection, "stable-launch-key");
  expect(fetcher).toHaveBeenCalledExactlyOnceWith("/api/v1/deepteam-runs", expect.objectContaining({ method: "POST",
    headers: expect.objectContaining({ "Idempotency-Key": "stable-launch-key", "X-SecMate-Local-Run": "confirmed" }), body: JSON.stringify(selection) }));
});

describe("formatApiErrorDetail", () => {
  it("formats FastAPI validation arrays", () => {
    expect(formatApiErrorDetail([
      { loc: ["body", "max_total_tokens"], msg: "Input should be greater than or equal to 10000", type: "greater_than_equal" },
    ], 422)).toBe("max_total_tokens: Input should be greater than or equal to 10000");
  });

  it("explains an outdated adaptive API", () => {
    expect(formatApiErrorDetail([
      { loc: ["body", "execution_mode"], msg: "Extra inputs are not permitted", type: "extra_forbidden" },
      { loc: ["body", "max_paths"], msg: "Extra inputs are not permitted", type: "extra_forbidden" },
    ], 422)).toContain("Restart SecMate");
  });
});
