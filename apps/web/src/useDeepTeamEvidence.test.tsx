import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useDeepTeamEvidence } from "./useDeepTeamEvidence";
import { modelConnectivityService } from "./modelConnectivityService";
import type { DeepTeamAuditReport, DeepTeamRunRecord } from "./modelConnectivityService";

const run = { run_id: "saved-run", status: "COMPLETED", artifact_available: true } as DeepTeamRunRecord;
const audit = { run_id: "saved-run", manifest: {}, evidence: {}, summary: {}, deepteam_risk: {} } as DeepTeamAuditReport;
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(modelConnectivityService, "getDeepTeamRun").mockResolvedValue(run);
  vi.spyOn(modelConnectivityService, "getDeepTeamAudit").mockResolvedValue(audit);
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

it("recovers a terminal audit after transient failure without launching work or remounting", async () => {
  vi.mocked(modelConnectivityService.getDeepTeamAudit).mockRejectedValueOnce(new Error("Temporary evidence outage"));
  const { result } = renderHook(() => useDeepTeamEvidence("saved-run"));
  await act(async () => {});
  expect(result.current.run).toEqual(run);
  expect(result.current.error).toBe("Temporary evidence outage");
  expect(result.current.audit).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(result.current.audit).toEqual(audit);
  expect(result.current.error).toBe("");
  expect(modelConnectivityService.getDeepTeamAudit).toHaveBeenCalledTimes(2);
  expect(vi.getTimerCount()).toBe(0);
});

it("bounds automatic failures and allows explicit recovery after retries are exhausted", async () => {
  vi.mocked(modelConnectivityService.getDeepTeamAudit).mockRejectedValue(new Error("Still unavailable"));
  const { result } = renderHook(() => useDeepTeamEvidence("saved-run"));
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(modelConnectivityService.getDeepTeamAudit).toHaveBeenCalledTimes(4);
  expect(result.current.run).toEqual(run);
  expect(vi.getTimerCount()).toBe(0);
  vi.mocked(modelConnectivityService.getDeepTeamAudit).mockResolvedValue(audit);
  await act(async () => { result.current.retry(); });
  expect(result.current.audit).toEqual(audit);
  expect(result.current.error).toBe("");
});

it("ignores late evidence from a previously selected run and cancels its retry timer", async () => {
  let resolve!: (value: DeepTeamAuditReport) => void;
  vi.mocked(modelConnectivityService.getDeepTeamAudit).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  const { result, rerender, unmount } = renderHook(({ id }) => useDeepTeamEvidence(id), { initialProps: { id: "saved-run" } });
  await act(async () => {});
  vi.mocked(modelConnectivityService.getDeepTeamRun).mockResolvedValue({ ...run, run_id: "other" });
  const otherAudit = { ...audit, run_id: "other" };
  vi.mocked(modelConnectivityService.getDeepTeamAudit).mockResolvedValue(otherAudit);
  rerender({ id: "other" });
  await act(async () => { resolve(audit); });
  expect(result.current.audit).toEqual(otherAudit);
  expect(result.current.run?.run_id).toBe("other");
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
