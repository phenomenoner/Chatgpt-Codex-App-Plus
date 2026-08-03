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
- Supervise long runs cheaply: move heartbeat, stall detection, and terminal wakeups outside expensive reasoning turns.
- Delegate with brakes: require a real independence and ownership case before spawning workers.
- Reproduce the useful parts: ship safe configuration examples and installable skills without copying runtime state.
- Sync without leaks: export only explicit allow-listed files and fail closed on secrets, private paths, unknown files, or hash drift.

## Included components

The bundle vendors seven original skills and tools, including batch-complete review, long-run supervision, a bounded Luna CLI worker, completeness synthesis, incident-to-regression packaging, an explicit Claude review adapter, and an A2A Superhub operator skill.

Components that already have a canonical public home—such as [baton-fanout-skill](https://github.com/phenomenoner/baton-fanout-skill), [Understand Anything](https://github.com/Egonex-AI/Understand-Anything), and [OpenAI skills](https://github.com/openai/skills)—stay as versioned pointers instead of copied forks. See the [component catalog](catalog/components.json) for the complete inventory.

## Quick start

```powershell
git clone https://github.com/phenomenoner/Chatgpt-Codex-App-Plus.git
Set-Location Chatgpt-Codex-App-Plus
python scripts/public_sync.py validate
pwsh -File scripts/install.ps1 -WhatIf
```

Install the recommended set after reviewing the preview:

```powershell
pwsh -File scripts/install.ps1
```

Or select individual skills:

```powershell
pwsh -File scripts/install.ps1 -Skill long-run-supervisor,batch-complete-independent-review
```

Codex discovers user and repository skills from `.agents/skills` locations. See OpenAI's official [Build skills](https://learn.chatgpt.com/docs/build-skills), [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), and [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) guides before installing durable global behavior.

## Public-safety contract

The exporter never mirrors a Codex home directory. It copies only manifest-approved text files, normalizes them deterministically, scans for private state and credentials, and binds the result to a SHA-256 lock. New sources require an explicit allow-list change and human review. Scheduled synchronization may refresh approved components, but it may not expand scope on its own.

Read [the architecture](docs/architecture.md) and [weekly sync contract](docs/weekly-sync.md) for details.

## Distribution status

This repository is currently a directly installable skill and tool collection, not an official plugin. Skills are the reusable workflow layer; a plugin becomes appropriate when the collection is ready to ship as one installable bundle with additional integrations. That packaging step is intentionally deferred until the public surface stabilizes.

## License

Original material in this repository is available under the [MIT License](LICENSE). Pointer-only dependencies remain under their upstream licenses. See [NOTICE.md](NOTICE.md).
