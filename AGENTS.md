# Repository agent instructions

## Scope

- Keep this repository public-safe, self-contained, and useful to readers with no private project context.
- Preserve unrelated work. Do not publish, tag, change repository visibility, or modify scheduled automation unless the active user request explicitly authorizes it.

## Source and provenance

- `manifest/public-sources.json` is the only authority for local source export. Do not broaden it automatically.
- Vendor original components maintained here. Prefer a versioned pointer when a canonical public repository already exists.
- Never import authentication, sessions, memories, goals, logs, attachments, project trust paths, backups, local plugin caches, or connector state.

## Changes and verification

- Edit authored repository files intentionally. Use `scripts/public_sync.py sync --apply` only for manifest-authorized mechanical refreshes.
- For exporter or scanner behavior changes, add a fail-first regression test. Credential findings must remain non-exemptible.
- Before a completion or publication claim, run:
  - `python -m unittest discover -s tests -v`
  - vendored deterministic component checks relevant to the diff
  - `python scripts/public_sync.py validate`
  - `git diff --check`
- Read the full public diff after scanners pass. Replace private shorthand with behavior, impact, verification, and honest limitations.

## Publishing

- Stage explicit files in a mixed worktree. Do not use a broad add when unrelated files exist.
- Keep README, ABOUT, repository description, topics, catalog, and notices aligned when the public positioning changes.
- Do not claim official OpenAI, Anthropic, or upstream-project status.
