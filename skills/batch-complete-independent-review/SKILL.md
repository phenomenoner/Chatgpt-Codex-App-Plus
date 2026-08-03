---
name: batch-complete-independent-review
description: Provider-neutral, batch-complete code and engineering review gate. Use whenever Codex is asked to review code, a diff, pull request, patch, migration, frozen candidate, release, or pre-cutover change; when a project requires an independent hash-bound review; when judging whether reviewed code is ready; or when serial reviews keep discovering sibling blockers one round at a time. Default to one counterfactual fixed-point reviewer, distinguish actual PASS from PASS_UNDER_ASSUMPTIONS, and escalate through Baton only when risk, disagreement, or coverage gaps justify another reviewer. Do not trigger merely because ordinary implementation work occurred without a review request or project review gate.
---

# Batch-Complete Independent Review

Find the complete actionable blocker batch before repair instead of stopping at
the first issue. Keep actual-candidate truth separate from counterfactual
closure.

## Preserve the surrounding rules

- Use the smallest reliable review shape. This skill does not mandate a
  reviewer loop for every code change.
- Invoke `baton-fanout-skill` before dispatching any subagent. Let Baton own
  worker count, model/effort routing, context minimization, and write ownership.
- Apply `completeness-and-test-synthesis` for blast-radius and required T0-T4
  evidence. Do not duplicate or weaken its test gate.
- Use `claude-independent-review` only when the user explicitly authorizes
  Claude. Treat Claude, Codex subagents, and local CLIs as execution adapters,
  not as this protocol's authority.
- Obey stricter project privacy, freeze, release, live-operation, and cutover
  rules. Review authority never authorizes implementation or live mutation.

## Choose the review shape

Start with one primary reviewer using the counterfactual fixed-point pass.

- **L1 local:** one batch-complete reviewer; no automatic auditor.
- **L2 cross-cutting:** one primary reviewer. Add one narrow coverage auditor
  when authority, identity, shared mutation, recovery, concurrency, or multiple
  lifecycle phases are involved.
- **L3 release/cutover critical:** one primary reviewer plus one narrow,
  independently dispatched coverage/assumption auditor. Upgrade to two sealed
  blind first passes with orthogonal lenses and reciprocal coverage audits when
  the gate combines authority/security with release or cutover, or when a
  supposedly covered family recently escaped another HIGH/CRITICAL sibling.
  Add a third full reviewer only for an unresolved supported disagreement, an
  unowned matrix partition, hash/binding failure, or an incomplete lane.

Never add a reviewer merely because a concurrency slot is free. One
well-supported blocker blocks; do not use majority vote.

Read [references/protocol.md](references/protocol.md) for risk classification,
the fixed-point algorithm, matrix construction, escalation, and invalidation.

## Build deterministic intake

Before semantic review, create or identify:

1. An immutable candidate manifest, including intended untracked files.
2. A verification-evidence index with executable and receipt hashes.
3. A neutral review plan with contracts, authority boundaries, and budgets.
4. A required coverage matrix spanning entrypoints, lifecycle phases,
   mutations, recovery/cleanup paths, adversarial variants, and evidence tiers.

Use `scripts/review_gate.py bind` to hash these four artifacts into one review
wave. Hashing and schema checks are tooling work, not frontier-model work.

```powershell
python scripts/review_gate.py bind `
  --candidate-manifest <candidate.json> `
  --evidence-index <evidence.json> `
  --review-plan <plan.json> `
  --coverage-matrix <matrix.json> `
  --output <review-wave.json>
```

Do not start semantic review when the candidate is moving or any required
binding is missing.

## Separate visitation, support, and audited completion

Do not infer completeness from a cell count. These are distinct claims:

- **Visited:** the reviewer wrote a disposition for the cell.
- **Supported closure:** a no-finding disposition has evidence at the matrix's
  required tier, or a finding is supported strongly enough to block.
- **Lane complete:** one sealed reviewer has no open or unsupported required
  cell and its own reopen obligations reached a stable fixed point.
- **Audited batch complete:** the main-agent synthesis resolves every coverage
  and finding challenge across the required auditor topology.

A report can visit every cell and still be incomplete because a closure is
unsupported, at the wrong evidence tier, or invalidated by a finding that
should have reopened sibling cells. Individual lane `BATCH_COMPLETE` is never
the final multi-review gate verdict.

## Run the counterfactual fixed-point pass

Give the primary reviewer the frozen wave, matrix, contracts, source, and
evidence paths. Do not give it a desired verdict or peer findings.

Require this loop:

1. Review the actual frozen candidate against every required matrix cell.
2. On a blocker, record the exact precondition, first unsafe operation, impact,
   evidence, sibling paths, and required regressions.
3. Define a narrow, falsifiable repair postcondition in the assumption ledger.
   Never assume an implementation or broadly assume that a subsystem is fixed.
4. Continue under the accumulated postconditions.
5. Reopen every previously closed cell that depends on a new or expanded
   assumption.
6. Repeat full matrix traversal until no blocker, assumption, or reopened-cell
   status changes.
7. Record explicit reopen obligations for each finding and assumption. A
   finding's required regression cells must all receive a reviewed
   disposition; an ID-only reference is insufficient.
8. Attack the claimed closures across sibling call sites, lifecycle phases,
   unrecognized current-live third states, evidence altitude, and repair
   postcondition completeness.
9. Repeat when any attack changes a finding, assumption, evidence tier, or cell
   disposition. `stable: true` is valid only after all applicable attacks and
   reopen obligations are closed.

Finding a blocker changes the actual verdict to `BLOCKED`; it never ends the
review. If budget, access, hash drift, scope, or an unvisited required cell
prevents convergence, return `INCOMPLETE`.

## Keep verdicts non-substitutable

Use all three fields:

- `actualCandidateVerdict`: `PASS`, `BLOCKED`, or `INCOMPLETE`.
- `findingSetStatus`: `BATCH_COMPLETE` or an explicit incomplete reason.
- `counterfactualVerdict`: `NOT_NEEDED`, `PASS_UNDER_ASSUMPTIONS`, or
  `UNRESOLVED`.

`PASS_UNDER_ASSUMPTIONS` is a repair-planning result, never approval to merge,
ship, release, migrate, preflight, or cut over. Any blocker means the actual
candidate remains `BLOCKED`.

After implementation changes, freeze the actual new bytes, reacquire the
mapped evidence, and obtain the project-required fresh review. Historical
findings remain useful; their verdict never transfers to new bytes.

## Audit coverage without repeating the full review

For L2/L3 triggers, give a narrow auditor only the sealed primary report, review
wave, matrix, call-site/test map, and necessary source evidence. Ask it to find:

- required cells left unvisited, unsupported, or closed below the required
  evidence tier;
- blocker families with missing sibling-path disposition;
- assumptions that are broad, unfalsifiable, inconsistent, or circular;
- dependent cells that were not reopened;
- saved-state or ownership proofs that never attack unrecognized current-live
  bytes before the first mutation;
- provenance-only repairs that do not execute the required behavior at the
  required compatibility altitude;
- unsupported findings or severity;
- reasons the claimed fixed point is not stable.

The auditor does not rerun the whole review or modify the sealed report. The
main agent resolves challenges from primary evidence and owns synthesis.

For the two-blind L3 shape, keep both first passes sealed until both finish.
Then let A audit B and B audit A. Each reciprocal audit must hash-bind both
reports and classify challenges as `UNSUPPORTED_CLOSURE`, `WRONG_TIER`,
`MISSED_SIBLING`, `INCOMPLETE_REPAIR_POSTCONDITION`, or another explicit
protocol category. Classify overlaps as full duplicates, partial overlaps that
retain distinct acceptance axes, related-family nonduplicates, or unique
findings. Do not repair source until both audits and main-agent union synthesis
finish.

Set `auditMode` explicitly. A reciprocal audit uses `RECIPROCAL`, binds the
auditor's own sealed first pass plus the peer pass, and requires distinct
reviewer identities. A narrow audit uses `NARROW`, binds both report-hash fields
to the single sealed primary report, and requires an auditor identity distinct
from that primary reviewer. Do not silently treat a narrow audit as a second
blind lane.

## Validate the report

Require `references/review-report.schema.json`. Then run:

```powershell
python scripts/review_gate.py validate-report `
  --wave <review-wave.json> `
  --report <review-report.json>
```

For each reciprocal direction, validate the sealed reports and audit together:

```powershell
python scripts/review_gate.py validate-audit `
  --wave <review-wave.json> `
  --own-report <own-sealed-report.json> `
  --peer-report <peer-sealed-report.json> `
  --audit <cross-audit.json>
```

Finally validate the selected topology and main-agent union synthesis:

```powershell
python scripts/review_gate.py validate-synthesis `
  --wave <review-wave.json> `
  --synthesis <review-synthesis.json>
```

The validator rejects hash drift and impossible verdict combinations, including
actual PASS with blocking findings, actual PASS under assumptions, batch-complete
claims with unvisited, unsupported, wrong-tier, or unstable required cells, and
counterfactual closure without an assumption covering every blocker and its
reopen obligations. The synthesis validator also rejects duplicate lane
identity, missing reciprocal direction, unsupported matrix closure, unresolved
challenge laundering, incomplete lane promotion, unclassified findings, and
finding rejection without disposition evidence. For a multi-lane topology,
only a passing synthesis validation may authorize
`AUDITED_BATCH_COMPLETE`.

## Synthesize one coherent repair batch

The main agent must:

1. Verify current wave and report hashes.
2. Union every sealed lane and reciprocal/narrow-audit challenge. Never use one
   lane alone when the selected topology requires multiple lanes.
3. Cluster only by invariant, precondition, first unsafe operation, and failure
   effect. Mark full duplicates, partial overlaps, related-family
   nonduplicates, and unique findings while retaining distinct lifecycle paths,
   evidence axes, and regression cells.
4. Recompute matrix closure from the union. Resolve every unsupported,
   wrong-tier, missed-sibling, and repair-postcondition challenge.
5. Set `AUDITED_BATCH_COMPLETE` only when the union has a concrete disposition
   for every required cell and challenge. A lane's self-declared
   `BATCH_COMPLETE` is insufficient.
6. Trigger a third reviewer only when a supported blocker remains disputed, a
   partition is unowned, a binding fails, or the union still has an unresolved
   coverage challenge. Finding count or lane disagreement alone is not enough.
7. Repair only after the complete review wave finishes.
8. Report actual verdict, counterfactual verdict, audited finding-set status,
   open coverage, and minimum coherent repair properties separately.

Do not let a reviewer self-approve its proposed repair, rerun broad suites to
manufacture confidence, inspect live secrets, mutate source/evidence, or perform
release/cutover actions unless separately authorized.
