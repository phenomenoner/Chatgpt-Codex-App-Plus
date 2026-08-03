---
name: codex-cli-luna-worker
description: Generate a bounded implementation patch through PowerShell and Codex CLI with gpt-5.6-luna at max reasoning when the native collaboration tool does not expose Luna. Use only after baton-fanout-skill selects delegation for stable code-generation work with exact target paths; the Luna worker stays read-only and the main agent reviews, applies, and verifies the patch. Do not use for architecture, security or authority decisions, independent review, release or cutover judgment, live operations, or overlapping work.
---

# Codex CLI Luna Worker

Use Codex CLI as a compatibility bridge, not as a way around dispatch governance. Treat the CLI process as a delegated worker even though it is not created by `spawn_agent`. Keep its workspace read-only: Luna generates code as a structured `apply_patch` proposal, and the main agent owns the actual write.

## Preconditions

1. Read and apply the active `baton-fanout-skill`.
2. Establish the outcome, direct-work alternative, independence, exclusive ownership, and main-agent closure owner.
3. Confirm the contract is stable and the work is bounded code generation. Keep architecture, authorization, security, release, review, and live-operation decisions with the main agent.
4. Capture the repository status and hashes of the target surface. Preserve existing dirty work.
5. Put no credentials, connection profiles, private receipts, or secrets in the worker prompt.

Do not invoke this skill when the worker would need `.agent-harness`, live configuration, external publication, destructive Git operations, or files concurrently owned by another agent.

## Prepare the brief

Create a task-local prompt file that states:

- repository root and exact objective;
- observable acceptance conditions;
- exact files or directories the proposal may target;
- all forbidden writes, especially shared schemas, lockfiles, generated artifacts, live homes, and unrelated dirty files;
- source material it must read;
- focused checks it may run;
- required final result format;
- stop conditions when the contract is incomplete or an outside-path change is needed.

Prefer one coherent proposal for coupled files. Do not run multiple CLI workers against the same contract concurrently.

## Invoke the worker

Run the bundled script from PowerShell:

```powershell
& "$env:USERPROFILE\.codex\skills\codex-cli-luna-worker\scripts\invoke_luna_worker.ps1" `
  -Workspace 'D:\path\to\worktree' `
  -PromptFile 'D:\path\to\brief.md' `
  -OutputDirectory 'D:\path\to\.debug\luna-worker-run' `
  -TargetPath 'crates\example\src\lib.rs','crates\example\tests\contract.rs' `
  -ExpectedMaxMinutes 15
```

The script uses:

- `gpt-5.6-luna`;
- `model_reasoning_effort="max"`;
- `codex exec --ephemeral --ignore-user-config`;
- approval policy `never` and a read-only sandbox;
- project `AGENTS.md` plus a generated bounded-worker preamble;
- before/after hashes of tracked and non-ignored untracked files.

It never uses `--dangerously-bypass-approvals-and-sandbox`.

Override `-ReasoningEffort` only when the active routing policy calls for a cheaper lane. Do not change the wrapper to `danger-full-access` merely because Windows rejects direct workspace writes.

## Verify and integrate

The script writes `events.jsonl`, `stderr.log`, `last-message.json`, `proposal.patch`, and `run-manifest.json`. It validates both the structured `targetPaths` and the actual add/update/delete/move patch headers. A non-zero exit, any workspace mutation, or any proposed path outside `TargetPath` is a failed worker result.

It also renders Luna's streamed progress messages and tool events into `task-wal.md`. Read that WAL while a long worker is still running; the worker does not receive filesystem authority to write it directly. The wrapper asks Luna to emit a complete structured checkpoint before the final completion reserve. When one arrives, the host writes `checkpoint-last-message.json` and `checkpoint-proposal.patch` outside the read-only workspace. A checkpoint is recoverable partial output, not an accepted result.

Choose the outer execution timeout from task shape rather than using a fixed five minutes:

- 5 minutes for a one-file mechanical proposal;
- 15 minutes for a bounded cross-file implementation;
- up to 30 minutes for a large but stable proposal only while `task-wal.md` continues to advance.

Treat `ExpectedMaxMinutes` as the total worker budget. The wrapper reserves 20 percent, bounded to one through five minutes, for serialization and handoff; Luna must emit its best complete parseable checkpoint before that reserve begins. Set the caller's hard timeout slightly above the total budget only for process and log flush, not for more design work.

Judge progress from the newest meaningful WAL entry, not total elapsed time alone. Intervene when the WAL has no meaningful progress for about five minutes, repeats the same failed read or hypothesis, crosses scope, or exhausts the declared total budget. Do not interrupt merely because a complex proposal exceeds five minutes. A late message that only says formatting or consistency work continues is not a substitute for the required parseable checkpoint.

After the process exits, the main agent must:

1. inspect `task-wal.md` for normal progress, repeated failure, and scope adherence;
2. prove that the Luna process did not change the workspace;
3. inspect the complete `apply_patch` proposal against the declared target paths and current source;
4. apply an accepted proposal with the main agent's normal file-edit mechanism;
5. run focused tests independently, then the shared gates at the correct freeze boundary;
6. resolve contradictions and retain final judgment;
7. report partial, failed, unauthenticated, or skipped results as coverage gaps.

Do not treat the worker's final message as completion evidence. Do not let it commit, push, publish, cut over, or mutate live state.

If the caller's hard timeout fires, mark the run timed out even when the WAL was advancing. Preserve the WAL, events, stderr, and any host-captured checkpoint as partial evidence. Never reconstruct or apply an in-memory draft mentioned only in prose. A complete checkpoint may be reviewed manually, but it still needs the normal target-path, current-source, workspace-mutation, and test gates because the interrupted wrapper may not have produced a final manifest.

## Failure and escalation

Repair an incomplete brief before increasing capability. When a worker times out without a complete checkpoint, split the task into a narrower contract instead of replaying the unchanged brief with a longer timeout. After one same-cause retry, stop and change the work boundary, use direct execution, or move the task to an exposed Terra/Sol lane. Never launch an unchanged third attempt.
