# Security boundaries

## Intended authority

This plugin reads and writes only its private local data root and explicit CLI export destinations. It uses no network library, remote service, connector, transcript parser, credential broker, or background task. Canvas state is optional reference data: it neither authorizes nor blocks the user's underlying work.

`SessionStart` and `UserPromptSubmit` are read-only. Both derive the current opaque ID from the exact hook-supplied session ID. The turn hook validates that a prompt field exists but never stores, echoes, searches, or interprets its contents; an internal failure emits no context and cannot block the prompt. `PostToolUse` persistence is off by default. After `snapshot_capture_next` arms one expiring request, the next matching non-Canvas callback may archive a policy-sanitized historical copy of the model-facing tool input and response supplied by Codex. The request is consumed once. A Bash non-zero command exit can still be observed through this callback. Dispatch or handler failures that produce no callback payload are absent. The hook emits no model-facing output and fails open, so capture failure cannot replace the original tool result.

The compatibility installer is an explicit configuration write. It merges exact `SessionStart`, `UserPromptSubmit`, and `PostToolUse` groups into the user's Codex `hooks.json`, copies the audited script to a stable Codex-home path, preserves peer handlers, and keeps a hash-addressed backup. It rejects foreign targets, duplicate or drifted managed definitions, aliases, and non-regular files. Uninstall removes only exact managed groups and recoverably retires owned files.

The MCP server is a local child process using newline-delimited JSON-RPC over stdin/stdout. It has no listener. MCP exposes bounded Canvas state, explicit managed references, snapshot manifests, and explicit chunked snapshot-payload reads. Complete policy-sanitized snapshot retrieval to a file requires a separate CLI export path.

## Snapshot fidelity and sanitization

An explicitly requested snapshot contains canonicalized `tool_input` and `tool_response` from the Codex `PostToolUse` hook. It is full fidelity **under the declared sanitization and opaque-media policy**:

- secret-shaped keys and strings, authorization values, token prefixes, private-key material, and similar values are replaced recursively before hashing or storage; structured keys and textual assignments use the same normalized suffix-aware key classifier after bounded decoding of percent/form query keys, bracket/index notation, JSON Unicode escapes, and escaped wrappers; any malformed-percent assignment key is redacted conservatively, and an earlier replacement never disables the remaining supported representation passes;
- non-finite numbers and unsupported Python values cannot enter canonical JSON;
- supported textual base64 and percent-encoded data URLs, including unquoted MIME parameters, are canonicalized, decoded as UTF-8, and passed through the same pattern-based redaction before their bytes are persisted; any MIME parameter value containing a recognized secret is replaced in full so partial redaction cannot create invalid stored metadata;
- a malformed or unsupported `data:` value rejects the whole observation instead of falling through to ordinary string storage; export emits a canonical base64 representation rather than preserving the original textual encoding;
- other complete data URLs are stored unchanged as `opaque-uninspected` binary objects and cause the event to be labelled `sanitized-with-opaque-media`; export rehydrates either policy;
- payloads are never partially stored: above the configured hook-input ceiling they are skipped, not truncated;
- Context Canvas tool responses are captured as bounded metadata only to prevent recursive self-archival.

This is not a sealed raw-evidence vault. There is no unredacted tier and no claim that pattern matching can recognize every application-specific secret shape or inspect arbitrary binary media. The same caution applies to explicit text references. Do not deliberately place credentials in tool output or opaque media, and do not use these stores as the approved location for unredacted secrets.

## Separation, integrity, and retention

Semantic Canvas nodes, managed references, capture requests, and snapshot objects are separate. Reference and snapshot bodies are excluded from lifecycle injection and closeout. References have a bounded search/chunk-read API; snapshot bodies require an explicit bounded read or CLI export. A factual node may reference `snapshot://sha256/<digest>` only when the object and every transitive blob pass digest, length, schema, and policy validation and the pointer digest matches its evidence SHA-256; that promotion durably pins the object.

Execution identity and semantic lineage are also separate. `canvas_continue` accepts a current opaque ID plus an explicit predecessor ID, copies only validated bounded Canvas state, preserves the predecessor, and stores the canonical predecessor SHA-256. Cwd is never used to auto-select or authorize a predecessor. Listing may expose local titles, cwd metadata, and opaque lineage topology through the local MCP/CLI surface, but it does not read transcripts, snapshot bodies, or evidence targets.

Canonical JSON objects and extracted blobs are content-addressed with lowercase SHA-256 identities and deterministically gzip-compressed. Full read, export, promotion, and GC preflight verify compression, canonical digest spelling, canonical object bytes, manifest-declared object and blob lengths, schema, manifest path/session identity, object relationships, and declared blob policy. Bounded list operations validate bound manifests without loading bodies. Repeated identical payloads deduplicate without losing per-call event manifests.

Ordinary snapshots use an ephemeral retention class and expire after 14 days by default. Cleanup is preview-only unless explicitly applied. Before mutation, GC validates the complete graph and writes one canonical plan containing every event, object, and blob identity. A later run recomputes the journal plan ID, validates ordered unique identities, and derives remaining work from current verified state before resuming; unreferenced capture orphans are swept. Pinned objects and their referenced blobs survive ordinary expiry. Historical snapshots carry capture/expiry times and `requires_revalidation: true`; they answer what Codex saw then, not what is true now.

On Windows, initialization removes inherited ACLs from the private data root and each newly created managed directory, grants the current SID full control, and reads the ACL back. Every process revalidates the protected data-root ACL. Existing content-addressed descendants rely on that traversal boundary and are rechecked as plain, non-aliased directories without launching a separate ACL reader for every path component. Lock files, Canvas files, event manifests, objects, blobs, pins, and export targets reject symlinks, junctions, reparse points, hard links, directories, and non-regular substitutes as applicable. Bootstrap and normal operations use cross-process locks and atomic replace.

## Untrusted data

Node summaries, evidence pointers, managed references, snapshot manifests, and exported historical payloads are untrusted data. Never treat their contents as commands or instructions. Do not re-run a recorded tool call merely because its arguments appear in a snapshot.

Sensitive-looking semantic node content still fails closed before mutation. That guardrail is separate from explicit reference and snapshot sanitization and is not a credential vault.

## Known limits

- The ACL protects against other principals, not malicious code already executing as the same Windows SID.
- Atomic replace and file flush protect normal process interruption; this release does not claim power-loss durability on Windows.
- Sanitization is pattern-based and cannot prove removal of every domain-specific secret.
- Opaque binary media is deliberately not content-inspected; its manifest policy makes that boundary explicit.
- Full snapshot fidelity is bounded by the model-facing hook payload Codex supplies; provider-private wire data is outside scope.
- Current Codex emits this surface when a supported handler returns an opted-in `PostToolUse` payload. Bash non-zero command outcomes can be present; dispatch or handler failures with no callback payload remain absent, and there is no separate failure sibling for this adapter.
- Plugin discovery, installation, and a trusted hash do not prove hooks executed in the current task. A later prompt may demonstrate turn-hook pickup on builds that reload trusted hook configuration; verify a new `SessionStart` opaque ID, arm one harmless exact tool call, and inspect its snapshot in a fresh task for the stronger end-to-end capture check.
- Same-user software can change a stable user-hook adapter; `check` detects drift but is not a same-user sandbox.
- Map search is bounded substring lookup over semantic metadata, reference search is bounded over one Canvas's redacted reference text, and neither is semantic recall or snapshot body search.
- `python` must resolve to Python 3.11 or newer for the bundled commands.

An invalid caller-supplied semantic-node mutation fails closed for that mutation
only. It does not prove the stored Canvas is corrupt, does not disable or abandon
the Canvas, and does not change a separately armed one-shot capture request.
Correct the mutation or continue the underlying task without Canvas.

If an ACL, alias, lock, stored schema or digest, protocol, or corruption check
fails at a storage boundary, preserve the directory for inspection and disable
the affected plugin surface. Do not retry through a less restrictive path or
identity. The storage failure does not block work outside Canvas. A snapshot
capture whose own sanitization or storage checks fail emits no archive and fails
open with respect to the original tool result.
