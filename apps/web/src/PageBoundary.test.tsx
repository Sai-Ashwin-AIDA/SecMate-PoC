import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PageBoundary, PAGE_ERROR_EVENT } from "./PageBoundary";

afterEach(() => vi.restoreAllMocks());

it.each([new Error("synthetic-private-render-detail"), null])("contains descendant failures and reports only safe diagnostics: %s", (failure) => {
  window.history.replaceState({}, "", "/reports?run=synthetic-private-query");
  vi.spyOn(console, "error").mockImplementation(() => {});
  const events = vi.spyOn(window, "dispatchEvent");
  function Broken(): never { throw failure; }
  render(<PageBoundary><Broken /></PageBoundary>);
  expect(screen.getByRole("heading", { name: "This page could not load" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Reload page" })).toBeEnabled();
  const diagnostic = events.mock.calls.map(([event]) => event).find((event) => event.type === PAGE_ERROR_EVENT) as CustomEvent;
  expect(diagnostic.detail).toEqual({ code: "PAGE_RENDER", route: "/reports" });
  expect(JSON.stringify(diagnostic.detail)).not.toContain("private");
});
