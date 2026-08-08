# Global Codex Working Agreements

## Smallest reliable workflow

- Use the smallest workflow that can reliably establish the requested outcome. Plans, tests, skills, and reviewer loops are tools, not proof of quality by themselves.
- Preserve unrelated user work. Do not reset, clean, overwrite, or publish material outside the requested scope.
- Keep final synthesis, conflict resolution, and verification ownership with the main agent.

## Optional Context Canvas

- Treat Context Canvas as a semantic map and snapshot index, not permission to work. A missing hook identity or uninitialized canvas must not block an otherwise authorized task.
- Use only a trusted hook-injected opaque identity. Continue without Canvas when it is unavailable; use explicit lineage when a new session should inherit an old map.

## Evidence-driven development

- For a local change, run the smallest discriminating check that can falsify the changed behavior. Do not require a plan, WAL, handoff, matrix, or reviewer merely to declare ordinary work complete.
- Use `completeness-and-test-synthesis` for an explicit readiness judgment, recurring regression, cross-component/lifecycle change, green-tests-but-broken-real-use failure, or material evidence gap.
- Prefer fail-first for a safe, reproducible existing bug. It is not mandatory for net-new, documentation/mechanical, already-failing, or unsafe/unavailable pre-change cases.
- Use T2 for a touched real seam, T3 only when a lifecycle or user scenario cannot be represented lower, and T4 only for an authorized live/external claim. Run a full suite only for a release-wide blast radius or unresolved coverage gap.
- Treat timeouts, output loss, stale receipts, and zero-match filters as unverified rather than passing.

## Review gates

- For an ordinary code, diff, patch, or pull-request review, inspect the change and sibling paths directly and continue after the first finding. Do not require formal gate artifacts.
- Use `batch-complete-independent-review` formal mode only for an explicitly independent/final/release/migration/pre-cutover decision, a project gate, or recurring sibling blockers.
- Keep the actual frozen-candidate verdict separate from counterfactual analysis. `PASS_UNDER_ASSUMPTIONS` is not an actual `PASS` and cannot authorize merge, release, deployment, or cutover.
- Preserve provider-specific authorization. In particular, use the Claude adapter only when the user explicitly asks to invoke Claude.

## Subagent dispatch

- Before creating a subagent, use `baton-fanout-skill` when installed. Dispatch only when the outcome, direct-work alternative, genuine independence, exclusive write ownership, stop conditions, and main-agent verification owner are clear.
- Do not parallelize overlapping writes or unresolved shared contracts. Treat failed or unavailable workers as visible coverage gaps.

## Long-running commands

- For commands expected to exceed five minutes, use `long-run-supervisor` when installed. Let the supervisor own heartbeat, stall detection, and terminal wakeups; do not spend reasoning turns on short-interval polling while the supervisor reports healthy state.

## Public publishing

- Before publishing, scan both source and generated artifacts for secrets, private paths, machine identifiers, internal milestones, drafts, checklists, and stale status claims.
- Rewrite internal shorthand into self-contained public language: behavior, compatibility boundary, impact, verification, and honest limitations.
- Do not copy third-party tools when a canonical public source and pointer are sufficient. Preserve license and provenance metadata.

## Destructive and external actions

- Resolve exact targets before destructive operations and prefer recoverable actions. Do not use broad roots, unresolved globs, or ambient environment variables as destructive targets.
- External publication, messages, live operations, purchases, and credential changes require task-level authority; delegation never expands that authority.
