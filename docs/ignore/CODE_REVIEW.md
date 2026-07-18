# Code Review: Weaknesses and Coverage

Review of the full codebase against the assignment's functional and tech requirements. Findings are tiered **Critical, Medium, Okay**. A requirements-coverage matrix (implemented vs. TODO) is at the end.

Overall: the app is functionally complete and cleanly layered (routes, services, models, schemas, validators on the backend; App Router with Server Actions on the frontend). Backend suite is 76 passing tests. The issues below are the gaps.

This is a point-in-time snapshot. Several of these findings (notably #1, #2, #3) have since been fixed; see `SESSION_SUMMARY.md` and the current code for what's still open.

---

## Critical

### 1. Test dependency is an impostor package (`httpx2`), not `httpx`

- **Where:** `backend/requirements-dev.txt` lists `httpx2`. The installed venv also has `starlette/testclient.py` hand-patched to `import httpx2 as httpx` (real Starlette imports `httpx`).
- **Why it's critical:**
  - `httpx2` is not the standard HTTP client. It impersonates real `httpx`'s identity (author "Tom Christie", summary "The next generation HTTP client") but ships from a fake `github.com/pydantic/httpx2` repo and pulls equally off-name deps (`httpcore2`, `truststore`). This is the classic typosquat/dependency-confusion shape. Whatever is published under that name on PyPI gets pulled and its code runs on the dev/CI machine during `pytest`.
  - It's also broken for anyone else: real `httpx` is absent from both requirements files and from the venv. A clean `pip install -r requirements-dev.txt` on an unmodified Starlette would fail at `from fastapi.testclient import TestClient` (Starlette raises "requires the httpx package"). The suite only passes here because this venv's Starlette was manually edited, and that edit is not, and cannot be, committed (`.venv/` is gitignored).
- **Fix:** replace `httpx2` with `httpx` in `requirements-dev.txt`, `pip uninstall httpx2 httpcore2`, reinstall real `httpx`, and recreate the venv from scratch to discard the patched Starlette. Then confirm the suite still passes against unmodified Starlette. I scanned the `httpx2` source and found no obvious import-time payload, no `.pth`/`sitecustomize` hooks, but "looks benign on a quick read" is not a reason to keep an unvetted impostor dependency.

---

## Medium

### 2. `new Response(null, { status: 0 })` crashes the dashboard on backend-unreachable

- **Where:** `frontend/src/app/dashboard/page.tsx:63` (the `catch` around the leads `fetch`).
- **Bug:** the `Response` constructor throws `RangeError` for any status outside 200 to 599 (verified). So when the backend is unreachable and `fetch` throws, the catch block itself throws, uncaught, and the whole dashboard render errors out instead of showing the intended "Couldn't load leads." message.
- **Fix:** don't fabricate a sentinel `Response`. Set `loadError = true` directly in the catch, or use a status in range (e.g. `503`).

### 3. Following the README literally, you can't log in

- **Where:** `README.md` "Getting Started" starts `uvicorn` without setting `JWT_SECRET_KEY` or the `SEED_ATTORNEY_*` vars.
- **Consequences:**
  - `JWT_SECRET_KEY` is required (no default, by design). Without it the server still boots, but `POST /api/auth/login` and every authed request 500s (`RuntimeError` from `_get_jwt_secret`).
  - Without `SEED_ATTORNEY_EMAIL/PASSWORD/NAME`, no attorney account is ever created, so there are no credentials to log into the dashboard with.
- **Net effect:** a reviewer who follows the quickstart can submit a lead but cannot reach the internal UI at all. The vars are documented in the env-var table lower down, but the runnable quickstart doesn't wire them. Add them to the Getting Started commands, or ship a `.env.example` for the backend and auto-load it.

### 4. "Integrate with an email service" is only a console stub by default

- **Where:** `email_service.py`. Default `EMAIL_BACKEND=console` just logs. `SMTPEmailSender` exists but is unconfigured and undemoed.
- **Gap:** the assignment says "integrate with an email service." As shipped, no email actually leaves the process without extra SMTP config that isn't provided or documented end-to-end (no Mailtrap/Resend wiring). The abstraction is good, the integration is unfinished. Tracked in `BACKLOG.md` (#2 "actually send emails", #3 "async") and `SYSTEM_DESIGN.md` TODO, acknowledged but still a visible weak spot for this requirement.

### 5. Required deliverable missing: agent-usage writeup and attribution

- The assignment requires a half-page writeup (tools used, delegated vs. hand-written, one place the agent produced wrong/subtly-bad code and how it was caught) and attribution marking agent-generated vs. hand-written code (NOTES file or commit attribution).
- Present: `prompts` (prompt log). Missing: the writeup and the attribution/NOTES file. Finding #1, the impostor `httpx2`, is a ready-made, honest answer to "one place the agent produced subtly bad code."

### 6. Frontend has no tests

- The build plan called for "a couple of frontend tests for the form validation and the dashboard state-transition action." None exist (no test runner configured). Backend is well-covered (76 tests), the frontend is not covered at all.

---

## Okay / Minor

Noted, low urgency. Most already have a TODO.

- **Lead state-transition race** (`lead_service.update_lead_state` read-then-write). Two attorneys can double-write or misattribute. Already documented as a TODO in `SYSTEM_DESIGN.md` (atomic conditional `UPDATE ... WHERE state='PENDING'` plus `409`). Fine to defer.
- **Resume type trusts the client `Content-Type` header** (no magic-byte sniffing). Already in `PRODUCTION_READINESS.md` as must-fix-before-launch.
- **Orphaned resume file** if `db.commit()` fails after the file is written in `create_lead` (no cleanup/transaction wrapping). Low likelihood, worth a note.
- **`validate_content_length` does `int(content_length)`** with no guard. A malformed non-numeric `Content-Length` would raise `ValueError` (not `HTTPException`) and 500 rather than being rejected cleanly. Edge case, most servers reject bad Content-Length upstream.
- **`DATABASE_URL` swap isn't drop-in.** `database.py` hardcodes `connect_args={"check_same_thread": False}` (SQLite-only). Pointing `DATABASE_URL` at Postgres would need that removed. Migration path is in `BACKLOG.md`/`PRODUCTION_READINESS.md`.
- **`isPending` disables every row's button** while any single "Mark as Reached Out" is in flight (`LeadsTable.tsx`). Minor UX, not incorrect.
- **bcrypt silently truncates passwords over 72 bytes.** Negligible for this use case.
- **Design-rationale doc is thin.** `SYSTEM_DESIGN.md` (contracts and TODOs) and `PRODUCTION_READINESS.md` (tiered) are solid, but the "why I chose X over Y" narrative (SQLite vs Postgres, JWT vs session, local disk vs S3) is mostly captured only as terse bullets in `discussion points.md`. The assignment asks for a design doc on why/how choices were made, worth expanding.

---

## Requirements coverage matrix

| Requirement | Status |
|---|---|
| Public lead form (firstName, lastName, email, resume) | Implemented (`/apply`, `POST /api/leads`) |
| Email prospect and attorney on submit | Implemented as console stub; real send = TODO (#4, Backlog) |
| Internal auth-guarded leads list | Implemented (`/dashboard`, JWT plus middleware) |
| Lead state PENDING to REACHED_OUT (manual) | Implemented; concurrency hardening = TODO (documented) |
| FastAPI backend | Done |
| Next.js frontend | Done |
| Persistent storage | SQLite (Postgres = documented future) |
| Email service integration | Abstraction plus SMTP option present; real provider not wired/demoed |
| Production-style structure | Clean layering, both tiers |
| System design doc | `docs/SYSTEM_DESIGN.md` |
| "How to run locally" doc | `README.md` present but quickstart can't reach the dashboard (#3) |
| Design-choices doc | Partial (see minor note) |
| Agent-usage writeup and attribution | Prompt log present; writeup and NOTES/attribution missing (#5) |
| Backend tests | 76 passing (but see #1) |
| Frontend tests | None (#6) |

**Bottom line:** one true must-fix (#1, the `httpx2` dependency), two functional/doc gaps that a reviewer will hit immediately (#2 dashboard crash on unreachable backend, #3 can't log in from the quickstart), and the remaining items are either already-tracked TODOs or missing submission deliverables (#4 to #6).
