# Backlog

Running list of things left to do, plus a couple already resolved and kept here for the record. See `DESIGN_DECISIONS.md` for the reasoning behind choices already made. This is just the punch list.

1. ~~**Create a script to automatically test & deploy locally.**~~ *(done)*
   `dev.sh` starts backend + frontend together (handles first-run setup, seeds an attorney account, `Ctrl+C` stops both). `smoke-test.sh` runs the full flow against it: health check, submit a lead, log in, confirm it shows up in the dashboard.

2. ~~**Script to actually send emails.**~~ *(done)*
   `EMAIL_BACKEND=resend` sends real email via Resend's HTTP API, stdlib-only client, no SDK dependency.

3. ~~**Async way of sending emails.**~~ *(done)*
   Moved to FastAPI `BackgroundTasks` with retry-with-backoff, so a slow or down email provider can't block lead creation.

4. **Add `models.py` to a separate `/models` path.**
   Currently one flat file (`Lead`, `User`). Worth splitting into a package once there are more models to justify it, not urgent at two.

5. **Rate limiting.**
   `POST /api/leads` is the one public, unauthenticated endpoint and currently has nothing slowing down spam or bot submissions.

6. **Idempotency.**
   Duplicate submissions (double-click, retried request) just create another lead row today. Dedupe was deliberately rejected in favor of always inserting (see `DESIGN_DECISIONS.md`), but true request-level idempotency is still open.

## Future Improvements

1. **Use a production-grade database (Postgres/MySQL).**
   SQLite is fine at this scale but doesn't hold up under real concurrent writes. `DATABASE_URL` is env-driven so the swap is config, not a rewrite.

2. **Alembic to manage data migrations.**
   `create_all` on startup can only create missing tables. It can't evolve a schema once real data already exists.
