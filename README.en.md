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

- Keep engineering workflows canonical: review, supervision, verification, and incident skills live in one dedicated toolkit instead of a second vendored copy.
- Navigate session work and offload context: keep hook transport identity, an optional task map, explicit retrievable references, and one-shot historical snapshots separate.
- Delegate with brakes: require a real independence and ownership case, then use native per-spawn model and effort routing for eligible workers.
- Reproduce the useful parts: ship safe configuration examples and installable skills without copying runtime state.
- Sync without leaks: export only explicit allow-listed files and fail closed on secrets, private paths, unknown files, or hash drift.

## Included components

The bundle includes the `context-canvas-codex` plugin and the optional `operate-a2a-superhub` skill. Context Canvas provides optional session navigation for goals, decisions, progress, dependencies, blockers, and next steps; explicit text references with digest-bound search ranges, chunk reads, and deterministic previews; and default-off, one-shot historical tool snapshots. Hook-derived IDs are transport provenance for Canvas actions, not task authority. Missing Canvas state never blocks the underlying work.

Components that already have a canonical public home stay as versioned pointers instead of copied forks. General planning, specification, review, testing, delegation, recovery, and release workflows now live in the [Smart Agentic Engineering Toolkit](https://github.com/phenomenoner/smart-agentic-engineering-toolkit). The unified [Baton Fanout repository](https://github.com/phenomenoner/baton-fanout-skill) keeps its portable dispatch brake and applies GPT-specific model/effort routing only through its Codex adapter, while [Understand Anything](https://github.com/Egonex-AI/Understand-Anything) and [OpenAI skills](https://github.com/openai/skills) remain upstream pointers. See the [component catalog](catalog/components.json) for the complete inventory.

The [Context Canvas technical note](docs/context-canvas-codex.md) records the Hermes comparison, Codex-specific boundaries, schema, and reproducible latency probe.

## Quick start

```powershell
git clone https://github.com/phenomenoner/Chatgpt-Codex-App-Plus.git
Set-Location Chatgpt-Codex-App-Plus
python scripts/public_sync.py validate
```

Install the canonical Smart Agentic Engineering Toolkit:

```powershell
codex plugin marketplace add phenomenoner/smart-agentic-engineering-toolkit --ref v0.1.0
codex plugin add smart-agentic-engineering-toolkit@smart-agentic-engineering-toolkit
codex plugin list
```

Install the Context Canvas plugin from this repository marketplace:

```powershell
codex plugin marketplace add phenomenoner/Chatgpt-Codex-App-Plus --ref context-canvas-codex-v0.6.0
codex plugin add context-canvas-codex@codex-app-plus
codex plugin list
```

If the plugin, skill, and MCP server appear but the current prompt receives no
opaque Context Canvas ID, install the same `SessionStart`,
`UserPromptSubmit`, and `PostToolUse` hooks through Codex's user
configuration layer from the repository root:

```powershell
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py install
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py check
```

Then use `/hooks` in Codex CLI to review and trust all three definitions. The
next prompt can prove `UserPromptSubmit` recovery without rotating the task;
use one fresh task only to prove `SessionStart`, then arm one exact harmless tool
call with `snapshot_capture_next` so a new `_snapshots/events` manifest proves capture. A missing Canvas ID
means the optional map is unavailable; it does not make the underlying task
blocked. In a
local Codex CLI 0.146.0 acceptance run, plugin MCP and skill discovery worked
while the plugin-bundled hook did not execute. The explicit installer is the
compatibility layer; it preserves peer hooks and a hash-addressed backup.
Installation, catalog discovery, or a tool event marked only `started` is not
runtime proof.

This repository no longer copies the general-engineering skills. To install the
optional vendored `operate-a2a-superhub` skill, preview the exact operation:

```powershell
pwsh -File scripts/install.ps1 -Skill operate-a2a-superhub -WhatIf
```

Then install it:

```powershell
pwsh -File scripts/install.ps1 -Skill operate-a2a-superhub
```

Codex discovers user and repository skills from `.agents/skills` locations, while plugins can bundle skills, MCP servers, and lifecycle hooks. Native subagents support `[agents]` model/effort defaults and explicit per-spawn overrides; explicit spawn values take precedence. This repository leaves those defaults commented because Baton routes by task class instead of applying Luna/max to architecture, security, or independent review. See OpenAI's official [Build skills](https://learn.chatgpt.com/docs/build-skills), [Package plugins](https://developers.openai.com/plugins/build/plugins), [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), and [Config reference](https://learn.chatgpt.com/docs/config-file/config-reference) guides before installing durable global behavior.

## Public-safety contract

The exporter never mirrors a Codex home directory. It copies only manifest-approved text files, normalizes them deterministically, scans for private state and credentials, and binds the result to a SHA-256 lock. New sources require an explicit allow-list change and human review. Scheduled synchronization may refresh approved components, but it may not expand scope on its own.

Read [the architecture](docs/architecture.md) and [weekly sync contract](docs/weekly-sync.md) for details.

## Context Canvas layers

Context Canvas 0.6 does not equate “preserve useful context” with “create a semantic node.” `reference_put`, `reference_search`, `reference_preview`, `reference_read`, and `reference_delete` provide explicit redacted text offload with bounded native retrieval. Content-search hits carry the source digest, exact UTF-8 byte range, and a directly usable read hint. `reference_preview` explicitly applies either `log-v1` or strict line-oriented `search-results-v1` and returns ephemeral exact source slices under a caller-supplied budget. It never runs automatically, rewrites the stored body, creates a derived cache, or substitutes a lossy summary for the original. `PostToolUse` persistence is off by default: `snapshot_capture_next` arms one expiring request, exact tool mismatches do not consume it, Canvas self-tools are ignored, and a match consumes it once. The captured model-facing payload still uses the declared sanitization, content-addressing, dedupe, TTL, pin, and integrity-checked GC policies. Snapshot bodies stay outside task-map search and lifecycle injection; an explicit MCP/CLI read returns bounded chunks, while complete file export remains CLI-only.

Current Codex invokes `PostToolUse` when a supported handler returns an opted-in post-tool payload. That is a host transport surface, not a Canvas persistence decision. A Bash command with a non-zero exit can still produce the callback; dispatch or handler failures that produce no callback payload remain absent. After installation, prove actual capture in a fresh task by arming one harmless exact call and inspecting its new manifest; plugin discovery or configuration state alone is insufficient.

The repository includes a machine-readable benchmark covering persistent MCP reads, fresh CLI startup, snapshot-store writes, warm dedupe, manifest reads, exact GC preview, and cold small/large hooks. Direct store-write measurements do not imply default-on capture. Python startup, ACL checks, storage, antivirus, concurrent load, and payload shape materially affect results.

With `approval_policy = "never"`, non-interactive Codex cancels MCP calls that
still require approval; it does not auto-approve them. Acceptance therefore
needs an explicit, reviewed plugin-scoped MCP approval policy plus completed
tool receipts and canonical JSON readback. See the
[technical note](docs/context-canvas-codex.md).

The repository now contains one marketplace-ready Context Canvas community plugin, an optional A2A skill, and versioned pointers to the canonical engineering toolkit. It is not an official OpenAI plugin; the repository marketplace makes source, version, and installation paths inspectable and reproducible.

## License

Original material in this repository is available under the [MIT License](LICENSE). Pointer-only dependencies remain under their upstream licenses. See [NOTICE.md](NOTICE.md).
