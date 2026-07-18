# Prompt Log

Representative prompts from building this app with Claude Code. The working pattern throughout: I drove design and direction, Claude executed.

- I made the calls on data model, API contracts, and edge cases (dedupe vs. always-insert, concurrency handling, single attorney inbox) before any implementation started. See `SYSTEM_DESIGN.md` and `DESIGN_DECISIONS.md`.
- Once a decision was made, implementation was handed off as a scoped, specific prompt. Claude wrote the actual code.
- I reviewed the output, asked follow-up questions when something looked off, and only accepted a step as done once the test suite was green and (for user-facing features) manually verified.

The ten prompts below were issued in sequence, each building on the last, to take the app from an empty repo to a working end-to-end system.

1. Check docs/SYSTEM_DESIGN.md and set up SQLite + SQLAlchemy in backend/. Build the Lead model exactly like the spec says (fields, PENDING/REACHED_OUT state, timestamps) and add a startup hook so tables get created if they're missing. No endpoints yet, just the model and DB setup.

2. Now build POST /api/leads per the design doc. Multipart form (firstName, lastName, email, resume), validate everything including file type/size, save the resume locally to uploads/resumes/, create a PENDING lead, return it as JSON. No auth on this one, it's public.

3. Add an email abstraction, just an interface with a console/log version for now so it's easy to run locally, swap in real SMTP later. Wire it into POST /api/leads so it sends a confirmation to the prospect and a notification to the attorney, address from an env var. Keep it synchronous for now.

4. Add attorney auth. User table per the design doc, POST /api/auth/login that issues a JWT, password hashing, and a reusable dependency to protect routes with. Also add a way to seed one test attorney from env vars so I can log in locally.

5. Add the internal endpoints from the design doc, all behind the auth dependency from the last step: GET /api/leads (list, optional state filter), GET /api/leads/:id, and PATCH /api/leads/:id. Only PENDING to REACHED_OUT is allowed, reject anything else with a 400.

6. On the frontend, build the public lead form at /apply. First name, last name, email, resume upload, client-side validation, submit to POST /api/leads. Show a success state after submitting and surface any validation/server errors.

7. Build the login page too. Posts to POST /api/auth/login, stores the token in an httpOnly cookie (don't put the JWT in localStorage if you can avoid it), redirects to the dashboard on success, shows an error for bad credentials.

8. Build the internal dashboard. Auth-protected, redirect to login if there's no valid session. Table of leads from GET /api/leads with all the fields, a state filter, and a "Mark as Reached Out" button per row that calls PATCH /api/leads/:id, updating the row optimistically or on refetch.

9. Add backend tests, pytest, covering lead creation validation, file upload handling, state transition rules (both valid and invalid), and auth protection on the internal routes. Add a couple of frontend tests too, for the lead form's validation and the dashboard's state-transition action.

10. Write a dev script, dev.sh or a package.json/Makefile target, that starts backend and frontend together. Also a basic smoke-test script that hits /api/health, submits a test lead, logs in, and checks it shows up in the dashboard. This is the backlog item on local test and deploy.

## After the initial build

The prompts above got a working app end to end. Everything after that was iterative: reviewing what got built, asking pointed questions about edge cases the initial implementation hadn't considered, and directing specific fixes. Two examples where that follow-up work mattered most are detailed in `AGENT_USAGE.md`, under "Where the agent got it wrong": the concurrency race on the lead-state transition, and the dedupe/upsert approach that would have let a public resubmission silently reset attorney-owned state. Neither was something Claude flagged on its own. Both came from asking "what happens if" questions after the first pass was already built.

A few of the later prompts, kept verbatim, show that same pattern applied to hardening rather than new features — I'd already found the problem myself before writing the prompt, and gave the exact fix and how to verify it, not just a symptom to go chase:

1. In backend/, the dev dependency httpx2 in requirements-dev.txt is an impostor of the real httpx package (it impersonates httpx's metadata but ships from a fake pydantic/httpx2 repo and pulls httpcore2/truststore). The local venv's starlette/testclient.py was also hand-patched to import httpx2 as httpx, which is the only reason the tests currently pass. Fix this properly: (1) change httpx2 to httpx in backend/requirements-dev.txt; (2) pip uninstall -y httpx2 httpcore2 and any other off-name deps it pulled; (3) delete and recreate the venv from scratch (rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt) so the patched Starlette is discarded; (4) confirm .venv/lib/.../starlette/testclient.py imports the real httpx, and that .venv/bin/pytest still passes all tests against the unmodified Starlette. Report the final test count.

2. In frontend/src/app/dashboard/page.tsx, the catch block around the leads fetch does response = new Response(null, { status: 0 }). The Response constructor throws RangeError for any status outside 200–599, so on a network failure the catch itself throws uncaught and the whole dashboard render crashes instead of showing the intended "Couldn't load leads." message. Fix it by setting loadError = true directly in the catch and skipping the response handling (don't fabricate a sentinel Response). Verify the graceful error UI renders when the backend is down.

3. Following README.md's "Getting Started" literally, a reviewer can't log into the internal dashboard: uvicorn is started without JWT_SECRET_KEY (auth 500s) or the SEED_ATTORNEY_* vars (no attorney account is ever created). Fix the quickstart so it works end-to-end: add a backend/.env.example containing JWT_SECRET_KEY, SEED_ATTORNEY_EMAIL, SEED_ATTORNEY_PASSWORD, SEED_ATTORNEY_NAME (with sensible local-dev defaults), have the backend auto-load it (e.g. via python-dotenv in main.py, or document exporting them / cp .env.example .env), and update the backend "Getting Started" steps to include this before uvicorn. Confirm that a fresh clone → documented steps lets you submit a lead, log in with the seeded attorney, and see the lead in the dashboard.
