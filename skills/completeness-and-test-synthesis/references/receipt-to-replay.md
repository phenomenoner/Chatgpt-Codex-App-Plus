# Receipt / Log → Replay Test Recipe

Read this when you are actually building a replay-style regression test from a
system's recorded data. It expands Gate B of the parent SKILL.md.

The premise: a system that records the chain of a real interaction (structured
logs, telemetry events, JSONL receipts, a trace id that links the stages, a
recorded request/response, a captured session) already contains enough to replay
a real failure as a deterministic test. The data exists; the runner is missing.

## The six steps

### 1. Capture
Pull the full chain for **one real interaction** end to end — every stage from
the entry event through to the final outcome (e.g. ingress → queue → execution →
output → delivery, or request → handler → side-effect → response). Use whatever
correlation key the system has (trace id, request id, session id). List every
record/schema involved; you will assert against their fields.

### 2. Sanitize
Strip secrets, tokens, credentials, and PII. Keep the **structural** fields and
the **boundary/identity keys** — those are what the assertions need. Follow the
project's own redaction / public-hygiene rules. Never commit a fixture you have
not scrubbed.

### 3. Reduce
Minimize to the smallest record set that still reproduces the behavior under
test. A replay fixture is a readable specimen, not a raw dump. Delete records
that do not affect the assertion; keep just enough to drive the seam.

### 4. Assert against invariants (not field-presence)
Write assertions about *what must be true*, derived from the project's contract
catalog. Generic examples (adapt to your domain):

- **At-most-once:** replay N duplicate entry events → assert at most one unit of
  work / one side-effect.
- **Exactly-one-outcome:** assert exactly one success delivery OR one explicit
  terminal/error/dead-letter outcome — never zero, never both.
- **Terminal irreversibility:** feed a terminal record, then a stale "in
  progress" record → assert the terminal state is not resurrected.
- **Boundary preservation:** two actors/tenants sharing a channel → assert
  actor B's result is not suppressed or attributed by actor A's state, and the
  identity key survives through to the final output.
- **Surface separation:** intermediate/progress/diagnostic content must not leak
  into the final user-facing payload when configured to be hidden.
- **Budget/limit:** over-limit work is deferred or blocked, not silently dropped.

The anti-pattern to avoid: asserting that a field exists or that a config string
is present. That passes whether or not the behavior is correct.

### 5. Prove fail-first
Run the new test against the **pre-fix** code (or with the fix reverted) and
confirm it **fails**, then against the fixed code and confirm it **passes**. If
you cannot make it fail, it is not exercising the regression — find the real
trigger before continuing.

### 6. Wire it in
Place it where CI runs it (integration test dir, or a scenario module that forces
real module wiring). Name it by **contract + scenario** so coverage gaps are
visible at a glance. If the project keeps a "known gaps" / promotion-gate doc,
replace the relevant prose cell with a pointer to this test — the gate is now
executable.

## Determinism checklist for replay tests

- Inject time and ids; never read the wall clock or a real RNG.
- Reconstruct concurrency with seeded, ordered interleavings — not `sleep`.
- Fresh temp state per test; no shared global, no live environment.
- One clear failing assertion message that names the violated contract.

## Header template for a synthesized test

```
// Contract: <invariant id / name>
// Source: <incident ref / trace id>, sanitized replay
// Fails on: <the specific pre-fix behavior this reproduces>
// Asserts: <the behavioral guarantee, in one line>
```

## Scope note

Replay tests cover what is *reproducible from recorded data*: logic, ordering,
state transitions, boundary/identity handling, payload shaping. They do **not**
substitute for live/soak validation of timing, real-dependency behavior, and
concurrency under genuine load. Use replay to move reproducible failures from
"found in production" to "caught in CI"; keep a thin live/soak layer for the rest.
