"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS } from "@/lib/session";
import { parseErrorDetail, sanitizeRedirectTo, type LoginFormState } from "./helpers";

/** Server Action for the login form: authenticates against the backend,
 * stores the returned JWT in an httpOnly session cookie, and redirects
 * on success. */
export async function submitLogin(
  _prevState: LoginFormState,
  formData: FormData,
): Promise<LoginFormState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const redirectTo = sanitizeRedirectTo(formData.get("redirectTo"));

  const apiUrl = process.env.API_URL;
  if (!apiUrl) {
    return {
      status: "error",
      error: "Server is misconfigured. Please try again later.",
    };
  }

  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    return {
      status: "error",
      error: "Couldn't reach the server. Check your connection and try again.",
    };
  }

  if (response.status === 401) {
    return { status: "error", error: "Invalid email or password." };
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    return { status: "error", error: parseErrorDetail(body?.detail) };
  }

  const body = await response.json();
  const token: string = body.token;

  (await cookies()).set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });

  redirect(redirectTo);
}
