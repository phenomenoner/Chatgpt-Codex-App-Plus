# Public bundle architecture

## Goal

Publish reusable Codex customization without turning a personal Codex home into a public mirror. The repository separates authored components, upstream pointers, public configuration examples, and local runtime state.

## Trust boundaries

```text
personal Codex and agent homes
          |
          | explicit source manifest only
          v
  fail-closed exporter ----> blocked findings
          |
          | normalized UTF-8/LF files
          v
  vendored public skills + SHA-256 lock
          |
          | tests + repository-wide hygiene scan
          v
       GitHub public repository
```

Runtime state is outside the export boundary. Authentication, sessions, memories, goals, logs, attachments, connector state, project trust paths, backups, and local plugin caches are not eligible sources.

## Vendored versus pointer-only

A component is vendored only when it is authored or maintained as part of this collection, has a clear public license boundary, and passes the public scanner. A component remains pointer-only when a canonical public repository already exists or its redistribution terms belong upstream.

Pointers are bound to a full commit in `manifest/public-sources.json` and copied into `manifest/public-lock.json`. Weekly automation may report upstream drift, but it must not silently replace a pinned dependency or copy upstream content into this repository.

## Export invariant

The exporter computes the desired public tree from the manifest, not from directory discovery. Unlisted files remain local. Listed text is normalized, scanned, and hashed before any destination write. Source or destination path escape, symlinks, binary input, credential patterns, private paths, and backup/runtime file types fail closed.

An exception is possible only for a non-secret finding named in the exporter's fixed set, on an exact component-relative file, with a public reason in the manifest. Credential findings are not exemptible.

## Lock invariant

`manifest/public-lock.json` binds every vendored public skill file to:

- repository-relative path;
- component identity;
- byte length;
- SHA-256.

Validation rejects missing, modified, or extra skill files and requires the pointer set to match the source manifest.

## Distribution layers

- `skills/`: directly installable workflow packages.
- `config/`: safe examples, not a copy of a private profile.
- `catalog/`: human-facing component purpose, maturity, and requirements.
- `manifest/`: machine-enforced export authority and lock.
- `scripts/`: deterministic export, validation, and installation helpers.

The collection may become a plugin later. That step should add plugin metadata and installation UX without weakening the current source, license, or public-safety boundaries.
