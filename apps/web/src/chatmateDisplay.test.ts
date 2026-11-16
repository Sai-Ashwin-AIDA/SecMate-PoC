import { describe, expect, it } from "vitest";
import { chatMateErrorMessage } from "./chatmateDisplay";
import { evaluatedRun } from "./chatmateTestFixtures";

describe("ChatMate failure reasons", () => {
  it("preserves the concise backend reason rather than replacing it with an error-code label", () => {
    const error_message = "Groq rejected the generation request: reasoning_effort is unsupported for this model.";
    expect(chatMateErrorMessage(evaluatedRun({ error_code: "PROVIDER_REQUEST_REJECTED", error_message }))).toBe(error_message);
  });

  it.each([
    ["context_length_exceeded", "The requested input exceeds this model's maximum context length.", "context limit"],
    ["insufficient_quota", "Your project quota is exhausted.", "quota was exhausted"],
    ["rate_limit_exceeded", "Too many requests. Retry after 60 seconds.", "rate limit"],
    ["json_validate_failed", "Failed to generate JSON. Adjust your prompt.", "required format"],
    ["unsupported_parameter", "reasoning_effort is not supported with this model.", "request parameter"],
  ])("maps legacy %s while retaining the actual provider reason", (code, reason, expected) => {
    const error_message = `Candidate generation failed.\nTraceback (most recent call last):\n${"  File \"worker.py\", line 10\n".repeat(40)}BadRequestError: Error code: 400 - ${JSON.stringify({ error: { code, message: reason } })}`;
    const message = chatMateErrorMessage(evaluatedRun({ error_code: "GENERATION_FAILED", error_message }));
    expect(message).toContain(expected);
    expect(message).toContain(reason);
    expect(message).not.toMatch(/Traceback|worker\.py|BadRequestError/);
    expect(message.length).toBeLessThan(400);
  });

  it("retains an unknown exception's reason rather than a generic provider failure", () => {
    const error_message = `Traceback (most recent call last):\n${"  File \"worker.py\", line 10\n".repeat(40)}RuntimeError: The candidate artifact could not be written: permission denied on output directory.`;
    expect(chatMateErrorMessage(evaluatedRun({ error_message }))).toBe("The candidate artifact could not be written: permission denied on output directory.");
  });

  it("redacts credentials in visible provider reasons", () => {
    const message = chatMateErrorMessage(evaluatedRun({ error_message: "Provider rejected api_key=sk-secret-value and Bearer PRIVATE_TOKEN." }));
    expect(message).toContain("Provider rejected");
    expect(message).not.toMatch(/sk-secret-value|PRIVATE_TOKEN/);
  });
});
