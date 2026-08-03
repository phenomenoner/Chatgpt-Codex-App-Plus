# Read-only troubleshooting

1. Capture target, product version, health, readiness, and structured
   capabilities. For memory v2, record `memoryContract`, `deliveryModel`,
   `wakeupAckMode`, `ackCursorSource`, and `lifecycleProjection`.
2. Distinguish connection failure, authentication failure, scope denial,
   version mismatch, cursor invalidity, cursor refresh requirement, and
   advertised degraded state. Preserve safe `status`, `code`, `message`,
   `retryable`, bounded `details`, and `traceId` fields when available.
3. When `operationalDiagnostics` is advertised and the principal has `hub.admin`,
   capture payload-free store counts, source/index revisions, `lagRecords`, queue
   depth, quarantine, retrieval model identity, state bytes, product version, and
   `generatedAt`. Concurrent requests can receive the last completed snapshot
   while one refresh is running; an unchanged timestamp is cached evidence, not
   proof that current state was freshly collected. Source/index fields describe
   the last completed convergence snapshot and may remain unchanged during an
   active filesystem scan; use the final stopped-state audit when exact terminal
   queue and lag proof is required.
4. Sanitize tokens, note bodies, private paths, and real user data.
5. State whether evidence is contract/static, integration, scenario, or soak altitude.

Do not repair, reindex, rotate credentials, migrate, restore, or delete state as
part of diagnosis. If a requested diagnostic endpoint is absent, report the
capability gap instead of guessing from local files.

If the server advertises v1 during the 0.3.x compatibility window, report that
inbox entries are per-reason rows. Do not combine them into v2 logical
identities during diagnosis. If ACK returns `CURSOR_REFRESH_REQUIRED`, the
historical cursor lacks proven inbox purpose and would advance state; fetch a
new inbox page rather than retrying or synthesizing a cursor.

A wakeup response must not contain a cursor. If one appears, stop the
write-bearing workflow and report a contract mismatch. Successful wakeup,
resource refresh, or context insertion never proves that unread state changed.
Lifecycle facts can prove storage, indexing, queueing, recorded ACK, or links;
they cannot prove comprehension or execution.

For a single-hub endurance result, preserve the operation-specific failure code
and the final sanitized audit as separate facts. A code such as
`operation-timeout:search` identifies the surface whose connection retry window
expired; it does not prove process exit, state loss, or authorization leakage.
Confirm those claims from the child-process status and final audit. Raw child
stdout/stderr is private operator evidence and must not be copied into a public
report.

If three consecutive endurance samples retain the same diagnostic `generatedAt`,
report `diagnostics-stale`. Do not reinterpret prompt cached responses as healthy
refresh progress. The final queue/quarantine/outbox audit is taken offline after
the child stops and remains separate from the last online diagnostic snapshot.

If an approved offline operation reports an active state lease, stop. Identify the
running hub process and arrange an explicit maintenance window; never bypass or remove
the lock file. A backup public-target refusal means sensitive state was detected, not
a scanner malfunction. A migration parity failure leaves the active provider unchanged.

Before opening upgraded state, identify the operations schema version. An older
binary must never open schema v4. Before the first v4 write, rollback requires
restoring a verified pre-upgrade v3 backup; after any v4 write, recovery is
roll-forward with a compatible binary.
