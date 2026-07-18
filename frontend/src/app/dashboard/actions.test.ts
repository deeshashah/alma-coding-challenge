import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookieGet = vi.fn();
const cookiesMock = vi.fn(async () => ({ get: cookieGet }));
const revalidatePathMock = vi.fn();

vi.mock("next/headers", () => ({
  cookies: () => cookiesMock(),
}));

vi.mock("next/cache", () => ({
  revalidatePath: (path: string) => revalidatePathMock(path),
}));

const { markReachedOut } = await import("./actions");
const { SESSION_COOKIE_NAME } = await import("@/lib/session");

const lead = {
  id: "lead-1",
  firstName: "Ada",
  lastName: "Lovelace",
  email: "ada@example.com",
  resumeUrl: "https://files.test/resume.pdf",
  state: "REACHED_OUT" as const,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-02T00:00:00Z",
};

describe("markReachedOut", () => {
  const originalApiUrl = process.env.API_URL;

  beforeEach(() => {
    process.env.API_URL = "https://api.test";
    cookieGet.mockReturnValue({ value: "jwt-token" });
    revalidatePathMock.mockClear();
    cookiesMock.mockClear();
  });

  afterEach(() => {
    process.env.API_URL = originalApiUrl;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns a misconfiguration error when API_URL is unset", async () => {
    delete process.env.API_URL;
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "Server is misconfigured. Please try again later." });
  });

  it("returns an expired-session error when there is no session cookie", async () => {
    cookieGet.mockReturnValue(undefined);
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "Your session has expired. Please log in again." });
  });

  it("returns a network error when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({
      ok: false,
      error: "Couldn't reach the server. Check your connection and try again.",
    });
  });

  it("returns the updated lead and revalidates the dashboard on 200", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: vi.fn().mockResolvedValue(lead),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await markReachedOut("lead-1");

    expect(result).toEqual({ ok: true, lead });
    expect(revalidatePathMock).toHaveBeenCalledWith("/dashboard");
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.test/api/leads/lead-1",
      expect.objectContaining({
        method: "PATCH",
        headers: expect.objectContaining({ Authorization: `Bearer jwt-token` }),
      }),
    );
  });

  it("returns an expired-session error on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401 }));
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "Your session has expired. Please log in again." });
  });

  it("returns a not-found error on 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 404 }));
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "This lead no longer exists." });
  });

  it("returns the backend's detail message on 400", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 400,
        json: vi.fn().mockResolvedValue({ detail: "Lead is already reached out." }),
      }),
    );
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "Lead is already reached out." });
  });

  it("falls back to a generic message on 400 without a string detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 400,
        json: vi.fn().mockResolvedValue(null),
      }),
    );
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "This lead can no longer be updated." });
  });

  it("falls back to a generic error for an unhandled status code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 500 }));
    const result = await markReachedOut("lead-1");
    expect(result).toEqual({ ok: false, error: "Something went wrong. Please try again." });
  });
});
