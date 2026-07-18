import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/session";

/** Gate /dashboard on the presence of a session cookie.
 *
 * This only checks presence, not validity (verifying the JWT signature
 * needs Node APIs unavailable in the Edge runtime middleware runs in).
 * Expired/invalid tokens are caught server-side when the dashboard calls
 * the backend and gets a 401, which redirects to /login from there.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
