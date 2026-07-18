import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => "/dashboard",
}));

const { default: StateFilter } = await import("./StateFilter");

afterEach(() => {
  cleanup();
  pushMock.mockReset();
});

describe("StateFilter", () => {
  it("defaults to \"All\" when no currentState is given", () => {
    render(<StateFilter />);
    expect(screen.getByLabelText("Filter leads by state")).toHaveValue("ALL");
  });

  it("reflects the given currentState as the selected value", () => {
    render(<StateFilter currentState="REACHED_OUT" />);
    expect(screen.getByLabelText("Filter leads by state")).toHaveValue("REACHED_OUT");
  });

  it("pushes ?state=PENDING when Pending is selected", async () => {
    const user = userEvent.setup();
    render(<StateFilter />);

    await user.selectOptions(screen.getByLabelText("Filter leads by state"), "Pending");

    expect(pushMock).toHaveBeenCalledWith("/dashboard?state=PENDING");
  });

  it("pushes the bare pathname (no query param) when All is selected", async () => {
    const user = userEvent.setup();
    render(<StateFilter currentState="PENDING" />);

    await user.selectOptions(screen.getByLabelText("Filter leads by state"), "All");

    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });
});
