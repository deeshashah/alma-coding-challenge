// Pure helpers for the login form. Kept out of actions.ts because a
// "use server" file may only export async functions -- these are plain sync
// functions, needed both internally, by page.tsx, and directly by tests.

export type LoginFormState = {
  status: "idle" | "error";
  error?: string;
};

const DEFAULT_REDIRECT = "/dashboard";

/** Validate a candidate post-login redirect target, guarding against open
 * redirects (must be a same-site absolute path, not a protocol-relative
 * `//host` URL). Falls back to the dashboard when the value is missing or
 * unsafe. Shared by both submitLogin (validates the posted `redirectTo`
 * field) and page.tsx (validates the `from` query param before handing it
 * to the client). */
export function sanitizeRedirectTo(value: FormDataEntryValue | string | null | undefined): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return DEFAULT_REDIRECT;
  }
  return value;
}

/** Map the backend's `{"detail": ...}` shape (string from HTTPException, or a
 * pydantic error list from RequestValidationError) onto a single form-level
 * message. */
export function parseErrorDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }

  return "Something went wrong. Please try again.";
}
