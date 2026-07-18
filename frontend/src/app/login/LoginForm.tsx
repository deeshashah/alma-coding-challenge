"use client";

import { useActionState, useState } from "react";
import { submitLogin } from "./actions";
import type { LoginFormState } from "./helpers";
import styles from "./login.module.css";

const initialLoginFormState: LoginFormState = { status: "idle" };

type ClientErrors = { email?: string; password?: string };

/** Validate the login form client-side before allowing submission: both
 * fields must be non-empty. This is a UX nicety only — the backend is the
 * source of truth for whether the credentials are actually valid. */
function validateClientSide(formData: FormData): ClientErrors {
  const errors: ClientErrors = {};
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email) errors.email = "Email is required.";
  if (!password) errors.password = "Password is required.";

  return errors;
}

/** Client form for /login: an uncontrolled form wired to the submitLogin
 * Server Action via useActionState, with a client-side non-empty check
 * layered on top for immediate feedback. */
export default function LoginForm({ redirectTo }: { redirectTo: string }) {
  const [state, formAction, pending] = useActionState<LoginFormState, FormData>(
    submitLogin,
    initialLoginFormState,
  );
  const [clientErrors, setClientErrors] = useState<ClientErrors>({});

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    const errors = validateClientSide(new FormData(event.currentTarget));
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      event.preventDefault();
    }
  }

  function clearFieldError(field: keyof ClientErrors) {
    setClientErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  const formError = Object.keys(clientErrors).length > 0 ? undefined : state.error;

  return (
    <form className={styles.form} action={formAction} onSubmit={handleSubmit} noValidate>
      <h1>Log in</h1>
      <p className={styles.subtitle}>Welcome back. Enter your credentials to continue.</p>

      {formError && (
        <p className={styles.formError} role="alert">
          {formError}
        </p>
      )}

      <input type="hidden" name="redirectTo" value={redirectTo} />

      <div className={styles.field}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          aria-invalid={Boolean(clientErrors.email)}
          aria-describedby={clientErrors.email ? "email-error" : undefined}
          onChange={() => clearFieldError("email")}
        />
        {clientErrors.email && (
          <span className={styles.error} id="email-error">
            {clientErrors.email}
          </span>
        )}
      </div>

      <div className={styles.field}>
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={Boolean(clientErrors.password)}
          aria-describedby={clientErrors.password ? "password-error" : undefined}
          onChange={() => clearFieldError("password")}
        />
        {clientErrors.password && (
          <span className={styles.error} id="password-error">
            {clientErrors.password}
          </span>
        )}
      </div>

      <button type="submit" className={styles.submit} disabled={pending}>
        {pending ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}
