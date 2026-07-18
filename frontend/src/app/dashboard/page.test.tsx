import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const cookieGet = vi.fn();
const cookiesMock = vi.fn(async () => ({ get: cookieGet }));
const redirectMock = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT:${url}`);
});

vi.mock("next/headers", () => ({
  cookies: () => cookiesMock(),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => redirectMock(url),
  // Real unstable_rethrow lets Next.js's own control-flow errors (redirect,
  // notFound) propagate out of a try/catch instead of being swallowed as a
  // normal error; this mock replicates that specifically for our redirect
  // sentinel so the page's catch block still re-throws it correctly.
  unstable_rethrow: (err: unknown) => {
    if (err instanceof Error && err.message.startsWith("NEXT_REDIRECT:")) {
      throw err;
    }
  },
}));

vi.mock("./StateFilter", () => ({
  default: ({ currentState }: { currentState?: string }) => (
    <div data-testid="state-filter">{currentState ?? "ALL"}</div>
  ),
}));

vi.mock("./LeadsTable", () => ({
  default: ({ leads }: { leads: Array<{ id: string }> }) => (
    <div data-testid="leads-table">{leads.length} leads</div>
  ),
}));

const { default: DashboardPage } = await import("./page");

const searchParams = (state?: string) => Promise.resolve(state ? { state } : {});

describe("DashboardPage", () => {
  const originalApiUrl = process.env.API_URL;

  beforeEach(() => {
    process.env.API_URL = "https://api.test";
  });

  afterEach(() => {
    cleanup();
    process.env.API_URL = originalApiUrl;
    cookieGet.mockReset();
    redirectMock.mockClear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("redirects to /login when there is no session cookie", async () => {
    cookieGet.mockReturnValue(undefined);

    await expect(DashboardPage({ searchParams: searchParams() })).rejects.toThrow(
      "NEXT_REDIRECT:/login",
    );
    expect(redirectMock).toHaveBeenCalledWith("/login");
  });

  it("redirects to /login when the backend responds 401", async () => {
    cookieGet.mockReturnValue({ value: "expired-jwt" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401, ok: false }));

    await expect(DashboardPage({ searchParams: searchParams() })).rejects.toThrow(
      "NEXT_REDIRECT:/login",
    );
    expect(redirectMock).toHaveBeenCalledWith("/login");
  });

  it("shows a load error, not a crash, on other backend failures", async () => {
    cookieGet.mockReturnValue({ value: "some-jwt" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 500, ok: false }));

    render(await DashboardPage({ searchParams: searchParams() }));

    expect(screen.getByText("Couldn't load leads.")).toBeInTheDocument();
    expect(screen.queryByTestId("leads-table")).not.toBeInTheDocument();
  });

  it("shows a load error when API_URL is unset, without crashing", async () => {
    delete process.env.API_URL;
    cookieGet.mockReturnValue({ value: "some-jwt" });

    render(await DashboardPage({ searchParams: searchParams() }));

    expect(screen.getByText("Couldn't load leads.")).toBeInTheDocument();
  });

  it("renders the filter and table with the fetched leads on success", async () => {
    cookieGet.mockReturnValue({ value: "some-jwt" });
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({
        items: [{ id: "lead-1" }, { id: "lead-2" }],
        page: 1,
        pageSize: 20,
        total: 2,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await DashboardPage({ searchParams: searchParams() }));

    expect(screen.getByTestId("leads-table")).toHaveTextContent("2 leads");
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.test/api/leads",
      expect.objectContaining({ headers: { Authorization: "Bearer some-jwt" } }),
    );
  });

  it("forwards a valid state filter to the backend query string and the filter UI", async () => {
    cookieGet.mockReturnValue({ value: "some-jwt" });
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ items: [], page: 1, pageSize: 20, total: 0 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await DashboardPage({ searchParams: searchParams("PENDING") }));

    expect(screen.getByTestId("state-filter")).toHaveTextContent("PENDING");
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.test/api/leads?state=PENDING",
      expect.anything(),
    );
  });

  it("treats an unrecognized state value as \"show all\" rather than passing it through", async () => {
    cookieGet.mockReturnValue({ value: "some-jwt" });
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ items: [], page: 1, pageSize: 20, total: 0 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await DashboardPage({ searchParams: searchParams("NOT_A_REAL_STATE") }));

    expect(screen.getByTestId("state-filter")).toHaveTextContent("ALL");
    expect(fetchMock).toHaveBeenCalledWith("https://api.test/api/leads", expect.anything());
  });
});
