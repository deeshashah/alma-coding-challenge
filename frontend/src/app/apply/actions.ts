"use server";

import { parseErrorDetail, type ApplyFormState } from "./helpers";

export async function submitLead(
  _prevState: ApplyFormState,
  formData: FormData,
): Promise<ApplyFormState> {
  const apiUrl = process.env.API_URL;
  if (!apiUrl) {
    return {
      status: "error",
      fieldErrors: {},
      formError: "Server is misconfigured. Please try again later.",
    };
  }

  let response: Response;
  try {
    response = await fetch(`${apiUrl}/api/leads`, {
      method: "POST",
      body: formData,
    });
  } catch {
    return {
      status: "error",
      fieldErrors: {},
      formError: "Couldn't reach the server. Check your connection and try again.",
    };
  }

  if (response.status === 201) {
    const lead = await response.json();
    return {
      status: "success",
      fieldErrors: {},
      lead: {
        id: lead.id,
        firstName: lead.firstName,
        lastName: lead.lastName,
        email: lead.email,
      },
    };
  }

  if (response.status === 413) {
    return {
      status: "error",
      fieldErrors: { resume: "Resume file is too large (max 5MB)." },
    };
  }

  if (response.status === 400) {
    const body = await response.json().catch(() => null);
    return parseErrorDetail(body?.detail);
  }

  return {
    status: "error",
    fieldErrors: {},
    formError: "Something went wrong. Please try again.",
  };
}
