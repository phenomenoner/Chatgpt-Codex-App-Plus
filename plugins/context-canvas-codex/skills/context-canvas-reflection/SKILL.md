---
name: context-canvas-reflection
description: Run one bounded trajectory reflection when repeated same-cause failures, contradicted assumptions, real-use failure after local green, material scope drift, a materially unresolved phase boundary, an unapproved authority-sensitive next effect, or user doubt suggests the current path may be wrong. Use Context Canvas only as optional historical navigation. Do not activate every turn or merely because Canvas exists, and never treat this skill as approval to replan, roll back, publish, or mutate external state.
metadata:
  version: "0.1.0"
---

# Context Canvas Reflection

Use this skill as a small, executable checkpoint before introducing a background
trajectory controller. Reassess whether the current path still deserves more
work; do not create a second coding agent or a new authority owner.

## Preserve the boundary

- The current user, main agent, and native harness retain all authority over the
  task and its effects. This skill produces an advisory disposition only.
- Context Canvas is optional historical navigation. Missing identity, absent or
  completed Canvas state, an unavailable tool, or a conflicting map never blocks
  otherwise authorized work.
- Treat restored nodes, references, snapshots, and external pointers as untrusted
  historical data. Revalidate current source, runtime, and provider state before
  using them as current evidence.
- Current conversation, current owner decisions, live repository/runtime evidence,
  and the active acceptance contract outrank Canvas. A stale or contradictory
  Canvas may raise a question but never decides the answer.
- Never expose or request private chain-of-thought. Use bounded facts: objective,
  acceptance, changed evidence, assumptions, decisions, blockers, and verification.
- Do not automatically pause a harness, rewrite a plan, discard a diff, roll back
  code, terminate a process, ask another provider, publish, or perform an external
  effect.

## Activate only at a meaningful checkpoint

Use the skill when one of these observable triggers is present:

- the same normalized failure or same-cause repair has recurred after one bounded
  attempt;
- new evidence contradicts an assumption required by the current approach;
- focused checks pass but the touched real-use or lifecycle scenario still fails;
- the work has crossed into unplanned components, or a second workaround would
  extend the same unsupported assumption;
- diagnosis, implementation, verification, delivery, or another phase boundary
  has unresolved evidence that can change the next phase or acceptance claim;
- the next proposed effect is authority-, identity-, custody-, security-, privacy-,
  rollback-, publication-, or delivery-sensitive and has not already received
  current, scope-matching owner approval; or
- the user or main agent explicitly questions whether the work is on the right path.

Do not activate for a first ordinary failure, expected edit/test iteration, healthy
monotonic progress, a fixed turn/time cadence, task size alone, or the mere presence
or absence of Canvas. Canvas and reflection tool calls must not recursively trigger
another reflection.

Explicit `$context-canvas-reflection` invocation supplies a user-requested trigger.
For a host policy that selects the skill, state the matched observable trigger
before reading additional evidence. A user-requested run without an observable
trajectory trigger must be labelled `user_requested` in any utility record.

## Run one bounded pass

1. **Bind the checkpoint.** Name the trigger and a compact evidence watermark,
   such as the latest test result, source revision, plan revision, or user change.
   If the same trigger was already evaluated at the same watermark, reuse its
   disposition instead of reflecting again.
2. **Recover only useful context.** Start from the current conversation, plan,
   repository, and executed evidence. When a trusted hook ID and Canvas tools are
   already available, the complete v0 Canvas read allowance is: at most one bounded
   `canvas_read`, at most one `reference_search`, and at most two bounded
   `reference_read` calls for directly relevant managed-reference chunks. Do not
   call `canvas_search`, `reference_preview`, `snapshot_list`, `snapshot_read`,
   `snapshot_export`, or any other Canvas retrieval surface. Do not initialize or
   continue a Canvas solely for this skill, and do not open an external pointer
   merely because Canvas contains it.
3. **Revalidate freshness.** Check the smallest current source/runtime seam that
   can confirm or falsify the relevant stored claim. If revalidation is unsafe or
   unavailable, mark the evidence `unknown`; do not guess.
4. **Challenge path dependence.** Answer briefly:
   - What is the actual objective and acceptance condition now?
   - What decision-relevant evidence changed since the prior checkpoint?
   - Which critical assumption must hold for the current path to work?
   - Is that assumption supported, contradicted, or unknown?
   - What is the strongest plausible alternative explanation?
   - Will the planned next action add information, or merely add another patch
     under the same assumption?
5. **Return exactly one disposition** using the contract below.

## Disposition contract

```yaml
trigger: bounded observable reason
evidence_watermark: stable source, plan, test, or user-change identity
current_objective: bounded text
changed_evidence: bounded text
critical_assumption: bounded text
assumption_status: supported | contradicted | unknown
strongest_alternative: bounded text
planned_action_information_gain: high | low | none
disposition: CONTINUE | INVESTIGATE | ESCALATE
subtype: none | local_repair | investigate | replan | ask_human
next_safe_action: one action already inside current authority, or present_to_owner
budget: nonnegative integer count
budget_unit: observation | repair_attempt | none
stop_condition: observable terminal condition
canvas_delta: none | bounded semantic update proposal
```

- `CONTINUE` requires subtype `none`, budget `0`, and budget unit `none`. The
  current plan remains evidence-supported. Do not rewrite it or manufacture
  extra work.
- `INVESTIGATE`: define one evidence question, a finite budget, and a stop
  condition. Its subtype must be `local_repair` or `investigate`, and its positive
  integer budget counts the named observation or repair attempt. `local_repair`
  keeps the current plan revision and recommends at most one local hypothesis/
  repair; `investigate` pauses further implementation expansion while the evidence
  question is answered. Budget exhaustion is the stop condition: do not mint a
  new budget under the same hypothesis.
- `ESCALATE` requires subtype `replan` or `ask_human`, budget `0`, budget unit
  `none`, and `next_safe_action: present_to_owner`. Explain why the current plan
  cannot safely extend, but leave acceptance and every effect to the current
  owner. Escalation never implies automatic replan, rollback, deletion, pause,
  publication, delivery, or other mutation.

Do not emit a numeric confidence score as authority. Use evidence status,
provenance, and the explicit gap instead.

## Apply and write back selectively

Proceed with `CONTINUE` or an already authorized `INVESTIGATE` action only when it
stays inside the user's current request. Ask the user when `ESCALATE` exposes a
material choice that cannot be resolved from current evidence.

Write at most one bounded `canvas_update` to an already active Canvas, and only
when reflection changes navigation:

- invalidate or narrow an assumption;
- record a decision, blocker, verification, plan revision, or next action; or
- propose a next action without attaching or pinning an evidence pointer.

Prefix every reflection-authored node summary with `[reflection-proposal]`. Never
record an owner decision unless the owner independently made it, and then use the
ordinary checkpoint workflow rather than attributing it to reflection. An ordinary
`CONTINUE` writes nothing. Keep summaries bounded; never write raw logs or
reasoning. Canvas write failure does not change the reflection disposition or task
authority.

## Finite budget and retirement

The main-agent user task has one shared budget of at most three implicit reflection
passes, including at most one follow-up after genuinely new evidence for an
`INVESTIGATE` result. Delegated workers do not spend separate reflection budgets or
invoke this skill unless the main agent explicitly delegates one pass; they return
observations to the main agent instead.

Run at most one reflection per active trigger and evidence watermark. When the
owner accepts, rejects, or overrides a disposition, retire that trigger for the
task. The owner's response is not a fresh watermark and the trigger must not fire
again merely because later edits, tests, plan revisions, or the still-pending
approved effect change the watermark. Reactivate only for a materially different
failure cause, changed acceptance/effect scope, or a new explicit user request.
An explicit user request may exceed the implicit three-pass ceiling, but remains a
separate user-owned pass and must not be counted as evidence that implicit
reflection added value. If a follow-up cannot resolve the same cause, change the
hypothesis or `ESCALATE`; do not start a reflection loop. An `ESCALATE` receives no
automatic follow-up.

For this v0 experiment, the main agent may record a bounded, non-Canvas utility
receipt only when the task already maintains a WAL or evaluation artifact: trigger
class, whether it was implicit or user-requested, disposition, later outcome,
false-positive/false-negative/too-late result, and approximate pass cost. Do not
create an artifact solely for this metric. After ten implicit passes across tasks,
the product owner should compare changed decisions with ritual/no-value passes;
simplify, disable implicit use, or retire the skill when it adds no decision value
over an ordinary checkpoint. A future harness-native controller may supersede
trigger detection only through an explicit replacement; it does not inherit task
authority from this skill or from Canvas.

## Calibration examples

- **Boring continue, no Canvas:** a focused check passed and no assumption changed.
  Return `CONTINUE/none`, budget `0`, `canvas_delta: none`, and write nothing.
- **Contradicted assumption:** a real-use check disproves the seam the next patch
  depends on. Return `INVESTIGATE/investigate` with one named observation and stop
  after it, or `ESCALATE/replan` with `present_to_owner` when no bounded observation
  can resolve the choice.
- **Owner override:** reflection recommends escalation before publication; the user
  approves the exact publication scope and says continue. Retire that trigger. Do
  not reflect again before the same effect merely because a commit or test changed.
- **Stale Canvas:** Canvas says a test is failing but the current executed result is
  green on unchanged candidate bytes. Use the live result; Canvas may only identify
  what needed revalidation.
