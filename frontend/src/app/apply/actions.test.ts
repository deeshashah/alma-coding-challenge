import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { submitLead } from "./actions";
import { parseErrorDetail, type ApplyFormState } from "./helpers";

const initialState: ApplyFormState = { status: "idle", fieldErrors: {} };

function buildLeadFormData(): FormData {
  const formData = new FormData();
  formData.set("firstName", "Ada");
  formData.set("lastName", "Lovelace");
  formData.set("email", "ada@example.com");
  formData.set("resume", new File(["hello"], "resume.pdf", { type: "application/pdf" }));
  return formData;
}

describe("parseErrorDetail", () => {
  it("maps a plain string detail that mentions a known field onto that field", () => {
    const result = parseErrorDetail("email already registered");
    expect(result).toEqual({ status: "error", fieldErrors: { email: "email already registered" } });
  });

  it("maps a plain string detail with no field match onto a form-level error", () => {
    const result = parseErrorDetail("Something unexpected happened");
    expect(result).toEqual({
      status: "error",
      fieldErrors: {},
      formError: "Something unexpected happened",
    });
  });

  it("maps a pydantic-style error list onto per-field messages by loc", () => {
    const detail = [
      { loc: ["body", "firstName"], msg: "field required" },
      { loc: ["body", "email"], msg: "value is not a valid email address" },
    ];
    const result = parseErrorDetail(detail);
    expect(result).toEqual({
      status: "error",
      fieldErrors: {
        firstName: "field required",
        email: "value is not a valid email address",
      },
    });
  });

  it("falls back to a generic form error when a pydantic list has no matching fields", () => {
    const detail = [{ loc: ["body", "someUnknownField"], msg: "bad value" }];
    const result = parseErrorDetail(detail);
    expect(result).toEqual({
      status: "error",
      fieldErrors: {},
      formError: "Please check your information and try again.",
    });
  });

  it("falls back to a generic error for an unrecognized detail shape", () => {
    const result = parseErrorDetail(null);
    expect(result).toEqual({
      status: "error",
      fieldErrors: {},
      formError: "Something went wrong. Please try again.",
    });
  });
});

describe("submitLead", () => {
  const originalApiUrl = process.env.API_URL;

  beforeEach(() => {
    process.env.API_URL = "https://api.test";
  });

  afterEach(() => {
    process.env.API_URL = originalApiUrl;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns a misconfiguration error when API_URL is unset", async () => {
    delete process.env.API_URL;
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({
      status: "error",
      fieldErrors: {},
      formError: "Server is misconfigured. Please try again later.",
    });
  });

  it("returns a network error when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({
      status: "error",
      fieldErrors: {},
      formError: "Couldn't reach the server. Check your connection and try again.",
    });
  });

  it("returns success with the created lead on 201", async () => {
    const lead = { id: "lead-1", firstName: "Ada", lastName: "Lovelace", email: "ada@example.com" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 201,
        json: vi.fn().mockResolvedValue(lead),
      }),
    );
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({ status: "success", fieldErrors: {}, lead });
  });

  it("maps a 400 with a string detail to a field error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 400,
        json: vi.fn().mockResolvedValue({ detail: "email already registered" }),
      }),
    );
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({
      status: "error",
      fieldErrors: { email: "email already registered" },
    });
  });

  it("maps a 400 with a pydantic error-list detail to field errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 400,
        json: vi.fn().mockResolvedValue({
          detail: [{ loc: ["body", "lastName"], msg: "field required" }],
        }),
      }),
    );
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({
      status: "error",
      fieldErrors: { lastName: "field required" },
    });
  });

  it("returns a resume-specific error on 413", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 413 }));
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({
      status: "error",
      fieldErrors: { resume: "Resume file is too large (max 5MB)." },
    });
  });

  it("falls back to a generic error for an unhandled status code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 500 }));
    const result = await submitLead(initialState, buildLeadFormData());
    expect(result).toEqual({
      status: "error",
      fieldErrors: {},
      formError: "Something went wrong. Please try again.",
    });
  });
});
