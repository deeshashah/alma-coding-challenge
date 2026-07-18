# Production Readiness

Gaps between the current take-home implementation and a production-grade version, tiered by actual risk/urgency rather than listed flat. Assumes current real-world scale: one firm, a handful of attorneys, low daily lead volume.

## Must-fix before real launch

These are either data-loss/compliance risks or things that break under any real usage.

- **PII and compliance handling.** Resumes and contact info are personal data for prospective immigration clients. Needs encryption at rest and a retention policy. Unlike typical consumer PII, legal/immigration case data is often subject to mandatory retention rules (bar/regulatory requirements), so "delete for privacy" is the wrong default. The policy needs to be driven by what the firm's compliance obligations actually require, not just data minimization instinct.
- **Database.** Swap SQLite for Postgres with real migrations (Alembic) instead of `create_all`-on-startup, which can't evolve a schema that already has data.
- **File storage off local disk**, to S3 or equivalent object storage. This is both a durability issue (local disk doesn't survive redeploys or backups) and what's currently blocking horizontal scaling: a second app instance wouldn't see resumes written by the first. One fix, two problems.
- **Resume upload validation.** Don't trust the client's `Content-Type` header, sniff file signatures (magic bytes) server-side instead. Also enforce size limits before buffering the full upload into memory, not after.
- **Rate limiting** on the public, unauthenticated `POST /api/leads`. It's the one endpoint open to the internet with no auth, and a real target for spam/bot submissions.
- **Auth hardening.** Short-lived JWTs plus refresh tokens, tokens in httpOnly secure cookies (not localStorage), login rate limiting/lockout.
- **Secrets management.** Move off `.env` files to a real secrets manager (AWS Secrets Manager, Vault, etc.) for DB credentials, JWT signing key, email provider API key.
- **CORS** locked to the actual production frontend origin. Currently scoped to `localhost:3000`.
- **Idempotent submission handling.** Block a duplicate submission for the same email while an existing `PENDING` lead for that email already exists. Not a blanket permanent dedupe, since a prospect legitimately reapplying months later shouldn't be blocked.
- **Audit trail.** `Lead.state` currently only tracks `updatedAt`. Add a `LeadStateChange` (or similar) table logging who transitioned a lead and when. Needed for compliance and for resolving "who reached out" disputes, which matters more in a legal context than most CRUD apps.

## Should-do soon

Not launch-blocking, but gaps that will bite within the first few months of real usage.

- **Email.** Replace the console/log stub with a real provider (Resend, Postmark, SES) behind the existing abstraction. Move sending off the request path (`BackgroundTasks` is sufficient at this volume) with retry-with-backoff and failure logging/alerting. A silent background failure otherwise means a prospect or attorney never gets their email and nobody knows.
- **Resume malware scanning** (e.g. ClamAV). Attorneys will be opening files uploaded by unauthenticated members of the public.
- **Automated backups.** DB point-in-time recovery, object storage versioning/lifecycle rules.
- **Structured logging** (JSON) instead of print/log statements.
- **Error tracking** (Sentry or similar) for both backend and frontend.
- **Health/readiness checks** beyond the current `/api/health`. Should verify DB connectivity, not just that the process is up.
- **CI pipeline.** Lint, type checks, test suites on every PR, plus dependency/vulnerability scanning (Dependabot, `pip-audit`, `npm audit`).
- **Environment separation** (dev/staging/prod) with separate databases, buckets, and email-provider keys.
- **Containerize the backend** (Docker) for consistent deploys.
- **Frontend input sanitization** on lead data rendered in the dashboard, to prevent stored XSS (e.g. a prospect submitting `<script>` as their name).
- **Basic alerting/on-call path** for the error tracking and email-failure logging above. A dashboard nobody watches doesn't help.

## Later, if scale demands it

Legitimate production concerns, but premature at current volume. Revisit if there's actual evidence of the underlying problem.

- **Real task queue** (Celery/RQ/arq + Redis) for email. Only once `BackgroundTasks`-level latency or reliability actually becomes a measurable problem.
- **Attorney assignment/round-robin routing.** Only once there's more than one attorney fielding leads. Today a single configured inbox is correct, not a shortcut.
- **Infra as code** (Terraform). Worth it once environment setup is repeated/error-prone enough to justify the overhead.
- **CDN for frontend static assets.** Worth it at real traffic, not day one.
- **API versioning strategy** (e.g. `/api/v1/...`). Adopt at the point of the first breaking change, not preemptively.
- **TLS.** Usually free by default on modern hosting (Vercel, Render, Fly.io, an ALB) rather than something to build. Just confirm it's on, don't over-invest here.
