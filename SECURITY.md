# Security policy

## Reporting a vulnerability

Please use GitHub's private security advisory flow for vulnerabilities or accidental disclosure reports. Do not open a public issue containing credentials, private paths, personal identifiers, or exploit details that would create immediate risk.

Include the affected file or component, impact, reproduction conditions, and a minimal redacted proof. Do not test against systems or accounts you do not own or have explicit permission to assess.

## Public-data boundary

This repository is designed to contain reusable instructions, plugin source, scripts, examples, manifests, and public documentation only. Authentication, sessions, canvas data, evidence targets, memories, logs, attachments, private configuration, local plugin caches, and connector data are out of scope. If such material appears, treat it as an incident even when the credential seems expired.

The Context Canvas MCP server is local stdio only and never returns snapshot bodies. When Codex emits an opted-in `PostToolUse` payload, the hook archives the complete model-facing payload under a declared sanitization policy into a separate local content-addressed store. Structured and textual key classification recognizes percent/form query encoding, bracket/index notation, JSON Unicode escapes, and escaped wrappers before persistence; every malformed-percent assignment key is redacted conservatively, and mixed representations are scanned to a bounded fixed point. Supported textual data URLs are decoded and pattern-redacted; malformed or unsupported `data:` values reject the whole observation, while arbitrary binary media remains byte-for-byte `opaque-uninspected`. Bash non-zero command outcomes can still be observed. Dispatch or handler failures that produce no callback payload are absent, as are provider-private wire data and transcripts. This is not a sealed or provably secret-free raw-evidence vault. Full historical retrieval is an explicit CLI export, and snapshots remain outside semantic search and public synchronization.

The Context Canvas hook compatibility installer is an explicit user-config
mutation, not an automatic post-install action. It may add only its exact
`SessionStart` and `PostToolUse` groups, preserve unrelated hooks, keep a content-addressed backup,
and fail closed on foreign or drifted owned files. It recovers a script-first
interruption only when the installed bytes exactly match the current source. Legacy migration additionally binds the recorded SessionStart handler and installed-file digests to the owned bytes. A plugin upgrade requires a
new installer `check`; Codex hook trust does not sandbox other software already
running as the same user.

## Supported versions

Security fixes apply to the default branch until tagged releases are introduced. Pointer-only dependencies follow their upstream security and support policies.
