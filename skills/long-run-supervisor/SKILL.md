---
name: long-run-supervisor
description: Launch and supervise long-running PowerShell commands with a local heartbeat, private task state, deterministic polling, terminal-only output, and optional idle-only multi-task fan-in; also apply the same work-conserving blocking-wait discipline to already-dispatched native collaboration agents without wrapping them as processes. Use when a long command or delegated worker would otherwise consume repeated status turns. Treat Goal as optional intent retention and App exec notifications as deferred delivery, not a polling clock or durable thread-wake mechanism.
---

# Long-Run Supervisor

Keep the goal or main agent responsible for intent and judgment. Delegate only process observation to `scripts/long-run-supervisor.ps1`; `Wait` and the optional `WaitMany` stay silent while their configured condition is unmet.

## Start a task

Resolve the script path and launch the command:

```powershell
$supervisor = Join-Path $env:USERPROFILE '.codex\skills\long-run-supervisor\scripts\long-run-supervisor.ps1'
$launch = & $supervisor -Action Start -CommandFile 'C:\absolute\private\command.ps1' -ExpectedMinutes 20 | ConvertFrom-Json
$launch
```

Use `-CommandFile` for commands containing sensitive values. `-Command '...'` is supported, but command text can enter the caller's shell history or tool transcript. Prefer environment variables, Windows credential facilities, or an existing private script over embedding credentials.

`-CommandFile` copies the source bytes exactly into the ACL-restricted private task file before launch. A script that hashes `$PSCommandPath` therefore sees the same bytes as the supplied source; the private copy is still removed at terminal cleanup.

`Start` creates a new ACL-restricted task directory. Its public metadata contains an ephemeral-key HMAC digest, never the command body. The private command copy is removed when execution ends. Treat stdout and stderr as private and potentially sensitive.

Timeout defaults are intentionally lenient for coding work: expected duration defaults to 15 minutes; deadline defaults to the greater of 60 minutes or four times the expectation; stall detection defaults to the greater of 15 minutes or the expectation, capped at 60 minutes. Override `-DeadlineMinutes`, `-StallMinutes`, or `-HeartbeatSeconds` when the command's behavior is known.

## Wait without agent polling

Run one blocking watcher in a host that can remain attached without caller-side
resumes:

```powershell
& $supervisor -Action Wait -TaskDirectory $launch.taskDirectory -CompletedExitCode 0
```

This is the canonical observation path: invoke `Wait` exactly once and let it block. Its internal `-PollSeconds` interval is implementation detail, not permission to create caller-side polling. Healthy unchanged checks produce no output, so do not add progress chatter, periodic tool turns, or a short `Poll`/`Wait` loop around it. When `Wait` prints a terminal receipt, consume that receipt and stop; do not call `Poll` or `Wait` again merely to confirm the same terminal state.

## Keep same-turn continuation inside one execution cell

When the user needs the agent to continue immediately after a bounded terminal
event and no callable App heartbeat or event-wake primitive exists, keep both
`Start` and the one `Wait` inside one outer tool call. Use
`scripts/run-supervised-blocking.ps1` so the model never regains control between
launch and receipt:

```javascript
// Set this beyond the accepted blocking window; the example is a short smoke.
// @exec: {"yield_time_ms": 60000}
let result = await tools.exec_command({
  cmd: "& (Join-Path $env:USERPROFILE '.codex\\skills\\long-run-supervisor\\scripts\\run-supervised-blocking.ps1') -CommandFile 'C:\\private\\command.ps1' -ExpectedMinutes 5 -DeadlineMinutes 10 -StallMinutes 5",
  workdir: "C:\\private",
  yield_time_ms: 30000,
  max_output_tokens: 10000
});
while (result.session_id !== undefined) {
  result = await tools.write_stdin({
    session_id: result.session_id,
    chars: "",
    yield_time_ms: 300000,
    max_output_tokens: 10000
  });
}
text(result);
```

The outer execution yield window should exceed the bounded wait window the user
accepts when the host permits it; otherwise use the exact-cell continuation
below. Keep every process-transport continuation alive through the supervisor
deadline. Announce the communication blackout before entering it. Best case,
the first tool result contains the terminal receipt.

`exec_command` may return a process `session_id` before the supervised command
finishes. The directly awaited, long-window `write_stdin` continuation above is
process-transport continuation inside the same outer execution cell, not a
supervisor `Poll`; keep it in that cell and do not return control to the model.

Some hosts yield a stable `Script running with cell ID ...` while the same
underlying execution and its single supervisor `Wait` remain alive. When the
runtime exposes a blocking continuation tool for that exact cell and immediate
same-turn continuation is required, keep the current turn open and resume only
that cell with the longest practical continuation window. Do not rerun
`run-supervised-blocking.ps1`, invoke another supervisor `Wait`, call supervisor
`Poll`, create a second cell, or add status chatter. A same-cell continuation is
transport resumption, not a supervisor-state poll, but it still consumes agent
scheduling and therefore is not true uninterrupted host blocking. Record the
transport yield honestly. If the turn emits `final`, the cell is not a wake
strategy.

The continuation call itself must be synchronously awaited by the active agent
turn. In a runtime that exposes `functions.wait`, call it directly with the
exact returned `cell_id`, a long `yield_time_ms` (use the longest host-supported
window; `120000` ms is the baseline for this runtime), and a sufficient output
budget. Do not use the default short continuation window for a long task:

```javascript
await functions.wait({
  cell_id: "<exact running cell id>",
  yield_time_ms: 120000,
  max_tokens: 10000
});
```

Never fire-and-forget this continuation, leave its promise unawaited, put it in
a background/parallel branch, call `yield_control()`, or switch to `notify` for
the same cell. Those shapes allow the agent turn to regain control before the
continuation window or terminal event and therefore destroy the intended
substantive blocking behavior. If the long continuation window expires while
the exact cell is still running, the next execution action is another awaited
long `functions.wait` for that same `cell_id`; do not interleave commentary,
diagnostics, or unrelated tools unless a newly steered user message requires an
immediate response.

This is synchronous continuation, not post-turn wake. It is appropriate only
when the caller deliberately accepts that steering/status messages may wait
until the blocking call returns. In one 2026-08-06 host smoke, a 12-second child
completed through Start and Wait in one 36.6-second outer call with no cell-ID
yield, model turn, Poll, or timer. A subsequent two-lane real gate kept both
supervised waits inside one 148.3-second outer call and returned both terminal
envelopes together. A later isolated full-core gate stayed in one outer call for
3,250.9 seconds and returned its actual terminal nonzero test receipt directly;
the model did not need a status turn or post-final wake to learn that 1,930 tests
passed and two failed. Treat these as environment evidence, not a universal
guarantee; calibrate a new host with one short bounded smoke before using a
longer blackout.

In one 2026-08-07 closeout, a single already-started supervisor `Wait` remained
inside one execution cell for 2,334.2 seconds across long same-cell continuation
windows, then returned its terminal `process_exit_zero` receipt. No supervisor
`Poll`, second `Wait`, reattach, replacement task, or post-final wake occurred.
This validates the bounded transport-continuation fallback in that runtime; it
does not prove zero scheduling overhead or durable event wake.

For more than one blocking lane, do not use a fail-fast host aggregate that can
discard a sibling receipt when one wrapper exits nonzero. Prefer one immutable
mother `WaitMany` generation, or use an all-settled/per-call-caught host aggregate
that returns every terminal envelope. In one 2026-08-07 gate, the passing sibling
had already completed before the failing sibling returned, but raw `Promise.all`
surfaced only the rejection; one later state inventory was required to recover
the hidden PASS. This is a receipt-aggregation defect, not evidence that the
sibling task failed or that caller polling is appropriate.

## Optional idle-only fan-in

Use a mother watcher only when the main agent has no useful independent work. Do not arm it while analysis, repairs, review preparation, or other progress can continue. Bind already-started tasks into one immutable generation:

Treat this as a work-conserving scheduling rule:

1. Start only the long tasks already justified by the active work.
2. Continue every independent main-agent action that can materially advance the objective without those results.
3. When that useful-work queue is empty, create one watch generation and attach exactly one blocking `WaitMany`.
4. On its terminal event, acknowledge the exact event, consume all newly unlocked diagnosis or synthesis work, and re-arm only if the useful-work queue becomes empty again.

Do not keep a mother watcher attached merely because tasks exist. If useful work is available, leave the tasks running without caller observation; a later idle-time generation will immediately report members that became terminal in the meantime. Prefer `AnyTerminal` when any member outcome unlocks useful work. Prefer `FailFastAll` when any failure needs immediate attention but successful results are useful only after the entire set completes.

```powershell
$watch = & $supervisor -Action CreateWatchSet `
  -TaskDirectory @($taskA.taskDirectory, $taskB.taskDirectory) `
  -FanInMode AnyTerminal | ConvertFrom-Json

& $supervisor -Action WaitMany `
  -WatchSetDirectory $watch.watchSetDirectory `
  -CompletedExitCode 0
```

Attach exactly one blocking `WaitMany` call and keep its result in the same awaited outer call. If that execution yields a stable cell ID, continue only that exact cell with the long-window rule above. `AnyTerminal` returns all receipts visible when any member reaches completion, failure, stall, deadline, or interruption. `FailFastAll` returns immediately for any non-completed attention receipt, stays silent while only some members have completed, and returns `all_completed` when every member completes.

After processing an event, acknowledge its exact stable ID:

```powershell
& $supervisor -Action AckWatchEvent `
  -WatchSetDirectory $watch.watchSetDirectory `
  -EventId $event.eventId
```

Add or remove members only by creating the next generation with `-PreviousWatchSetDirectory`; acknowledgement and cursor continuity are mandatory. If useful main-agent work resumes, do not re-arm until the agent is idle again. Events are exactly-once-ish: one stable event may be delivered more than once before acknowledgement, but acknowledged generations require re-arm and do not intentionally redeliver.

`PollMany` is a one-snapshot transport-recovery action. It emits nothing and exits `0` while the generation is healthy. Never wrap it in a caller-side loop. Goal is optional and never drives `PollMany`, `WaitMany`, local timer calls, or no-work turns.

Basic script-level fan-in can be verified locally. In one 2026-08-06 Codex App closeout, two separate mother calls stayed inside one blocking tool call for 3,326.9 and 3,168.2 seconds, produced no caller polls or empty turns, and returned only on terminal fan-in events. This is positive evidence for the work-conserving blocking shape in that environment. It is not proof that every host will preserve blocking, that a transport will never yield, or that terminal delivery can durably wake a task after its turn has ended.

## Native collaboration fan-in

Native subagents are not child processes owned by this PowerShell supervisor. When the collaboration runtime exposes a blocking mailbox/fan-in wait such as `wait_agent`, use that primitive directly; do not wrap a native agent, PID guess, or collaboration state in `long-run-supervisor.ps1`.

Apply the same work-conserving sequence:

1. Let dispatched agents run while the main agent completes all independent analysis, evidence preparation, or other useful work.
2. Only when their result is the next dependency, keep the current turn open and issue one long blocking native wait with a timeout beyond the expected remaining worker window when practical.
3. Treat a delivered message, final result, steered user input, or timeout according to the tool's actual return contract. A mailbox update is not necessarily an all-workers-terminal event; inspect the delivered update and current agent states once.
4. Consume all newly unlocked work. Re-arm a native wait only when required agents remain active and the useful-work queue is empty again.

Never build a short `wait_agent` loop, emit status-only turns, or finish the agent turn while claiming the native wait will later wake it. On 2026-08-06, one long native collaboration wait remained inside the active turn until a reciprocal-review terminal mailbox event, then returned control and the main agent continued synthesis immediately without Goal, App Server resume, or caller polling. This proves same-turn continuation in that runtime instance only; it does not establish post-`final` wake or universal transport behavior.

## Codex App deferred terminal delivery

`notify` is deferred delivery, not same-turn continuation and not a durable
event-to-task wake after `final`. It is not a fallback for a yielded execution
cell in this runtime. Once the host returns a stable cell ID, the active turn
must continue that exact cell through directly awaited long-window
`functions.wait` calls until the cell completes or new user steering requires
an immediate response. Do not switch that cell to `notify`, call
`yield_control()`, or put its continuation in a background branch.

Another host that does not expose a stable continuation ID may separately
demonstrate a deferred-delivery contract, but that is a different transport
mode and does not authorize claims of same-turn continuation or automatic
wake. Do not infer it from this supervisor or from historical App behavior.

There is no value in keeping the model active with short local waits while the
watcher is healthy. After starting the persistent watcher, stop model-side work
that exists only to occupy time. If the turn must end, report that the task is
still delegated to the supervisor and that automatic resumption is unavailable
without a separately documented durable thread-wake capability; do not
manufacture liveness with timer calls.

## Choose the continuation owner

The supervisor owns process observation only. It does not schedule model turns.
Choose one outer continuation owner explicitly:

- For native collaboration agents, use the runtime's one blocking same-turn wait
  while the turn is still active and only after useful local work is exhausted.
  This is a continuation owner for the current turn, not a durable wake after
  `final`.
- Use Goal mode for a durable multi-hour or multi-day objective when the user
  explicitly requests a goal. Goal state preserves the outcome and completion
  criteria, but it does not convert `notify` into an event wake. Keep it active
  only while each continuation can perform useful objective work independent
  of the supervised process.
- Use a same-chat heartbeat automation only when the user asks to monitor,
  check back, wake later, or keep working later and the App exposes that
  capability. Match its cadence to the command's expected duration or stall
  boundary; never imitate a sub-minute watcher loop. Stop or disable the
  heartbeat as soon as the terminal receipt is consumed.
- With neither Goal mode nor a heartbeat, automatic model resumption is not
  available. End the turn honestly and wait for a user message or another
  authorized continuation source.

Goal mode and heartbeat scheduling do not expand sandbox, approval, live,
publication, or destructive-action authority.

If the only remaining action is to wait for a supervisor receipt, Goal is not a
valid waiting mechanism. An active Goal may schedule another model turn even
without a terminal event; a no-op final, status-only message, local delay, or
supervisor snapshot in that turn is still churn. Pause or stop the Goal through
the user-controlled App surface at that boundary. Do not falsely mark an
unfinished goal complete or blocked merely to suppress continuation. Without a
supported Goal pause or an App-owned event wake, automatic resume and zero idle
model turns cannot both be guaranteed.

## Do not bridge into an App-owned task out of process

Do not wire the supervisor worker directly to a standalone `codex app-server`
or `codex exec resume` process for an existing Codex App task. A standalone
app-server can read stored thread metadata and can drive its own ephemeral
thread, but its runtime `thread.status` is process-local. In a Windows App
probe, the standalone server reported the same task as `notLoaded` while the
App host reported it as `active`. It therefore cannot prove that the App-owned
task is idle before `thread/resume` or `turn/start`.

This boundary also has no shared transaction or documented idempotency key
across the terminal receipt and `turn/start`. A local claim file can limit the
bridge to one attempt, but it cannot prove exactly-once continuation across the
crash window after the server accepts a turn and before the claim is committed.
Treat that window as ambiguous and fail closed; do not disguise at-most-once
delivery as exactly-once execution.

A safe event-driven bridge requires an App-supported external wake primitive
that targets the owning host, observes or queues behind the real active turn,
and deduplicates a caller-supplied event identity. Until that primitive exists,
use Goal only for useful objective work and consume a deferred terminal receipt
when it arrives; never spend Goal turns checking supervisor state. A
user-authorized same-chat heartbeat remains a scheduled fallback, not an event
bridge. It is not an event bridge.

## Transport-yield fallback

Prefer a watcher host that can persist the one blocking `Wait` without making
the model resume its transport. A silent transport yield is not a healthy
supervisor result: it is a transport boundary.

When the runtime returns a stable execution-cell ID, use only the bounded
same-cell path described above, with long continuation windows. This is
mandatory for the active turn: do not call another supervisor `Wait`, run
`Poll`, create a replacement cell, emit status chatter, or select deferred
delivery between windows. If the runtime exposes no stable continuation ID at
all, retain the private `taskDirectory`, `taskId`, and
`blindedCommandDigest` for a real later continuation and report the transport
gap honestly. Neither path can wake Codex after `final`, and same-cell transport
continuation still consumes agent scheduling even though it is not supervisor
polling.

On a later user message or separately authorized continuation, if no execution
cell remains available and the result is needed, run exactly one snapshot:

```powershell
& $supervisor -Action Poll -TaskDirectory $launch.taskDirectory -CompletedExitCode 0
```

If it emits a receipt, consume it. If it exits `0` with no output, the task is
still healthy: leave it running and do not reattach a watcher or schedule a
model turn merely to check again. Use `Interrupt` only for an actual user
request to stop the task.

`-CompletedExitCode 0` lets ordinary shells and CLI/tool wrappers consume normal completion without rendering it as a generic command failure. The JSON receipt remains machine-readable and its `condition` remains `completed`. Non-success wakes keep distinct nonzero exit codes:

- `0`: completed, when `-CompletedExitCode 0` is selected
- `11`: failed or invalid state
- `12`: stalled, stale heartbeat, or lost worker identity
- `13`: deadline reached
- `14`: user interruption

For backward compatibility, omitting `-CompletedExitCode 0` preserves the original wake exit codes:

- `10`: completed
- `11`: failed or invalid state
- `12`: stalled, stale heartbeat, or lost worker identity
- `13`: deadline reached
- `14`: user interruption

The `waitCommand` returned by new `Start` calls includes `-CompletedExitCode 0`. Existing callers that branch on exit code `10` can keep omitting the option; migrate them only when they are ready to treat a successful wrapper invocation plus `condition: completed` as completion. The option remaps only the completed condition and never collapses failure, stall, deadline, or interruption.

Do not use `Poll` as a fallback for an agent-side loop. If the runtime truly cannot hold one blocking `Wait`, a non-agent external scheduler may run one `Poll` per scheduled invocation and hand the receipt to an independently configured notification path:

```powershell
& $supervisor -Action Poll -TaskDirectory $launch.taskDirectory
```

`Poll` exits `0` with no output while healthy. Use `-AsJson` only for an explicit diagnostic snapshot.

If the watcher transport ends before any terminal receipt is delivered, inspect the transport failure first. Use the transport-yield fallback above; do not repeatedly reattach `Wait`.

## Interrupt safely

Request cooperative interruption through the recorded worker:

```powershell
& $supervisor -Action Interrupt -TaskDirectory $launch.taskDirectory
```

The worker validates PID plus process start time before stopping the owned child tree. Never kill a PID from state without the matching start time; PIDs can be reused. If ownership cannot be proven, preserve the process and wake for inspection.

## Consume the receipt

Read `state.json` for the latest heartbeat and `exit.json` for the terminal receipt. `events.jsonl` contains transition-only WAL entries; it does not grow on ordinary heartbeats. Bind conclusions to `taskId` and `blindedCommandDigest`. Inspect command output only when needed and redact it before placing any portion in a public document or model-visible report.

Supervisor JSON publication uses a flushed same-directory temporary file and an old-or-new atomic replacement. Internal readers share deletion and both readers and writers retry bounded transient Windows sharing collisions; they never consume truncate-in-place state. An exhausted collision or an invalid JSON/schema still fails closed and remains distinguishable from healthy execution.

Keep each task directory on a local Windows filesystem with ACL support. Do not place it at a drive root, repository root, shared/public directory, symlink, junction, or reparse point. The launcher rejects unsafe task roots and fails closed if it cannot restrict the new task directory to the current user and SYSTEM.
