# Batch-Complete Review Protocol

## Contents

1. Risk classification
2. Coverage matrix
3. Counterfactual fixed point
4. Assumption ledger
5. Closure support and fixed-point stability
6. Coverage audit, two-blind synthesis, and escalation
7. Freeze and invalidation
8. Cost controls

## 1. Risk classification

### L1: local

Use for a leaf computation with no shared state, authority, identity, schema,
recovery, concurrency, or live boundary. A single batch-complete reviewer is
normally sufficient.

### L2: cross-cutting

Use when a change crosses modules or affects shared state, schemas, routing,
identity, mutation ordering, retries, cancellation, or more than one lifecycle
phase. Start with one fixed-point reviewer. Add a narrow coverage auditor when
the change includes active mutation, recovery, authority, identity, or a recent
sibling escape.

### L3: release or cutover critical

Use for security/authority boundaries, rollback-sensitive transitions,
destructive operations, migrations, releases, pre-cutover gates, or repeated
escaped HIGH/CRITICAL siblings. Normally use one fixed-point reviewer plus a
narrow coverage/assumption auditor. Use two sealed blind reviewers with
orthogonal lenses plus reciprocal audits when authority/security is coupled to
release or cutover, or when a supposedly covered family recently escaped
another HIGH/CRITICAL sibling. A third full reviewer remains escalation, not
default.

## 2. Coverage matrix

Build required cells from these dimensions:

- contract or invariant;
- public/operator entrypoint and internal caller;
- lifecycle, journal, or state phase;
- validation, mutation, recovery, retry, rollback, and terminal cleanup;
- exact/fresh, stale, same-owner-new-generation, foreign, missing, malformed,
  expired, repeated, and idempotent variants as applicable;
- expected success or fail-closed behavior;
- required T0-T4 evidence tier;
- source and executable evidence.

Each row is atomic and names exactly one contract, entrypoint, operation,
lifecycle phase, adversarial variant, expected behavior, and required evidence
tier. Do not bind composite rows such as "all crash phases" or "all stale and
foreign variants." If semantic review discovers a required subcell that the
matrix omitted, record a matrix gap, return an incomplete finding-set status,
and rebind before any lane can claim `BATCH_COMPLETE`.

Allowed cell status:

- `COVERED_NO_FINDING`;
- `FINDING`;
- `NOT_APPLICABLE`, with evidence-backed reason;
- `EVIDENCE_GAP`;
- `UNVISITED`.

Record `closureSupport` independently:

- `SUPPORTED`;
- `WRONG_TIER`;
- `UNSUPPORTED`;
- `NOT_APPLICABLE`;
- `OPEN`.

Also record the highest evidence tier actually supporting the disposition.
`COVERED_NO_FINDING` requires `SUPPORTED` evidence at or above the matrix's
required tier. `FINDING` may block at a lower tier when the unsafe behavior is
already established, but its evidence and required regression/reopen cells
must be explicit. `NOT_APPLICABLE` requires an evidence-backed reason.

PASS requires zero required `EVIDENCE_GAP`, `UNVISITED`, `WRONG_TIER`,
`UNSUPPORTED`, and `OPEN` cells. Writing 22 dispositions for 22 cells proves
visitation, not closure.

Use `EVIDENCE_CLOSURE_INCOMPLETE` when a supported blocker establishes actual
`BLOCKED` but required evidence tiers, safe sibling dispositions, or reopen
obligations remain open. Keep the counterfactual verdict `UNRESOLVED`. This
preserves known candidate truth without laundering partial coverage into a
complete repair batch.

Treat the four levels as non-equivalent:

`visited != supported closure != lane complete != audited batch complete`

Only the final synthesis can make the fourth claim when an auditor topology is
selected.

When one primitive is unsafe, enumerate every call site and sibling lifecycle
path. Classify each as affected, safe with evidence, not applicable with reason,
or unvisited. Do not close a contract with broad prose.

## 3. Counterfactual fixed point

Let `A0` be an empty assumption set. Traverse the full matrix against the actual
candidate. For each new blocker `Bi`:

1. Record `Bi` against actual source and evidence.
2. Define minimal behavioral postcondition `Ai`; do not imagine patch details.
3. Add `Ai` only if it is falsifiable and consistent with prior assumptions.
4. Compute its affected callers, consumers, state phases, and matrix cells.
5. Reopen every affected cell, including cells previously marked safe.
6. Traverse all open and required cells under the accumulated assumption set.

Converge only when a complete traversal adds no blocker, changes no assumption,
and reopens no cell. Then perform an adversarial assumption audit. If that audit
changes anything, iterate again.

This establishes counterfactual closure, not correctness of real bytes.

## 4. Assumption ledger

Each assumption must contain:

- stable ID and covered finding IDs;
- violated invariant or contract;
- narrow repair postcondition;
- affected symbols, call sites, and lifecycle cells;
- cells reopened when the assumption was added or expanded;
- required regression cells and evidence tier;
- conflicts or dependencies on other assumptions;
- falsification condition.

Reject assumptions such as “assume fence handling is fixed” or “assume tests
pass.” Prefer a behavioral rule such as “before the first restore, validate the
current fence's exact plan and receipt digest; revalidate before terminal clear.”

Every blocking finding must be covered by at least one assumption before
`PASS_UNDER_ASSUMPTIONS` is valid. An assumption cannot cover a finding by ID
alone; its postcondition and affected cells must address the unsafe operation.

## 5. Closure support and fixed-point stability

Every finding and assumption creates reopen obligations. Each obligation names
the trigger, affected cells, required disposition, and supporting evidence.
Before a lane may claim `BATCH_COMPLETE`:

1. every required cell is visited;
2. every no-finding closure is supported at the required tier;
3. every finding's required regression cells are covered by reviewed reopen
   obligations;
4. every assumption's reopened cells are reviewed under the accumulated
   assumption set;
5. no reopen obligation or coverage challenge remains open;
6. the reviewer has explicitly attacked all applicable dimensions:
   - sibling call sites;
   - lifecycle/state transitions;
   - unrecognized current-live third states before the first mutation;
   - evidence/compatibility altitude;
   - repair-postcondition completeness.

The third-state attack is mandatory when a repair, rollback, recovery, or
cleanup path trusts a saved preimage, journal, fence, lease, claim, or authority
artifact. Proving the saved artifact belongs to the transaction does not prove
the current target bytes are safe to overwrite.

The evidence-altitude attack separates provenance from behavior. Hash-binding
an existing receipt does not close a cell when the receipt never executed the
required production seam, recovery sibling, compatibility status path, or
policy decision.

If any attack adds or expands a finding, assumption, evidence gap, or affected
cell, mark the fixed point unstable, reopen those cells, and iterate.

## 6. Coverage audit, two-blind synthesis, and escalation

Use a narrow independent auditor when L2/L3 triggers require it. The auditor
examines the sealed report's completeness, not the implementer's desired result.
Mark this artifact `auditMode: NARROW`, bind both report-hash fields to the one
sealed primary report, and use a distinct auditor identity. This makes the
single-lane topology explicit without pretending the auditor performed another
blind full pass.

Escalate to a second full blind reviewer only when:

- a supported HIGH/CRITICAL finding is disputed after the narrow audit;
- a required matrix partition remains unowned or over budget;
- the primary reviewer is incomplete, unavailable, unauthenticated, or
  hash-mismatched;
- a prior supposedly covered cell has another sibling HIGH/CRITICAL escape;
- genuinely independent critical contract families require distinct expertise.

The second reviewer receives a neutral frozen context and does not see disputed
verdicts until its bounded pass is sealed. Never use majority vote.

For the selected two-blind topology:

1. assign orthogonal lenses and the same frozen matrix;
2. keep each first pass blind to peer artifacts until both are sealed;
3. require both lanes to continue after the first blocker and close their own
   reopen obligations;
4. let A audit B and B audit A without rewriting either first pass;
5. hash-bind both first-pass reports in each audit;
   mark each audit `auditMode: RECIPROCAL` and bind the auditor identity to the
   owner of `ownReportSha256`;
6. challenge unsupported closure, wrong tier, missed siblings, incomplete
   repair postconditions, weak evidence, and unstable fixed points;
7. cluster overlaps as:
   - `FULL_DUPLICATE_PRIMITIVE`;
   - `PARTIAL_OVERLAP_RETAIN_DISTINCT_AXES`;
   - `RELATED_FAMILY_NOT_DUPLICATE`;
   - `UNIQUE`;
8. let the main agent recompute closure from the union.

Only the synthesis may claim `AUDITED_BATCH_COMPLETE`. A first-pass
`BATCH_COMPLETE` is lane-local. Start a third reviewer only when the reciprocal
union still has a supported disputed blocker, unowned partition, hash mismatch,
or unresolved coverage challenge. When every challenge has a concrete union
disposition, synthesize without a third reviewer even if the lanes found
different or differently clustered issues.

Every cross-audit finding must be actionable input to synthesis, not a prose
aside. Record its contracts and matrix cells, preconditions, execution path,
first unsafe operation, impact, evidence tier, repair properties, and required
regression cells. Every synthesis cluster must carry disposition evidence,
preserve the blocking status of accepted members, and retain the union of their
regression cells. Rejecting a lane finding requires evidence; omission is not a
rejection.

## 7. Freeze and invalidation

Bind four artifacts into one review wave:

1. candidate manifest: source, tests, build inputs, contracts, bundled skills,
   intended untracked bytes;
2. evidence index: executable hashes and raw verification receipts;
3. review plan: risk class, contracts, roles, budgets, protocol version;
4. coverage matrix: required cells and evidence tiers.

Production source, tests, executable contracts, build inputs, or bundled skill
bytes require a new candidate and review wave. Changed executable evidence
requires reacquiring the smallest affected evidence and a new binding. Pure
review-artifact or auxiliary wording changes do not invalidate executable tests
unless they change a contract or reveal a gap.

Never repair after the first finding while the review wave is still running.
Finish enumeration, synthesize one coherent batch, then change source.

## 8. Cost controls

- Make hashing, schema validation, manifest comparison, and raw test counting
  deterministic.
- Provide paths and hashes instead of pasting large logs.
- Let reviewers open evidence on demand.
- Use the lowest model/effort lane that can meet the role; reserve maximum
  reasoning for a bounded unresolved contradiction.
- Do not rerun broad tests merely to perform source review.
- Declare budgets before review. Budget exhaustion returns `INCOMPLETE` with all
  unvisited cells.
- Track late sibling escapes, challenged findings, coverage gaps, refreeze
  count, and unnecessary escalations. Do not reward finding count.
