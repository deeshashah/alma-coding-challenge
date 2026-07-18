# System Design: Lead Management

## Overview

Two surfaces:

- **Public lead form.** Unauthenticated prospects submit their info and resume/CV.
- **Internal dashboard.** Authenticated attorneys view all leads and transition their state.

On lead creation, the backend emails both the prospect (confirmation) and an internal attorney (notification).

---

## Data Models

### Lead

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `firstName` | string | required |
| `lastName` | string | required |
| `email` | string | required, validated format (not unique, see note below) |
| `resumeUrl` | string | required, path to file on local disk (`/uploads/resumes/<timestamp>_<id>.pdf`), served via a static/download route |
| `state` | enum: `PENDING`, `REACHED_OUT` | defaults to `PENDING` |
| `createdAt` | datetime | set on submit |
| `updatedAt` | datetime | set on any mutation |

State machine: `PENDING -> REACHED_OUT`. One-way, manual transition only, triggered by an attorney.

**Resume filenames** are `<timestamp>_<lead_id><extension>`.

- The timestamp isn't for collision avoidance. `lead_id` is a fresh UUID per submission, so different leads already can't collide.
- It's for on-disk traceability and sortability, and defense-in-depth against a future change away from random UUIDs (e.g. sequential IDs), which would otherwise reintroduce a real overwrite risk for resumes uploaded close together.

**No dedupe on email.** A `POST /api/leads` always inserts a new row, even if the email matches an existing lead. Each submission is treated as a distinct expression of interest, not an update to a durable person-record.

**Alternatives considered: always create (chosen) vs. dedupe/upsert by email**

Reasons for always creating (what we chose):

- A lead is an expression of interest at a point in time, not a durable person. Two submissions months apart, or minutes apart with a corrected resume, are two real events an attorney may want to see and act on separately.
- Keeps full history. An upsert would overwrite the prior name/resume, losing what was originally sent, which can matter in a legal context.
- Keeps the public write path from ever touching an attorney-owned record. No "never reset `state` on update" carve-out needed, since a resubmission is always a fresh `PENDING` row with its own id.
- Keeps the write path a plain insert. No unique constraint, no conflict-fallback, no race window to reason about.
- Its one real cost, duplicate rows for the same person, is a UI concern (grouping/badging rows that share an email in the dashboard) rather than a data-model one, so it doesn't have to be solved by destroying data at write time.

Reasons for dedupe/upsert:

- Optimizes for a single clean record per person, which can be a more natural mental model for an attorney working the list, and avoids the dashboard ever showing duplicates.
- The cost is real: lost history (the previous submission's contents are gone once overwritten), a write path that has to special-case attorney-owned state (an update must never silently reset `state` back to `PENDING`), and since dedupe still needs to be race-safe, a DB-level unique constraint plus an insert-then-fall-back-to-update-on-conflict path. All more moving parts than a plain insert.

**Net decision:** always-create keeps the write path simple and preserves history, at the cost of possible duplicate rows in the dashboard (a UI-layer fix, not a data loss). Dedupe/upsert gives a cleaner internal view at the cost of losing history and a more complex, state-aware write path. We chose always-create: simpler, safer default, with duplicate-handling left as a dashboard-side concern rather than baked into the write path.

### User (Attorney)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `email` | string | unique, used for login |
| `passwordHash` | string | never returned in API responses |
| `name` | string | |
| `createdAt` | datetime | |

---

## API Contracts

### Public

#### `POST /api/leads`

Creates a lead. No auth required. `multipart/form-data` (for the resume file).

**Request**
```
firstName: string       (required)
lastName: string        (required)
email: string            (required)
resume: file              (required, pdf/doc/docx, size-limited)
```

**Response `201`**
```json
{
  "id": "3f2a1c...",
  "firstName": "Jane",
  "lastName": "Doe",
  "email": "jane@example.com",
  "resumeUrl": "/uploads/resumes/20260717T120000Z_3f2a1c....pdf",
  "state": "PENDING",
  "createdAt": "2026-07-17T12:00:00Z"
}
```

**Errors:** `400` validation (missing field, bad email, bad file type/size).

**Side effect:** sends two emails, a confirmation to `email` and a notification to the assigned attorney inbox (address from an env var).

- Backed by a swappable `EmailSender` interface: console/log (default, local dev), SMTP, or Resend (real HTTP API, stdlib-only client, no SDK dependency), selected via an env var.
- Sending is scheduled via FastAPI `BackgroundTasks` (runs after the response is sent, off the request path) so a slow or down provider never blocks lead creation.
- Retry-with-backoff (3 attempts) plus failure logging, since a background failure is otherwise silent. The final give-up is logged at error level even though it never reaches an HTTP response.

---

### Internal (requires auth: session or bearer token)

#### `GET /api/leads`

List leads, most recent first.

**Query params:** `state` (optional filter), `page`, `pageSize`

**Response `200`**
```json
{
  "items": [
    {
      "id": "3f2a1c...",
      "firstName": "Jane",
      "lastName": "Doe",
      "email": "jane@example.com",
      "resumeUrl": "/uploads/resumes/3f2a1c.pdf",
      "state": "PENDING",
      "createdAt": "2026-07-17T12:00:00Z",
      "updatedAt": "2026-07-17T12:00:00Z"
    }
  ],
  "page": 1,
  "pageSize": 20,
  "total": 1
}
```

#### `GET /api/leads/:id`

Fetch a single lead. `200` with the same shape as above, or `404`.

#### `PATCH /api/leads/:id`

Update lead state. Body restricted to state transitions (`PENDING -> REACHED_OUT` only).

**Request**
```json
{ "state": "REACHED_OUT" }
```

**Response `200`:** updated lead object.

**Errors:**

- `400`: the requested target state is never a valid transition (anything other than `REACHED_OUT`, e.g. explicitly targeting `PENDING`), regardless of the lead's current state.
- `404`: no lead with that id.
- `409`: the lead exists and `REACHED_OUT` was requested, but it wasn't `PENDING` at the moment the update ran (e.g. another request already transitioned it a moment ago, two attorneys racing on the same lead).

The `409` case is implemented as a single atomic conditional update (`UPDATE leads SET state='REACHED_OUT' WHERE id=:id AND state='PENDING'`), checking the affected row count, rather than a read-then-write.

- Two concurrent requests can't both pass a state check before either commits.
- The frontend can distinguish "someone already handled this" (409) from a generic bad request (400).
- Holds up across multiple backend instances since it relies on DB-level atomicity, not an in-process lock.

---

### Auth

#### `POST /api/auth/login`
```json
// request
{ "email": "attorney@alma.com", "password": "..." }

// response 200
{ "token": "...", "user": { "id": "...", "email": "...", "name": "..." } }
```

`401` on bad credentials. Internal endpoints require this token (e.g. `Authorization: Bearer <token>`).
