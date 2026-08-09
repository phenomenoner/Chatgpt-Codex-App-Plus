# Context Canvas Codex

Context Canvas Codex 0.4 keeps three deliberately separate concerns for Codex App and CLI work that needs durable coordination or is expected to contain a long-running tool call:

- hook-derived execution identity for the current Codex session;
- a bounded, explicitly continuable semantic task lineage for goals, blockers, decisions, dependencies, findings, and verification pointers;
- a full-fidelity-under-declared-policy historical snapshot store for each opted-in Codex `PostToolUse` callback payload that the host emits.

The split follows one rule: **copy broadly, index selectively, promote semantically, retain intentionally**. Automatic tool telemetry no longer has to become Canvas nodes, while a future investigation can still recover what Codex received at that point in time.

The adapter follows the factual-node to evidence-ref invariant from [`phenomenoner/hermes-agent-harness-plus`](https://github.com/phenomenoner/hermes-agent-harness-plus) at comparison commit `7d6beb485d658a0342194c0e42edcdb7106ed1cb`. It is a clean Codex adaptation; no upstream source code was copied.

## Capability map

| Capability | Codex adaptation |
|---|---|
| Bind, discover, and continue a task canvas | Opaque canvas identity comes only from trusted `SessionStart` or `UserPromptSubmit` input. `canvas_list` discovers recent semantic maps; explicit `canvas_continue` copies one active map into the current ID with stable lineage and a canonical predecessor digest. |
| Initialize before a long tool call | The bundled skill directs the agent to call `canvas_start` at the first useful boundary whenever one tool call is reasonably expected to exceed five minutes, regardless of domain or task type. Hooks only supply trusted identity; they never predict duration or create a Canvas. |
| Non-destructive reopen | Repeating `canvas_start` never overwrites an existing ID. A rephrased goal, cwd, or title returns reviewable conflicts instead of a blocking security error. |
| Objective versus blocker state | The durable objective is `active`, `completed`, or `abandoned`. Open problems are blocker nodes; a goal cannot be marked `blocked`. Legacy blocked goals restore as active objectives. |
| Evidence-backed semantic nodes | Terminal factual nodes require pointer plus SHA-256 evidence. A `snapshot://sha256/<digest>` pointer is verified and durably pinned before the node commit. |
| Full historical tool snapshots | A supported `PostToolUse` callback captures the complete model-facing `tool_input` and `tool_response` delivered by Codex after the declared recursive sanitization policy. Materialized snapshots are never truncated. |
| Content-addressed storage | Canonical JSON and extracted data-URL blobs are SHA-256 addressed, deterministically gzip-compressed, integrity-checked, and deduplicated. Supported textual base64 and percent-encoded data URLs, including unquoted MIME parameters, are decoded and redacted before persistence; opaque binary media is stored unchanged and explicitly labelled uninspected. |
| Retention | Ordinary snapshots expire after 14 days by default. GC previews an exact integrity-checked plan and is non-mutating unless `--apply`; referenced or explicitly pinned objects survive ordinary TTL cleanup. |
| Selective projection | Raw snapshot bodies stay outside Canvas substring search, lifecycle injection, closeout, and MCP responses. Only an intentional evidence pointer promotes a snapshot into the semantic map. |
| Historical truth | Manifests label snapshots `historical-only`, record capture and expiry times, and require revalidation before making a current-state claim. |
| Native tool surface | The local MCP server exposes semantic `canvas_*` tools, recent-canvas discovery, explicit continuation, and bounded `snapshot_list`, `snapshot_read`, `snapshot_pin`, and dry-run-first `snapshot_gc`. Snapshot listing supports tool, capture-status, pin-state, and cursor filters. Full body retrieval remains CLI-only. |
| Concurrency | Writes use cross-process locks, atomic replacement, strict path checks, and a bootstrap lock that covers first-use directory hardening. |

“Full” means the complete model-facing payload supplied to the hook after the declared sanitization policy—not a provider-private wire response that Codex never exposed. Structured and textual assignments share the same normalized secret-key classifier, including suffix-qualified names, percent/form-encoded query keys, bracket/index decoration, JSON Unicode escapes, and bounded escaped wrappers. Any assignment key containing a malformed percent escape is redacted conservatively, and supported encoded/escaped representations are scanned to a bounded fixed point even after an earlier replacement. Secret-shaped keys and strings are replaced before storage while unrelated adjacent query parameters remain usable. Supported textual data URLs are canonicalized, decoded as UTF-8, and redacted before their bytes are persisted; if any MIME parameter value contains a recognized secret, that whole value becomes the redaction sentinel so the stored media type remains valid. Export rehydrates data URLs in canonical base64 form rather than preserving the original textual encoding. A malformed or unsupported `data:` value rejects the whole observation instead of being stored as an ordinary string. Other media is preserved byte-for-byte as `opaque-uninspected`, and the manifest is labelled `sanitized-with-opaque-media`; this is not a claim that image, audio, video, or arbitrary binary content was inspected for secrets. Payloads above the configured 64 MiB hook-input ceiling are skipped rather than silently truncated, and the hook fails open so archiving cannot break the original tool call.

Context Canvas calls do not recursively archive their own response bodies. Their event manifests retain bounded metadata only.

## State layout and identity

The default data root is:

```text
%LOCALAPPDATA%\Codex\context-canvas-codex
```

Semantic canvases remain in `cc-*` directories. Snapshot data is physically and logically separate:

```text
_snapshots/
  events/<opaque-canvas-id>/obs-<event-hash>.json
  objects/sha256/<prefix>/<payload-hash>.json.gz
  blobs/sha256/<prefix>/<blob-hash>.bin.gz
  pins/sha256/<prefix>/<payload-hash>.json
  gc/current.json
```

The lifecycle hooks hash the exact Codex `session_id` with SHA-256. A workspace path is metadata only and never determines identity. Startup or clear reports the opaque ID without creating a Canvas; the agent applies the skill's five-minute prediction rule and initializes through `canvas_start` at the first useful boundary. Resume or compact injects at most 4,800 UTF-8 bytes of bounded semantic state. `UserPromptSubmit` adds a sub-1,000-byte current-turn binding, so a running task can recover its ID on a later prompt after hook activation instead of depending forever on its first `SessionStart`. Snapshot bodies never enter either injection.

Schema v3 gives each initial Canvas a stable lineage ID. `canvas_continue` requires both the current hook-provided ID and an explicit predecessor ID, copies only the bounded semantic map, leaves the predecessor unchanged, and records the SHA-256 of the canonical predecessor state. `canvas_list` derives predecessor/successor navigation without treating an old session as current execution identity.

## App, MCP, CLI, and snapshots

Once the plugin is enabled, Codex App and CLI can use the bundled MCP tools. For repeated semantic or manifest operations, MCP avoids a fresh Python process. Use the CLI for complete policy-sanitized snapshot export:

Keep one MCP registration authority. The plugin-provided local stdio server is the default; do not
also retain a user-level `context-canvas` entry, because an absolute cache path can pin an older
plugin version and duplicate server processes after an upgrade.

For an older Codex build that cannot launch plugin-provided MCP servers, use this explicit-path
compatibility fallback only while the plugin-provided registration is disabled or unavailable,
then restart the Codex App:

```powershell
$python = (Get-Command python -ErrorAction Stop).Source
$server = (Resolve-Path .\scripts\context_canvas_mcp.py).Path
codex mcp add context-canvas -- $python -B -I $server
codex mcp get context-canvas
```

The final `get` output must show absolute paths for both `command` and the server script. Never
leave both registrations active. A fresh task must still call a `canvas_*` tool successfully;
configuration readback alone is not runtime proof.

```powershell
python -I scripts/context_canvas.py snapshot-list --canvas-id <opaque-id> --limit 20
python -I scripts/context_canvas.py snapshot-read --canvas-id <opaque-id> --event-id <obs-id>
python -I scripts/context_canvas.py snapshot-export --canvas-id <opaque-id> --event-id <obs-id> --output <absolute-json-path>
python -I scripts/context_canvas.py snapshot-pin --sha256 <payload-sha256> --reason "Referenced by incident finding"
python -I scripts/context_canvas.py snapshot-gc
python -I scripts/context_canvas.py snapshot-gc --apply
```

The ordinary semantic map remains intentional:

```powershell
python -I scripts/context_canvas.py init --canvas-id <opaque-id> --goal "Bounded goal" --cwd <absolute-workspace>
python -I scripts/context_canvas.py list --limit 8 --cwd <absolute-workspace>
python -I scripts/context_canvas.py continue --canvas-id <current-opaque-id> --predecessor-canvas-id <prior-opaque-id>
python -I scripts/context_canvas.py upsert --canvas-id <opaque-id> --kind plan --status planned --summary "Inspect the boundary"
python -I scripts/context_canvas.py search "boundary" --canvas-id <opaque-id>
python -I scripts/context_canvas.py closeout --canvas-id <opaque-id> --no-write
```

To promote a snapshot as durable evidence, attach its exact URI and digest to a factual node. The store verifies the URI, object, every transitive blob, digest, length, and declared media policy, then pins the object before committing the Canvas mutation.

## Hook installation

The plugin bundles three hooks:

- `SessionStart` restores bounded semantic state;
- `UserPromptSubmit` refreshes the current opaque ID and compact lineage state without reading the prompt body or writing a Canvas;
- `PostToolUse` archives policy-sanitized historical snapshots for callback payloads that Codex actually emits and emits no model-facing output.

If the current Codex build does not execute plugin-bundled hooks, install the same audited pair through the user configuration layer:

```powershell
python -I scripts/install_context_canvas_hook.py install
python -I scripts/install_context_canvas_hook.py check
```

The installer migrates older SessionStart-only and SessionStart-plus-PostToolUse installations, preserves peer handlers, keeps content-addressed backups, and checks all three managed event groups plus stable script bytes. It recovers an interrupted script-first installation only when the unmanifested bytes exactly match the current source. Re-run `install` after each plugin upgrade.

Current Codex invokes `PostToolUse` when a supported handler returns an opted-in post-tool payload. A Bash command that exits non-zero can still produce that callback and its exit metadata can be archived. Dispatch or handler failures that produce no callback payload remain absent, and Codex exposes no separate failure sibling to this adapter. This is a host-surface limit, not a silent fallback. Verify actual coverage in a fresh task after installation; see the [official hook behavior](https://learn.chatgpt.com/docs/hooks#posttooluse).

## Performance probe

Run the reproducible probe on the target machine:

```powershell
python -B -I scripts/benchmark_context_canvas.py
```

The probe reports persistent MCP reads, fresh CLI startup, first snapshot write, warmed content dedupe, manifest reads, exact GC preview, and cold small/large `PostToolUse` hook execution as machine-readable JSON. GC verifies event/object/blob relationships and includes orphan discovery, so its result is not comparable to an earlier count-only preview. Snapshot latency depends strongly on Python startup, ACL verification, storage, antivirus, concurrent load, and payload shape; publish or compare measurements only with the executable hashes and environment from the same receipt.

## Security and truth boundary

- The snapshot layer stores policy-sanitized structured/textual content plus explicitly labelled opaque media from the model-facing payload, not a sealed unredacted evidence tier and not provider-private transport data.
- Automatic capture has no sealed-secret tier. If preserving an unredacted secret is genuinely necessary, use a separately approved encrypted evidence system.
- Export answers “what did Codex see then?” It does not prove the source is still current; manifests require revalidation.
- Snapshot bodies never participate in Canvas search or MCP output. Explicit CLI export is the body-read boundary.
- The store verifies the protected private-root ACL in every process and rejects descendant aliases, reparse points, hard links, non-regular files, corrupt hashes, invalid manifests, and unprovable locks. GC recomputes and validates the journal plan identity before mutation, derives remaining work from current verified state after interruption, and sweeps unreferenced objects and blobs.

See [SECURITY.md](SECURITY.md) and [docs/SNAPSHOT_STORE_DESIGN.md](docs/SNAPSHOT_STORE_DESIGN.md).

## Activation and retirement

Installation and catalog state do not prove a running task loaded the hooks. Current Codex App builds require manual approval of newly installed hook definitions, so if the opaque ID or turn binding is missing, open `/hooks` and check the Context Canvas approval/trust state before reinstalling the hook or restarting the computer. After approval, a later prompt in an already-running task may prove `UserPromptSubmit` pickup by supplying its current opaque ID. A fresh task is still the stronger end-to-end check: require a new opaque ID from `SessionStart`, then a new manifest after a harmless tool call. Treat any current-task pickup as runtime evidence, not a guarantee that every Codex build hot-reloads hook configuration.

For retirement, run `python -I scripts/install_context_canvas_hook.py uninstall` to remove only the exact managed user-hook groups and recoverably retire owned files. Disable the MCP server and skill before archiving the plugin and its data root. Do not delete repository WALs, receipts, pinned snapshot exports, or evidence targets referenced by Canvas nodes.
