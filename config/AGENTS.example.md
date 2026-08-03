# Global Codex Working Agreements

## Smallest reliable workflow

- Use the smallest workflow that can reliably establish the requested outcome. Plans, tests, skills, and reviewer loops are tools, not proof of quality by themselves.
- Preserve unrelated user work. Do not reset, clean, overwrite, or publish material outside the requested scope.
- Keep final synthesis, conflict resolution, and verification ownership with the main agent.

## Development completeness

- Before claiming software work is done, use `completeness-and-test-synthesis` or apply the same method manually: classify blast radius, map affected invariants, gather fresh evidence at the correct tier, and disclose remaining gaps.
- Use the lowest verification altitude that can falsify the changed behavior. Prefer focused unit and contract tests while editing; run broader scenario or repository suites once at a justified freeze boundary.
- Treat timeouts, output loss, stale receipts, and zero-match filters as unverified rather than passing.

## Review gates

- When the user asks for a code, diff, patch, pull-request, independent, final, release, migration, or pre-cutover review—or a project contract requires one—use `batch-complete-independent-review` as the default methodology. Ordinary implementation does not automatically trigger a reviewer loop.
- Continue after the first blocker. Record narrow repair postconditions, reopen dependent coverage cells, and stop only at coverage closure or an explicit incomplete condition.
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
