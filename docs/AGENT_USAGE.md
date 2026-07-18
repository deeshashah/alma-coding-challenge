# Agent Usage

## Tools

- Built entirely with Claude Code. Mostly Sonnet, switching to Opus for the deeper review/planning passes (the "review like a principal engineer" pass on production-readiness, and the full-codebase audit that found the `httpx2` issue below).
- Leaned heavily on parallel background subagents to parallelize implementation once the core scaffolding existed. For example, the email abstraction and attorney auth were built concurrently by separate subagents, each scoped to a non-overlapping set of files so they couldn't collide.
- Reviewed each subagent's output diligently, kept the test suite green throughout, and added features incrementally rather than in one large batch.
- Anything I didn't want to tackle immediately went into a running backlog (`BACKLOG.md`, `discussion points.md`) instead of being solved on the spot or silently dropped.

## Delegated vs. wrote myself

I drafted the initial system design myself: the API contracts and data models in `SYSTEM_DESIGN.md`, before any implementation started. That included several of the edge cases that shaped it: how a duplicate submission by email should behave, whether the lead-state transition needed to be race-safe, how attorney notification should be routed.

Everything past that was implemented by Claude, mostly through parallel subagents once the design was settled: the actual endpoints, models, validation, the email abstraction, auth, the frontend form/dashboard, and the test suite.

Two decisions I want to call out as mine specifically, not just agent suggestions I accepted:

- **The atomicity issue on the state transition.** I raised the concern that two attorneys marking the same lead `REACHED_OUT` around the same time could race, and that a plain read-then-write wouldn't reliably catch that. The conditional atomic `UPDATE ... WHERE state = 'PENDING'` (with a rowcount check and a `409` on conflict) was the fix I asked for once I'd identified the problem, not something the agent flagged unprompted.
- **New row vs. update-in-place for duplicate emails.** I had the agent build the upsert version first, then walked through the trade-offs with it explicitly: an upsert risks silently resetting attorney-owned state and losing the prior submission's contents, versus a plain insert which keeps full history at the cost of duplicate rows in the dashboard. I made the call to go with always-inserting new rows for now, and had the upsert version reverted. Both sides of that trade-off are written up in `SYSTEM_DESIGN.md` and `DESIGN_DECISIONS.md`.

## Where the agent got it wrong

The clearest example: at some point a background/setup pass added `httpx2` to `requirements-dev.txt` instead of the real `httpx` (needed for FastAPI's `TestClient`).

- It's not a typo. `httpx2` is a convincingly-named impostor package (same author name, same tagline as real httpx, fake GitHub org) that pulls its own off-name dependencies.
- Worse, the local venv's vendored Starlette had been hand-patched to `import httpx2 as httpx`, which is the only reason the test suite ran at all. A clean install on unmodified Starlette would have failed outright.
- This didn't show up as a test failure. All 76 tests passed, because the patched import made everything work locally.

I only caught it by explicitly asking for a full-codebase review and having the agent scan `requirements-dev.txt` and the installed venv against what should actually be there, rather than trusting "tests are green."

Fix was straightforward once found: swap `httpx2` for `httpx` in the requirements file, uninstall the impostor packages, and rebuild the venv from scratch so the patched Starlette was discarded.

The lesson I took from it: a green test suite is not the same as a trustworthy dependency tree. That's exactly the kind of thing worth a deliberate review pass rather than assuming heavy agent usage is safe by default.
