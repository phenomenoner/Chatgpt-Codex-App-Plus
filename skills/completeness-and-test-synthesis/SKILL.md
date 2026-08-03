---
name: completeness-and-test-synthesis
description: "Engineering completeness gate and test-case synthesis methodology. Use this BEFORE claiming any implementation is 'done', finished, complete, ready to merge/ship/release/cut over, or whenever verifying that a change is actually complete and adequately tested. Also use when tests pass but the feature still breaks in real use, when fixing one thing keeps breaking another ('fix A break B'), when a new version immediately reveals new or un-resolved bugs, when judging whether test coverage sits at the right altitude (unit vs integration vs scenario/replay), or when turning recorded logs/telemetry/receipts into replay regression tests. Applies verification-altitude tiers (T0-T4), blast-radius to required-tier mapping, fail-first and regression-first discipline, and an anti-self-attestation rule. Trigger even when the user only says 'is this done?', 'is it ready to ship?', 'did we actually finish this?', or 'why does it keep breaking right after release?'."
---

# Completeness & Test Synthesis

## What this is for

Two failure modes dominate mature codebases that are nonetheless "well tested":

1. **Fix A breaks B** — a local fix silently violates a cross-cutting contract.
2. **Ship, then immediately discover the bug** — a new version reveals a new (or
   un-resolved old) problem the first time it is actually used.

Both can be true *while the test suite is green*, because of one root cause:

> **Verification altitude is wrong.** The tests sit at the isolated-function
> layer, but the bugs live in cross-module, stateful, concurrent, multi-actor
> **integrated paths**. Green units prove the parts, not the assembled feature.

A second, compounding cause: teams record rich evidence (logs, telemetry,
receipts, traces) but turn the regressions they should catch into *prose* (a
"known gaps" doc, a checklist string) instead of an *executable test*. Prose does
not fail a build, so it cannot block a regression.

This skill is the discipline that fixes both. It is two **gates**, not advice.
A gate has a pass/fail condition; if it does not pass, the work is not done.

- **Gate A — Completeness check.** Run before declaring "done". Decides whether
  the change is verified at the altitude its blast radius requires.
- **Gate B — Test synthesis.** How to manufacture the missing higher-altitude
  tests, especially by replaying recorded data.

Start by running the **Project Adapter** (bottom) once per project, so the gates
bind to that project's real contracts, boundaries, recorded data, and test
runner. Without the adapter the gates are generic and weak.

---

## Gate A — Completeness Check

### A1. Classify the blast radius

Before deciding what evidence is needed, find out how far the change reaches.

- Does it touch a **cross-cutting boundary** — an identity/routing key, a shared
  state store, a serialization/schema contract, a concurrency or ordering rule, a
  security/permission boundary? (The Project Adapter lists these for your repo.)
- Does it touch a **component that owns an invariant/contract**?
- Does it touch an **active-mutation path** (writes, deletes, state transitions,
  retries, cancellation, delivery) versus a pure read/compute path?
- **Grep the callers, not just the changed function.** In large files the blast
  radius will not fit in one read; the cross-file effects are exactly where
  "fix A break B" hides.

### A2. Assign the required tier

| Tier | Meaning | Evidence that proves it |
|---|---|---|
| T0 | Mechanism exists | Compiles; branch/function present |
| T1 | Unit-tested in isolation | A test on the changed unit; asserts behavior, not field-presence |
| T2 | Integration-tested | A test drives ≥2 real modules through the real seam (no mock of the seam under test) |
| T3 | Scenario / replay-tested | A test reproduces a real user-journey at integrated altitude and asserts the relevant invariants |
| T4 | Live / soak validated | Captured live evidence: timing, real dependency behavior, concurrency under load |

**Required-tier rule (hard):**
- Touches a cross-cutting boundary, an invariant-owning component, or an
  active-mutation path → **T3 is required** (plus the boundary scenario pack from
  the adapter). T1 alone does **not** clear the gate.
- Pure local/leaf change, no shared state, no boundary → T1/T2 may suffice.

`Mechanism + T1` is the default trap. Most field bugs reported as "we fixed and
tested this but it broke" are T3 problems mislabeled as done at T1.

### A3. The completeness checklist (not satisfied = not done)

Each item must be answered with **evidence** — a passing/failing test or a
captured artifact — not with a sentence. These are gate conditions; the reason
each one is hard is given so you can see it is not bureaucracy.

1. **Invariant impact mapped.** Every invariant/contract the change can affect is
   listed (via the adapter's catalog). *Why: you cannot protect a contract you
   did not name.*
2. **Executable assertion per touched invariant.** For each, a test asserts it
   *for this change* — not just a prose note in a gaps doc. *Why: prose does not
   fail the build, so it never blocks the regression.*
3. **Fail-first proven.** At least one new/changed test **fails on the pre-change
   code and passes after**. *Why: a test that passes both ways proves nothing; it
   is the most common form of fake coverage.*
4. **Active-mutation actually exercised.** For state-changing paths, the mutation
   was run (in a test or staging), not merely inspected read-only afterward.
   *Why: read-only inspection confirms the field exists, not that the transition
   is correct; the mutation path's first real execution must not be production.*
5. **Boundary scenario pack run.** For changes on a cross-cutting boundary, the
   adapter's scenario pack ran (e.g. the allowed case still works AND the
   isolation case is still isolated). *Why: this is where "fix A break B" lands.*
6. **Negative / fail-closed case covered.** Not only "allowed path works" but
   "blocked path is blocked". *Why: most security and isolation regressions are
   silent loosenings of a previously-closed door.*
7. **Blast radius re-checked.** Callers/consumers of the changed surface were
   examined, not just the surface. *Why: the integrated effect is off-screen in
   the file you edited.*

### A4. Output: completeness verdict

Produce this table. Any row where `reached < required` is a **blocker**, stated
as such — do not soften it.

```text
| Item        | Tier required | Tier reached | Gap                         | Blocks done? |
|-------------|---------------|--------------|-----------------------------|--------------|
| <change>    | T3 (boundary) | T1           | no scenario test for <inv>  | YES          |
```

If you cannot reach the required tier now, say so plainly and record the gap as
**open** — do not relabel a fallback or a partial as full parity.

---

## Gate B — Test Synthesis

When Gate A finds a gap, manufacture the missing T2/T3 test. Three sources:

- **From a live incident — regression-first.** When a bug is found in use, the
  *first* artifact is a failing test that reproduces it; *then* the fix. This
  inverts the common order (fix → patch → unit-test-the-patch → ship → find the
  next break) that lets the same class of bug recur.
- **From a known-gaps list.** If the project keeps a "tested vs not-yet-tested"
  table (the adapter points at it), each untested cell usually already *names*
  the scenario to build. Treat that column as a synthesis backlog.
- **From the boundary matrix.** Generate the combinatorial cases across the
  project's routing/identity keys — cheapest first: the pairwise ones that have
  bitten before (same-actor vs different-actor, fresh vs stale, class A vs B).

### Synthesizing from recorded data (the high-leverage technique)

Most systems already record enough to replay a real failure as a deterministic
test. The data exists; the runner is what is missing. Full step-by-step recipe,
with assertion examples, is in **`references/receipt-to-replay.md`** — read it
when you actually build one. In brief: **capture** the trace/log chain for one
real interaction → **sanitize** (strip secrets/PII) → **reduce** to the minimal
set that reproduces → **assert against invariants** (not field-presence) →
**prove fail-first** → **wire it in** and point the prose gate at it.

### Anatomy of a synthesized test that is worth keeping

- **Deterministic** — no wall-clock or RNG dependence; inject time/ids. Make
  concurrency cases reproducible (seeded interleavings, not `sleep`).
- **Hermetic** — temp dirs / fresh state per test; no shared globals, no live
  environment.
- **Behavioral, not structural** — assert *what happened* (exactly one delivery;
  terminal state not resurrected; identity key preserved), not *that a field is
  present*. Asserting "the config contains string X" is the structural
  anti-pattern.
- **Has a clear failing mode** — when it breaks, the message names the contract
  violated.

### What synthesis does NOT replace

It raises the floor, not to bug-free. T4 live/soak is still needed for timing,
real-dependency behavior, true concurrency under load, and long-run parity. The
goal is to move *reproducible-from-recorded-data* failures from "discovered in
production" down to "caught in CI".

---

## Hard rules (non-negotiable across both gates)

1. **Anti-self-attestation.** A checklist item, a doc sentence, or a "passed X"
   string is a *reminder that evidence must exist*, never the evidence itself.
   Evidence is a test result or a captured artifact.
2. **Fail-first or it does not count.** New coverage must demonstrably fail
   without the change under test.
3. **Regression-first on incidents.** Reproduce before you repair.
4. **Name the tier honestly.** Do not collapse a lower tier, a fallback, or a
   partial into "done"/"full parity" in any summary, doc, or handoff.
5. **Batch remediation before independent review.** Do not turn independent
   review into a per-patch ceremony. Stabilize and locally verify one complete,
   hash-bound candidate before asking for the review that authorizes release or
   cutover.

### Candidate stabilization and review batching

When one failure invalidates a release or cutover candidate:

1. Contain any active hazard immediately; safety recovery never waits for a
   batching exercise.
2. Reproduce the failure and perform one phase-wide sweep across the coupled
   mutation, recovery, authorization, receipt, caller, and rollback paths.
3. Record all findings in one remediation ledger. Repair the coherent batch,
   including fail-first, negative, and recovery coverage, before freezing new
   hashes.
4. Run the main agent's local completeness gates on the whole batch. Freeze one
   candidate only after those gates pass.
5. Request one independent review of that stabilized candidate. If review finds
   multiple blockers, collect the complete finding set, remediate them as the
   next batch, rerun local gates, then request one fresh review.

Do not ask a reviewer to bless each small patch when the same candidate is
still changing. A genuinely new live-only observation may invalidate the
candidate and require another review, but first repeat the phase-wide sweep so
the next review covers a coherent repair batch rather than the first visible
symptom.

---

## Project Adapter (run once per project, then reuse)

The gates are only as strong as their binding to a real project. On first use in
a repo, discover and record these — then later invocations reuse them:

1. **Contract/invariant catalog.** Where are this project's invariants, contracts,
   or guarantees written? (e.g. an `invariants.md`, a topology/contract doc, a
   `*_catalog()` function, ADRs, or — if none exists — derive a short list from
   the most painful past regressions.) These are what Gate A item 1 maps against.
2. **Cross-cutting boundaries.** What are the routing/identity keys, shared
   stores, schema contracts, and concurrency rules that, if broken, cause
   cross-feature regressions? These drive the A1 blast-radius classification and
   the A3 item-5 scenario pack.
3. **Recorded data sources.** What does the system record that can be replayed —
   structured logs, telemetry events, JSONL/receipts, trace ids, recorded
   sessions, request captures? Note the schemas. This is Gate B's raw material.
4. **Test runner & layout.** How are unit / integration / scenario tests run and
   where do they live? Where should a new T2/T3 test go so it actually executes
   in CI?
5. **Release/ready gate.** Is there an existing checklist or release gate whose
   prose items should now point at executable tests instead of being self-
   attested?

If the project already has a written instantiation of this skill (a project-local
SOP), read it first and treat it as the adapter — this skill is the general
engine; that doc is the project's concrete bindings.

---

## When invoked, produce

- The **blast-radius classification** and **required tier** for the change.
- The **completeness verdict table** (A4), with blockers stated as blockers.
- For each gap, a **synthesis plan**: which source (incident / gaps-list /
  boundary matrix), and — if from recorded data — a sketch of the replay test and
  its invariant assertions.
- The honest **tier label** for the current state, with any open gaps recorded as
  open.
