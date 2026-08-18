# Security policy

## Reporting a vulnerability

Please use GitHub's private security advisory flow for vulnerabilities or accidental disclosure reports. Do not open a public issue containing credentials, private paths, personal identifiers, or exploit details that would create immediate risk.

Include the affected file or component, impact, reproduction conditions, and a minimal redacted proof. Do not test against systems or accounts you do not own or have explicit permission to assess.

## Public-data boundary

This repository is designed to contain reusable instructions, plugin source, scripts, examples, manifests, and public documentation only. Authentication, sessions, canvas data, evidence targets, memories, logs, attachments, private configuration, local plugin caches, and connector data are out of scope. If such material appears, treat it as an incident even when the credential seems expired.

The Context Canvas MCP server is local stdio only. It exposes an optional task map, explicit policy-redacted text references, and bounded reads. `PostToolUse` persistence is off by default: after `snapshot_capture_next` arms one expiring request, only the next matching non-Canvas callback may be archived, and the request is consumed once. Stored payloads retain the declared structured/textual sanitization, data-URL policy, content addressing, dedupe, TTL, pinning, and integrity-checked GC. Arbitrary binary media remains byte-for-byte `opaque-uninspected`. Bash non-zero command outcomes can still be observed; dispatch or handler failures that produce no callback payload remain absent, as do provider-private wire data and transcripts. This is not a sealed or provably secret-free raw-evidence vault. MCP payload reads are explicit and bounded; complete file export remains CLI-only. Reference and snapshot bodies remain outside lifecycle injection and public synchronization.

The Context Canvas hook compatibility installer is an explicit user-config
mutation, not an automatic post-install action. It may add only its exact
`SessionStart`, `UserPromptSubmit`, and `PostToolUse` groups, preserve unrelated hooks, keep a content-addressed backup,
and fail closed on foreign or drifted owned files. It recovers a script-first
interruption only when the installed bytes exactly match the current source. Legacy migration additionally binds the recorded SessionStart handler and installed-file digests to the owned bytes. A plugin upgrade requires a
new installer `check`; Codex hook trust does not sandbox other software already
running as the same user.

## Supported versions

Security fixes for Context Canvas target the latest `context-canvas-codex-v*`
component release and the default branch. Older component tags are not
guaranteed to receive backports. Pointer-only dependencies follow their
upstream security and support policies.
