# Alma Coding Challenge

Next.js (App Router) frontend + FastAPI backend.

## Getting Started

**Quickest: backend + frontend together**

```sh
./dev.sh
```

Clears any stale process already bound to port 8000/3000 (e.g. left over
from a previous run that didn't shut down cleanly — override the ports with
`BACKEND_PORT`/`FRONTEND_PORT`), bootstraps `backend/.venv` and
`frontend/node_modules`/`.env.local` on first run if they don't exist yet,
generates an ephemeral `JWT_SECRET_KEY`, seeds a dev attorney account
(`attorney@example.com` / `devpassword123` by default — override via
`SEED_ATTORNEY_EMAIL`/`SEED_ATTORNEY_PASSWORD`/`SEED_ATTORNEY_NAME`), starts
both servers, waits for each to report healthy, then prints the URLs and
login credentials. `backend/.env`, if present, is loaded automatically too
(e.g. for `EMAIL_BACKEND=resend` to demo real email — see
`backend/.env.example`). Ctrl+C stops both servers and sweeps their ports
again as a safety net, since `uvicorn --reload`'s worker subprocess and
`npm run dev`'s spawned `next-server` don't always exit with their direct
parent process.

**Backend** (manual, if you'd rather run it yourself)

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # sets JWT_SECRET_KEY and seeds a local attorney login
.venv/bin/uvicorn main:app --reload --port 8000
```

`.env` is loaded automatically on startup (via `python-dotenv` in `main.py`).
Without it, `POST /api/auth/login` 500s (no `JWT_SECRET_KEY`) and no attorney
account exists to log in with — see `backend/.env.example` for what it sets
and why. The seeded credentials match `dev.sh`'s defaults: `attorney@example.com`
/ `devpassword123`.

**Frontend** (manual)

```sh
cd frontend
cp .env.example .env.local   # sets API_URL for the backend
npm install
npm run dev
```

Visit http://localhost:3000 — it server-renders a call to the backend's
`/api/health` endpoint to confirm the two are wired together.

## Development

Backend layering — routes / control logic / models are kept in separate modules:

- `backend/main.py` — FastAPI app entrypoint; composition root (middleware, static mounts, exception handlers, router registration, table creation + attorney seeding on startup).
- `backend/database.py` — SQLAlchemy engine/session setup (`DATABASE_URL` env var, defaults to `sqlite:///./alma.db`).
- `backend/models.py` — SQLAlchemy models (`Lead`, `LeadState`, `User`).
- `backend/schemas.py` — Pydantic response models, camelCase JSON per `docs/SYSTEM_DESIGN.md` (`LeadOut`, `LeadListOut`, `LeadStateUpdate`, `LoginRequest`, `LoginResponse`, `UserOut`).
- `backend/validators.py` — reusable request/file validation (required fields, resume type/size, Content-Length precheck).
- `backend/leads.py` — routes for `/api/leads*` (thin: parse + validate + delegate).
- `backend/lead_service.py` — control logic for leads: writes resumes to `UPLOAD_DIR` (env var, defaults to `backend/uploads/resumes/`), persists/queries/updates `Lead` rows. Every submission creates a new lead (no dedupe by email — see `docs/SYSTEM_DESIGN.md` for the tradeoff). `update_lead_state` uses a single atomic conditional `UPDATE` (not read-then-write) so two concurrent PATCH requests can't both win a state transition.
- `backend/email_service.py` — `EmailSender` abstraction: `ConsoleEmailSender` (default, logs to console — for local dev), `SMTPEmailSender`, and `ResendEmailSender` (real HTTP API, stdlib `urllib` only, no SDK), selected via `get_email_sender()`. `send_with_retry()` wraps any sender with retry-with-backoff (3 attempts) and failure logging. Notification emails are scheduled via FastAPI `BackgroundTasks` from the `POST /api/leads` route, not sent on the request path.
- `backend/auth.py` — route for `POST /api/auth/login` (thin).
- `backend/auth_service.py` — control logic for auth: password hashing (bcrypt), JWT issuing/verification (PyJWT, HS256), `authenticate_attorney`, the reusable `get_current_attorney` dependency, and `seed_attorney_from_env`.
- `frontend/src/app/page.tsx` — homepage; links applicants to `/apply` and attorneys to `/login` or `/dashboard` (whichever applies, checked via the session cookie), plus a live `API_URL` health-status indicator.
- `frontend/src/app/apply/` — public lead-intake form (`POST /api/leads`), client + server-surfaced validation, success state.
- `frontend/src/app/login/` — attorney login (`POST /api/auth/login`); stores the returned JWT in an httpOnly session cookie (never in localStorage) and redirects to `/dashboard` (or wherever `/login?from=` pointed) on success.
- `frontend/src/app/dashboard/` — auth-protected leads table (`GET /api/leads`), state filter, "Mark as Reached Out" action (`PATCH /api/leads/:id`) with optimistic update + refetch.
- `frontend/src/middleware.ts` / `frontend/src/lib/session.ts` — gate `/dashboard/:path*` on the presence of the session cookie; redirect to `/login` if it's missing. (Cookie *validity* — expiry/tampering — is checked per-request by whichever page/action calls the backend, since middleware runs in the Edge runtime and can't verify the JWT itself; a stale cookie gets redirected to `/login` from there instead.)
- CORS on the backend is currently scoped to `http://localhost:3000`.
- `dev.sh` — starts backend + frontend together for local dev (see Getting Started above).
- `smoke-test.sh` — full-stack sanity check against a running dev environment (see Testing below).

### Endpoints

**Public**
- `POST /api/leads` — `multipart/form-data` (`firstName`, `lastName`, `email`, `resume`). Validates fields and resume type (pdf/doc/docx)/size (5MB limit), stores the resume under `uploads/resumes/<timestamp>_<id>.ext`, creates a `PENDING` lead, returns it as JSON (**201**, always — every submission creates a new lead, no dedupe by email). Validation errors return 400; oversized uploads are rejected as 413 before the body is fully read. Confirmation/notification emails are queued via `BackgroundTasks` (sent after the response, not blocking it) with retry-with-backoff.
- `POST /api/auth/login` — `{"email", "password"}` JSON body. Returns `{"token", "user"}` (200) or 401 on bad credentials.

**Internal** (require `Authorization: Bearer <token>` from `/api/auth/login`, via the `get_current_attorney` dependency)
- `GET /api/leads` — list, most-recent-first. Query params: `state` (optional filter), `page` (default 1), `pageSize` (default 20, max 100).
- `GET /api/leads/:id` — single lead, or 404.
- `PATCH /api/leads/:id` — body `{"state": "REACHED_OUT"}`. Only `PENDING → REACHED_OUT` is valid: **400** if the target state itself is never valid (e.g. explicitly targeting `PENDING`), **404** if the id doesn't exist, **409** if the lead exists and `REACHED_OUT` was requested but it wasn't `PENDING` at the moment the atomic update ran (e.g. another request already transitioned it — two attorneys racing on the same lead).

### Environment variables

| Var | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./alma.db` |
| `UPLOAD_DIR` | Where resumes are written | `backend/uploads/resumes/` |
| `ATTORNEY_NOTIFICATION_EMAIL` | Recipient of new-lead notification emails | `attorney@example.com` (logs a warning if unset) |
| `EMAIL_BACKEND` | `console`, `smtp`, or `resend` | `console` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS` | Used only when `EMAIL_BACKEND=smtp` | `SMTP_PORT` defaults to `587` |
| `RESEND_API_KEY`, `RESEND_FROM_ADDRESS` | Used only when `EMAIL_BACKEND=resend` | `RESEND_FROM_ADDRESS` defaults to `no-reply@example.com` |
| `JWT_SECRET_KEY` | Signs/verifies login JWTs | **required** — no insecure default; use a random value of 32+ bytes (a short key trips a PyJWT `InsecureKeyLengthWarning`) |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `60` |
| `SEED_ATTORNEY_EMAIL`, `SEED_ATTORNEY_PASSWORD`, `SEED_ATTORNEY_NAME` | If all three are set, an idempotent startup hook creates one attorney account for local dev/login testing | unset (no seeding) |

## Testing

Backend tests live in `backend/tests/` (pytest, 83 tests). `tests/conftest.py`
points `DATABASE_URL`/`UPLOAD_DIR`/`JWT_SECRET_KEY` at throwaway locations
**at import time** (module level, not inside a fixture — pytest imports every
test file during collection before any fixture runs, so anything relying on a
fixture to set these would be too late for test files with module-level model
imports). An autouse fixture clears the `leads`/`users` tables after every
test so row-count/pagination assertions aren't order-dependent. Never touches
the dev `alma.db`/`uploads/`. A minimal placeholder PDF fixture lives at
`backend/tests/fixtures/dummy_resume.pdf`.

```sh
cd backend
.venv/bin/pip install -r requirements-dev.txt   # once
.venv/bin/pytest
```

Run this after every backend change — the suite is meant to be kept in sync
as new models/endpoints are added.

## Smoke test

`./smoke-test.sh` is a quick full-stack sanity check against a **running**
dev environment (start one first, e.g. `./dev.sh`). It exercises the real
HTTP contract end to end:

1. `GET /api/health` on the backend, and a plain reachability check on the
   frontend.
2. Submits a real test lead via `POST /api/leads` (multipart, using the
   `backend/tests/fixtures/dummy_resume.pdf` fixture).
3. Logs in via `POST /api/auth/login`.
4. Confirms the new lead appears in `GET /api/leads` — the same endpoint
   the dashboard reads from.
5. Confirms it also renders in the real `/dashboard` page HTML, by sending
   a plain `GET` with the session cookie set directly (no need to replay
   Next.js's internal Server Action wire format — a page load is a normal
   request).

```sh
./smoke-test.sh
```

Respects `API_URL`, `FRONTEND_URL`, `ATTORNEY_EMAIL`, and `ATTORNEY_PASSWORD`
env vars if your environment isn't running on the defaults `./dev.sh` uses.
