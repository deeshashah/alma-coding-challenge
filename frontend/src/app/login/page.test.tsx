import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import LoginPage from "./page";

afterEach(() => {
  cleanup();
});

describe("LoginPage", () => {
  it("passes a safe `from` path through as the redirect target", async () => {
    const jsx = await LoginPage({ searchParams: Promise.resolve({ from: "/dashboard/leads" }) });
    const { container } = render(jsx);
    const hidden = container.querySelector('input[name="redirectTo"]') as HTMLInputElement;
    expect(hidden.value).toBe("/dashboard/leads");
  });

  it("falls back to /dashboard when `from` is absent", async () => {
    const jsx = await LoginPage({ searchParams: Promise.resolve({}) });
    const { container } = render(jsx);
    const hidden = container.querySelector('input[name="redirectTo"]') as HTMLInputElement;
    expect(hidden.value).toBe("/dashboard");
  });

  it("falls back to /dashboard when `from` is a protocol-relative open-redirect attempt", async () => {
    const jsx = await LoginPage({
      searchParams: Promise.resolve({ from: "//evil.example.com" }),
    });
    const { container } = render(jsx);
    const hidden = container.querySelector('input[name="redirectTo"]') as HTMLInputElement;
    expect(hidden.value).toBe("/dashboard");
  });
});
