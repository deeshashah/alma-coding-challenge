# Agent Usage

## Tools

- Built entirely with Claude Code. Mostly Sonnet, switching to Opus for the deeper review and planning passes.
- Leaned heavily on parallel background subagents to parallelize implementation once the core scaffolding existed. For example, the email abstraction and attorney auth were built concurrently by separate subagents, each scoped to a non-overlapping set of files so they couldn't collide.
- Reviewed each subagent's output diligently, kept the test suite green throughout, and added features incrementally rather than in one large batch.
- Anything I didn't want to tackle immediately went into a running backlog (`BACKLOG.md`, `discussion points.md`) instead of being solved on the spot or silently dropped.

## Delegated vs. wrote myself

I drafted the initial system design myself: the API contracts and data models in `SYSTEM_DESIGN.md`, before any implementation started. That included several of the edge cases that shaped it: how a duplicate submission by email should behave, whether the lead-state transition needed to be race-safe, how attorney notification should be routed.

Everything past that was implemented by Claude, mostly through parallel subagents once the design was settled: the actual endpoints, models, validation, the email abstraction, auth, the frontend form/dashboard, and the test suite.

Two decisions I want to call out as mine specifically, not just agent suggestions I accepted: the atomicity fix on the state transition, and going with new rows instead of update-in-place for duplicate emails. Both are also the clearest examples of catching the agent about to get something wrong, detailed in the next section.

## Where the agent got it wrong

Two concrete cases where the agent didn't catch a real problem on its own, and I had to find it myself.

**It did not find the concurrency issue.** The agent's first draft of the `PATCH /api/leads/:id` contract in `SYSTEM_DESIGN.md` was a plain "update the state" endpoint. Nothing in it accounted for concurrent access, and left as specified it would have led straight to a naive read-then-write implementation.

- I asked, before any code existed, whether two attorneys marking the same lead at the same time would cause problems. The agent hadn't raised this on its own.
- Working through it surfaced a real bug the naive version would have shipped with: a plain read-check-then-write lets two concurrent requests both pass the "is it PENDING" check before either commits. Both succeed silently, no error, and whichever write lands last wins the audit record, even if that attorney wasn't the one who actually reached out.
- Fix: a single atomic conditional `UPDATE ... WHERE id = ? AND state = 'PENDING'`, checking the affected row count, returning `409` if someone already won the race.

**It just assumed an approach for handling duplicate leads.** When asked to handle a prospect submitting the same email twice, the agent defaulted to upsert (update the existing lead in place) and built and tested that version without flagging the risk.

- The problem: an upsert lets the public, unauthenticated form silently reset an attorney's `REACHED_OUT` status back to `PENDING`, undoing real work with no audit trail of why. The agent didn't surface that as a consequence of the approach it picked.
- I only caught it by specifically asking what happens on a resubmit after an attorney already reached out.
- Fix: reverted to always inserting a new row per submission instead of updating in place. Full trade-off writeup is in `SYSTEM_DESIGN.md` and `DESIGN_DECISIONS.md`.

**The pattern in both:** the agent picks a reasonable-looking default and extends the shape of whatever's already there, but it doesn't reliably stop to ask "what happens under concurrency" or "what happens when a public write path touches state an internal user owns" unless someone specifically thinks to ask. Both of those questions were mine to raise, not the agent's.

A smaller, separate example also worth a mention: at one point a background/setup pass added `httpx2` (a convincingly-named impostor of the real `httpx` package) to `requirements-dev.txt`, and the local venv's vendored Starlette had been hand-patched to import it, which is the only reason the test suite passed. This one wasn't something I noticed by reading code. It surfaced during a deliberate full-codebase review pass I asked the agent to run, which is really the same lesson as above: an agent's own output, including its test suite going green, isn't proof that everything underneath it is correct. Fixed by swapping in real `httpx` and rebuilding the venv from scratch.
