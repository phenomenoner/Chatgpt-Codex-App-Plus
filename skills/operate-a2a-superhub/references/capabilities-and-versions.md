# Capabilities and versions

The machine authority is `compatibility.json`; do not infer features from a
planning or marketing label.

The current opt-in memory, hybrid-retrieval, artifact-text, and agent-protocol contract pins:

- product baseline: 0.3.0;
- memory API: `memory.v2` for current agents, with `memory.v1` per-reason
  delivery views dual-written and served through version 0.3.x;
- note schema: `a2a-superhub.memory.note.v1`, implemented for Markdown notes;
- A2A `Part` mapping: `text`, `raw`, `url`, and `data` oneofs are implemented;
  legacy `kind` input requires an explicit compatibility flag, while the complete
  normative A2A 1.0 JSON-RPC binding is still not implemented;
- artifact API: `artifacts.v1` with base64 compatibility, raw binary, and resumable
  chunk transports; the advertised `maxArtifactBytes` is a guardrail, not a capacity claim;
- derivation: default off, with bounded local PDF text extraction and an optional
  Tesseract executable for image OCR; all output is `untrusted-data`;
- operations API: `operations.v1`, with payload-free admin diagnostics plus local
  authoritative backup/clean restore, recoverable retention, and parity-gated
  Qdrant provider activation/rollback;
- MCP negotiation: protocol `2025-11-25`, implemented by the stateless stdio
  sidecar over memory v2 with ten tools and `memory://note/{id}` plus
  `memory://wakeup/{agent}` resources;
- legacy JSON-RPC coordination: implemented and separately identified.

For memory v2, require `memoryContract: v2`, `deliveryModel: logical.v2`,
`wakeupAckMode: none`, `ackCursorSource: inbox-only`, and
`lifecycleProjection: true` before using those behaviors. One inbox item is one
logical delivery for a note and recipient, with the complete bounded `reasons`
array. V1 exposes one row per reason and is not interchangeable with that
identity model.

Wakeup is always a bounded preview and never carries an acknowledgeable cursor.
Only an inbox response issues ACK authority, bound to the exact page membership,
principal, and consumer. Acknowledge only after the intended consumer accepts
that page. A migrated historical cursor that lacks recorded inbox purpose can
be a no-op only when it does not advance state; otherwise refetch after
`CURSOR_REFRESH_REQUIRED`.

V2 writes require relation targets in the `agent:`, `note:`, `project:`,
`task:`, `event:`, or `artifact:` namespace. Note reads can request
`includeLifecycle`; the result is an authorized set of stored, indexed, queued,
acknowledged, and linked-reference facts, not a claim of comprehension or
execution. Typed HTTP errors preserve safe `code`, `message`, `retryable`,
bounded validation `details`, and `traceId` fields through the client and MCP.

Treat `memoryFoundation`, `memorySharing`, `timelineGraph`, `safeWakeup`,
`adapter`, `runtimeWatcher`, and `taskLog` as independent granular capabilities.
Treat `memorySearch`, the retrieval mode/version, and `fallbackReason` as
independent search signals. Hybrid means dense+sparse RRF with recency and
authorization pushdown; keyword is the compatible fallback.
`memoryFull` remains false. Delivery, task-log, and watcher side effects default off;
the running instance must explicitly advertise each enabled feature.

Treat `artifactDerivation`, `artifactUploads`, `maxArtifactBytes`, and
`derivedTextTrust` independently. Derivation additionally requires
`memoryFoundation`, `artifact.read`, and `memory.write`; shared/direct derived
notes require the corresponding share authority. Image media support does not
mean the Tesseract executable is installed, so provider availability must be
reported rather than inferred.

Treat `operationalDiagnostics`, `offlineAuthoritativeBackup`, and
`recoverableRetention` independently. HTTP advertises and serves diagnostics only;
state mutations remain local CLI operations and require the hub runtime lease to be free.
An activated Qdrant provider is consumed only with `--search-mode configured`.

MCP resource subscription is independently negotiated. Use resource-updated
notifications when `resources.subscribe` is true. Otherwise poll the same
authorized resource; do not infer subscription support from the protocol version.

Compare the normalized contract fingerprint before operating. On mismatch,
perform read-only discovery, report the differing product/protocol/schema fields,
and stop unless the server advertises a safe compatible fallback.

The current response also returns the authenticated principal subject, kind,
token ID, and sorted scopes. This metadata is not authorization by itself, but
the adapter must match it to its intended principal and the server remains the
final authority. A missing current capabilities route may downgrade to legacy
read-only discovery. Authentication, connection, and transient HTTP failures
must never be relabeled as legacy compatibility.

Operations schema v4 stores logical deliveries and exact inbox-page ACK
membership. Before its first write, rollback requires restoring a verified
pre-upgrade v3 backup before starting the previous binary. After any v4 write,
recovery is roll-forward with a compatible binary. Dual-written v1 rows do not
make a v4 state directory readable by an older binary.
