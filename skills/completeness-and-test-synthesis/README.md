# completeness-and-test-synthesis

A portable Claude skill that turns "is this actually done, and is it tested at the
right altitude?" into two hard gates instead of a vibe.

## What problem it solves

Two failure modes dominate mature, "well-tested" codebases:

1. **Fix A breaks B** — a local fix silently violates a cross-cutting contract.
2. **Ship, then immediately discover the bug** — a new version reveals a new (or
   un-resolved old) problem the first time it is actually used.

Both happen *while the test suite is green*. The root cause is **verification
altitude**: the tests sit at the isolated-function layer, but the bugs live in
cross-module, stateful, concurrent, multi-actor **integrated paths**. Green units
prove the parts, not the assembled feature. A compounding cause: teams record
rich evidence (logs, telemetry, receipts, traces) but encode the regressions they
should catch as *prose* (a "known gaps" doc, a checklist string) rather than an
*executable test* — and prose cannot fail a build.

This skill is the discipline that closes both gaps.

## What it does

It applies two **gates** (pass/fail conditions, not advice):

- **Gate A — Completeness check.** Classify a change's blast radius, assign the
  test tier it requires (T0–T4), run a hard checklist where each item needs
  *evidence* (a passing/failing test or a captured artifact), and emit a verdict
  table where `reached < required` is a stated blocker.
- **Gate B — Test synthesis.** Manufacture the missing higher-altitude tests —
  regression-first from a live incident, from a known-gaps list, or from the
  boundary matrix — with a focus on **replaying recorded data** (logs / receipts
  / traces) into deterministic regression tests.

Four non-negotiable rules run through both: **anti-self-attestation** (a checklist
string is never the evidence), **fail-first** (a test must fail on the pre-change
code), **regression-first** (reproduce before you repair), and **honest tiering**
(never relabel a fallback/partial as "done"/"full parity").

## How it is structured (general engine + project adapter)

The skill body is project-agnostic. A **Project Adapter** section (run once per
repo) binds the gates to that project's real contracts, cross-cutting boundaries,
recorded-data sources, and test runner. So the same skill works across repos; each
repo gets a concrete instance.

```
completeness-and-test-synthesis/
├── README.md                       (this file)
├── SKILL.md                        (the skill: frontmatter + the two gates)
└── references/
    └── receipt-to-replay.md        (the 6-step recipe for replay tests from records)
```

`references/receipt-to-replay.md` is loaded on demand — only when actually building
a replay test — to keep the main skill lean (progressive disclosure).

## Install

Copy the skill folder into your user-level skills directory:

- macOS / Linux: `~/.claude/skills/completeness-and-test-synthesis/`
- Windows: `C:\Users\<you>\.claude\skills\completeness-and-test-synthesis\`

The loader reads `SKILL.md` (and `references/` on demand). `README.md` is
documentation only and is ignored by the loader, so it is safe to leave in place.

## When it triggers

Designed to fire whenever you (or a teammate) are about to call a change "done",
"finished", "ready to merge/ship/cut over", or when asking "is this ready?",
"did we actually finish this?", "why does it keep breaking right after release?",
or "is our test coverage at the right level?". See the `description` field in
`SKILL.md` for the full trigger surface.

## Positioning vs adjacent skills

- A manual "run the app and watch it" verify flow checks one change by hand; this
  skill decides *whether the change is verified at all*, at the right altitude.
- A diff code-review finds bugs in the patch; this skill asks whether the patch is
  *complete and adequately tested*, and how to synthesize the missing tests.
- A general dev-workflow skill covers planning→implementation→completion; this is
  the specialized engine that sharpens the "completion / is-it-done" check.

## Origin

Distilled from a 2026-06-28 second-opinion analysis of a long-lived Rust agent
harness that kept shipping versions that broke on first use despite rigorous unit
testing. The repo-specific instantiation of this skill (its first Project Adapter)
lives with that project as a local SOP; this folder is the portable, de-anchored
engine extracted from it.

## Status

`version 0.1.0`. Authored and registered; the optional eval/benchmark iteration
and description-triggering optimization passes have not yet been run.
