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
- Preserve long-task shape: keep goals, blockers, decisions, dependencies, and verification hashes local across resume and compaction boundaries.
- Supervise long runs cheaply: move heartbeat, stall detection, and terminal wakeups outside expensive reasoning turns.
- Delegate with brakes: require a real independence and ownership case before spawning workers.
- Reproduce the useful parts: ship safe configuration examples and installable skills without copying runtime state.
- Sync without leaks: export only explicit allow-listed files and fail closed on secrets, private paths, unknown files, or hash drift.

## Included components

The bundle includes the `context-canvas-codex` plugin plus seven original skills and tools. Context Canvas provides a local evidence-pointer task map, a read-only `SessionStart` restore hook, dependency-aware nodes, bounded search and closeout, and a persistent stdio MCP surface shared by Codex App and CLI. The other components cover batch-complete review, long-run supervision, a bounded Luna CLI worker, completeness synthesis, incident-to-regression packaging, an explicit Claude review adapter, and A2A Superhub operation.

Components that already have a canonical public home—such as [baton-fanout-skill](https://github.com/phenomenoner/baton-fanout-skill), [Understand Anything](https://github.com/Egonex-AI/Understand-Anything), and [OpenAI skills](https://github.com/openai/skills)—stay as versioned pointers instead of copied forks. See the [component catalog](catalog/components.json) for the complete inventory.

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
new ID does not, install the same read-only hook through Codex's user
configuration layer from the repository root:

```powershell
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py install
python -I plugins/context-canvas-codex/scripts/install_context_canvas_hook.py check
```

Then use `/hooks` in Codex CLI to review and trust that `SessionStart`
definition, and repeat the ID plus `canvas_*` proof in another fresh task. In a
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

## Context Canvas tradeoff

The Hermes autopilot captures selected tool results inside the agent process. The Codex adapter intentionally does not copy that behavior: `PostToolUse` exposes tool inputs and responses, and a command hook would add a process launch to every matched call. Checkpoints remain explicit and pointer-only; repeated operations use the persistent stdio MCP server. One 13-node Windows/Python 3.13.5 development snapshot measured MCP reads at 6.719 ms p50 / 8.569 ms p95 and fresh CLI reads at 626.397 ms p50. This is a reproducible machine snapshot, not a universal latency guarantee.

With `approval_policy = "never"`, non-interactive Codex cancels MCP calls that
still require approval; it does not auto-approve them. Acceptance therefore
needs an explicit, reviewed plugin-scoped MCP approval policy plus completed
tool receipts and canonical JSON readback. See the
[technical note](docs/context-canvas-codex.md).

The repository now contains directly installable skills and tools plus one marketplace-ready community plugin. It is not an official OpenAI plugin; the repository marketplace makes source, version, and installation paths inspectable and reproducible.

## License

Original material in this repository is available under the [MIT License](LICENSE). Pointer-only dependencies remain under their upstream licenses. See [NOTICE.md](NOTICE.md).
