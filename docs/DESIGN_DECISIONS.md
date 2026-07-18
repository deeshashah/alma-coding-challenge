# Design Decisions

Notes on why I built things the way I did. `SYSTEM_DESIGN.md` has the actual spec (models, API contracts). This is the reasoning behind it: what I considered, what I didn't go with, and what I knowingly punted on for this scope.

## Summary

Every choice below is scoped to this being a take-home exercise, not a real production system. Worth being explicit about that up front:

- SQLite, local disk for resumes, a single hardcoded attorney inbox, JWT with no revocation story. All "right-sized for this exercise," not "what I'd actually ship."
- For a real production system I'd do a fair amount differently from day one: Postgres instead of SQLite, S3 (or equivalent) instead of local disk, a Kafka-backed event queue instead of `BackgroundTasks` once volume (or the number of things that need to react to a new lead) justified it, rate limiting on the public endpoint, proper secrets management instead of env vars.
- None of that is a surprise. It's called out inline below and again in "What I intentionally didn't do" at the end.
- I'd rather build the right-sized thing for the actual scope and be upfront about the gap than over-build for a scale this doesn't have.

## Stack

Next.js + FastAPI was given. Within that:

- **Frontend uses Server Actions**, not a client-side fetch layer, for both the apply form and the dashboard actions. Main reason: keeps the JWT off the client completely. I didn't want it sitting in localStorage or getting passed around in the browser.
- **Backend is split into routes, services, and models.** Routes just parse and validate. The actual logic lives in `*_service.py`. Nothing fancy, just makes it testable and keeps the route files readable.

## DB: SQLite, not Postgres

- Went with SQLite because it's zero setup and this doesn't need more than that right now: one firm, not much lead volume, so SQLite's write serialization isn't actually a problem here.
- `DATABASE_URL` is an env var specifically so switching to Postgres later is just a config change, not a rewrite.
- Postgres + Alembic is the first thing I'd add before any real launch. `create_all` on startup can't handle schema changes once there's real data in the table.

## File storage: local disk, not S3

- Same logic as the DB. Fine for now, not fine for production. Resumes get written to `UPLOAD_DIR` and served through a static route.
- This breaks the moment there's more than one server instance (files won't be shared) or a redeploy happens (disk gets wiped). One of the first things I'd move to S3 or similar before this runs for real, along with adding backups, since local disk has no durability story at all.
- Filenames are `<timestamp>_<lead_id>.<ext>`. The lead_id is already a UUID so collisions weren't actually a risk, but I added the timestamp anyway for easier debugging on disk and just in case the ID scheme ever changes to something less random.

## Resume validation: content-type check for now

- Right now I'm checking the file's `Content-Type` header against an allow list (pdf/doc/docx) plus a size limit.
- This isn't real validation. The client sets that header, so it can be spoofed.
- Since attorneys are the ones opening these files, actually sniffing the file bytes (checking magic numbers instead of trusting the header) and ideally running them through malware scanning is something I'd want before this goes anywhere real. Noted, not something I missed.

## Auth: JWT, not sessions (yet)

- Went with JWT because it's stateless: no session store to run, and it still works fine if this ever runs on more than one instance.
- Login issues the token, the Next.js server action stores it in an httpOnly cookie, and the backend calls forward it as a bearer token. The token itself never touches client JS.
- I've gone back and forth on whether session-based auth is actually the better call here, mainly because revoking a JWT before it expires isn't really possible without extra infra, and a session you can just kill. Left it as JWT since revocation isn't something this needs yet, but it's a real open question, not something I've settled on for good.

## Leads: always insert, no dedupe by email

I actually built this two ways. First pass deduped on email: if the same email submitted again, it updated the existing lead instead of making a new one. Ended up reverting that.

Reasoning:

- An upsert overwrites whatever the person originally sent (name, resume), and there's no getting that back. Felt wrong for something like an immigration case history.
- It also meant the public form could touch a lead an attorney already marked `REACHED_OUT`, which needed a special rule (never let a resubmit reset state) just to avoid stepping on the attorney's work.
- Making the dedupe race-safe needed a unique constraint plus upsert-on-conflict logic, more to get wrong for not much benefit.

So now every submission is just a new row, plain insert, no dedupe.

- The downside is a person applying twice shows up as two rows, but that's a dashboard problem (could group/badge by email later), not a data problem.
- I'd rather solve that in the UI than lose data or add write-path complexity to avoid it.
- Full writeup with both sides is in `SYSTEM_DESIGN.md` under the Lead model if this ever needs to be revisited.

## Lead state: one-way, and made race-safe on purpose

`PENDING -> REACHED_OUT` only, attorney-triggered, no going back. A couple things I was deliberate about:

- **No transition back to PENDING.** Nothing asks for it, and it would make "who actually reached out" murky.
- **Not a naive read-check-then-write.** Two attorneys clicking the same lead close together could both pass a "is it PENDING" check before either one commits. That's a silent double-write with no error, and whichever one wrote last "wins" even if they weren't the one who actually called the prospect. Instead it's one atomic `UPDATE ... WHERE state = 'PENDING'`, checking the row count. If nothing changed, someone already got there first, and that returns a 409 instead of quietly succeeding. No locking needed, and it holds up even if this backend ever runs as multiple instances.

**Future case worth flagging:** there's no way to undo a "Mark as Reached Out" click right now, and that's a real problem in practice. It's a single button in a table row, and an attorney will eventually fat-finger it on the wrong lead.

- The one-way design above was deliberate (a togglable state makes the audit trail meaningless), so the fix isn't "allow REACHED_OUT -> PENDING as a normal transition." That just reopens the same problem from the other direction.
- Better shape: a distinct, explicit revert/undo action, separate from the normal transition, logged as its own event (who undid it and why, not just "state changed back"), possibly time-boxed so it's clearly for catching mistakes and not a way to routinely flip leads back and forth.
- Not built. Noting it because it's a real dashboard gap, not a made-up edge case.

## Email

Three decisions bundled in here:

- **Swappable backend.** There's an `EmailSender` interface: console logger by default (so nothing needs real credentials to run or grade this), and SMTP or Resend behind an env var when you actually want it sent.
- **One attorney inbox, not all of them.** The requirement just says "an attorney," singular, so one configured address covers it. Didn't want to broadcast to everyone (people could double up on outreach, or nobody takes it thinking someone else will), and round-robin assignment felt like building for a problem I don't have yet. Worth doing once there's actually more than one attorney handling leads.

**Off the request path.** Originally went with synchronous, inline in the request.

- At this volume (one firm, not many leads a day), an email call that normally finishes in well under a second isn't a real load problem, so async felt like solving something I didn't have.
- Switched to `BackgroundTasks` anyway, because the actual argument for it wasn't volume, it was failure isolation. If lead creation waits on the email provider, that provider's downtime becomes my downtime for the one thing that can't afford to break: the prospect's `201`. `BackgroundTasks` buys that isolation almost for free.
- Added retry-with-backoff too, since a background failure is otherwise completely silent and nobody would know an email never went out.

Worth being explicit about what `BackgroundTasks` actually is, though. It's in-process and in-memory, not a real queue.

- Runs in the same worker that handled the request, with no broker and no persistence. If the process dies between the response going out and the task actually running, that task is just gone, and there's nothing tracking "this failed" beyond a log line.
- Didn't reach for a real queue here because that's solving for volume, which still isn't the problem at this scale. `BackgroundTasks` covers the actual problem I had (isolation from the email provider), not durability or scale.
- For a real production version I'd put this behind Kafka instead. "Lead created" is naturally an event, not just a task tied to one background job, and a durable, replayable log is the right fit once more than one thing needs to react to it (email, but also audit logging, analytics, a future CRM sync) without each new consumer needing its own bolt-on to the request path.

## What I intentionally didn't do

None of this is stuff I missed, just didn't need for this scope:

- **Postgres + Alembic** instead of SQLite, once there's real concurrent write load or the schema needs to evolve under existing data.
- **S3 (or similar)** instead of local disk for resumes, plus backups. Needed as soon as this runs on more than one instance or needs to survive a redeploy.
- **Real resume validation.** Magic-byte sniffing instead of trusting `Content-Type`, and malware scanning, since attorneys open these files.
- **Rate limiting** on the public `POST /api/leads`. It's the one unauthenticated endpoint open to the internet, so it's the obvious target for spam or bot submissions.
- **Revisiting JWT vs. sessions.** Mainly for real revocation, not something I've settled on.
- **Round-robin attorney assignment** instead of one hardcoded inbox, once there's more than one attorney actually fielding leads.
- **A Kafka-backed event queue** instead of `BackgroundTasks`, once there's either real volume or more than one downstream consumer of "a lead was created" (email today, likely audit logging, analytics, and CRM sync later). Gets durability and replay that an in-process, in-memory task list can't.
- **A real PII/retention policy.** For a legal/immigration context this is probably mandatory-retention rules driven by compliance, not just "delete for privacy," so it needs actual input from someone who knows the regulatory side, not a default I should just pick.

See `BACKLOG.md` for the running list of these plus smaller stuff.
