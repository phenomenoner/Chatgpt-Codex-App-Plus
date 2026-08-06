# Security policy

## Reporting a vulnerability

Please use GitHub's private security advisory flow for vulnerabilities or accidental disclosure reports. Do not open a public issue containing credentials, private paths, personal identifiers, or exploit details that would create immediate risk.

Include the affected file or component, impact, reproduction conditions, and a minimal redacted proof. Do not test against systems or accounts you do not own or have explicit permission to assess.

## Public-data boundary

This repository is designed to contain reusable instructions, plugin source, scripts, examples, manifests, and public documentation only. Authentication, sessions, canvas data, evidence targets, memories, logs, attachments, private configuration, local plugin caches, and connector data are out of scope. If such material appears, treat it as an incident even when the credential seems expired.

The Context Canvas MCP server is local stdio only. It must not gain a network listener, transcript parser, raw evidence ingestion, or automatic tool-output capture without a new security review and explicit public contract change.

The Context Canvas hook compatibility installer is an explicit user-config
mutation, not an automatic post-install action. It may add only its exact
`SessionStart` group, preserve unrelated hooks, keep a content-addressed backup,
and fail closed on foreign or drifted owned files. A plugin upgrade requires a
new installer `check`; Codex hook trust does not sandbox other software already
running as the same user.

## Supported versions

Security fixes apply to the default branch until tagged releases are introduced. Pointer-only dependencies follow their upstream security and support policies.
