import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookieSet = vi.fn();
const cookiesMock = vi.fn(async () => ({ set: cookieSet }));
const redirectMock = vi.fn((url: string) => {
  throw new Error(`NEXT_REDIRECT:${url}`);
});

vi.mock("next/headers", () => ({
  cookies: () => cookiesMock(),
}));

vi.mock("next/navigation", () => ({
  redirect: (url: string) => redirectMock(url),
}));

const { submitLogin } = await import("./actions");
const { parseErrorDetail, sanitizeRedirectTo } = await import("./helpers");
const { SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS } = await import("@/lib/session");

const initialState = { status: "idle" as const };

function buildLoginFormData(overrides: Partial<Record<string, string>> = {}): FormData {
  const formData = new FormData();
  formData.set("email", overrides.email ?? "attorney@example.com");
  formData.set("password", overrides.password ?? "hunter2");
  if (overrides.redirectTo !== undefined) formData.set("redirectTo", overrides.redirectTo);
  return formData;
}

describe("sanitizeRedirectTo", () => {
  it("accepts a same-site absolute path", () => {
    expect(sanitizeRedirectTo("/dashboard?state=PENDING")).toBe("/dashboard?state=PENDING");
  });

  it("falls back to /dashboard for a missing value", () => {
    expect(sanitizeRedirectTo(null)).toBe("/dashboard");
  });

  it("falls back to /dashboard for a non-string value", () => {
    const file = new File(["x"], "x.txt");
    expect(sanitizeRedirectTo(file)).toBe("/dashboard");
  });

  it("falls back to /dashboard for a value that doesn't start with /", () => {
    expect(sanitizeRedirectTo("dashboard")).toBe("/dashboard");
  });

  it("rejects a protocol-relative //host open-redirect payload", () => {
    expect(sanitizeRedirectTo("//evil.example.com")).toBe("/dashboard");
  });
});

describe("parseErrorDetail", () => {
  it("returns a plain string detail as-is", () => {
    expect(parseErrorDetail("Invalid email or password.")).toBe("Invalid email or password.");
  });

  it("returns the first message from a pydantic error list", () => {
    const detail = [{ msg: "field required" }, { msg: "second error" }];
    expect(parseErrorDetail(detail)).toBe("field required");
  });

  it("falls back to a generic message for an unrecognized shape", () => {
    expect(parseErrorDetail(undefined)).toBe("Something went wrong. Please try again.");
  });
});

describe("submitLogin", () => {
  const originalApiUrl = process.env.API_URL;

  beforeEach(() => {
    process.env.API_URL = "https://api.test";
    cookieSet.mockClear();
    redirectMock.mockClear();
    cookiesMock.mockClear();
  });

  afterEach(() => {
    process.env.API_URL = originalApiUrl;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns a misconfiguration error when API_URL is unset", async () => {
    delete process.env.API_URL;
    const result = await submitLogin(initialState, buildLoginFormData());
    expect(result).toEqual({
      status: "error",
      error: "Server is misconfigured. Please try again later.",
    });
  });

  it("returns a network error when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const result = await submitLogin(initialState, buildLoginFormData());
    expect(result).toEqual({
      status: "error",
      error: "Couldn't reach the server. Check your connection and try again.",
    });
  });

  it("returns an invalid-credentials error on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401, ok: false }));
    const result = await submitLogin(initialState, buildLoginFormData());
    expect(result).toEqual({ status: "error", error: "Invalid email or password." });
  });

  it("maps a non-401 error status's string detail to the form error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 400,
        ok: false,
        json: vi.fn().mockResolvedValue({ detail: "Malformed request." }),
      }),
    );
    const result = await submitLogin(initialState, buildLoginFormData());
    expect(result).toEqual({ status: "error", error: "Malformed request." });
  });

  it("maps a non-401 error status's pydantic-list detail to the form error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 422,
        ok: false,
        json: vi.fn().mockResolvedValue({ detail: [{ msg: "value is not a valid email address" }] }),
      }),
    );
    const result = await submitLogin(initialState, buildLoginFormData());
    expect(result).toEqual({ status: "error", error: "value is not a valid email address" });
  });

  it("sets the session cookie and redirects to the sanitized target on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: vi.fn().mockResolvedValue({ token: "jwt-token" }),
      }),
    );

    await expect(
      submitLogin(initialState, buildLoginFormData({ redirectTo: "/dashboard?state=PENDING" })),
    ).rejects.toThrow("NEXT_REDIRECT:/dashboard?state=PENDING");

    expect(cookieSet).toHaveBeenCalledWith(
      SESSION_COOKIE_NAME,
      "jwt-token",
      expect.objectContaining({
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: SESSION_MAX_AGE_SECONDS,
      }),
    );
    expect(redirectMock).toHaveBeenCalledWith("/dashboard?state=PENDING");
  });

  it("redirects to the default /dashboard when redirectTo is an open-redirect payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: vi.fn().mockResolvedValue({ token: "jwt-token" }),
      }),
    );

    await expect(
      submitLogin(initialState, buildLoginFormData({ redirectTo: "//evil.example.com" })),
    ).rejects.toThrow("NEXT_REDIRECT:/dashboard");
  });
});
