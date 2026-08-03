#!/usr/bin/env python3
"""Validate a redacted incident-to-regression record.

This validates structure and claim gating only. It does not attest evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TIERS = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4}
STATES = {
    "draft": 0,
    "reproduced": 1,
    "repair-verified": 2,
    "cutover-ready": 3,
    "live-observed": 4,
}
FAIL_FIRST_STATES = {"not-run", "not-reproduced", "observed"}
BLAST_RADIUS = {"local", "component", "cross-cutting", "live-external"}
REVIEW_STATES = {"not-required", "not-run", "pass", "fail"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_TEXT = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key material"),
    (re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+"), "bearer credential"),
    (re.compile(r"(?i)\b(client_secret|access_token|refresh_token|password)\s*[=:]\s*[^\s,}]+"), "credential-like value"),
    (re.compile(r"(?i)https://(?:discord(?:app)?\.com/api/)?webhooks/\d+/[A-Za-z0-9._-]+"), "webhook credential"),
    (re.compile(r"(?i)[A-Z]:\\Users\\(?!<user>\\)[^\\\s]+\\"), "unredacted Windows user path"),
    (re.compile(r"/(?:home|Users)/(?!<user>/)[^/\s]+/"), "unredacted user home path"),
)


def template() -> dict[str, Any]:
    return {
        "schemaVersion": "incident-to-regression/v1",
        "incidentId": "INCIDENT-REDACTED",
        "signature": {
            "component": "component-name",
            "trigger": "stable triggering condition",
            "observedFailure": "observable failure without local identity",
            "expectedInvariant": "contract that should have held",
            "environmentDimensions": ["os-family", "runtime-mode"],
            "excludedVolatileFields": ["timestamp", "pid", "absolute-path"],
        },
        "affectedInvariants": ["INV-EXAMPLE"],
        "blastRadius": {
            "class": "component",
            "affectedConsumers": ["redacted-consumer-class"],
            "rationale": "Why the failure is contained to this radius.",
        },
        "failFirstArtifact": {
            "pointer": "evidence://incident/fail-first",
            "command": None,
            "expectedFailure": "Exact semantic failure expected before repair.",
            "status": "not-run",
            "beforeRepairObserved": False,
            "actualPreRepairResult": None,
            "evidenceId": None,
            "fixtureProvenance": {
                "pointer": "fixture://incident/fail-first-v1",
                "sha256": None,
                "redacted": True,
            },
        },
        "repairPattern": {
            "summary": "Reusable repair mechanism or proposed mechanism.",
            "applied": False,
            "rollback": "How to reverse only the repair.",
        },
        "verification": {
            "requiredTier": "T3",
            "achievedTier": "T0",
            "evidenceIds": [],
            "independentReview": {
                "status": "not-run",
                "evidenceId": None,
            },
        },
        "cutoverGuard": {
            "preconditions": ["Fresh candidate hash and stopped-state readback."],
            "stopConditions": ["Any ownership or routing mismatch."],
            "externalEffectsConstraints": [
                "Do not contact a provider unless the scenario explicitly authorizes it."
            ],
            "rollbackPlan": "Materialize and verify a complete rollback generation.",
            "rollbackReady": False,
        },
        "replayFixture": {
            "pointer": "fixture://incident/replay-v1",
            "deterministicInputs": ["sanitized-input"],
            "redactions": ["identity", "credential", "absolute-path"],
            "provenance": {
                "sourcePointer": "evidence://incident/redacted-source",
                "sourceSha256": None,
            },
        },
        "evidencePointers": [],
        "blockingGaps": ["Fail-first replay has not run."],
        "limitations": ["Live behavior has not been observed."],
        "status": "draft",
    }


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_object(parent: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key}: expected object")
        return {}
    return value


def require_nonempty(obj: dict[str, Any], key: str, path: str, errors: list[str]) -> None:
    if not nonempty_string(obj.get(key)):
        errors.append(f"{path}.{key}: expected non-empty string")


def require_string_list(obj: dict[str, Any], key: str, path: str, errors: list[str], *, nonempty: bool = False) -> list[str]:
    value = obj.get(key)
    if not isinstance(value, list) or any(not nonempty_string(item) for item in value):
        errors.append(f"{path}.{key}: expected a list of non-empty strings")
        return []
    if nonempty and not value:
        errors.append(f"{path}.{key}: must not be empty")
    return value


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def scan_sensitive_text(document: dict[str, Any], errors: list[str]) -> None:
    findings: set[str] = set()
    for text in iter_strings(document):
        for pattern, label in SENSITIVE_TEXT:
            if pattern.search(text):
                findings.add(label)
    for label in sorted(findings):
        errors.append(f"record contains {label}; replace it with a redacted pointer")


def validate(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["root: expected object"]

    if document.get("schemaVersion") != "incident-to-regression/v1":
        errors.append("schemaVersion: expected incident-to-regression/v1")
    require_nonempty(document, "incidentId", "root", errors)

    signature = require_object(document, "signature", errors)
    for key in ("component", "trigger", "observedFailure", "expectedInvariant"):
        require_nonempty(signature, key, "signature", errors)
    require_string_list(signature, "environmentDimensions", "signature", errors, nonempty=True)
    require_string_list(signature, "excludedVolatileFields", "signature", errors)

    require_string_list(document, "affectedInvariants", "root", errors, nonempty=True)

    blast = require_object(document, "blastRadius", errors)
    if blast.get("class") not in BLAST_RADIUS:
        errors.append(f"blastRadius.class: expected one of {sorted(BLAST_RADIUS)}")
    require_string_list(blast, "affectedConsumers", "blastRadius", errors, nonempty=True)
    require_nonempty(blast, "rationale", "blastRadius", errors)

    fail_first = require_object(document, "failFirstArtifact", errors)
    for key in ("pointer", "expectedFailure"):
        require_nonempty(fail_first, key, "failFirstArtifact", errors)
    if fail_first.get("status") not in FAIL_FIRST_STATES:
        errors.append(f"failFirstArtifact.status: expected one of {sorted(FAIL_FIRST_STATES)}")
    if not isinstance(fail_first.get("beforeRepairObserved"), bool):
        errors.append("failFirstArtifact.beforeRepairObserved: expected boolean")
    if fail_first.get("beforeRepairObserved") and fail_first.get("status") != "observed":
        errors.append("failFirstArtifact: beforeRepairObserved=true requires status=observed")
    fail_first_command = fail_first.get("command")
    if fail_first_command is not None and not nonempty_string(fail_first_command):
        errors.append("failFirstArtifact.command: expected non-empty string or null")
    actual_pre_repair = fail_first.get("actualPreRepairResult")
    if actual_pre_repair is not None and not nonempty_string(actual_pre_repair):
        errors.append("failFirstArtifact.actualPreRepairResult: expected non-empty string or null")
    fail_first_evidence_id = fail_first.get("evidenceId")
    if fail_first_evidence_id is not None and not nonempty_string(fail_first_evidence_id):
        errors.append("failFirstArtifact.evidenceId: expected non-empty string or null")
    fixture_provenance = require_object(fail_first, "fixtureProvenance", errors)
    require_nonempty(fixture_provenance, "pointer", "failFirstArtifact.fixtureProvenance", errors)
    fixture_digest = fixture_provenance.get("sha256")
    if fixture_digest is not None and (
        not isinstance(fixture_digest, str) or not SHA256_RE.fullmatch(fixture_digest)
    ):
        errors.append(
            "failFirstArtifact.fixtureProvenance.sha256: expected 64 lowercase hex characters or null"
        )
    if fixture_provenance.get("redacted") is not True:
        errors.append("failFirstArtifact.fixtureProvenance.redacted: must be true")
    if fail_first.get("status") == "observed":
        if not nonempty_string(fail_first_command):
            errors.append("failFirstArtifact: observed status requires command")
        if not nonempty_string(actual_pre_repair):
            errors.append("failFirstArtifact: observed status requires actualPreRepairResult")
        if not nonempty_string(fail_first_evidence_id):
            errors.append("failFirstArtifact: observed status requires evidenceId")
        if not isinstance(fixture_digest, str) or not SHA256_RE.fullmatch(fixture_digest):
            errors.append("failFirstArtifact: observed status requires hash-bound fixture provenance")

    repair = require_object(document, "repairPattern", errors)
    require_nonempty(repair, "summary", "repairPattern", errors)
    require_nonempty(repair, "rollback", "repairPattern", errors)
    if not isinstance(repair.get("applied"), bool):
        errors.append("repairPattern.applied: expected boolean")

    verification = require_object(document, "verification", errors)
    required_tier = verification.get("requiredTier")
    achieved_tier = verification.get("achievedTier")
    if required_tier not in TIERS:
        errors.append(f"verification.requiredTier: expected one of {sorted(TIERS)}")
    if achieved_tier not in TIERS:
        errors.append(f"verification.achievedTier: expected one of {sorted(TIERS)}")
    evidence_ids = require_string_list(verification, "evidenceIds", "verification", errors)
    review = require_object(verification, "independentReview", errors)
    if review.get("status") not in REVIEW_STATES:
        errors.append(f"verification.independentReview.status: expected one of {sorted(REVIEW_STATES)}")
    review_evidence_id = review.get("evidenceId")
    if review_evidence_id is not None and not nonempty_string(review_evidence_id):
        errors.append("verification.independentReview.evidenceId: expected string or null")
    if review.get("status") == "pass" and not nonempty_string(review_evidence_id):
        errors.append("verification.independentReview: pass requires evidenceId")

    cutover = require_object(document, "cutoverGuard", errors)
    require_string_list(cutover, "preconditions", "cutoverGuard", errors, nonempty=True)
    require_string_list(cutover, "stopConditions", "cutoverGuard", errors, nonempty=True)
    require_string_list(
        cutover,
        "externalEffectsConstraints",
        "cutoverGuard",
        errors,
        nonempty=True,
    )
    require_nonempty(cutover, "rollbackPlan", "cutoverGuard", errors)
    if not isinstance(cutover.get("rollbackReady"), bool):
        errors.append("cutoverGuard.rollbackReady: expected boolean")

    replay = require_object(document, "replayFixture", errors)
    require_nonempty(replay, "pointer", "replayFixture", errors)
    require_string_list(replay, "deterministicInputs", "replayFixture", errors, nonempty=True)
    require_string_list(replay, "redactions", "replayFixture", errors, nonempty=True)
    replay_provenance = require_object(replay, "provenance", errors)
    require_nonempty(replay_provenance, "sourcePointer", "replayFixture.provenance", errors)
    replay_digest = replay_provenance.get("sourceSha256")
    if replay_digest is not None and (
        not isinstance(replay_digest, str) or not SHA256_RE.fullmatch(replay_digest)
    ):
        errors.append(
            "replayFixture.provenance.sourceSha256: expected 64 lowercase hex characters or null"
        )

    pointers = document.get("evidencePointers")
    pointer_ids: set[str] = set()
    if not isinstance(pointers, list):
        errors.append("evidencePointers: expected list")
        pointers = []
    for index, item in enumerate(pointers):
        path = f"evidencePointers[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: expected object")
            continue
        for key in ("id", "kind", "purpose", "pointer"):
            require_nonempty(item, key, path, errors)
        evidence_id = item.get("id")
        if nonempty_string(evidence_id):
            if evidence_id in pointer_ids:
                errors.append(f"{path}.id: duplicate evidence id {evidence_id!r}")
            pointer_ids.add(evidence_id)
        if item.get("redacted") is not True:
            errors.append(f"{path}.redacted: must be true")
        digest = item.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not SHA256_RE.fullmatch(digest)):
            errors.append(f"{path}.sha256: expected 64 lowercase hex characters or null")
        if "embeddedContent" in item:
            errors.append(f"{path}.embeddedContent: embed no raw evidence; use pointer only")

    for evidence_id in evidence_ids:
        if evidence_id not in pointer_ids:
            errors.append(f"verification.evidenceIds: unknown evidence id {evidence_id!r}")
    if nonempty_string(review_evidence_id) and review_evidence_id not in pointer_ids:
        errors.append(f"verification.independentReview.evidenceId: unknown evidence id {review_evidence_id!r}")
    if nonempty_string(fail_first_evidence_id):
        if fail_first_evidence_id not in pointer_ids:
            errors.append(
                f"failFirstArtifact.evidenceId: unknown evidence id {fail_first_evidence_id!r}"
            )
        else:
            matching_pointer = next(
                (
                    item
                    for item in pointers
                    if isinstance(item, dict) and item.get("id") == fail_first_evidence_id
                ),
                None,
            )
            if matching_pointer is not None and not isinstance(matching_pointer.get("sha256"), str):
                errors.append("failFirstArtifact.evidenceId: referenced evidence must include sha256")

    blocking_gaps = require_string_list(document, "blockingGaps", "root", errors)
    require_string_list(document, "limitations", "root", errors)
    status = document.get("status")
    if status not in STATES:
        errors.append(f"status: expected one of {sorted(STATES)}")
        status_rank = -1
    else:
        status_rank = STATES[status]

    if status_rank >= STATES["reproduced"]:
        if fail_first.get("status") != "observed" or fail_first.get("beforeRepairObserved") is not True:
            errors.append(f"status={status}: requires an observed fail-first failure")
    if status_rank >= STATES["repair-verified"]:
        if repair.get("applied") is not True:
            errors.append(f"status={status}: requires repairPattern.applied=true")
        if required_tier in TIERS and achieved_tier in TIERS and TIERS[achieved_tier] < TIERS[required_tier]:
            errors.append(f"status={status}: achievedTier is below requiredTier")
        if not evidence_ids:
            errors.append(f"status={status}: requires verification evidenceIds")
        if not isinstance(replay_digest, str) or not SHA256_RE.fullmatch(replay_digest):
            errors.append(f"status={status}: requires hash-bound replay fixture provenance")
    if status_rank >= STATES["cutover-ready"]:
        if blocking_gaps:
            errors.append(f"status={status}: blockingGaps must be empty")
        if cutover.get("rollbackReady") is not True:
            errors.append(f"status={status}: requires cutoverGuard.rollbackReady=true")
        if review.get("status") != "pass":
            errors.append(f"status={status}: requires independentReview.status=pass")
    if status_rank >= STATES["live-observed"]:
        if achieved_tier != "T4":
            errors.append("status=live-observed: requires achievedTier=T4")
        if not any(isinstance(item, dict) and item.get("kind") == "post-readback" for item in pointers):
            errors.append("status=live-observed: requires a post-readback evidence pointer")

    if blast.get("class") in {"cross-cutting", "live-external"} and required_tier in TIERS and TIERS[required_tier] < TIERS["T3"]:
        errors.append("cross-cutting or live-external blast radius requires at least T3")

    scan_sensitive_text(document, errors)
    return errors


def load_document(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", nargs="?", help="JSON record path, or - for stdin")
    parser.add_argument("--template", action="store_true", help="print a valid draft template")
    args = parser.parse_args()

    if args.template:
        if args.record:
            parser.error("--template does not accept a record")
        json.dump(template(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    if not args.record:
        parser.error("record is required unless --template is used")

    try:
        document = load_document(args.record)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to read JSON: {exc}", file=sys.stderr)
        return 2

    errors = validate(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("VALID: incident-to-regression/v1 record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
