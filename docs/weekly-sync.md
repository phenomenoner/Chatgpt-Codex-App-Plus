# Weekly synchronization contract

The weekly task runs against the local repository and may update only sources already authorized in `manifest/public-sources.json`.

## Required sequence

1. Run `python scripts/public_sync.py sync --apply`.
2. Stop without commit or push if the exporter reports any blocked finding.
3. Run `python -m unittest discover -s tests -v`.
4. Run the vendored skill checks listed by the repository validation workflow.
5. Run `python scripts/public_sync.py validate` and `git diff --check`.
6. Inspect the complete public diff for provenance, marketing claims, private context, and license changes.
7. If no tracked bytes changed, finish without creating a commit.
8. If all gates pass, commit the allow-listed refresh and push the default branch.

## Hard brakes

The scheduled task must not:

- add or broaden manifest entries;
- copy an upstream pointer into the repository;
- publish authentication, sessions, memories, logs, project paths, backups, or connector state;
- weaken a scanner rule or add a public exception;
- change GitHub visibility, repository permissions, secrets, Actions permissions, or branch protection;
- install dependencies globally or mutate the source Codex/agent homes;
- push after a failed, timed-out, partial, or output-lost verification.

Changes to authority—the manifest, scanner rules, exception set, lock schema, release policy, or scheduled prompt—always require an interactive human-reviewed update.

The computer and ChatGPT desktop app must be running for scheduled work that needs local files. Review the official [Scheduled tasks](https://learn.chatgpt.com/docs/automations) guidance, especially sandbox and permission implications.
