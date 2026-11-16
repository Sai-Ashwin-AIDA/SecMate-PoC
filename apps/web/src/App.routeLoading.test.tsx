import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("./ModulePages", () => { throw new Error("Failed to fetch dynamically imported module: synthetic-private-url"); });

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

it("keeps navigation and a reload action usable when a deferred route cannot load", async () => {
  localStorage.setItem("secmate.demo.session", JSON.stringify({ email: "review@example.test", displayName: "Reviewer", role: "Local Preview" }));
  localStorage.setItem("secmate.theme", "secmate-dark");
  window.history.replaceState({}, "", "/reports");
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => [] })));
  vi.spyOn(console, "error").mockImplementation(() => {});
  const events = vi.spyOn(window, "dispatchEvent");
  render(<App />);
  expect(await screen.findByRole("heading", { name: "This page could not load" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Reload page" })).toBeEnabled();
  expect(screen.getByRole("button", { name: /^Notifications,/ })).toBeEnabled();
  const diagnostics = events.mock.calls.map(([event]) => event).filter((event) => event.type === "secmate:page-error");
  expect(diagnostics).toHaveLength(1);
  expect((diagnostics[0] as CustomEvent).detail).toEqual({ code: "CHUNK_LOAD", route: "/reports" });
  await userEvent.click(screen.getByRole("link", { name: "Executive Dashboard" }));
  expect(screen.queryByRole("heading", { name: "This page could not load" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Executive Dashboard" })).toBeVisible();
});
