<p align="center">
  <strong>ChatGPT Codex App Plus</strong><br>
  Turn a battle-tested Codex setup into a public-safe, installable, and continuously synchronized toolkit.
</p>

<p align="center">
  <a href="README.md">繁體中文</a> · <a href="README.en.md">English</a> ·
  <a href="ABOUT.md">About</a> · <a href="SECURITY.md">Security</a>
</p>

> Community-maintained and independent. This is not an official release from OpenAI, Anthropic, or any referenced upstream project.

## The 30-second story

The best Codex workflows rarely live in one file. They emerge across durable instructions, focused skills, PowerShell helpers, and safety contracts. Codex App Plus packages the reusable parts into one curated outer layer:

- Review to closure: do not stop at the first blocker; keep going until required coverage reaches a fixed point.
- Preserve long-task shape and evidence: keep a semantic task map separate from historical tool snapshots governed by an explicit sanitization policy across resume, compaction, and later investigation.
- Supervise long runs cheaply: move heartbeat, stall detection, and terminal wakeups outside expensive reasoning turns.
- Delegate with brakes: require a real independence and ownership case before spawning workers.
- Reproduce the useful parts: ship safe configuration examples and installable skills without copying runtime state.
- Sync without leaks: export only explicit allow-listed files and fail closed on secrets, private paths, unknown files, or hash drift.

## Included components

The bundle includes the `context-canvas-codex` plugin plus seven original skills and tools. Context Canvas provides a local semantic task map plus content-addressed, deduplicated, TTL/pin-managed historical tool snapshots captured after sanitization. It also provides resume/compact recovery, dependency-aware nodes, bounded search and closeout, and a persistent stdio MCP surface shared by Codex App and CLI. The other components cover batch-complete review, long-run supervision, a bounded Luna CLI worker, completeness synthesis, incident-to-regression packaging, an explicit Claude review adapter, and A2A Superhub operation.

Components that already have a canonical public home stay as versioned pointers instead of copied forks. Codex users are pointed directly to the [Codex-specialized Baton branch](https://github.com/phenomenoner/baton-fanout-skill/tree/codex/add-model-effort-routing), while [Understand Anything](https://github.com/Egonex-AI/Understand-Anything) and [OpenAI skills](https://github.com/openai/skills) remain upstream pointers. See the [component catalog](catalog/components.json) for the complete inventory.

The [Context Canvas technical note](docs/context-canvas-codex.md) records the Hermes comparison, Codex-specific boundaries, schema, and reproducible latency probe.

## Quick start

```powershell
git clone https://github.com/phenomenoner/Chatgpt-Codex-App-Plus.git
Set-Location Chatgpt-Codex-App-Plus
python scripts/public_sync.py validate
pwsh -File scripts/install.ps1 -WhatIf
```

Install the Context Canvas plugin from this repository marketplace:

```powershell
codex plugin marketplace add phenomenoner/Chatgpt-Codex-App-Plus --ref main
codex plugin add context-canvas-codex@codex-app-plus
codex plugin list
```

First open a new task and confirm that the model actually received that task's
opaque Context Canvas ID. If the plugin, skill, and MCP server appear but the
new ID does not, install the same `SessionStart` plus `PostToolUse` hook pair through Codex's user
configuration layer from the repository root:

```powershell
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py install
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py check
```

Then use `/hooks` in Codex CLI to review and trust both definitions. In another fresh task, repeat the opaque-ID proof and make one harmless tool call; a new `_snapshots/events` manifest is the capture proof. In a
local Codex CLI 0.146.0 acceptance run, plugin MCP and skill discovery worked
while the plugin-bundled hook did not execute. The explicit installer is the
compatibility layer; it preserves peer hooks and a hash-addressed backup.
Installation, catalog discovery, or a tool event marked only `started` is not
runtime proof.

Install the recommended set after reviewing the preview:

```powershell
pwsh -File scripts/install.ps1
```

Or select individual skills:

```powershell
pwsh -File scripts/install.ps1 -Skill long-run-supervisor,batch-complete-independent-review
```

Codex discovers user and repository skills from `.agents/skills` locations, while plugins can bundle skills, MCP servers, and lifecycle hooks. See OpenAI's official [Build skills](https://learn.chatgpt.com/docs/build-skills), [Package plugins](https://developers.openai.com/plugins/build/plugins), [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), and [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) guides before installing durable global behavior.

## Public-safety contract

The exporter never mirrors a Codex home directory. It copies only manifest-approved text files, normalizes them deterministically, scans for private state and credentials, and binds the result to a SHA-256 lock. New sources require an explicit allow-list change and human review. Scheduled synchronization may refresh approved components, but it may not expand scope on its own.

Read [the architecture](docs/architecture.md) and [weekly sync contract](docs/weekly-sync.md) for details.

## Context Canvas layers

The current design does not equate “preserve a complete tool result” with “create a semantic node.” For opted-in `PostToolUse` callback payloads that Codex actually emits, it archives the complete model-facing payload supplied to the hook under the declared sanitization policy. One suffix-aware classifier covers structured keys, textual assignments, percent/form query keys, bracket/index notation, JSON Unicode escapes, and escaped wrappers. Any malformed-percent assignment key is redacted conservatively, and earlier matches do not suppress the remaining encoded or escaped representation passes; adjacent safe query parameters remain usable. Supported base64 and percent-encoded textual data URLs, including unquoted MIME parameters, are canonicalized, decoded, and redacted; a `data:` value that cannot be parsed safely rejects the whole observation. Image, audio, video, and arbitrary binary media is preserved byte-for-byte and explicitly labelled `opaque-uninspected`, not represented as inspected or sealed raw evidence. Oversized inputs are skipped whole rather than truncated; SHA-256-addressed deterministic gzip objects deduplicate repeated content; ordinary snapshots have a 14-day TTL. GC recomputes and validates the canonical journal plan, then derives interruption recovery from current verified state. Semantic promotion verifies transitive blobs before pinning. Snapshot bodies stay outside Canvas search, resume injection, closeout, and MCP responses. Full retrieval is an explicit CLI export.

Current Codex invokes `PostToolUse` when a supported handler returns an opted-in post-tool payload. A Bash command with a non-zero exit can still produce that callback and archived exit metadata. Dispatch or handler failures that produce no callback payload remain absent, and this adapter has no separate failure sibling. After installation, prove actual capture in a fresh task with a harmless call and a new manifest; plugin discovery or configuration state alone is insufficient.

The repository includes a machine-readable benchmark covering persistent MCP reads, fresh CLI startup, first snapshot write, warm dedupe, manifest reads, exact GC preview, and cold small/large `PostToolUse` hooks. GC validates the event/object/blob graph and discovers orphans, so it is not comparable to an earlier count-only preview. Python startup, ACL checks, storage, antivirus, concurrent load, and payload shape materially affect results; publish or compare numbers only with the executable hashes and environment from the same receipt.

With `approval_policy = "never"`, non-interactive Codex cancels MCP calls that
still require approval; it does not auto-approve them. Acceptance therefore
needs an explicit, reviewed plugin-scoped MCP approval policy plus completed
tool receipts and canonical JSON readback. See the
[technical note](docs/context-canvas-codex.md).

The repository now contains directly installable skills and tools plus one marketplace-ready community plugin. It is not an official OpenAI plugin; the repository marketplace makes source, version, and installation paths inspectable and reproducible.

## License

Original material in this repository is available under the [MIT License](LICENSE). Pointer-only dependencies remain under their upstream licenses. See [NOTICE.md](NOTICE.md).
