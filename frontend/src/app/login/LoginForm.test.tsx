import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginForm from "./LoginForm";

const submitLoginMock = vi.fn();

vi.mock("./actions", () => ({
  submitLogin: (...args: unknown[]) => submitLoginMock(...args),
}));

afterEach(() => {
  cleanup();
  submitLoginMock.mockReset();
});

describe("LoginForm", () => {
  it("renders the expected fields, labels, and the redirectTo hidden field", () => {
    render(<LoginForm redirectTo="/dashboard?state=PENDING" />);
    expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();

    const hidden = document.querySelector('input[name="redirectTo"]') as HTMLInputElement;
    expect(hidden.value).toBe("/dashboard?state=PENDING");
  });

  it("shows client-side validation errors and does not call the action when fields are empty", async () => {
    const user = userEvent.setup();
    render(<LoginForm redirectTo="/dashboard" />);

    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("Email is required.")).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
    expect(submitLoginMock).not.toHaveBeenCalled();
  });

  it("clears a field's client error as soon as the user edits it", async () => {
    const user = userEvent.setup();
    render(<LoginForm redirectTo="/dashboard" />);

    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByText("Email is required.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Email"), "a");
    expect(screen.queryByText("Email is required.")).not.toBeInTheDocument();
  });

  it("renders a form-level error returned from the server action state", async () => {
    submitLoginMock.mockResolvedValue({ status: "error", error: "Invalid email or password." });
    const user = userEvent.setup();
    render(<LoginForm redirectTo="/dashboard" />);

    await user.type(screen.getByLabelText("Email"), "attorney@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
  });

  it("disables the submit button and shows pending text while the action is pending", async () => {
    let resolveAction: (value: unknown) => void = () => {};
    submitLoginMock.mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<LoginForm redirectTo="/dashboard" />);

    await user.type(screen.getByLabelText("Email"), "attorney@example.com");
    await user.type(screen.getByLabelText("Password"), "devpassword123");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Logging in…" })).toBeDisabled(),
    );

    resolveAction({ status: "idle" });
  });
});
