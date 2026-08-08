# Context Canvas snapshot store design

## Purpose

Context Canvas keeps two different kinds of state:

1. a small semantic map of goals, blockers, decisions, findings, and verification; and
2. a historical evidence cache containing the complete post-sanitization payload that Codex supplied to a `PostToolUse` hook.

The snapshot cache preserves what the agent actually saw at a point in time without turning every tool invocation into a semantic node. The guiding rule is:

> Copy broadly, index selectively, promote semantically, retain intentionally.

## Fidelity boundary

The capture source is the Codex `PostToolUse` hook payload. Current Codex emits it when a supported handler returns an opted-in post-tool payload; a Bash command that exits non-zero can still produce it. Dispatch or handler failures that produce no callback payload remain absent, and Codex exposes no separate failure sibling to this adapter. For MCP calls it contains the MCP call result; for other supported tools it normally contains the model-facing result. A snapshot therefore proves what Codex delivered to this hook, not necessarily the provider's private wire response, and it cannot prove that every attempted call was observed.

The stored object contains the full captured `tool_input` and `tool_response` after deterministic sanitization. It is never silently truncated. If the hook input exceeds the configured hard limit or cannot be parsed, capture fails as an explicit observation error rather than writing a partial object.

Default capture removes credentials recognized in structured and textual content. Structured keys and textual assignments share one normalized, suffix-aware secret-key classifier. Before textual classification, the bounded sanitizer recognizes percent/form-encoded query keys, bracket/index decoration, JSON Unicode escapes, and escaped wrappers. Any assignment key containing a malformed percent escape is redacted conservatively; supported escaped and percent-decoded views continue to a bounded fixed point even if an earlier representation already produced a replacement, while safe neighboring query parameters remain intact. Sensitive key names, bearer credentials, known token forms, and private-key blocks are replaced before hashing or persistence. Supported textual base64 and percent-encoded data URLs with unquoted MIME parameters are canonicalized, decoded as UTF-8, and redacted under the same policy. If a MIME parameter contains a recognized secret, its complete value becomes the redaction sentinel so stored metadata remains syntactically valid; export rehydrates canonical base64 rather than the original textual encoding. A malformed or unsupported `data:` value rejects the whole observation. Arbitrary binary media is preserved unchanged as explicitly labelled `opaque-uninspected` content; it is not inspected for embedded secrets. A sealed raw-evidence tier would require an explicit encryption and key-management contract and is outside this version.

## Storage layout

The snapshot store is separate from semantic canvases and their search path:

```text
context-canvas-codex/
├── cc-<opaque-id>/
│   ├── canvas.json
│   └── closeout.md
└── _snapshots/
    ├── .snapshot.lock
    ├── objects/sha256/<prefix>/<digest>.json.gz
    ├── blobs/sha256/<prefix>/<digest>.bin.gz
    ├── events/cc-<opaque-id>/obs-<digest>.json
    ├── pins/sha256/<prefix>/<digest>.json
    └── gc/current.json
```

- Object identity is the SHA-256 of canonical uncompressed JSON. Identical sanitized payloads deduplicate even when several tool calls reference them.
- Gzip is deterministic and available in the Python standard library. This keeps the plugin dependency-free on Codex App and CLI hosts.
- Supported embedded `data:` URLs are decoded into content-addressed blobs. Textual MIME content is redacted before persistence and records `text-redacted`; other media records `opaque-uninspected`. The JSON object stores a typed blob reference and export rehydrates a canonical base64 data URL.
- Each observation manifest records provenance independently from the deduplicated object.
- Snapshot bodies and blob contents are excluded from `canvas_search`; only promoted node summaries and evidence pointers are searchable.

## Observation manifest

Each captured call records:

- schema and capture implementation version;
- capture time and expiry time;
- opaque Canvas ID plus hashed session identity;
- Codex turn ID and tool-use ID;
- tool name, model, permission mode, working directory, and hook event;
- original hook-input byte length and sanitized object byte length;
- object URI, SHA-256, compression, media type, and extracted blob metadata;
- `truncated: false` for every materialized snapshot;
- fidelity class (`codex-post-tool-use-model-facing`);
- sensitivity class (`sanitized` or `sanitized-with-opaque-media`), redaction count, per-blob content policy, and retention class;
- capture status, inferred exit/error metadata when the tool response exposes it;
- replayability class and whether current-state revalidation is required.

Event identity is derived from the opaque Canvas ID, turn, tool-use ID, and tool name. Validation requires lowercase canonical SHA-256 identities and binds the manifest to its parent path, session hash, event filename, retention interval, canonical object bytes and declared byte length, and every declared blob. Re-running the same hook input is idempotent. Context Canvas tool calls are recorded as metadata-only observations so the cache does not recursively capture itself.

## Retention and promotion

New materialized snapshots are `ephemeral` and receive a local retention deadline. Garbage collection is an explicit CLI/MCP action; there is no background service. Preview and apply use the same exact validated event/object/blob plan. Apply journals the canonical ordered, unique candidate identities before the first unlink. A later invocation recomputes the journal plan ID and derives remaining work from current verified state before resuming; unreferenced objects or blobs left by an interrupted capture are included as orphans.

An evidence ref with both:

```text
pointer = snapshot://sha256/<digest>
sha256  = <same digest>
```

is validated against the local object and every transitive blob, then pinned before the semantic node is committed. A pin is content-level, can be referenced by more than one node, and exempts the object from ordinary expiry. A failed Canvas commit may leave a conservative extra pin, but never a semantic reference to missing or corrupt evidence.

Ordinary file and URL evidence pointers keep their existing pointer-plus-hash semantics and are not copied automatically by the semantic API.

## Retrieval modes

- `historical`: read or export the stored sanitized snapshot without rerunning the tool.
- `current`: not generic in this version; tool-specific revalidation adapters would be required.
- `either`: callers may use the historical snapshot and decide separately whether freshness requires a new tool call.

Every manifest includes capture time, expiry, source identity, replayability, and a revalidation flag so historical evidence cannot be mistaken for current truth.

## Interfaces

The hidden `hook-post-tool-use` command captures observations and exits without adding model context. Capture errors are fail-open for the completed tool call and emit bounded diagnostics without echoing payload content.

Operator interfaces provide:

- bounded manifest listing and inspection with exact tool-name, capture-status,
  pin-state, and stable event-cursor filters;
- explicit complete policy-sanitized export to a caller-selected file;
- explicit pinning;
- dry-run-first retention garbage collection with exact candidate identities and interruption recovery; and
- snapshot URIs suitable for semantic-node evidence refs.

MCP responses remain bounded. Large payload export stays a CLI operation so retrieving evidence does not flood the model context.

## Security and concurrency

The snapshot hierarchy uses the same no-symlink/no-reparse-point, cross-process-lock, and atomic-replace rules as canonical Canvas state. Each process revalidates the protected private data-root ACL; newly created managed directories are hardened once, while existing descendants rely on the root traversal boundary and undergo cheap plain-directory checks. Hash verification occurs after decompression during read/export. Manifest, object, and transitive blob verification occurs before promotion or destructive GC mutation. Corrupt or missing content fails closed.

Hook stdout stays empty on success, so snapshots consume storage rather than model context. Manifests may contain local paths and tool provenance and therefore remain local-only; the public repository contains code and schemas, never captured data.

## Verification contract

The implementation is accepted only with focused evidence for:

- complete round-trip capture and CLI export, including Unicode and embedded binary data;
- deterministic sanitization including suffix-qualified, percent/form-encoded, malformed-percent, bracket-decorated, JSON-escaped, escaped-wrapper, and mixed-representation assignment keys, with safe neighboring query controls preserved, secret sentinels absent from every inspected textual or decompressed file, and explicit opaque-media policy;
- textual data-URL body and whole-value MIME-parameter redaction that self-validates before persistence and survives read, export, promotion, and GC preflight;
- content-addressed deduplication and idempotent event capture;
- snapshot exclusion from semantic search;
- automatic transitive-integrity pin promotion and expiry-safe garbage collection;
- exact GC preview, orphan sweep, pending-plan recovery, and corrupt-graph preflight before mutation;
- corruption, nested-alias, manifest-identity, oversize, and concurrent-writer behavior;
- installer merge/uninstall, exact legacy owner-digest migration, drift refusal, and interrupted-install recovery for `SessionStart`, `UserPromptSubmit`, and `PostToolUse` handlers;
- MCP message bounds and CLI error behavior; and
- measured hook latency and compression ratios on representative small and large payloads.
