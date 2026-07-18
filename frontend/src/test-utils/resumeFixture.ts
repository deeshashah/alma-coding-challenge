import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const FIXTURE_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../backend/tests/fixtures/dummy_resume.pdf",
);

/** Load the small real PDF fixture shared with the backend test suite, as a
 * `File`, so component tests exercise a realistic resume upload instead of a
 * fabricated placeholder blob. */
export function loadResumeFixture(name = "resume.pdf"): File {
  const bytes = readFileSync(FIXTURE_PATH);
  return new File([bytes], name, { type: "application/pdf" });
}

/** Build an oversized (>5MB) synthetic file for exercising the client-side
 * resume size-limit validation. Unlike `loadResumeFixture`, this is
 * deliberately synthetic: it's testing a byte-count boundary, not standing
 * in for real resume content. */
export function buildOversizedResumeFile(name = "big-resume.pdf"): File {
  const bytes = new Uint8Array(5 * 1024 * 1024 + 1);
  return new File([bytes], name, { type: "application/pdf" });
}
