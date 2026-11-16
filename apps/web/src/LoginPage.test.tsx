import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

describe("LoginPage", () => {
  it("rejects empty preview credentials", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    render(<LoginPage onLogin={onLogin} />);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a username and password");
    expect(onLogin).not.toHaveBeenCalled();
  });

  it("submits non-empty preview credentials", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue({ email: "reviewer", displayName: "reviewer", role: "Local Preview" });
    render(<LoginPage onLogin={onLogin} />);
    await user.type(screen.getByLabelText("Username"), "reviewer");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(onLogin).toHaveBeenCalledWith("reviewer", "secret");
  });

  it("shows SSO as a neutral preview notice", async () => {
    const user = userEvent.setup();
    render(<LoginPage onLogin={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /Continue with SSO/i }));
    expect(screen.getByRole("status")).toHaveTextContent("Enterprise SSO is not connected");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
