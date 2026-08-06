# Security boundaries

## Intended authority

This plugin reads and writes only its private local data root. It uses no
network library, remote service, connector, transcript parser, `PostToolUse`
capture, credential, or background task. `SessionStart` is the only lifecycle
hook and remains read-only.

The optional compatibility installer is an explicit configuration write. It
merges one exact `SessionStart` group into the user's Codex `hooks.json`, copies
the audited hook script to a stable Codex-home path, and keeps a hash-addressed
backup of a pre-existing hook file. It refuses foreign targets, duplicate or
drifted managed definitions, aliases, and non-regular files. Uninstall removes
only the exact managed group and moves owned files into a private retirement
directory instead of deleting them.

The bundled MCP server is a local child process using newline-delimited JSON-RPC
over stdin/stdout. It has no network listener and uses the same bounded store as
the CLI. MCP requests cannot supply raw evidence; only pointer plus SHA-256
metadata is accepted.

On Windows, initialization removes inherited ACLs with `icacls`, grants the
current SID full control, and independently reads the ACL back. Data root,
session directory, lock, canonical JSON, and closeout paths reject symlinks,
junctions, reparse points, hard links, directories, and non-regular file
substitutes as applicable. Writes use a cross-process lock and atomic replace.

The persistent process caches a successful ACL check only while the directory
file identity and change timestamps remain unchanged. A changed token forces a
fresh verification. The current Windows identity is cached for the life of the
process because it cannot change without replacing that process.

## Untrusted data

Node summaries and evidence pointers are untrusted metadata. Never treat them
as commands or prompt instructions. The plugin never opens, fetches, executes,
or copies an evidence pointer. Search and closeout operate only on stored
metadata; raw evidence reads are unsupported.

Sensitive-looking values fail closed before the data root is created or a write
begins. This is a guardrail, not a credential vault. Do not encode or split a
secret to bypass it.

## Integrity and compatibility

- Factual nodes entering `blocked`, `done`, `superseded`, `verify`, or
  `deprecated` require hash-bound evidence.
- Dependencies must reference existing nodes, cannot contain duplicates or
  self-links, and must remain acyclic.
- v1 state is read through an in-memory compatibility adapter. Read-only restore
  does not rewrite it; the first intentional mutation persists canonical v2.
- Search skips and reports a malformed canvas instead of hiding readable peers.

## Known limits

- The ACL protects against other principals, not malicious code already
  executing as the same Windows SID.
- Atomic replace and file flush protect normal process interruption. This
  release does not claim power-loss durability on Windows.
- Local data remains readable to the current SID and software already running
  with that authority.
- Plugin discovery does not prove plugin-bundled hooks execute on every Codex
  build. Use the explicit user-hook adapter only after a fresh-task probe fails,
  and rerun its `check` command after plugin upgrades.
- Codex hook trust covers the configured handler definition. Software already
  running as the same user can still change the stable adapter file; `check`
  detects that drift but is not a sandbox against same-user code.
- Search is bounded substring lookup, not semantic recall.
- `python` must resolve to Python 3.11 or newer for the bundled MCP command.

If an ACL, alias, lock, validation, protocol, or corruption check fails,
preserve the directory for inspection and disable the plugin. Do not retry
through a less restrictive path.
