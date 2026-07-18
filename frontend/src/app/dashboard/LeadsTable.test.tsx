import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LeadsTable from "./LeadsTable";
import type { LeadOut } from "./actions";

const markReachedOutMock = vi.fn();

vi.mock("./actions", () => ({
  markReachedOut: (...args: unknown[]) => markReachedOutMock(...args),
}));

afterEach(() => {
  cleanup();
  markReachedOutMock.mockReset();
});

const pendingLead: LeadOut = {
  id: "lead-1",
  firstName: "Ada",
  lastName: "Lovelace",
  email: "ada@example.com",
  resumeUrl: "https://files.test/ada.pdf",
  state: "PENDING",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
};

const reachedOutLead: LeadOut = {
  ...pendingLead,
  id: "lead-2",
  firstName: "Grace",
  lastName: "Hopper",
  email: "grace@example.com",
  state: "REACHED_OUT",
};

describe("LeadsTable", () => {
  it("shows an empty state when there are no leads", () => {
    render(<LeadsTable leads={[]} />);
    expect(screen.getByText("No leads found.")).toBeInTheDocument();
  });

  it("renders every field for a lead, with a resume link", () => {
    render(<LeadsTable leads={[pendingLead]} />);

    expect(screen.getByText("lead-1")).toBeInTheDocument();
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByText("Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    const resumeLink = screen.getByRole("link", { name: "View" });
    expect(resumeLink).toHaveAttribute("href", "https://files.test/ada.pdf");
  });

  it("shows a Mark as Reached Out button only for PENDING leads", () => {
    render(<LeadsTable leads={[pendingLead, reachedOutLead]} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(within(rows[0]).getByRole("button", { name: "Mark as Reached Out" })).toBeInTheDocument();
    expect(within(rows[1]).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rows[1]).getByText("—")).toBeInTheDocument();
  });

  it("optimistically flips a row to Reached Out on click, before the action resolves", async () => {
    let resolveAction: (value: unknown) => void = () => {};
    markReachedOutMock.mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
    );
    const user = userEvent.setup();
    render(<LeadsTable leads={[pendingLead]} />);

    await user.click(screen.getByRole("button", { name: "Mark as Reached Out" }));

    expect(await screen.findByText("Reached Out")).toBeInTheDocument();
    expect(markReachedOutMock).toHaveBeenCalledWith("lead-1");

    resolveAction({ ok: true, lead: { ...pendingLead, state: "REACHED_OUT" } });
  });

  it("shows an inline row error when the action fails, without crashing the table", async () => {
    markReachedOutMock.mockResolvedValue({ ok: false, error: "This lead no longer exists." });
    const user = userEvent.setup();
    render(<LeadsTable leads={[pendingLead]} />);

    await user.click(screen.getByRole("button", { name: "Mark as Reached Out" }));

    expect(await screen.findByText("This lead no longer exists.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Ada")).toBeInTheDocument());
  });
});
