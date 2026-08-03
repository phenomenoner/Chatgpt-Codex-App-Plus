# Sanitized Pitfall Patterns

Use these as recognition and test-design seeds, not as proof that a new incident
has the same cause. Confirm the signature from current primary evidence.

## 1. Principal spelling differs from canonical identity

- **Signature:** Authorization or ownership logic compares a Windows principal
  spelling or alias even though both names resolve to the same SID.
- **Invariant:** Identity decisions use a canonical identifier, not display text.
- **Fail-first seed:** Exercise two valid spellings that resolve to one SID plus
  a genuinely different SID.
- **Repair and guard:** Resolve then compare canonical SIDs; validate under the
  actual service identity before rollout.

## 2. Process preflight observes itself

- **Signature:** A process-table safety scan treats its own CLI invocation or a
  descendant probe as a conflicting live owner.
- **Invariant:** Preflight distinguishes the observer tree from independently
  owned processes.
- **Fail-first seed:** Run the probe with only its own descendants, then with one
  real conflicting owner.
- **Repair and guard:** Exclude the proven observer tree while retaining an exact
  positive conflict fixture.

## 3. Atomic restore exceeds a long-path budget

- **Signature:** A restore path fits, but an added temporary or backup suffix
  exceeds the platform path limit during atomic replacement.
- **Invariant:** Every intermediate name stays within the destination path
  budget and on the required filesystem.
- **Fail-first seed:** Restore at the maximum supported depth with the longest
  generated temporary name.
- **Repair and guard:** Use bounded or hashed sibling names and validate all
  intermediate paths before mutation.

## 4. Captured baseline predates a stronger readiness contract

- **Signature:** A stored baseline or fixture is internally valid but cannot
  satisfy newly required readiness fields or semantics.
- **Invariant:** Baselines declare their contract version and are migrated or
  rejected explicitly.
- **Fail-first seed:** Evaluate both the prior contract and a malformed current
  contract against the stronger checker.
- **Repair and guard:** Version the contract, perform an explicit migration, and
  never reinterpret old success as new readiness.

## 5. Contained recovery has one exact disabled task

- **Signature:** A broad “no scheduled tasks” assertion rejects a deliberately
  retained, exact, disabled recovery task, or a loose assertion accepts extras.
- **Invariant:** Containment permits only the named semantic task definition and
  proves it is disabled.
- **Fail-first seed:** Cover zero tasks, the one exact disabled task, a modified
  action, an enabled copy, and an extra task.
- **Repair and guard:** Validate semantic action, arguments, identity, count, and
  disabled state rather than relying only on serialized export hashes.

## 6. Stale stopped-state snapshot is replayed

- **Signature:** Recovery imports commands, ownership, or state from a snapshot
  captured under an older generation or binary.
- **Invariant:** Compatibility import is stopped-state only, provenance-bound,
  and cannot activate stale process intent.
- **Fail-first seed:** Replay a current stopped snapshot and variants with stale
  generation, binary hash, or owner metadata.
- **Repair and guard:** Validate provenance and freshness; import data without
  launching until the new owner establishes authority.

## 7. Validator is not bound to its report

- **Signature:** A validator passes while reading an older report, different
  candidate, or changed validator implementation.
- **Invariant:** The receipt binds report, validator, candidate, inputs, and run
  generation by stable hashes.
- **Fail-first seed:** Swap or modify each bound artifact independently and
  require a closed failure.
- **Repair and guard:** Emit and verify the complete hash binding in the same
  run before promotion.

## 8. Production receipt is a collection but fixture is scalar

- **Signature:** Production deserialization yields `Object[]` or an empty
  collection while a scalar-only fixture passes.
- **Invariant:** Receipt cardinality and type are explicit for zero, one, and
  many records.
- **Fail-first seed:** Replay zero-, one-, and multi-item shapes from the real
  serialization boundary.
- **Repair and guard:** Normalize intentionally or enforce the collection schema;
  do not let a scalar fixture define production shape.

## 9. Large backup inherits a generic timeout

- **Signature:** A correct backup of a large tree is killed by a timeout selected
  for small commands, leaving ambiguous partial output.
- **Invariant:** Backup completion is size-aware, progress-observable, and
  produces a complete manifest before promotion.
- **Fail-first seed:** Use a deterministic tree above the former timeout class
  and interrupt once to verify partial-output handling.
- **Repair and guard:** Use an operation-specific deadline or progress watchdog;
  require manifest counts, warnings, and integrity checks.

## 10. Fixture state leaks across process generations

- **Signature:** A replay passes or fails depending on markers, ports, locks, or
  files left by an earlier process generation.
- **Invariant:** Each replay owns isolated state and can run repeatedly in any
  order.
- **Fail-first seed:** Run the same scenario twice, reverse scenario order, and
  inject a stale generation marker.
- **Repair and guard:** Allocate generation-specific state, assert cleanup or
  quarantine, and include the generation in receipts.

## 11. Interactive scheduled action opens a console

- **Signature:** A direct `InteractiveToken` or equivalent scheduled action
  launches a visible console despite a hidden-window requirement.
- **Invariant:** Background runtime components remain non-interactive and
  windowless while preserving process ownership and exit reporting.
- **Fail-first seed:** Observe window creation for the direct action and prove
  zero visible windows through the hidden adapter.
- **Repair and guard:** Use platform-appropriate hidden process flags or a
  dedicated adapter; include window enumeration in post-launch verification.

## 12. File existence is mistaken for durable readiness

- **Signature:** A watcher observes that a receipt, PID file, or state file
  exists and immediately reads it, but the writer still holds a sharing lock,
  has not completed the payload, or has not atomically promoted the final
  content.
- **Invariant:** Readiness requires a readable, complete, schema-valid payload
  from the expected generation; directory-entry visibility alone is not a
  commit boundary.
- **Fail-first seed:** Delay the writer after file creation but before close,
  expose a partial payload, and on Windows retain a non-sharing write handle.
- **Repair and guard:** Prefer write-and-atomic-rename when the producer owns the
  protocol. Otherwise retry boundedly until the payload is readable and valid,
  then bind its generation and content; never convert a sharing violation or
  partial parse into success.

## 13. Declared container toolchain differs from the observed compiler

- **Signature:** A versioned build image starts a different compiler because a
  repository toolchain file selects a floating channel, or a login shell
  rewrites `PATH` and hides the image's toolchain launcher.
- **Invariant:** Release evidence records and enforces the compiler actually
  invoked; image tags and configuration text are inputs, not proof of the
  observed toolchain.
- **Fail-first seed:** Run the same version-report command through direct,
  non-login, and login-shell entry paths, then add a repository-level floating
  toolchain override.
- **Repair and guard:** Invoke an exact toolchain selector, print compiler and
  package-manager versions before compilation, fail before the build on any
  mismatch, and retain target/cache paths independently of the container's
  writable layer.

## 14. Test temp root consumes the downstream path budget

- **Signature:** Integration tests create correctly shaped nested state but
  SQLite or another native dependency reports `cannot open` only when `TEMP`
  starts below a long workspace/evidence path; later tests may fail from a
  poisoned shared mutex and obscure the first cause.
- **Invariant:** The entire generated path, including the caller-selected temp
  root, case name, generation suffix, and deepest native file, stays within the
  supported platform budget.
- **Fail-first seed:** Run one long-named stateful case under both a deliberately
  long and a short task-owned temp root, then verify that follow-on poison
  failures are classified as consequences rather than independent defects.
- **Repair and guard:** Select a short, scoped temp root on the intended
  filesystem, calculate the deepest prospective path before the suite, retain
  the first native error separately, and do not weaken product path validation
  merely to accommodate an avoidably long test prefix. When policy requires
  the physical scratch directory to remain below a longer project path, use a
  verified short logical alias to that exact directory and record both the
  logical and physical roots. Re-run at least one exact fail-first case before
  treating a full-suite rerun as release evidence.

## 15. Logical path alias is compared as physical identity

- **Signature:** A Windows test enters through `subst`, a junction, or another
  short alias, while the product deliberately canonicalizes an existing path;
  assertions then compare the alias text with the physical path text and fail
  even though both address the same object.
- **Invariant:** Contracts that promise physical containment or canonical
  provenance compare canonical identity. Contracts that intentionally preserve
  caller spelling compare lexical form. Tests state which contract they need.
- **Fail-first seed:** Run the same path-bearing scenario once through its
  physical root and once through a verified alias, then inspect whether the
  returned path is contractually canonical or caller-preserving.
- **Repair and guard:** Derive expectations from the component's canonical
  plan or receipt when canonical identity is the contract. Do not remove
  security-relevant canonicalization merely to satisfy a lexical assertion,
  and record the alias-to-physical mapping in the test evidence.

## 16. Successful child exit is omitted from the durable log

- **Signature:** A native command completes with exit code zero and its visible
  output looks green, but a pipeline records only child stdout/stderr; the shell
  prints the exit marker after `Tee` has closed, so the durable artifact cannot
  prove command success. A related wrapper failure occurs when an unsupported
  append parameter set prevents the child from running while still creating a
  plausible-looking header file.
- **Invariant:** One immutable command-outcome package binds the exact argv,
  source-before and source-after identity, child exit code, stdout/stderr
  digests, and the candidate or release generation under test.
- **Fail-first seed:** Exercise a successful child, a nonzero child, a wrapper
  that fails before launch, and a pipeline whose exit marker is emitted after
  capture. Require each case to remain distinguishable after the interactive
  terminal is gone.
- **Repair and guard:** Prefer structured process execution that captures the
  native exit code directly and writes metadata only after stdout/stderr close.
  If a text log is required, append the exit marker through the same supported
  capture path and reject missing markers. Never repair release evidence by
  retrospectively adding an unbound success line; rerun the gate or emit a
  separately hash-bound outcome receipt from an authoritative execution host.

## 17. Empty child output is mistaken for a missing argument

- **Signature:** A child process exits successfully with an empty stderr or
  stdout stream, but the wrapper's mandatory string parameter rejects `""`
  before it can persist the stream and report the observed exit code.
- **Invariant:** Empty output is a valid, distinguishable byte sequence. A
  wrapper separately represents missing evidence, unreadable evidence, empty
  evidence, and non-empty evidence.
- **Fail-first seed:** Execute children that produce all four stdout/stderr
  combinations, including two empty streams, and require zero-byte artifacts
  plus the native exit code for every successful launch.
- **Repair and guard:** Explicitly allow empty strings or pass byte arrays at
  the persistence boundary. Test the actual wrapper function, not a substitute,
  and keep the resulting zero-byte file hash-bound with the command outcome.

## 18. Expensive validation reaches a nonexistent schema property

- **Signature:** Candidate and rollback evidence survive a costly inventory or
  hash pass, then the validator fails on a misspelled, renamed, or assumed JSON
  property instead of a domain invariant.
- **Invariant:** Every property path consumed by a release gate belongs to the
  frozen producer schema, and schema compatibility is checked before expensive
  or mutating phases.
- **Fail-first seed:** Traverse all statically addressable verifier property
  paths against representative frozen receipts, then remove or rename one key
  and require an immediate schema-contract failure.
- **Repair and guard:** Give receipts explicit schemas, validate required keys
  and types early, and mechanically compare verifier paths with representative
  artifacts. Do not reuse a failed transaction after repairing verifier code;
  freeze new script hashes and create a new transaction.

## 19. A requested failpoint is satisfied by an earlier unrelated failure

- **Signature:** A failpoint run exits nonzero and recovers safely, so the
  harness reports the requested failpoint as covered even though execution
  failed before reaching that location.
- **Invariant:** Failpoint evidence proves both containment and exact reach:
  the requested marker is set only at the intended boundary, and the primary
  error exactly identifies that intentional failure.
- **Fail-first seed:** Cause an earlier setup or promotion error while requesting
  a later failpoint. Require it to be classified as an ordinary failed-contained
  run, not as expected failpoint coverage.
- **Repair and guard:** Persist `failpoint`, `failpointReached`, reach time, and
  exact primary error in runner and containment receipts. The invoker accepts a
  failpoint only when all fields agree with the request; nonzero exit plus safe
  recovery alone is insufficient.

## 20. A transaction-bound predecessor is rejected as foreign

- **Signature:** A new scheduler plan changes an ownership or action digest, so
  its conservative installer refuses to overwrite the disabled predecessor
  even though the release transaction explicitly froze that exact prior task
  and retained its rollback image.
- **Invariant:** Replacement authority comes from the frozen transition
  transaction, not from either generation accepting the other's ownership
  digest. Only the exact disabled predecessor may be removed, immediately
  before installing its exact successor.
- **Fail-first seed:** Freeze a predecessor task, change one legitimate action
  field so the new digest differs, and require the ordinary installer to reject
  direct overwrite. Then exercise the transaction wrapper with a drifted XML,
  an enabled task, a live process, and an incomplete rollback package; every
  case must fail before unregister.
- **Repair and guard:** Run authorized preflight, export and hash the current
  task twice immediately, require both hashes to equal the transaction baseline,
  prove zero deployment processes and an identical rollback copy, unregister
  that exact task object, and install the successor disabled. Preserve both
  readbacks in the cutover receipt and use a real post-install failpoint to
  prove rollback restores the predecessor.

## 21. Recovery reuses authorization for a different action

- **Signature:** A cutover authorized only for `Restart` invokes a generated
  `Stop` control during failure containment. The control correctly rejects the
  token, turning an otherwise recoverable intentional failpoint into a
  catastrophic or auxiliary-error result.
- **Invariant:** Authorization action is exact and is never silently widened,
  including on recovery paths. Containment must remain possible without
  impersonating another authorized action.
- **Fail-first seed:** Inject a valid Restart-only token, enter recovery before
  and after runtime start, and require any Stop-only control to reject it.
  Verify that the approved containment path still reaches zero processes and
  restores the frozen disabled baseline.
- **Repair and guard:** Use persistent holds, disable or stop the scheduler
  authority, wait boundedly for graceful exit, and apply a scoped process-tree
  fallback before exact rollback. If a true Stop operation is required, obtain
  and receipt a separate Stop authorization; never reuse or relabel Restart.

## 22. A broad action grant is checked through an exact-action status gate

- **Signature:** The authorization model says a broad action such as `Restart`
  may semantically cover `Start`, but the generated control script validates
  through a status endpoint that deliberately requires the token's recorded
  action to equal `Start`. The broader token is valid elsewhere yet the real
  start control fails before launch.
- **Invariant:** The grant presented at each executable control boundary
  satisfies that boundary's actual validator semantics, including whether it
  accepts delegated scope or requires exact action identity.
- **Fail-first seed:** Present a Restart token to both the general
  scope-aware validator and the exact Start status endpoint. Require the first
  to accept delegated scope and the second to reject it, then drive the real
  generated Start script.
- **Repair and guard:** Inventory the whole transaction's action boundaries
  before review. Obtain distinct exact grants where exact status is used,
  hand them off only through separate process-environment names, switch the
  standard control variable only for the bounded child invocation, clear both
  afterward, scan output for both secrets, and receipt both action identities
  without persisting either raw token.

## 23. Distinct workspace roles collapse inside the verifier

- **Signature:** The producer correctly emits separate agent workspace and
  runtime-working-directory paths, but a post-cutover verifier compares both
  fields or both flags with the runtime path. A healthy promoted plan is
  rejected, or a loose substring check accepts the wrong flag/value pairing.
- **Invariant:** Every path role is named and verified independently. The
  `--workspace` value identifies the agent workspace, while
  `--runtime-workspace` and process working directory identify the runtime
  execution root; one path appearing elsewhere in a command line cannot satisfy
  another flag's contract.
- **Fail-first seed:** Build a plan whose workspace and runtime workspace are
  deliberately distinct. Require the plan, dry-run inventory, keeper, and each
  owner readback to preserve both exact pairs. Add duplicate flags, swapped
  values, and a command where the expected path appears only under the other
  flag; all must fail.
- **Repair and guard:** Centralize the two derived paths, validate structured
  argument vectors with exactly one occurrence per flag, and parse live command
  lines into exact flag/value pairs rather than independent substring hits.
  Report each plan sub-contract separately so one early failure does not hide
  the rest of the static mismatch set.

## 24. Child evidence is recorded only after demanding success

- **Signature:** A child runner writes a detailed failure receipt, but its
  caller asserts the expected success outcome before copying the child exit,
  receipt path, hash, status, or validation result into the durable parent
  receipt. A lower wrapper may also throw on timeout, nonzero exit, missing
  report, or malformed JSON before closing output capture and writing any
  observation. Recovery succeeds, yet the parent record contains only a generic
  mismatch and investigators must rediscover the child artifact.
- **Invariant:** Observed child evidence is durable before outcome
  classification. Recording an exit or receipt is not accepting it as success;
  policy validation and recovery happen afterward. Secret-bearing output is
  represented by a redacted exposure marker and lengths, never persisted raw.
- **Fail-first seed:** Return a valid hash-bound failed-contained child receipt
  during a normal-success request, then replay timeout, nonzero, missing-report,
  malformed-report, and token-exposure variants. Require a pre-classification
  observation to retain the safe child exit, timeout, path, hash, parse state,
  reach marker, and error count before rejection or emergency containment.
- **Repair and guard:** Initialize stable nullable receipt fields, capture and
  hash safe child output immediately after process exit or bounded kill, probe
  and hash any receipt even on timeout, persist each post-validation or
  canonical observation before its assertion, then classify the outcome.
  Continue to scan for secrets and reject unbound or malformed receipts;
  observability must not weaken the release gate.

## 25. Source-text inspection is presented as behavioral replay

- **Signature:** A fixture reports T3 coverage because `Contains`, `IndexOf`, an
  AST query, or a line-order check found the intended helper, assignment, or
  assertion in source. The fixture never executes the affected path and accepts
  duplicate, swapped, cross-flag, timeout, nonzero, or malformed inputs in real
  use.
- **Invariant:** Behavioral evidence drives the production helper or the exact
  shared contract through observed inputs and asserts outcomes. Source
  inspection may prove mechanism presence at T0, but it cannot prove runtime
  ordering, rejection semantics, or recovery behavior.
- **Fail-first seed:** Keep the expected strings in source while deliberately
  breaking the helper's return value or moving durable evidence after the
  assertion. Require the structural check to stay green and the behavioral
  replay to fail. For a verifier incident, feed the hash-bound recorded receipt
  plus duplicate, swapped, and cross-flag mutations through the same contract
  function used by the live path.
- **Repair and guard:** Label structural checks T0, add an offline executable
  probe with no live authority, bind it to the incident receipt and current
  script hashes, and require negative as well as positive outcomes. Keep the
  live/soak gap explicit after the replay passes.
