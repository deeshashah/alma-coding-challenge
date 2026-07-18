# Backlog

Open items in priority order, completed items kept below for the record. See `DESIGN_DECISIONS.md` for the reasoning behind choices already made.

## Open

1. **Rate limiting.**
   `POST /api/leads` is the one public, unauthenticated endpoint and currently has nothing slowing down spam or bot submissions. Highest priority since it's a live gap on the one endpoint open to the internet.

2. **Idempotency.**
   Duplicate submissions (double-click, retried request) just create another lead row today. Dedupe was deliberately rejected in favor of always inserting (see `DESIGN_DECISIONS.md`), but true request-level idempotency (e.g. dedupe on a client-supplied request id within a short window) is still open.

3. **Resend sandbox mode silently blocks prospect confirmation emails.**
   The account has no verified sending domain, so Resend is in testing/sandbox mode and only actually delivers to the account owner's own address. Any other email typed into the `/apply` form gets a 422 from Resend (`Invalid "to" field`), which fails the confirmation send. The attorney notification still arrives, since `ATTORNEY_NOTIFICATION_EMAIL` is the verified address, but the prospect confirmation fails after 3 retries with only a "giving up" error log, nothing surfaced to the browser, and the lead still gets created (`201`) either way. This is the silent-failure risk already noted in `DESIGN_DECISIONS.md` under the email section, now observed in practice. Real fix is verifying a sending domain in the Resend dashboard, which lifts the sandbox restriction entirely; needs a domain, not something to set up mid-demo. Workaround for now: use the verified address as the prospect email too when testing, so both emails land in the same inbox.

4. **Allow correcting an accidental "Mark as Reached Out."**
   There's currently no way to undo that click, and it's a single button in a table row, so an attorney will eventually hit it on the wrong lead. Shouldn't be a plain `REACHED_OUT -> PENDING` toggle (that just reopens the audit-trail problem from the other side). Should be a distinct, explicit revert action, logged as its own event (who undid it and why), possibly time-boxed to a short window after the original click so it's for catching mistakes, not routine flip-flopping. Already flagged as a future case in `DESIGN_DECISIONS.md`; this is where it becomes a tracked item.

5. **Basic account functionality: logout, and visibility into who's logged in.**
   There's currently no way to log out. The JWT sits in an httpOnly cookie until it naturally expires (60 minutes by default) or the cookie is cleared by hand. Needs a logout action (a Server Action clearing the session cookie; no server-side token invalidation needed since JWTs are stateless) reachable from the dashboard, plus some visible indication of who's currently logged in. Basic account hygiene an attorney-facing tool shouldn't ship without.

6. **Proper navigation across pages.**
   Right now only the homepage links out (to `/apply` and the attorney area). `/apply`, `/login`, and `/dashboard` are all dead ends with no way back without editing the URL bar. Needs a shared nav or header, at minimum a link back to the dashboard from every authenticated page, and a way to get from the dashboard back to the public site.

7. **Group or badge duplicate leads by email in the dashboard.**
   Direct consequence of the always-insert decision: a prospect who applies twice shows up as two separate rows today, with no way to tell at a glance that they're the same person. This was always the intended mitigation for that trade-off (see `SYSTEM_DESIGN.md`'s alternatives note) but was never actually built.

8. **Add `models.py` to a separate `/models` path.**
   Currently one flat file (`Lead`, `User`). Worth splitting into a package once there are more models to justify it. Lowest priority, pure organization, not urgent at two models.

## Future Improvements

Bigger infrastructure changes, not day-to-day backlog items.

1. **Use a production-grade database (Postgres/MySQL).**
   SQLite is fine at this scale but doesn't hold up under real concurrent writes. `DATABASE_URL` is env-driven so the swap is config, not a rewrite.

2. **Alembic to manage data migrations.**
   `create_all` on startup can only create missing tables. It can't evolve a schema once real data already exists. Depends on the Postgres move above to matter in practice.

## Completed

- ~~**Create a script to automatically test & deploy locally.**~~
  `dev.sh` starts backend + frontend together (handles first-run setup, seeds an attorney account, `Ctrl+C` stops both). `smoke-test.sh` runs the full flow against it: health check, submit a lead, log in, confirm it shows up in the dashboard.

- ~~**Script to actually send emails.**~~
  `EMAIL_BACKEND=resend` sends real email via Resend's HTTP API, stdlib-only client, no SDK dependency.

- ~~**Async way of sending emails.**~~
  Moved to FastAPI `BackgroundTasks` with retry-with-backoff, so a slow or down email provider can't block lead creation.
