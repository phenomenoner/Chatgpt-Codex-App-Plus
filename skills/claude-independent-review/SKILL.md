---
name: claude-independent-review
description: Run a local Claude Code CLI as an independent, read-only, hash-bound engineering review gate. Use when the user explicitly asks Codex to invoke Claude or `claude -p` for a final code, release, migration, or pre-cutover review, especially when a PASS/BLOCKED decision must be bound to a frozen candidate and verification evidence.
---

# Claude Independent Review

Use the locally installed Claude Code CLI as an external reviewer, never as the implementation owner or live operator.

## Preconditions

1. Require explicit user authorization to send scoped artifacts to Claude.
2. Finish implementation and required local verification first.
3. Freeze the candidate, public/source diff, manifest, and evidence hashes before review.
4. Exclude secrets, `.env` contents, bearer tokens, credentials, raw private receipts, personal identifiers, unrelated files, and live runtime data.
5. Do not let Claude modify files, run live commands, approve its own findings, or perform cutover.

## Resolve the model

Inspect the installed CLI:

```powershell
Get-Command claude
claude --version
claude --help
```

For Opus 5, probe the exact full model name without tools or persistence:

```powershell
claude -p --model claude-opus-5 --effort high --tools "" --no-session-persistence --output-format json "Reply with exactly MODEL_OK."
```

Accept `claude-opus-5` only when the JSON result succeeds and `modelUsage` reports canonical model `claude-opus-5`. Do not silently substitute an alias, fallback model, or another provider. Re-probe when the CLI or model availability may have changed.

Use effort `high` by default. Honor `xhigh` or `max` when explicitly requested and available; never reduce an explicitly requested minimum.

## Prepare the review input

Create a small, review-only bundle under the repository's approved scratch/evidence directory. Include:

- candidate identity and SHA-256 hashes;
- exact diff or changed-file inventory;
- affected contracts and invariants;
- executed tests, counts, tiers, and raw result paths;
- known limitations and rollback/cutover gates;
- the requested decision schema.

Write neutral review instructions. Do not disclose the implementer's desired verdict or prior reviewer conclusions unless comparison is the explicit task. Give Claude only the files required to reconstruct the result.

## Run the reviewer

Run from the trusted repository or isolated review directory. Prefer safe mode, no session persistence, read-only tools, and structured output:

```powershell
claude -p `
  --model claude-opus-5 `
  --effort high `
  --safe-mode `
  --no-session-persistence `
  --permission-mode plan `
  --tools "Read,Glob,Grep" `
  --output-format json `
  --json-schema '<task-specific JSON schema>' `
  '<neutral review prompt with exact artifact paths and hashes>'
```

If the reviewer needs a diff, generate it before invocation rather than granting a general shell. Add only explicitly needed read-only tools. Never use `--dangerously-skip-permissions` for a release gate.

Require structured output containing at least:

- `decision`: `PASS` or `BLOCKED`;
- candidate and manifest hashes reviewed;
- blocker findings with file/line evidence;
- verification gaps;
- a concise rationale.

Store the complete Claude result in the approved private evidence area. Do not publish private review inputs or outputs.

## Enforce the gate

Treat the result as `BLOCKED` when any of these occurs:

- timeout, authentication failure, overload, fallback, or non-zero exit;
- invalid or incomplete structured output;
- hashes do not exactly match the frozen candidate;
- any blocker or unverified required invariant remains;
- Claude modified artifacts or relied on live mutation;
- the candidate changed after review.

Proceed only on a fresh, explicit `PASS` bound to the exact frozen hashes. Independently inspect the primary artifacts and rerun the repository's shared verification; Claude's verdict is evidence, not authority.
