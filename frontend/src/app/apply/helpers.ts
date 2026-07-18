// Pure helpers for the apply form's error handling. Kept out of actions.ts
// because a "use server" file may only export async functions -- these are
// plain sync functions, needed both internally and directly by tests.

type FieldName = "firstName" | "lastName" | "email" | "resume";

const FIELD_NAMES: FieldName[] = ["firstName", "lastName", "email", "resume"];

export type ApplyFormState = {
  status: "idle" | "error" | "success";
  fieldErrors: Partial<Record<FieldName, string>>;
  formError?: string;
  lead?: { id: string; firstName: string; lastName: string; email: string };
};

function fieldFromString(message: string): FieldName | undefined {
  const lower = message.toLowerCase();
  return FIELD_NAMES.find((name) => lower.includes(name.toLowerCase()));
}

function fieldFromLoc(loc: unknown): FieldName | undefined {
  if (!Array.isArray(loc)) return undefined;
  const last = loc[loc.length - 1];
  return FIELD_NAMES.find((name) => name === last);
}

/** Map the backend's `{"detail": ...}` shape (string from HTTPException, or a
 * pydantic error list from RequestValidationError) onto per-field messages. */
export function parseErrorDetail(detail: unknown): ApplyFormState {
  const fieldErrors: ApplyFormState["fieldErrors"] = {};

  if (typeof detail === "string") {
    const field = fieldFromString(detail);
    return field
      ? { status: "error", fieldErrors: { [field]: detail } }
      : { status: "error", fieldErrors, formError: detail };
  }

  if (Array.isArray(detail)) {
    for (const entry of detail) {
      const field = fieldFromLoc((entry as { loc?: unknown })?.loc);
      const msg = (entry as { msg?: string })?.msg;
      if (field && msg) fieldErrors[field] = msg;
    }
    return Object.keys(fieldErrors).length > 0
      ? { status: "error", fieldErrors }
      : {
          status: "error",
          fieldErrors,
          formError: "Please check your information and try again.",
        };
  }

  return {
    status: "error",
    fieldErrors,
    formError: "Something went wrong. Please try again.",
  };
}
