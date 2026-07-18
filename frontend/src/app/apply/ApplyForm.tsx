"use client";

import { useActionState, useState } from "react";
import { submitLead } from "./actions";
import type { ApplyFormState } from "./helpers";
import styles from "./apply.module.css";

const initialApplyFormState: ApplyFormState = { status: "idle", fieldErrors: {} };

type FieldName = "firstName" | "lastName" | "email" | "resume";
type ClientErrors = Partial<Record<FieldName, string>>;

const ALLOWED_RESUME_EXTENSIONS = [".pdf", ".doc", ".docx"];
const MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const RESUME_ACCEPT =
  ".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function validateClientSide(formData: FormData): ClientErrors {
  const errors: ClientErrors = {};
  const firstName = String(formData.get("firstName") ?? "").trim();
  const lastName = String(formData.get("lastName") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const resume = formData.get("resume");

  if (!firstName) errors.firstName = "First name is required.";
  if (!lastName) errors.lastName = "Last name is required.";
  if (!email) errors.email = "Email is required.";
  else if (!EMAIL_PATTERN.test(email)) errors.email = "Enter a valid email address.";

  if (!(resume instanceof File) || resume.size === 0) {
    errors.resume = "Resume is required.";
  } else {
    const lowerName = resume.name.toLowerCase();
    const hasAllowedExtension = ALLOWED_RESUME_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!hasAllowedExtension) {
      errors.resume = "Resume must be a PDF, DOC, or DOCX file.";
    } else if (resume.size > MAX_RESUME_SIZE_BYTES) {
      errors.resume = "Resume must be under 5MB.";
    }
  }

  return errors;
}

export default function ApplyForm() {
  const [state, formAction, pending] = useActionState<ApplyFormState, FormData>(
    submitLead,
    initialApplyFormState,
  );
  const [clientErrors, setClientErrors] = useState<ClientErrors>({});

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    const fd = new FormData(event.currentTarget);
    const r = fd.get("resume") as File;
    console.log("DEBUG resume name/size/instanceof", r?.name, r?.size, r instanceof File);
    const errors = validateClientSide(fd);
    console.log("DEBUG errors=", errors);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      event.preventDefault();
    }
  }

  function clearFieldError(field: FieldName) {
    setClientErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  if (state.status === "success" && state.lead) {
    return (
      <div className={styles.success} role="status">
        <h1>Thanks, {state.lead.firstName}!</h1>
        <p>
          We&apos;ve received your application and will reach out to{" "}
          <strong>{state.lead.email}</strong> soon.
        </p>
      </div>
    );
  }

  const errors: ClientErrors = { ...state.fieldErrors, ...clientErrors };
  const formError = Object.keys(clientErrors).length > 0 ? undefined : state.formError;

  return (
    <form className={styles.form} action={formAction} onSubmit={handleSubmit} noValidate>
      <h1>Apply now</h1>
      <p className={styles.subtitle}>Tell us about yourself and share your resume.</p>

      {formError && (
        <p className={styles.formError} role="alert">
          {formError}
        </p>
      )}

      <div className={styles.field}>
        <label htmlFor="firstName">First name</label>
        <input
          id="firstName"
          name="firstName"
          type="text"
          autoComplete="given-name"
          defaultValue=""
          aria-invalid={Boolean(errors.firstName)}
          aria-describedby={errors.firstName ? "firstName-error" : undefined}
          onChange={() => clearFieldError("firstName")}
        />
        {errors.firstName && (
          <span className={styles.error} id="firstName-error">
            {errors.firstName}
          </span>
        )}
      </div>

      <div className={styles.field}>
        <label htmlFor="lastName">Last name</label>
        <input
          id="lastName"
          name="lastName"
          type="text"
          autoComplete="family-name"
          aria-invalid={Boolean(errors.lastName)}
          aria-describedby={errors.lastName ? "lastName-error" : undefined}
          onChange={() => clearFieldError("lastName")}
        />
        {errors.lastName && (
          <span className={styles.error} id="lastName-error">
            {errors.lastName}
          </span>
        )}
      </div>

      <div className={styles.field}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? "email-error" : undefined}
          onChange={() => clearFieldError("email")}
        />
        {errors.email && (
          <span className={styles.error} id="email-error">
            {errors.email}
          </span>
        )}
      </div>

      <div className={styles.field}>
        <label htmlFor="resume">Resume (PDF, DOC, or DOCX, max 5MB)</label>
        <input
          id="resume"
          name="resume"
          type="file"
          accept={RESUME_ACCEPT}
          aria-invalid={Boolean(errors.resume)}
          aria-describedby={errors.resume ? "resume-error" : undefined}
          onChange={() => clearFieldError("resume")}
        />
        {errors.resume && (
          <span className={styles.error} id="resume-error">
            {errors.resume}
          </span>
        )}
      </div>

      <button type="submit" className={styles.submit} disabled={pending}>
        {pending ? "Submitting…" : "Submit application"}
      </button>
    </form>
  );
}
