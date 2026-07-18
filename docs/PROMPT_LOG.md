# Prompt Log

Representative prompts from building this app with Claude Code. The working pattern throughout: I drove design and direction, Claude executed.

- I made the calls on data model, API contracts, and edge cases (dedupe vs. always-insert, concurrency handling, single attorney inbox) before any implementation started. See `SYSTEM_DESIGN.md` and `DESIGN_DECISIONS.md`.
- Once a decision was made, implementation was handed off as a scoped, specific prompt. Claude wrote the actual code.
- I reviewed the output, asked follow-up questions when something looked off, and only accepted a step as done once the test suite was green and (for user-facing features) manually verified.

The ten prompts below were issued in sequence, each building on the last, to take the app from an empty repo to a working end-to-end system. Kept verbatim, including punctuation, since altering a direct quote would misrepresent the actual record.

1. Read `docs/SYSTEM_DESIGN.md`. In `backend/`, add SQLite + SQLAlchemy, define the Lead model exactly as specified (fields, PENDING/REACHED_OUT enum state, timestamps), and wire up a startup hook that creates the tables if they don't exist. Don't add any endpoints yet — just the model and DB session setup.

2. In `backend/`, implement `POST /api/leads` per `docs/SYSTEM_DESIGN.md`: accepts multipart/form-data (firstName, lastName, email, resume file), validates the fields and file type/size, saves the resume to a local uploads/resumes/ folder, creates a Lead row with state PENDING, and returns the created lead as JSON. No auth on this route.

3. Add an email-sending abstraction in `backend/` (a simple interface with a console/log-based implementation for local dev, easy to swap for real SMTP later). Call it from `POST /api/leads` to send a confirmation email to the prospect and a notification email to a hardcoded attorney address (from an env var). Keep it synchronous for now.

4. Add attorney auth to `backend/`: a User table (per `docs/SYSTEM_DESIGN.md`), a `POST /api/auth/login` endpoint issuing a JWT, password hashing, and a reusable auth dependency for protecting routes. Add a script or startup seed to create one test attorney user from env vars for local dev.

5. In `backend/`, add the internal endpoints from `docs/SYSTEM_DESIGN.md`, all protected by the auth dependency from the previous step: `GET /api/leads` (list, optional state filter), `GET /api/leads/:id`, and `PATCH /api/leads/:id` (only allows PENDING to REACHED_OUT, rejects other transitions with 400).

6. In `frontend/`, build the public lead form at `/apply` (or similar): first name, last name, email, resume upload, client-side validation, submits to the backend's `POST /api/leads`, shows a success state on submit and surfaces validation/server errors.

7. In `frontend/`, build a login page that posts to `POST /api/auth/login`, stores the token (httpOnly cookie or similar — avoid localStorage for the JWT if possible), and redirects to the dashboard on success, with an error state for bad credentials.

8. In `frontend/`, build the internal dashboard (auth-protected route/middleware that redirects to login if no valid session): a table of leads from `GET /api/leads` showing all fields, a filter by state, and a "Mark as Reached Out" action per row calling `PATCH /api/leads/:id`, updating the row optimistically or on refetch.

9. Add backend tests (pytest) covering: lead creation validation, file upload handling, state transition rules (valid and invalid), and auth-protection on internal routes. Add a couple of frontend tests for the lead form's validation and the dashboard's state-transition action.

10. Write a local dev script (`./dev.sh` or package.json/Makefile target) that starts the backend and frontend together, and a basic smoke-test script that hits `/api/health`, submits a test lead, logs in, and confirms it appears in the dashboard list. This addresses the `BACKLOG.md` item on local test and deploy.

## After the initial build

The prompts above got a working app end-to-end. Everything after that was iterative: reviewing what got built, asking pointed questions about edge cases the initial implementation hadn't considered, and directing specific fixes. Two examples where that follow-up work mattered most are detailed in `AGENT_USAGE.md`, under "Where the agent got it wrong": the concurrency race on the lead-state transition, and the dedupe/upsert approach that would have let a public resubmission silently reset attorney-owned state. Neither was something Claude flagged on its own; both came from asking "what happens if" questions after the first pass was already built.
