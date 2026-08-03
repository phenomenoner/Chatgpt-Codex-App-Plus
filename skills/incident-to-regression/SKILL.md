---
name: incident-to-regression
description: Convert production, staging, CI, or local engineering incidents into redacted fail-first regression packages with normalized signatures, invariant and blast-radius analysis, reusable replay fixtures, verification-altitude requirements, and guarded rollout criteria. Use when Codex investigates a recurring pitfall, writes a post-incident engineering record, turns logs or receipts into a regression test, judges whether a repair is actually verified, or prepares incident-derived launch, cutover, and rollback gates.
---

# Incident to Regression

Turn each incident into durable prevention evidence without turning notes or a
passing low-level test into a completion claim.

## Preserve authority and evidence

1. Determine whether the request authorizes diagnosis only, implementation,
   deployment, or live mutation. Do not broaden that authority.
2. Preserve raw evidence in its existing access-controlled location. Do not copy
   secrets, credentials, raw live payloads, personal paths, or exact account,
   channel, user, session, or machine identities into a skill artifact, fixture,
   public document, or chat response.
3. Use stable hashes and redacted pointers to refer to evidence. Keep source,
   staging, candidate, live, and provider-visible behavior as separate claims.
4. Record missing or inaccessible evidence as a gap. Never invent a reproduction,
   result, review, or live observation.

## Build the regression package

Perform these steps in order:

1. **Normalize the signature.** State the component, trigger, observed failure,
   expected invariant, relevant environment dimensions, and volatile fields
   intentionally excluded. Prefer stable semantics over timestamps, PIDs, paths,
   or identities.
2. **Map the invariant and blast radius.** Name every affected contract and
   downstream consumer. Classify the radius as `local`, `component`,
   `cross-cutting`, or `live-external`. A diagnostic or guard that prevents a
   live action but does not itself mutate or contact a live/external system is
   normally `component` or `cross-cutting`, based on affected consumers.
   Reserve `live-external` for incidents or repairs whose claim includes an
   actual live-system mutation, provider request, or externally visible effect.
3. **Capture fail-first evidence.** Create the smallest deterministic artifact
   that fails for the original reason before the repair. Record the exact
   sanitized command, expected failure, actual pre-repair result, and fixture
   provenance. Bind an observed failure to a hashed evidence pointer. If
   reproduction is unsafe or unavailable, leave it `not-run` or
   `not-reproduced`, set unavailable command/result fields to `null`, and explain
   the gap; do not invent a command or call the repair verified.
4. **Describe the repair pattern.** Explain the reusable mechanism, why it
   restores the invariant, the affected surfaces, and how to roll it back. Avoid
   encoding a one-machine workaround as the general rule.
5. **Choose verification altitude.**
   - `T0`: static inspection, formatting, or schema validation.
   - `T1`: isolated unit or pure-function test.
   - `T2`: component or integration boundary.
   - `T3`: end-to-end scenario or recorded replay through the affected path.
   - `T4`: guarded live observation, provider-visible proof, or bounded soak.

   Use at least T3 for cross-cutting identity, routing, shared state, process
   ownership, delivery, security, or supervisor changes. Use T4 only after lower
   tiers pass when the claim includes live or external behavior.
6. **Define cutover guards.** List executable preconditions, stop conditions,
   rollback material, explicit external-effects constraints, and post-cutover
   readback. Require an independent reviewer for a live cutover claim.
7. **Make the replay reusable.** Isolate generation-specific state, sanitize
   inputs, cover negative and boundary cases, and bind fixtures and validators
   to the evidence they evaluate.
8. **Write redacted evidence pointers.** Include a distinct ID, purpose, stable
   pointer, hash when available, and explicit redaction status. Do not embed raw
   evidence. A claim that depends on an observed fail-first artifact must use a
   hash-bound pointer.

Read [pitfall-patterns.md](references/pitfall-patterns.md) when the incident
resembles a known process, restore, readiness, receipt, backup, fixture, or
hidden-window failure.

## Emit and validate the record

Emit one JSON record shaped like the template produced by:

```text
python scripts/validate_incident_record.py --template
```

Keep `status` at the strongest state actually proven:

- `draft`: analysis may be incomplete.
- `reproduced`: fail-first failure was observed.
- `repair-verified`: the repaired path reached its required verification tier.
- `cutover-ready`: verification passed, blocking gaps are empty, rollback is
  ready, and independent review passed.
- `live-observed`: cutover-ready gates passed and T4 post-readback evidence was
  observed.

Validate a record before using it as a gate:

```text
python scripts/validate_incident_record.py path/to/redacted-record.json
```

Treat validator success as record-shape evidence only. It does not attest that
commands ran, evidence is genuine, the repair is correct, or cutover is safe.
Inspect the referenced primary artifacts and use an independent review for
release or live-operation decisions.

## Completion guard

Do not claim `repair-verified`, `cutover-ready`, or `live-observed` from:

- an incident narrative without an observed fail-first artifact;
- source-text, AST, or line-order inspection presented as behavioral replay;
- zero matched tests, stale output, or a validator applied to another report;
- T0-T2 evidence for a change whose blast radius requires T3;
- passive health in place of provider-visible or live-behavior proof;
- self-review alone when the action changes a live system;
- a replay contaminated by state from another process generation;
- a child timeout, nonzero exit, malformed report, or recovery whose safe
  observation was not persisted before outcome classification;
- a rollback plan that has not been materialized and checked.

Report the achieved tier, independent-review state, blocking gaps, limitations,
and the exact claim that remains unproven.
