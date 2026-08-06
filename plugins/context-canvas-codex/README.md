# Context Canvas Codex

Context Canvas Codex is a local, evidence-pointer-only task map for long Codex
App and Codex CLI work. Version 0.2.0 keeps the original read-only
`SessionStart` recovery path and adds a persistent stdio MCP server, richer CLI,
dependency maps, bounded metadata search, and pointer-only closeout exports.

The adapter follows the factual-node to evidence-ref invariant from
[`phenomenoner/hermes-agent-harness-plus`](https://github.com/phenomenoner/hermes-agent-harness-plus)
at comparison commit `7d6beb485d658a0342194c0e42edcdb7106ed1cb`. It is a clean Codex
adapter; no upstream source code was copied.

## What is aligned

| Capability | Codex adaptation |
|---|---|
| Start and resume a task canvas | Opaque canvas identity comes only from the trusted Codex `SessionStart` session id. |
| Evidence-backed factual nodes | A terminal factual node requires one or more pointer plus SHA-256 pairs. Evidence contents are never stored or opened. |
| Upsert and dependencies | Nodes support update-in-place, bounded `depends_on` edges, cycle rejection, and an on-demand Mermaid projection. |
| Search | Substring search covers bounded summaries and pointer strings across up to 256 canvases; corrupt canvases are reported and skipped. |
| Closeout | Generates a Codex-ready Markdown closeout containing verified facts, active follow-up, hashes, and Mermaid—never raw evidence. |
| Native tool surface | A dependency-free local MCP server exposes `canvas_start`, `canvas_upsert_node`, `canvas_set_status`, `canvas_read`, `canvas_search`, and `canvas_closeout`. |
| Concurrency | Same-canvas writes use a real cross-process lock on Windows and POSIX plus atomic canonical JSON replacement. |

Hermes autopilot captures selected tool results in-process. This Codex adapter
does not copy that behavior: Codex `PostToolUse` exposes tool inputs and outputs,
and a command hook adds a process launch to every matched call. Checkpoints stay
intentional and pointer-only. The plugin never parses transcripts or captures
tool output.

## State and identity

The default data root is:

```text
%LOCALAPPDATA%\Codex\context-canvas-codex
```

The `SessionStart` hook hashes the exact Codex `session_id` with SHA-256. A
workspace path is metadata only and never determines identity. Legacy v1
canvases are upgraded in memory for read-only restore and are persisted as v2
only on the next intentional mutation.

At startup or clear, the hook reports the opaque ID and a short use hint without
creating data. On resume or compact, it injects at most 4,800 UTF-8 bytes with
the active goal, blockers, decisions/findings, and latest verification. Stored
text and pointers are always labeled untrusted.

## App, MCP, and CLI

Once the plugin is enabled, Codex App and CLI can use the bundled `canvas_*`
MCP tools. For repeated operations, prefer MCP: the server stays alive and
reuses verified local security metadata.

The opaque task identity still comes only from `SessionStart`. Hosts that run
plugin-bundled hooks can use `hooks/hooks.json` directly. If a fresh task does
not receive a Context Canvas ID, install the same audited hook through Codex's
user configuration layer, then verify the installed bytes:

```powershell
python -I scripts/install_context_canvas_hook.py install
python -I scripts/install_context_canvas_hook.py check
```

The installer merges one exact handler into `%USERPROFILE%\.codex\hooks.json`,
preserves peer handlers, keeps a content-addressed backup, and copies the hook
script to a stable path. Run `install` again after each plugin upgrade; it is
idempotent when the bytes and handler already match.

The same store remains available directly:

```powershell
python -I scripts/context_canvas.py init --canvas-id <opaque-id> --goal "Bounded goal" --cwd <absolute-workspace>
python -I scripts/context_canvas.py upsert --canvas-id <opaque-id> --kind plan --status planned --summary "Inspect the boundary"
python -I scripts/context_canvas.py search "boundary" --canvas-id <opaque-id>
python -I scripts/context_canvas.py closeout --canvas-id <opaque-id> --no-write
```

The CLI rejects sensitive-looking content, oversized fields, excessive nodes,
invalid dependency graphs, corrupt JSON, aliases/reparse points, hard links,
non-regular canonical files, weak ACLs, and unprovable locks.

## Performance probe

Run:

```powershell
python -B -I scripts/benchmark_context_canvas.py
```

One Windows/Python 3.13.5 development snapshot with 13 nodes measured persistent
MCP reads at 6.719 ms p50 / 8.569 ms p95, versus 626.397 ms p50 for a fresh
CLI process. These numbers describe that machine and are not a universal
latency promise; the included command is the reproducible contract.

## Activation and retirement

Installation or enablement does not prove that a bundled hook executed. Open a
fresh task and check for its new opaque Context Canvas ID. If it is absent, run
the user-hook installer above. Review and trust the exact `SessionStart`
definition with `/hooks`, run `check`, and repeat the fresh-task proof. The MCP
server is local stdio only and can be disabled separately in Codex plugin
configuration.

Some non-interactive Codex profiles cancel MCP calls that require approval. Do
not treat a started or cancelled tool event as execution evidence. Configure an
explicit plugin-scoped MCP approval policy only after reviewing all six local
tools, and require completed calls plus canonical-store readback for an
acceptance test.

For retirement, run `python -I scripts/install_context_canvas_hook.py uninstall`
to remove only the exact managed user-hook group and recoverably retire its
owned files. Then disable the MCP server and skill before moving the plugin and
data root to a recoverable archive. Do not delete repository WALs or receipts
named by evidence pointers.
