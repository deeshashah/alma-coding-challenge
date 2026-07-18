import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const cookieGet = vi.fn();
const cookiesMock = vi.fn(async () => ({ get: cookieGet }));

vi.mock("next/headers", () => ({
  cookies: () => cookiesMock(),
}));

const { default: Home } = await import("./page");

afterEach(() => {
  cleanup();
  cookieGet.mockReset();
  vi.unstubAllGlobals();
});

describe("Home", () => {
  it("always links applicants to /apply", async () => {
    cookieGet.mockReturnValue(undefined);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

    render(await Home());

    expect(screen.getByRole("link", { name: "Apply now" })).toHaveAttribute("href", "/apply");
  });

  it("links attorneys to /login when no session cookie is present", async () => {
    cookieGet.mockReturnValue(undefined);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

    render(await Home());

    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
  });

  it("links attorneys to /dashboard when a session cookie is present", async () => {
    cookieGet.mockReturnValue({ value: "some-jwt" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

    render(await Home());

    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("shows Operational status when the backend health check succeeds", async () => {
    cookieGet.mockReturnValue(undefined);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

    render(await Home());

    expect(screen.getByText(/API status:/)).toHaveTextContent("Operational");
  });

  it("shows Unreachable status when the backend health check fails", async () => {
    cookieGet.mockReturnValue(undefined);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    render(await Home());

    expect(screen.getByText(/API status:/)).toHaveTextContent("Unreachable");
  });
});
