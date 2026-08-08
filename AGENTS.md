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
- For an existing exporter or scanner defect, add a discriminating regression and demonstrate fail-first when the old behavior is safely reproducible. Credential findings must remain non-exemptible.
- Before a completion or publication claim, run the focused repository and vendored component checks that can falsify the changed behavior, `python scripts/public_sync.py validate`, and `git diff --check`.
- Run the full repository suite only when exporter/scanner infrastructure, shared schemas or catalogs, release-wide behavior, or a remaining coverage gap makes the blast radius repository-wide.
- Read the full public diff after scanners pass. Replace private shorthand with behavior, impact, verification, and honest limitations.

## Publishing

- Stage explicit files in a mixed worktree. Do not use a broad add when unrelated files exist.
- Keep README, ABOUT, repository description, topics, catalog, and notices aligned when the public positioning changes.
- Do not claim official OpenAI, Anthropic, or upstream-project status.
