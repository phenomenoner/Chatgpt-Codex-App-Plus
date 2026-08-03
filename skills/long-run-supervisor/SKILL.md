---
name: long-run-supervisor
description: Launch and supervise long-running PowerShell commands with a local heartbeat, private task state, deterministic polling, and wake-only output. Use when a build, test, migration, analysis, or coding command is expected to run for more than five minutes and repeated high-context agent turns would otherwise be spent checking whether it is still running; also use when a goal should retain intent while process observation stays outside the LLM reasoning plane.
---

# Long-Run Supervisor

Keep the goal or main agent responsible for intent and judgment. Delegate only process observation to `scripts/long-run-supervisor.ps1`; its `Wait` action stays silent while work is healthy and returns only for completion, failure, stall, deadline, or user interruption.

## Start a task

Resolve the script path and launch the command:

```powershell
$supervisor = Join-Path $env:USERPROFILE '.codex\skills\long-run-supervisor\scripts\long-run-supervisor.ps1'
$launch = & $supervisor -Action Start -CommandFile 'C:\absolute\private\command.ps1' -ExpectedMinutes 20 | ConvertFrom-Json
$launch
```

Use `-CommandFile` for commands containing sensitive values. `-Command '...'` is supported, but command text can enter the caller's shell history or tool transcript. Prefer environment variables, Windows credential facilities, or an existing private script over embedding credentials.

`Start` creates a new ACL-restricted task directory. Its public metadata contains an ephemeral-key HMAC digest, never the command body. The private command copy is removed when execution ends. Treat stdout and stderr as private and potentially sensitive.

Timeout defaults are intentionally lenient for coding work: expected duration defaults to 15 minutes; deadline defaults to the greater of 60 minutes or four times the expectation; stall detection defaults to the greater of 15 minutes or the expectation, capped at 60 minutes. Override `-DeadlineMinutes`, `-StallMinutes`, or `-HeartbeatSeconds` when the command's behavior is known.

## Wait without agent polling

Run one blocking watcher in a low-context session, scheduler, or yielded tool call:

```powershell
& $supervisor -Action Wait -TaskDirectory $launch.taskDirectory -CompletedExitCode 0
```

This is the canonical observation path: invoke `Wait` exactly once and let it block. Its internal `-PollSeconds` interval is implementation detail, not permission to create caller-side polling. Healthy unchanged checks produce no output, so do not add progress chatter, periodic tool turns, or a short `Poll`/`Wait` loop around it. When `Wait` prints a terminal receipt, consume that receipt and stop; do not call `Poll` or `Wait` again merely to confirm the same terminal state.

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

Do not use `Poll` as a fallback for an agent-side loop. If the runtime truly cannot hold one blocking `Wait`, a non-agent external scheduler may run one `Poll` per scheduled invocation and wake the agent only when it emits a receipt:

```powershell
& $supervisor -Action Poll -TaskDirectory $launch.taskDirectory
```

`Poll` exits `0` with no output while healthy. Use `-AsJson` only for an explicit diagnostic snapshot.

If the watcher transport ends before any terminal receipt is delivered, inspect the transport failure first. A single reattachment with `Wait` is acceptable after establishing that no watcher remains, but repeated short reattachments are polling and are forbidden.

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
