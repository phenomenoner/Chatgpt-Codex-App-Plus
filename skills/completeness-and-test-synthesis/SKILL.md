---
name: completeness-and-test-synthesis
description: Engineering completeness and test-evidence synthesis for explicit readiness judgments, recurring regressions, green-tests-but-broken-real-use failures, cross-component or lifecycle changes, and choosing the lowest verification altitude that can falsify a claim. Use when the user asks whether work is actually done or ready, when evidence coverage is disputed, or when logs and receipts should become regression tests. Do not trigger for every ordinary implementation or merely because a task ends.
---

# Completeness and Test Synthesis

Decide whether the available evidence supports the exact claim, and manufacture
one missing test when it does not. The workflow is not an end-of-task ceremony:
small, local changes should stay small.

## Start from the claim

Before choosing tests, state:

1. the changed behavior or invariant;
2. the first seam where the old defect or a plausible regression would be
   observable;
3. the affected callers, state transitions, and external boundaries;
4. the strongest fresh evidence already available.

Use repository history, incident evidence, and call sites to identify blast
radius. Do not infer risk from file count, the word `mutation`, or a workflow
label alone.

## Choose the lowest falsifying altitude

| Tier | What it can establish |
|---|---|
| T0 | Static shape, compilation, formatting, schema, or generated-file consistency |
| T1 | Local behavior of one unit with controlled collaborators |
| T2 | Behavior across the touched real component or contract seam |
| T3 | A lifecycle, multi-component, or user scenario that lower tiers cannot faithfully represent |
| T4 | A bounded live/external claim such as provider visibility, timing, or soak behavior |

Choose the lowest tier at which the relevant defect would actually fail.

- A local state transition with an isolated contract may be fully falsifiable at
  T1.
- Serialization, persistence, IPC, or another touched boundary normally needs a
  focused T2 check.
- Use T3 when the claim depends on ordering across lifecycle phases, multiple
  real components, recovery, or a user journey that T1/T2 cannot represent.
- Use T4 only when the requested claim itself includes live or externally
  visible behavior and that operation is authorized.

Higher tiers do not replace lower-tier logic tests, and repeated integration
runs do not compensate for a non-discriminating assertion.

## Use regression-first where it proves something

For a safe, reproducible existing bug, prefer a test or fixture that fails for
the original reason before the repair and passes afterward. An already-failing
test is valid fail-first evidence; it does not need to be recreated.

Fail-first proof is not mandatory when:

- the behavior is net new rather than a repair;
- the change is documentation, formatting, generated metadata, or a mechanical
  synchronization;
- the pre-change state is unavailable or reproduction would be destructive,
  unsafe, flaky, or dependent on a live system;
- an existing trustworthy test already demonstrates the failure.

In those cases, use a current-state check that is still discriminating: it
should fail if the new behavior is removed or the relevant defect returns.
State any material limitation instead of inventing a pre-change run.

## Run the completeness check

Check only the rows relevant to the claim:

1. **Contract:** Name the behavior or invariant and the affected consumers.
2. **Discrimination:** Confirm each selected check can fail for a meaningful
   violation, not merely for a missing field or expected string.
3. **Seam:** Exercise the real failure-bearing seam at the lowest sufficient
   tier.
4. **Failure variants:** Add negative, boundary, recovery, concurrency, or
   stale-state cases only when they are credible failure modes.
5. **Evidence freshness:** Reuse results only while the executable bytes,
   relevant tests/contracts, toolchain, and required environment remain
   materially unchanged.
6. **Claim boundary:** Separate source correctness, artifact identity,
   deployment, and live behavior. Do not promote one into another.
7. **Open gaps:** Record gaps that could change the decision; do not turn
   optional process artifacts or untested implausible combinations into
   blockers.

For a local implementation, a short statement of behavior, command, result, and
remaining gap is enough. Use a table only when several independent claims or an
explicit readiness/release decision make it clearer.

## Synthesize the smallest missing test

When the check finds a material gap, create the smallest durable test that
closes it:

- **Incident:** Reduce the observed failure to a sanitized deterministic
  fixture, then assert the violated invariant.
- **Touched boundary:** Drive the real seam with the smallest representative
  allowed and disallowed cases.
- **Lifecycle:** Reproduce only the phases needed for the failure, including
  restart, retry, cancellation, or recovery when relevant.
- **Recorded evidence:** Capture, sanitize, minimize, assert, and wire the
  fixture into the narrowest reliable runner.

Read [references/receipt-to-replay.md](references/receipt-to-replay.md) when
turning traces, logs, or receipts into a replay fixture.

Prefer tests that are deterministic, hermetic, behavioral, and clear when they
fail. Inject time and identifiers; do not use sleeps or a live dependency where
a controlled seam proves the same contract.

## Bind artifact claims only when relevant

When a claim depends on build or deployment bytes, distinguish:

- source/input continuity;
- the immutable instance actually executed or selected for deployment;
- build-recipe identity;
- reproducible rebuild;
- semantic equivalence.

A mutable build output cannot prove that an earlier executed instance still
exists. Preserve the exact instance before another build can overwrite it.
Bind compiler, linker, SDK, flags, environment, and repeated byte equality only
when reproducibility is the claim.

Frozen release/review evidence stays append-only while that gate is active. If
an assertion is unsound, supersede it without erasing unaffected evidence.
These requirements do not apply to ordinary local test output.

## Keep review proportional

Independent review is evidence for an explicit review, release, migration,
cutover, or other high-risk gate—not a required blessing for each patch.
Stabilize one coherent candidate before a formal review. If ordinary local
checks close the requested claim, stop there.

## Project adapter

Create or reuse a project adapter only when repeated or high-risk work benefits
from stable knowledge of contracts, boundaries, test runners, replay sources,
and release gates. Do not create one for a one-off local change.

## Report

Report the exact claim, verification tier actually reached, meaningful commands
and results, and any gap that could change the conclusion. Say `not verified`
when the required behavior was not exercised; do not replace behavioral
evidence with a checklist sentence.
