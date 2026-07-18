import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "./middleware";
import { SESSION_COOKIE_NAME } from "@/lib/session";

describe("middleware", () => {
  it("redirects to /login with a `from` param when the session cookie is absent", () => {
    const request = new NextRequest("https://app.test/dashboard/leads");

    const response = middleware(request);

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("from")).toBe("/dashboard/leads");
  });

  it("passes the request through when the session cookie is present", () => {
    const request = new NextRequest("https://app.test/dashboard", {
      headers: { cookie: `${SESSION_COOKIE_NAME}=some-jwt-token` },
    });

    const response = middleware(request);

    // NextResponse.next() carries the special x-middleware-next header and
    // issues no redirect.
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
