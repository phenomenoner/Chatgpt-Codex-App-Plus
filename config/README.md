# Configuration profile

`config.example.toml` is intentionally safer than a power user's private runtime profile. It demonstrates durable settings without publishing project trust paths, notification commands, credentials, local marketplace sources, connector state, or machine-specific paths.

Codex configuration is layered. Personal defaults live in the Codex home, trusted repositories may add `.codex/config.toml`, and command-line overrides take precedence. Read the official [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) and [permissions](https://learn.chatgpt.com/docs/permissions) guidance before copying settings.

`AGENTS.example.md` is a reusable global guidance profile. Adopt it selectively: durable rules should express outcomes and safety boundaries, while project-specific commands and acceptance contracts belong in the nearest repository `AGENTS.md`.

This repo deliberately does not publish:

- authentication or connector state;
- sessions, memories, goals, logs, attachments, or automations;
- per-project trust entries and absolute paths;
- full-access or no-approval settings as a default;
- locally installed plugin caches or third-party source copies.
