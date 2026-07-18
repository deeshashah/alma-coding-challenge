import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ApplyForm from "./ApplyForm";
import { loadResumeFixture, buildOversizedResumeFile } from "@/test-utils/resumeFixture";

const submitLeadMock = vi.fn();

vi.mock("./actions", () => ({
  submitLead: (...args: unknown[]) => submitLeadMock(...args),
}));

afterEach(() => {
  cleanup();
  submitLeadMock.mockReset();
});

describe("ApplyForm", () => {
  it("renders the expected fields and labels", () => {
    render(<ApplyForm />);
    expect(screen.getByRole("heading", { name: "Apply now" })).toBeInTheDocument();
    expect(screen.getByLabelText("First name")).toBeInTheDocument();
    expect(screen.getByLabelText("Last name")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText(/Resume/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit application" })).toBeInTheDocument();
  });

  it("shows client-side validation errors and does not call the action when required fields are empty", async () => {
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByText("First name is required.")).toBeInTheDocument();
    expect(screen.getByText("Last name is required.")).toBeInTheDocument();
    expect(screen.getByText("Email is required.")).toBeInTheDocument();
    expect(screen.getByText("Resume is required.")).toBeInTheDocument();
    expect(submitLeadMock).not.toHaveBeenCalled();
  });

  it("flags an invalid email address client-side", async () => {
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.upload(screen.getByLabelText(/Resume/), loadResumeFixture());
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(submitLeadMock).not.toHaveBeenCalled();
  });

  it("flags a resume with a disallowed extension client-side", async () => {
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    const badFile = new File(["hi"], "resume.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText(/Resume/), badFile);
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByText("Resume must be a PDF, DOC, or DOCX file.")).toBeInTheDocument();
    expect(submitLeadMock).not.toHaveBeenCalled();
  });

  it("flags an oversized resume client-side", async () => {
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.upload(screen.getByLabelText(/Resume/), buildOversizedResumeFile());
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByText("Resume must be under 5MB.")).toBeInTheDocument();
    expect(submitLeadMock).not.toHaveBeenCalled();
  });

  it("clears a field's client error as soon as the user edits it", async () => {
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.click(screen.getByRole("button", { name: "Submit application" }));
    expect(await screen.findByText("First name is required.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("First name"), "A");
    expect(screen.queryByText("First name is required.")).not.toBeInTheDocument();
  });

  it("renders a field error returned from the server action state", async () => {
    submitLeadMock.mockResolvedValue({
      status: "error",
      fieldErrors: { email: "email already registered" },
    });
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.upload(screen.getByLabelText(/Resume/), loadResumeFixture());
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByText("email already registered")).toBeInTheDocument();
  });

  it("renders a form-level error returned from the server action state", async () => {
    submitLeadMock.mockResolvedValue({
      status: "error",
      fieldErrors: {},
      formError: "Something went wrong. Please try again.",
    });
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.upload(screen.getByLabelText(/Resume/), loadResumeFixture());
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Something went wrong. Please try again.",
    );
  });

  it("shows a success message with the created lead's info after a successful submission", async () => {
    submitLeadMock.mockResolvedValue({
      status: "success",
      fieldErrors: {},
      lead: { id: "lead-1", firstName: "Ada", lastName: "Lovelace", email: "ada@example.com" },
    });
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.upload(screen.getByLabelText(/Resume/), loadResumeFixture());
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    expect(await screen.findByRole("heading", { name: "Thanks, Ada!" })).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("disables the submit button while the action is pending", async () => {
    let resolveAction: (value: unknown) => void = () => {};
    submitLeadMock.mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<ApplyForm />);

    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.upload(screen.getByLabelText(/Resume/), loadResumeFixture());
    await user.click(screen.getByRole("button", { name: "Submit application" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled(),
    );

    resolveAction({ status: "idle", fieldErrors: {} });
  });
});
