# Session Summary: Backend Build (Claude Code)

Handoff doc for a fresh session. Covers everything built in this conversation: scaffolding, the full backend feature set, and the reasoning behind several non-obvious decisions.

The frontend (`frontend/src/app/apply`, `/dashboard`, `/login`, `middleware.ts`, `lib/session.ts`) was **not** built in this session. It exists already; treat it as external context, not something this summary explains.

## What this is

`docs/SYSTEM_DESIGN.md` is the source of truth for the API contracts and data model. Read that first for the actual spec. This doc is the narrative of how the backend got built and why specific calls were made.

Lead Management app: a public form where prospects submit their info and resume, and an internal attorney dashboard to review and manage leads.

## Build order

1. **Boilerplate.** Next.js (App Router, TS) frontend plus FastAPI backend, Python 3.14 venv at `backend/.venv` (system Python was 3.9, too old). Basic `/api/health` wired end-to-end.
2. **DB layer.** SQLAlchemy plus SQLite, `Lead` model per spec, tables created idempotently via a FastAPI `lifespan` startup hook.
3. **`POST /api/leads`.** Multipart upload, field/file validation, resume stored to disk, static-file serving for `resumeUrl`. Established the layering convention (see below) here.
4. **Test suite.** pytest, isolated tmp DB/upload dir per test session.
5. **Three parallel-ish pieces of work, done via subagents:**
   - Email-sending abstraction (`email_service.py`), called from lead creation.
   - Attorney auth: `User` model, `POST /api/auth/login`, JWT (bcrypt plus PyJWT), a reusable `get_current_attorney` dependency, env-var-driven dev seeding.
   - Internal endpoints (`GET /api/leads`, `GET /api/leads/:id`, `PATCH /api/leads/:id`), all behind the auth dependency.
   - After all three landed, an integration pass found and fixed two real bugs the subagents' own tests had masked (see "Bugs found" below).
6. **Implemented the three TODOs left in `SYSTEM_DESIGN.md`:**
   - Timestamped resume filenames (`<timestamp>_<lead_id><ext>`).
   - `PATCH` race fix: atomic conditional `UPDATE ... WHERE state='PENDING'` instead of read-then-write. Returns `409` (not `400`) when the row wasn't `PENDING` at update time.
   - Real email provider (Resend, via stdlib `urllib`, no SDK dependency), moved off the request path via FastAPI `BackgroundTasks`, with retry-with-backoff (3 attempts) and failure logging.
7. **Dedupe-by-email:** built, then reverted. See "Decision: no dedupe" below. This is the one significant piece of churn in the session and is worth reading if anything about `lead_service.create_lead` looks odd.

## Decision: no dedupe on email (Option A)

A `POST /api/leads` always creates a new `Lead` row, even if the email matches an existing one. This was genuinely debated mid-session.

- **Considered:** upsert-by-email (unique constraint on `Lead.email`, insert-or-update-on-conflict, `201`/`200` split, state preserved on update, differentiated email copy). Fully built and tested at one point.
- **Chosen instead:** always insert. Reasoning: a lead is an expression of interest at a point in time. Upserting destroys the previous submission's contents (matters in a legal context), forces the public write path to special-case attorney-owned state (`state` must never reset on resubmit), and adds a race-safety mechanism (unique constraint plus conflict fallback) that a plain insert doesn't need at all. Duplicate rows for the same person is a real cost, but it's a dashboard/UI problem (grouping/badging by email), not a data-model one.
- **Net effect on code:** `Lead.email` has no unique constraint. `lead_service.create_lead` always inserts. `POST /api/leads` always returns `201`. See `docs/SYSTEM_DESIGN.md`'s "Alternatives considered" note under the `Lead` model for the full writeup. It's preserved there intentionally so this doesn't get re-litigated from scratch.
- If asked to reconsider: the upsert version is straightforward to reconstruct from this doc plus `SYSTEM_DESIGN.md`'s alternatives section. It isn't in git history (no commits made this session, see below).

## Conventions established this session (follow these without re-asking)

- **Python venv, always.** `backend/.venv`, created via `/opt/homebrew/bin/python3.14 -m venv`. Never system Python.
- **Docstring on every function.** One line is fine. This overrides the usual "no comments" default; explicitly requested.
- **Layering.** Routes (`leads.py`, `auth.py`) are thin: parse, validate, delegate. Control logic lives in a `*_service.py` module (`lead_service.py`, `auth_service.py`). DB models in `models.py`. Pydantic I/O schemas in `schemas.py`. Reusable request/file validation in `validators.py`, not inlined in routes.
- **`main.py` is the sole composition root.** All `app.include_router`, `app.mount`, `app.middleware`, exception handlers live there, even for wiring that's conceptually feature-specific (e.g. the resume-upload size-check middleware). A `register(app)`-in-feature-module pattern was proposed and explicitly rejected.
- **Test suite must stay green and in sync.** Run `cd backend && .venv/bin/pytest -q` after every change; add tests for new behavior. Currently 83 tests, all passing.
- **Don't fabricate test fixtures.** For the resume-upload fixture, a minimal placeholder PDF was generated only after explicit sign-off (`backend/tests/fixtures/dummy_resume.pdf`). A real personal resume was used for manual `curl` verification but deliberately kept out of the committed test suite.
- **Verify live, not just via tests.** Every feature in this session was smoke-tested with a real running `uvicorn` process plus `curl` before being considered done. This caught real bugs unit tests missed (see below). Always clean up (`kill` the server, remove `alma.db`/`uploads/`) after.

## Bugs found and fixed (worth knowing about, not just the fix)

1. **Test DB isolation was silently broken.** `database.py` reads `DATABASE_URL` at module import time. `tests/conftest.py` originally set that env var inside a fixture, but pytest imports every test module during collection, before any fixture runs. A test file with a module-level `from models import ...` (which transitively imports `database.py`) bound the engine to the real dev `alma.db` before the fixture ever got a chance to override it. Fix: set `DATABASE_URL`, `UPLOAD_DIR`, `JWT_SECRET_KEY` at module level in `conftest.py` (conftest is guaranteed to load before test collection in its directory), not inside a fixture.
2. **Cross-test data leakage.** The test DB is session-scoped (created once), so rows from one test were still present when the next test ran, breaking a pagination test's exact-count assertions. Fixed with an autouse fixture that clears `leads`/`users` after every test.
3. **`ConsoleEmailSender` logged nothing in a real run.** `logger.info(...)` was silently dropped: Python's root logger defaults to `WARNING`, and uvicorn only configures its own `uvicorn.*` loggers, never `logging.basicConfig()`. The unit test passed anyway because it forced the level with `caplog.at_level(...)`, which doesn't reflect production behavior. Fix: attach a dedicated `StreamHandler` directly to the `email_service` logger, `propagate=False`, independent of how the app is launched.
4. **Retry backoff wasted real wall-clock time in tests.** Once `send_with_retry` was added (3 attempts, exponential backoff), a test simulating an always-failing send burned roughly 6s of real `time.sleep()` per run. Fixed by monkeypatching `time.sleep` in every test that exercises the failure path.
5. **Pydantic gotcha, recurring, watch for this in new schemas.** Any schema using `Field(alias=...)` for camelCase JSON keys (e.g. `firstName`, `pageSize`) must also set `model_config = ConfigDict(populate_by_name=True)`. Without it, both `.model_validate()` off an ORM object and direct keyword construction raise a spurious "Field required"/`ResponseValidationError` (500 at request time). Bit this project twice.

## Multi-agent orchestration notes

Two features (email abstraction, attorney auth) were built by two parallel background subagents. A third (internal endpoints) followed once auth landed.

- Each was scoped to a strictly non-overlapping file list to avoid collisions. No git worktrees were used since the repo had zero commits at the time, so worktree isolation wasn't viable; scoping was the substitute.
- A pre-launch file snapshot plus mtime diff was used afterward to confirm no agent touched anything outside its assignment.
- `README.md` was deliberately left to the orchestrating session to update, not delegated, to avoid two agents racing on the same doc file.

## Current file structure (`backend/`)

```
main.py            composition root: FastAPI app, middleware, routers, lifespan (create tables + seed attorney)
database.py        SQLAlchemy engine/session, get_db dependency, DATABASE_URL env override
models.py          Lead, LeadState, User (SQLAlchemy)
schemas.py         Pydantic I/O models: LeadOut, LeadListOut, LeadStateUpdate, LoginRequest, LoginResponse, UserOut
validators.py       reusable request/file validation (required fields, resume type/size, Content-Length precheck)
leads.py            routes: POST/GET/GET-by-id/PATCH /api/leads*
lead_service.py     control logic: create_lead, list_leads, get_lead, update_lead_state (atomic), notify_lead_created
email_service.py    EmailSender interface: ConsoleEmailSender, SMTPEmailSender, ResendEmailSender; send_with_retry()
auth.py              route: POST /api/auth/login
auth_service.py      hash_password/verify_password, create/decode_access_token, authenticate_attorney,
                     get_current_attorney (dependency), seed_attorney_from_env
tests/               83 tests; conftest.py sets up isolated tmp DB/upload dir + JWT secret at module level
```

## Environment variables

| Var | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./alma.db` |
| `UPLOAD_DIR` | Where resumes are written | `backend/uploads/resumes/` |
| `ATTORNEY_NOTIFICATION_EMAIL` | Recipient of new-lead notification emails | `attorney@example.com` (warns if unset) |
| `EMAIL_BACKEND` | `console` / `smtp` / `resend` | `console` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS` | SMTP config | used only if `EMAIL_BACKEND=smtp` |
| `RESEND_API_KEY`, `RESEND_FROM_ADDRESS` | Resend config | used only if `EMAIL_BACKEND=resend` |
| `JWT_SECRET_KEY` | Signs/verifies login JWTs | required, no insecure default, use 32+ random bytes |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `60` |
| `SEED_ATTORNEY_EMAIL`, `SEED_ATTORNEY_PASSWORD`, `SEED_ATTORNEY_NAME` | Idempotent dev-only attorney account, all three needed together | unset (no seeding) |

## Endpoints (current, final state)

- `POST /api/leads`: public, multipart. Always `201`. Validates fields and resume type/size. Stores resume as `<timestamp>_<id>.ext`. Queues confirmation and attorney-notification emails via `BackgroundTasks`.
- `POST /api/auth/login`: public, JSON. `200` plus `{token, user}`, or `401`.
- `GET /api/leads`, `GET /api/leads/:id`, `PATCH /api/leads/:id`: all require `Authorization: Bearer <token>` via `get_current_attorney`. `PATCH`: `400` invalid target state, `404` not found, `409` lost a race (lead existed but wasn't `PENDING` when the atomic update ran).

## Other docs in this repo (not written by this session)

- `docs/PRODUCTION_READINESS.md`: tiered gaps for a real launch (PII/compliance, Postgres plus Alembic, S3, rate limiting, auth hardening). Worth reading before doing production-hardening work.
- `BACKLOG.md`, `discussion points.md`: the user's own running notes. Several items overlap with what's now done (real email send, file size check before upload) and several are still open (round-robin attorney routing, session-vs-JWT reconsideration, rate limiting, idempotency, `models.py` to `/models` package split, Postgres/Alembic).
- `docs/CODE_REVIEW.md` exists but was explicitly set aside by the user during this session, not incorporated here.

## Git state

No commits exist in this repo as of this session's end. Everything above is uncommitted working-tree state. `git status` will show most files as untracked. Nothing was pushed or committed at any point; the user never asked for it.
