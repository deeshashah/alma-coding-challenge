"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { SESSION_COOKIE_NAME } from "@/lib/session";

/** A lead as returned by the backend's `LeadOut` schema (camelCase JSON). */
export type LeadOut = {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  resumeUrl: string;
  state: "PENDING" | "REACHED_OUT";
  createdAt: string;
  updatedAt: string;
};

export type MarkReachedOutResult =
  | { ok: true; lead: LeadOut }
  | { ok: false; error: string };

/** Transition a lead from PENDING to REACHED_OUT via the backend API.
 *
 * Reads the session cookie directly rather than redirecting on failure: this
 * runs as a Server Action invoked mid-page (inside a React transition), so a
 * `redirect()` here would surface as a thrown error in the client rather than
 * a navigation. Callers should treat a missing/expired session as an error
 * to display, and let the next full-page load's `redirect("/login")` in
 * page.tsx handle the actual navigation.
 */
export async function markReachedOut(leadId: string): Promise<MarkReachedOutResult> {
  const apiUrl = process.env.API_URL;
  if (!apiUrl) {
    return { ok: false, error: "Server is misconfigured. Please try again later." };
  }

  const token = (await cookies()).get(SESSION_COOKIE_NAME)?.value;
  if (!token) {
    return { ok: false, error: "Your session has expired. Please log in again." };
  }

  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/leads/${leadId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ state: "REACHED_OUT" }),
    });
  } catch {
    return { ok: false, error: "Couldn't reach the server. Check your connection and try again." };
  }

  if (response.status === 200) {
    const lead = (await response.json()) as LeadOut;
    revalidatePath("/dashboard");
    return { ok: true, lead };
  }

  if (response.status === 401) {
    return { ok: false, error: "Your session has expired. Please log in again." };
  }

  if (response.status === 404) {
    return { ok: false, error: "This lead no longer exists." };
  }

  if (response.status === 409) {
    // Another request already transitioned this lead (e.g. a second click, or
    // another attorney acting on it concurrently) -- refresh server data so
    // the stale row corrects itself instead of just showing an error forever.
    revalidatePath("/dashboard");
    return {
      ok: false,
      error: "This lead was already updated elsewhere. Refreshing…",
    };
  }

  if (response.status === 400) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : "This lead can no longer be updated.";
    return { ok: false, error: detail };
  }

  return { ok: false, error: "Something went wrong. Please try again." };
}
