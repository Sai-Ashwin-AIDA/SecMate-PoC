import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EvidenceResponse, JudgeReasoning, reasoningPresentation, responsePresentation } from "./EvidencePresentation";

describe("display-only evidence formatting", () => {
  it("recovers whole-response JSON clipboard artifacts without changing originals", () => {
    const raw = '{\\\n&#x20; "status": "ready",\\\n&#x20; "items": ["a", "b"]\\\n}';
    expect(responsePresentation(raw).text).toBe('{\n  "status": "ready",\n  "items": [\n    "a",\n    "b"\n  ]\n}');
    const { container } = render(<EvidenceResponse text={raw} />);
    expect(container.querySelector("details pre")?.textContent).toBe(raw);
    expect(screen.getByText("Original pasted text · formatted view above")).toBeInTheDocument();
  });

  it("does not reinterpret literal escapes in valid JSON, HTML, or malformed text", () => {
    const json = '{"literal":"&#x20;", "path":"C:\\\\new"}';
    expect(JSON.parse(responsePresentation(json).text)).toEqual(JSON.parse(json));
    const raw = '<script>alert(1)</script>\\\n&#x20; not JSON';
    expect(responsePresentation(raw)).toEqual({ text: raw, formatted: false });
    const { container } = render(<EvidenceResponse text={raw} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector(".chatmate-captured-response")?.textContent).toBe(raw);
  });

  it("formats fenced JSON while leaving ordinary prose exact", () => {
    expect(responsePresentation('```json\n{"ok": true}\n```').text).toBe('{\n  "ok": true\n}');
    expect(responsePresentation("  Plain refusal.\n").text).toBe("  Plain refusal.\n");
  });

  it("preserves number spellings, duplicate members, member order and escaped strings", () => {
    const raw = '{"id":9007199254740993,"role":"first","role":"second","nested":{"k":1,"k":2},"numbers":[1e400,-0,1.2300,2E+03],"escape":"\\u0041\\\""}';
    const formatted = responsePresentation(raw).text;
    expect(formatted).toContain('"id": 9007199254740993');
    expect(formatted).toContain('"role": "first",\n  "role": "second"');
    expect(formatted).toContain('"k": 1,\n    "k": 2');
    expect(formatted).toContain('1e400,\n    -0,\n    1.2300,\n    2E+03');
    expect(formatted).toContain('"escape": "\\u0041\\\""');
    // Removing only whitespace outside strings must leave identical evidence tokens.
    const compact = (value: string) => value.match(/"(?:\\.|[^"\\])*"|\S/g)?.join("");
    expect(compact(formatted)).toBe(compact(raw));
  });

  it("recovers whitespace only outside strings and preserves literal entity text", () => {
    const raw = '{\\\r\n&#32;"text":"&#32; and &#x20;",\\\n"quoted":"say \\\"&#32;\\\"",\\\n"id":9007199254740993\\\n}';
    const formatted = responsePresentation(raw).text;
    expect(formatted).toContain('"text": "&#32; and &#x20;"');
    expect(formatted).toContain('"quoted": "say \\\"&#32;\\\""');
    expect(formatted).toContain('"id": 9007199254740993');
    expect(responsePresentation('{"bad":"broken\\\nstring"}').formatted).toBe(false);
  });

  it("falls back to raw text instead of expanding deeply nested evidence", () => {
    const raw = "[".repeat(100) + "0" + "]".repeat(100);
    expect(responsePresentation(raw)).toEqual({ text: raw, formatted: false });
  });
});

describe("shared Judge presentation", () => {
  it("separates worker metadata from explanation without inventing observations", () => {
    const reasoning = "The target refused. Confidence is 0.95. No secret appeared. The boundary held."
      + "\n\nTest boundary fit: FIT.\nBehavior observations (Judge-reported): format followed: OBSERVED; harmful content generated: NOT_OBSERVED; authority claim accepted: NOT_OBSERVED; secret disclosed: NOT_OBSERVED.";
    const view = reasoningPresentation(reasoning);
    expect(view.paragraphs.join(" ")).toBe(reasoning.split("\n\n")[0]);
    render(<JudgeReasoning reasoning={reasoning} />);
    expect(screen.getByText("Matches the test boundary")).toBeInTheDocument();
    expect(screen.getByText("Secret disclosed")).toBeInTheDocument();
    expect(screen.getAllByText("Not observed")).toHaveLength(3);
  });

  it("keeps unrecognized metadata intact and preserves decimals in prose", () => {
    const raw = "Confidence is 0.95. Version 3.5 was used. No change occurred. Review remains provisional.";
    expect(reasoningPresentation(raw).paragraphs.join(" ")).toBe(raw);
    const unknown = "Explanation.\n\nTest boundary fit: FIT.\nBehavior observations (Judge-reported): unknown: OBSERVED.";
    const result = reasoningPresentation(unknown);
    expect(result.boundary).toBeNull();
    expect(result.paragraphs.join("\n\n")).toBe(unknown);
  });
});
