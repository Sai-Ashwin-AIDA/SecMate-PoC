import { afterEach, describe, expect, it, vi } from "vitest";
import { targetProjectionService } from "./targetProjectionService";

describe("targetProjectionService", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses only the read-only target projection endpoints", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => String(input).endsWith("/targets") ? [] : { id: "synthetic-socmate-tier1" },
    } as Response));
    vi.stubGlobal("fetch", fetchMock);

    await targetProjectionService.list();
    await targetProjectionService.get("synthetic-socmate-tier1");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/targets", expect.objectContaining({ cache: "no-store", method: "GET" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v1/targets/synthetic-socmate-tier1", expect.objectContaining({ cache: "no-store", method: "GET" }));
    expect(fetchMock.mock.calls.every(([, init]) => init?.method === "GET")).toBe(true);
  });

  it("encodes IDs and returns the API error detail", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => ({ ok: false, status: 404, json: async () => ({ detail: "Target not found." }) }) as Response);
    vi.stubGlobal("fetch", fetchMock);
    await expect(targetProjectionService.get("unknown/id")).rejects.toThrow("Target not found.");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/targets/unknown%2Fid");
  });
});
