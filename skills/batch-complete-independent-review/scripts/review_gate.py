#!/usr/bin/env python3
"""Bind and validate batch-complete independent review artifacts.

The validator is intentionally provider-neutral and uses only the Python standard
library.  It validates the deterministic gate invariants that should not depend
on reviewer prose or model judgment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "batch-complete-independent-review/v1"
WAVE_SCHEMA_VERSION = "batch-review-wave.v1"
MATRIX_SCHEMA_VERSION = "batch-review-coverage-matrix.v1"
REPORT_SCHEMA_VERSION = "batch-independent-review-report.v1"

TIERS = {"T0", "T1", "T2", "T3", "T4"}
TIER_ORDER = {"NONE": -1, "T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4}
COVERAGE_STATUSES = {
    "COVERED_NO_FINDING",
    "FINDING",
    "NOT_APPLICABLE",
    "EVIDENCE_GAP",
    "UNVISITED",
}
CLOSURE_SUPPORT_STATUSES = {
    "SUPPORTED",
    "WRONG_TIER",
    "UNSUPPORTED",
    "NOT_APPLICABLE",
    "OPEN",
}
ADVERSARIAL_DIMENSIONS = {
    "SIBLING_CALL_SITES",
    "LIFECYCLE_PHASES",
    "CURRENT_LIVE_THIRD_STATE",
    "EVIDENCE_ALTITUDE",
    "REPAIR_POSTCONDITION_COMPLETENESS",
}
ACTUAL_VERDICTS = {"PASS", "BLOCKED", "INCOMPLETE"}
FINDING_SET_STATUSES = {
    "BATCH_COMPLETE",
    "BUDGET_EXHAUSTED",
    "HASH_DRIFT",
    "ACCESS_BLOCKED",
    "SCOPE_ABORTED",
    "OVERFLOW_NEEDS_ENUMERATION",
}
COUNTERFACTUAL_VERDICTS = {
    "NOT_NEEDED",
    "PASS_UNDER_ASSUMPTIONS",
    "UNRESOLVED",
}
STOP_REASONS = {
    "COVERAGE_COMPLETE",
    "HASH_DRIFT",
    "ACCESS_FAILURE",
    "SCOPE_VIOLATION",
    "BUDGET_REACHED",
    "SAFETY_NOTIFICATION",
    "FINDING_OVERFLOW",
}


class GateInputError(ValueError):
    """Raised when an input cannot be bound or meaningfully validated."""


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateInputError(f"{label} does not exist: {path}") from exc
    except UnicodeDecodeError as exc:
        raise GateInputError(f"{label} is not valid UTF-8: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateInputError(
            f"{label} is not valid JSON at line {exc.lineno}, column {exc.colno}: {path}"
        ) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": str(resolved),
        "length": resolved.stat().st_size,
        "sha256": _sha256(resolved),
    }


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_evidence_list(
    value: Any, prefix: str, errors: list[str], *, require: bool = False
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{prefix} must be an array.")
        return []
    if require and not value:
        errors.append(f"{prefix} must contain supporting evidence.")
    tiers: list[str] = []
    for index, evidence in enumerate(value):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(evidence, dict):
            errors.append(f"{item_prefix} must be an object.")
            continue
        if evidence.get("kind") not in {
            "SOURCE",
            "CONTRACT",
            "TEST",
            "RECEIPT",
            "MANIFEST",
        }:
            errors.append(f"{item_prefix}.kind is invalid.")
        for field in ("path", "locator", "claim"):
            if not _is_nonempty_string(evidence.get(field)):
                errors.append(f"{item_prefix}.{field} must be a non-empty string.")
        tier = evidence.get("tier")
        if tier not in TIERS:
            errors.append(f"{item_prefix}.tier must be one of {sorted(TIERS)}.")
        else:
            tiers.append(tier)
        sha = evidence.get("sha256")
        if sha is not None and (not isinstance(sha, str) or len(sha) != 64):
            errors.append(f"{item_prefix}.sha256 must be a 64-character SHA-256.")
    return tiers


def _duplicate_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _validate_matrix(matrix: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(matrix, dict):
        return ["Coverage matrix must be a JSON object."]
    if matrix.get("schemaVersion") != MATRIX_SCHEMA_VERSION:
        errors.append(
            f"Coverage matrix schemaVersion must be {MATRIX_SCHEMA_VERSION!r}."
        )
    cells = matrix.get("cells")
    if not isinstance(cells, list) or not cells:
        errors.append("Coverage matrix cells must be a non-empty array.")
        return errors

    cell_ids: list[str] = []
    for index, cell in enumerate(cells):
        prefix = f"Coverage matrix cells[{index}]"
        if not isinstance(cell, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        for field in ("cellId", "contractId", "lifecyclePhase", "variant"):
            if not _is_nonempty_string(cell.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string.")
        if _is_nonempty_string(cell.get("cellId")):
            cell_ids.append(cell["cellId"])
        if not isinstance(cell.get("required"), bool):
            errors.append(f"{prefix}.required must be a boolean.")
        if cell.get("requiredTier") not in TIERS:
            errors.append(f"{prefix}.requiredTier must be one of {sorted(TIERS)}.")

    for duplicate in _duplicate_values(cell_ids):
        errors.append(f"Coverage matrix contains duplicate cellId {duplicate!r}.")
    return errors


def _bind(args: argparse.Namespace) -> int:
    inputs = {
        "candidateManifest": Path(args.candidate_manifest),
        "evidenceIndex": Path(args.evidence_index),
        "reviewPlan": Path(args.review_plan),
        "coverageMatrix": Path(args.coverage_matrix),
    }
    parsed = {
        name: _load_json(path, name) for name, path in inputs.items()
    }
    for name in ("candidateManifest", "evidenceIndex", "reviewPlan"):
        if not isinstance(parsed[name], dict):
            raise GateInputError(f"{name} must be a JSON object.")

    matrix_errors = _validate_matrix(parsed["coverageMatrix"])
    if matrix_errors:
        raise GateInputError(" ".join(matrix_errors))

    artifacts = {name: _artifact(path) for name, path in inputs.items()}
    binding_material = {
        "protocolVersion": PROTOCOL_VERSION,
        "candidateManifestSha256": artifacts["candidateManifest"]["sha256"],
        "evidenceIndexSha256": artifacts["evidenceIndex"]["sha256"],
        "reviewPlanSha256": artifacts["reviewPlan"]["sha256"],
        "coverageMatrixSha256": artifacts["coverageMatrix"]["sha256"],
    }
    wave = {
        "schemaVersion": WAVE_SCHEMA_VERSION,
        "protocolVersion": PROTOCOL_VERSION,
        "reviewWaveId": _canonical_sha256(binding_material),
        **artifacts,
    }
    output = Path(args.output)
    _write_json_atomic(output, wave)
    print(
        json.dumps(
            {
                "valid": True,
                "reviewWaveId": wave["reviewWaveId"],
                "output": str(output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


def _validate_wave_shape(wave: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(wave, dict):
        return ["Review wave must be a JSON object."]
    if wave.get("schemaVersion") != WAVE_SCHEMA_VERSION:
        errors.append(f"Review wave schemaVersion must be {WAVE_SCHEMA_VERSION!r}.")
    if wave.get("protocolVersion") != PROTOCOL_VERSION:
        errors.append(f"Review wave protocolVersion must be {PROTOCOL_VERSION!r}.")
    wave_id = wave.get("reviewWaveId")
    if not isinstance(wave_id, str) or len(wave_id) != 64:
        errors.append("Review wave reviewWaveId must be a 64-character SHA-256.")

    for name in (
        "candidateManifest",
        "evidenceIndex",
        "reviewPlan",
        "coverageMatrix",
    ):
        artifact = wave.get(name)
        if not isinstance(artifact, dict):
            errors.append(f"Review wave {name} must be an artifact object.")
            continue
        if not _is_nonempty_string(artifact.get("path")):
            errors.append(f"Review wave {name}.path must be a non-empty string.")
        if not isinstance(artifact.get("length"), int) or artifact.get("length", -1) < 0:
            errors.append(f"Review wave {name}.length must be a non-negative integer.")
        sha = artifact.get("sha256")
        if not isinstance(sha, str) or len(sha) != 64:
            errors.append(f"Review wave {name}.sha256 must be a 64-character SHA-256.")
    return errors


def _verify_bound_artifacts(wave: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for name in (
        "candidateManifest",
        "evidenceIndex",
        "reviewPlan",
        "coverageMatrix",
    ):
        artifact = wave.get(name)
        if not isinstance(artifact, dict) or not _is_nonempty_string(artifact.get("path")):
            continue
        path = Path(artifact["path"])
        if not path.exists():
            errors.append(f"Bound artifact is missing for {name}: {path}")
            continue
        if not path.is_file():
            errors.append(f"Bound artifact is not a file for {name}: {path}")
            continue
        actual_length = path.stat().st_size
        if actual_length != artifact.get("length"):
            errors.append(
                f"Bound artifact length drift for {name}: expected "
                f"{artifact.get('length')}, found {actual_length}."
            )
        actual_sha = _sha256(path)
        if actual_sha.lower() != str(artifact.get("sha256", "")).lower():
            errors.append(
                f"Bound artifact hash drift for {name}: expected "
                f"{artifact.get('sha256')}, found {actual_sha}."
            )

    if not errors:
        material = {
            "protocolVersion": wave.get("protocolVersion"),
            "candidateManifestSha256": wave["candidateManifest"]["sha256"],
            "evidenceIndexSha256": wave["evidenceIndex"]["sha256"],
            "reviewPlanSha256": wave["reviewPlan"]["sha256"],
            "coverageMatrixSha256": wave["coverageMatrix"]["sha256"],
        }
        expected_wave_id = _canonical_sha256(material)
        if wave.get("reviewWaveId") != expected_wave_id:
            errors.append(
                "Review wave ID does not match its protocol and bound artifact hashes."
            )
    return errors


def _validate_binding(report: dict[str, Any], wave: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    binding = report.get("binding")
    if not isinstance(binding, dict):
        return ["Report binding must be an object."]
    expected = {
        "reviewWaveId": wave.get("reviewWaveId"),
        "candidateManifestSha256": wave.get("candidateManifest", {}).get("sha256"),
        "evidenceIndexSha256": wave.get("evidenceIndex", {}).get("sha256"),
        "reviewPlanSha256": wave.get("reviewPlan", {}).get("sha256"),
        "coverageMatrixSha256": wave.get("coverageMatrix", {}).get("sha256"),
    }
    for field, expected_value in expected.items():
        actual = binding.get(field)
        if not isinstance(actual, str) or actual.lower() != str(expected_value).lower():
            errors.append(
                f"Report binding {field} does not match the frozen review wave."
            )
    return errors


def _validate_report_semantics(
    report: Any, matrix: dict[str, Any], wave: dict[str, Any]
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(report, dict):
        return ["Review report must be a JSON object."], warnings
    if report.get("schemaVersion") != REPORT_SCHEMA_VERSION:
        errors.append(f"Report schemaVersion must be {REPORT_SCHEMA_VERSION!r}.")
    errors.extend(_validate_binding(report, wave))

    reviewer = report.get("reviewer")
    if not isinstance(reviewer, dict):
        errors.append("Report reviewer must be an object.")
    else:
        if not _is_nonempty_string(reviewer.get("id")):
            errors.append("Report reviewer.id must be a non-empty string.")
        if reviewer.get("role") not in {
            "PRIMARY_FIXED_POINT",
            "COVERAGE_AUDITOR",
            "FULL_ESCALATION",
        }:
            errors.append("Report reviewer.role is invalid.")
        if reviewer.get("independentPass") is not True:
            errors.append("Independent review reports must set independentPass to true.")

    actual = report.get("actualCandidateVerdict")
    finding_set = report.get("findingSetStatus")
    counterfactual = report.get("counterfactualVerdict")
    if actual not in ACTUAL_VERDICTS:
        errors.append("Report actualCandidateVerdict is invalid.")
    if finding_set not in FINDING_SET_STATUSES:
        errors.append("Report findingSetStatus is invalid.")
    if counterfactual not in COUNTERFACTUAL_VERDICTS:
        errors.append("Report counterfactualVerdict is invalid.")
    if not isinstance(report.get("continuedAfterFirstBlocker"), bool):
        errors.append("Report continuedAfterFirstBlocker must be a boolean.")

    cells = matrix.get("cells", [])
    matrix_by_id = {
        cell["cellId"]: cell
        for cell in cells
        if isinstance(cell, dict) and _is_nonempty_string(cell.get("cellId"))
    }
    matrix_ids = set(matrix_by_id)
    required_ids = {
        cell_id for cell_id, cell in matrix_by_id.items() if cell.get("required") is True
    }

    coverage = report.get("coverage")
    if not isinstance(coverage, list):
        errors.append("Report coverage must be an array.")
        coverage = []
    coverage_ids = [
        item.get("cellId")
        for item in coverage
        if isinstance(item, dict) and isinstance(item.get("cellId"), str)
    ]
    for duplicate in _duplicate_values(coverage_ids):
        errors.append(f"Report coverage contains duplicate cellId {duplicate!r}.")
    coverage_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(coverage):
        prefix = f"Report coverage[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        cell_id = item.get("cellId")
        if not _is_nonempty_string(cell_id):
            errors.append(f"{prefix}.cellId must be a non-empty string.")
            continue
        if cell_id not in matrix_ids:
            errors.append(f"{prefix} references unknown coverage cell {cell_id!r}.")
        else:
            coverage_by_id[cell_id] = item
        status = item.get("status")
        if status not in COVERAGE_STATUSES:
            errors.append(f"{prefix}.status is invalid.")
        closure_support = item.get("closureSupport")
        if closure_support not in CLOSURE_SUPPORT_STATUSES:
            errors.append(f"{prefix}.closureSupport is invalid.")
        highest_tier = item.get("highestEvidenceTier")
        if highest_tier not in TIER_ORDER:
            errors.append(f"{prefix}.highestEvidenceTier is invalid.")
        evidence_tiers = _validate_evidence_list(
            item.get("evidence"),
            f"{prefix}.evidence",
            errors,
            require=status in {
                "COVERED_NO_FINDING",
                "FINDING",
                "NOT_APPLICABLE",
            },
        )
        observed_highest = (
            max(evidence_tiers, key=lambda tier: TIER_ORDER[tier])
            if evidence_tiers
            else "NONE"
        )
        if highest_tier in TIER_ORDER and highest_tier != observed_highest:
            errors.append(
                f"{prefix}.highestEvidenceTier must match the highest tier in its "
                f"evidence array ({observed_highest})."
            )
        finding_ids = item.get("findingIds")
        if not _string_list(finding_ids):
            errors.append(f"{prefix}.findingIds must be an array of strings.")
            finding_ids = []
        if status == "FINDING" and not finding_ids:
            errors.append(f"{prefix} with status FINDING must reference a finding.")
        if status in {"COVERED_NO_FINDING", "FINDING"} and closure_support != "SUPPORTED":
            errors.append(
                f"{prefix} with status {status} requires closureSupport SUPPORTED."
            )
        if status == "NOT_APPLICABLE" and not _is_nonempty_string(
            item.get("notApplicableReason")
        ):
            errors.append(
                f"{prefix} with status NOT_APPLICABLE needs notApplicableReason."
            )
        if status == "NOT_APPLICABLE" and closure_support != "NOT_APPLICABLE":
            errors.append(
                f"{prefix} with status NOT_APPLICABLE requires matching "
                "closureSupport."
            )
        if status == "EVIDENCE_GAP" and closure_support not in {
            "WRONG_TIER",
            "UNSUPPORTED",
            "OPEN",
        }:
            errors.append(
                f"{prefix} with status EVIDENCE_GAP must remain wrong-tier, "
                "unsupported, or open."
            )
        if status == "UNVISITED" and closure_support != "OPEN":
            errors.append(f"{prefix} with status UNVISITED requires closureSupport OPEN.")
        if (
            status == "COVERED_NO_FINDING"
            and cell_id in matrix_by_id
            and highest_tier in TIER_ORDER
            and TIER_ORDER[highest_tier]
            < TIER_ORDER[matrix_by_id[cell_id]["requiredTier"]]
        ):
            errors.append(
                f"{prefix} closes a safe cell below its required tier "
                f"{matrix_by_id[cell_id]['requiredTier']}."
            )

    incomplete_required = {
        cell_id
        for cell_id in required_ids
        if cell_id not in coverage_by_id
        or coverage_by_id[cell_id].get("status") in {"UNVISITED", "EVIDENCE_GAP"}
        or coverage_by_id[cell_id].get("closureSupport")
        in {"WRONG_TIER", "UNSUPPORTED", "OPEN"}
        or (
            coverage_by_id[cell_id].get("status") == "COVERED_NO_FINDING"
            and coverage_by_id[cell_id].get("highestEvidenceTier") in TIER_ORDER
            and TIER_ORDER[coverage_by_id[cell_id]["highestEvidenceTier"]]
            < TIER_ORDER[matrix_by_id[cell_id]["requiredTier"]]
        )
    }

    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("Report findings must be an array.")
        findings = []
    finding_ids = [
        item.get("id")
        for item in findings
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    for duplicate in _duplicate_values(finding_ids):
        errors.append(f"Report findings contains duplicate id {duplicate!r}.")
    finding_by_id: dict[str, dict[str, Any]] = {}
    for index, finding in enumerate(findings):
        prefix = f"Report findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        finding_id = finding.get("id")
        if not _is_nonempty_string(finding_id):
            errors.append(f"{prefix}.id must be a non-empty string.")
            continue
        finding_by_id[finding_id] = finding
        if finding.get("severity") not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            errors.append(f"{prefix}.severity is invalid.")
        if not isinstance(finding.get("blocksGate"), bool):
            errors.append(f"{prefix}.blocksGate must be a boolean.")
        for field in (
            "contractIds",
            "preconditions",
            "executionPath",
            "requiredRepairProperties",
            "requiredRegressionCellIds",
        ):
            if not _string_list(finding.get(field)):
                errors.append(f"{prefix}.{field} must be an array of strings.")
        for field in ("firstUnsafeOperation", "impact"):
            if not _is_nonempty_string(finding.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string.")
        _validate_evidence_list(
            finding.get("evidence"),
            f"{prefix}.evidence",
            errors,
            require=True,
        )
        sibling_disposition = finding.get("siblingCellDisposition")
        if not isinstance(sibling_disposition, list):
            errors.append(f"{prefix}.siblingCellDisposition must be an array.")
        else:
            for sibling in sibling_disposition:
                if isinstance(sibling, dict) and sibling.get("cellId") not in matrix_ids:
                    errors.append(
                        f"{prefix}.siblingCellDisposition references unknown cell "
                        f"{sibling.get('cellId')!r}."
                    )
        for cell_id in finding.get("requiredRegressionCellIds", []):
            if cell_id not in matrix_ids:
                errors.append(
                    f"{prefix}.requiredRegressionCellIds references unknown cell "
                    f"{cell_id!r}."
                )

    known_finding_ids = set(finding_by_id)
    referenced_finding_ids: set[str] = set()
    for item in coverage_by_id.values():
        for finding_id in item.get("findingIds", []):
            referenced_finding_ids.add(finding_id)
            if finding_id not in known_finding_ids:
                errors.append(
                    f"Coverage cell {item.get('cellId')!r} references unknown finding "
                    f"{finding_id!r}."
                )
    for finding_id in sorted(known_finding_ids - referenced_finding_ids):
        errors.append(f"Finding {finding_id!r} is not linked from any coverage cell.")

    assumptions = report.get("assumptions")
    if not isinstance(assumptions, list):
        errors.append("Report assumptions must be an array.")
        assumptions = []
    assumption_ids = [
        item.get("id")
        for item in assumptions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    for duplicate in _duplicate_values(assumption_ids):
        errors.append(f"Report assumptions contains duplicate id {duplicate!r}.")
    known_assumption_ids = set(assumption_ids)
    assumed_finding_ids: set[str] = set()
    for index, assumption in enumerate(assumptions):
        prefix = f"Report assumptions[{index}]"
        if not isinstance(assumption, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if not _is_nonempty_string(assumption.get("id")):
            errors.append(f"{prefix}.id must be a non-empty string.")
        finding_refs = assumption.get("findingIds")
        if not _string_list(finding_refs) or not finding_refs:
            errors.append(f"{prefix}.findingIds must be a non-empty string array.")
            finding_refs = []
        for finding_id in finding_refs:
            assumed_finding_ids.add(finding_id)
            if finding_id not in known_finding_ids:
                errors.append(f"{prefix} references unknown finding {finding_id!r}.")
        for field in (
            "affectedCellIds",
            "reopenedCellIds",
            "requiredRegressionCellIds",
        ):
            cell_refs = assumption.get(field)
            if not _string_list(cell_refs):
                errors.append(f"{prefix}.{field} must be an array of strings.")
                continue
            for cell_id in cell_refs:
                if cell_id not in matrix_ids:
                    errors.append(f"{prefix}.{field} references unknown cell {cell_id!r}.")
        for field in ("repairPostcondition", "falsificationCondition"):
            if not _is_nonempty_string(assumption.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string.")
        conflicts = assumption.get("conflictsWith", [])
        if not _string_list(conflicts):
            errors.append(f"{prefix}.conflictsWith must be an array of strings.")
        else:
            for conflict_id in conflicts:
                if conflict_id not in known_assumption_ids:
                    errors.append(
                        f"{prefix}.conflictsWith references unknown assumption "
                        f"{conflict_id!r}."
                    )

    fixed_point = report.get("fixedPoint")
    fixed_point_incomplete = True
    missing_reopen_by_trigger: dict[tuple[str, str], set[str]] = {}
    missing_attack_dimensions: set[str] = set(ADVERSARIAL_DIMENSIONS)
    if not isinstance(fixed_point, dict):
        errors.append("Report fixedPoint must be an object.")
    else:
        iteration_count = fixed_point.get("iterationCount")
        if not isinstance(iteration_count, int) or iteration_count < 1:
            errors.append("Report fixedPoint.iterationCount must be at least 1.")
        stable = fixed_point.get("stable")
        if not isinstance(stable, bool):
            errors.append("Report fixedPoint.stable must be a boolean.")

        unresolved_challenges = fixed_point.get("unresolvedChallengeIds")
        if not _string_list(unresolved_challenges):
            errors.append(
                "Report fixedPoint.unresolvedChallengeIds must be a string array."
            )
            unresolved_challenges = []

        obligations = fixed_point.get("reopenObligations")
        if not isinstance(obligations, list):
            errors.append("Report fixedPoint.reopenObligations must be an array.")
            obligations = []
        obligation_ids: list[str] = []
        reviewed_cells_by_trigger: dict[tuple[str, str], set[str]] = {}
        open_obligation_ids: list[str] = []
        for index, obligation in enumerate(obligations):
            prefix = f"Report fixedPoint.reopenObligations[{index}]"
            if not isinstance(obligation, dict):
                errors.append(f"{prefix} must be an object.")
                continue
            obligation_id = obligation.get("id")
            if not _is_nonempty_string(obligation_id):
                errors.append(f"{prefix}.id must be a non-empty string.")
            else:
                obligation_ids.append(obligation_id)
            trigger_kind = obligation.get("triggerKind")
            trigger_id = obligation.get("triggerId")
            if trigger_kind not in {"FINDING", "ASSUMPTION", "COVERAGE_CHALLENGE"}:
                errors.append(f"{prefix}.triggerKind is invalid.")
            if not _is_nonempty_string(trigger_id):
                errors.append(f"{prefix}.triggerId must be a non-empty string.")
            elif trigger_kind == "FINDING" and trigger_id not in known_finding_ids:
                errors.append(f"{prefix} references unknown finding {trigger_id!r}.")
            elif trigger_kind == "ASSUMPTION" and trigger_id not in known_assumption_ids:
                errors.append(f"{prefix} references unknown assumption {trigger_id!r}.")
            cell_refs = obligation.get("cellIds")
            if not _string_list(cell_refs) or not cell_refs:
                errors.append(f"{prefix}.cellIds must be a non-empty string array.")
                cell_refs = []
            for cell_id in cell_refs:
                if cell_id not in matrix_ids:
                    errors.append(f"{prefix}.cellIds references unknown cell {cell_id!r}.")
            disposition = obligation.get("disposition")
            if disposition not in {"REVIEWED", "OPEN"}:
                errors.append(f"{prefix}.disposition is invalid.")
            elif disposition == "OPEN" and _is_nonempty_string(obligation_id):
                open_obligation_ids.append(obligation_id)
            elif (
                disposition == "REVIEWED"
                and trigger_kind in {"FINDING", "ASSUMPTION", "COVERAGE_CHALLENGE"}
                and _is_nonempty_string(trigger_id)
            ):
                reviewed_cells_by_trigger.setdefault(
                    (trigger_kind, trigger_id), set()
                ).update(cell_refs)
            _validate_evidence_list(
                obligation.get("evidence"),
                f"{prefix}.evidence",
                errors,
                require=True,
            )
        for duplicate in _duplicate_values(obligation_ids):
            errors.append(
                f"Report fixedPoint.reopenObligations contains duplicate id "
                f"{duplicate!r}."
            )

        for finding_id, finding in finding_by_id.items():
            required_cells = set(finding.get("requiredRegressionCellIds", []))
            reviewed_cells = reviewed_cells_by_trigger.get(
                ("FINDING", finding_id), set()
            )
            missing = required_cells - reviewed_cells
            if missing:
                missing_reopen_by_trigger[("FINDING", finding_id)] = missing
        for assumption in assumptions:
            if not isinstance(assumption, dict) or not _is_nonempty_string(
                assumption.get("id")
            ):
                continue
            required_cells = set(assumption.get("reopenedCellIds", []))
            reviewed_cells = reviewed_cells_by_trigger.get(
                ("ASSUMPTION", assumption["id"]), set()
            )
            missing = required_cells - reviewed_cells
            if missing:
                missing_reopen_by_trigger[("ASSUMPTION", assumption["id"])] = missing

        checks = fixed_point.get("adversarialChecks")
        if not isinstance(checks, list):
            errors.append("Report fixedPoint.adversarialChecks must be an array.")
            checks = []
        check_dimensions: list[str] = []
        incomplete_applicable_checks: list[str] = []
        for index, check in enumerate(checks):
            prefix = f"Report fixedPoint.adversarialChecks[{index}]"
            if not isinstance(check, dict):
                errors.append(f"{prefix} must be an object.")
                continue
            dimension = check.get("dimension")
            if dimension not in ADVERSARIAL_DIMENSIONS:
                errors.append(f"{prefix}.dimension is invalid.")
            else:
                check_dimensions.append(dimension)
            applicable = check.get("applicable")
            completed = check.get("completed")
            if not isinstance(applicable, bool):
                errors.append(f"{prefix}.applicable must be a boolean.")
            if not isinstance(completed, bool):
                errors.append(f"{prefix}.completed must be a boolean.")
            if applicable is True and completed is not True and dimension in ADVERSARIAL_DIMENSIONS:
                incomplete_applicable_checks.append(dimension)
            if not _is_nonempty_string(check.get("note")):
                errors.append(f"{prefix}.note must be a non-empty string.")
            _validate_evidence_list(
                check.get("evidence"),
                f"{prefix}.evidence",
                errors,
                require=True,
            )
        for duplicate in _duplicate_values(check_dimensions):
            errors.append(
                f"Report fixedPoint.adversarialChecks contains duplicate dimension "
                f"{duplicate!r}."
            )
        missing_attack_dimensions = ADVERSARIAL_DIMENSIONS - set(check_dimensions)
        fixed_point_incomplete = bool(
            stable is not True
            or unresolved_challenges
            or open_obligation_ids
            or missing_reopen_by_trigger
            or missing_attack_dimensions
            or incomplete_applicable_checks
        )
        if finding_set == "BATCH_COMPLETE":
            if stable is not True:
                errors.append("BATCH_COMPLETE requires a stable fixed point.")
            if unresolved_challenges:
                errors.append(
                    "BATCH_COMPLETE cannot retain unresolved fixed-point challenges."
                )
            if open_obligation_ids:
                errors.append(
                    "BATCH_COMPLETE cannot retain open reopen obligations: "
                    + ", ".join(sorted(open_obligation_ids))
                )
            for (trigger_kind, trigger_id), missing in sorted(
                missing_reopen_by_trigger.items()
            ):
                errors.append(
                    f"BATCH_COMPLETE requires a complete reopen obligation for "
                    f"{trigger_kind} {trigger_id}; missing cells: "
                    + ", ".join(sorted(missing))
                )
            if missing_attack_dimensions:
                errors.append(
                    "BATCH_COMPLETE fixed point is missing adversarial dimensions: "
                    + ", ".join(sorted(missing_attack_dimensions))
                )
            if incomplete_applicable_checks:
                errors.append(
                    "BATCH_COMPLETE has incomplete applicable adversarial checks: "
                    + ", ".join(sorted(incomplete_applicable_checks))
                )

    gaps = report.get("verificationGaps")
    if not isinstance(gaps, list):
        errors.append("Report verificationGaps must be an array.")
        gaps = []
    blocking_gaps = []
    gap_ids: list[str] = []
    for index, gap in enumerate(gaps):
        prefix = f"Report verificationGaps[{index}]"
        if not isinstance(gap, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if _is_nonempty_string(gap.get("id")):
            gap_ids.append(gap["id"])
        else:
            errors.append(f"{prefix}.id must be a non-empty string.")
        if not isinstance(gap.get("blocksGate"), bool):
            errors.append(f"{prefix}.blocksGate must be a boolean.")
        elif gap["blocksGate"]:
            blocking_gaps.append(gap)
        cell_refs = gap.get("cellIds")
        if not _string_list(cell_refs):
            errors.append(f"{prefix}.cellIds must be an array of strings.")
        else:
            for cell_id in cell_refs:
                if cell_id not in matrix_ids:
                    errors.append(f"{prefix}.cellIds references unknown cell {cell_id!r}.")
        for field in ("reason", "requiredAction"):
            if not _is_nonempty_string(gap.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string.")
    for duplicate in _duplicate_values(gap_ids):
        errors.append(f"Report verificationGaps contains duplicate id {duplicate!r}.")

    stopping = report.get("stopping")
    if not isinstance(stopping, dict):
        errors.append("Report stopping must be an object.")
        stopping = {}
    stop_reason = stopping.get("reason")
    if stop_reason not in STOP_REASONS:
        errors.append("Report stopping.reason is invalid.")
    unvisited = stopping.get("unvisitedRequiredCellIds")
    if not _string_list(unvisited):
        errors.append("Report stopping.unvisitedRequiredCellIds must be a string array.")
        unvisited = []
    else:
        for cell_id in unvisited:
            if cell_id not in required_ids:
                errors.append(
                    "Report stopping.unvisitedRequiredCellIds contains a cell that is "
                    f"not required by the matrix: {cell_id!r}."
                )
    if set(unvisited) != incomplete_required:
        errors.append(
            "Report stopping.unvisitedRequiredCellIds must exactly match every "
            "missing, unvisited, evidence-gap, unsupported, or wrong-tier required "
            "coverage cell."
        )

    blockers = {
        finding_id
        for finding_id, finding in finding_by_id.items()
        if finding.get("blocksGate") is True
    }
    incomplete = bool(incomplete_required or blocking_gaps or fixed_point_incomplete)

    if finding_set == "BATCH_COMPLETE":
        if incomplete:
            errors.append(
                "BATCH_COMPLETE is invalid while required closure support, the fixed "
                "point, or blocking gaps remain incomplete."
            )
        if stop_reason != "COVERAGE_COMPLETE":
            errors.append("BATCH_COMPLETE requires stopping.reason COVERAGE_COMPLETE.")
        if unvisited:
            errors.append("BATCH_COMPLETE requires no unvisited required cells.")
    elif finding_set in FINDING_SET_STATUSES:
        if actual != "INCOMPLETE":
            errors.append(
                "A non-complete finding set requires actualCandidateVerdict INCOMPLETE."
            )

    expected_stop_status = {
        "HASH_DRIFT": "HASH_DRIFT",
        "ACCESS_FAILURE": "ACCESS_BLOCKED",
        "SCOPE_VIOLATION": "SCOPE_ABORTED",
        "BUDGET_REACHED": "BUDGET_EXHAUSTED",
        "FINDING_OVERFLOW": "OVERFLOW_NEEDS_ENUMERATION",
    }.get(stop_reason)
    if expected_stop_status and finding_set != expected_stop_status:
        errors.append(
            f"Stopping reason {stop_reason} requires findingSetStatus "
            f"{expected_stop_status}."
        )

    if actual == "PASS":
        if blockers or blocking_gaps:
            errors.append("Actual PASS is invalid while a blocker or blocking gap exists.")
        if finding_set != "BATCH_COMPLETE" or incomplete:
            errors.append("Actual PASS requires complete required coverage.")
        if assumptions:
            errors.append("Actual PASS cannot depend on synthetic repair assumptions.")
        if counterfactual != "NOT_NEEDED":
            errors.append("Actual PASS requires counterfactualVerdict NOT_NEEDED.")
        if stop_reason != "COVERAGE_COMPLETE":
            errors.append("Actual PASS requires stopping.reason COVERAGE_COMPLETE.")
    elif actual == "BLOCKED":
        if not blockers and not blocking_gaps:
            errors.append("BLOCKED requires at least one blocker or blocking gap.")
        if finding_set != "BATCH_COMPLETE":
            errors.append(
                "A report with an incomplete finding set must use actualCandidateVerdict "
                "INCOMPLETE, even if blockers are already known."
            )
    elif actual == "INCOMPLETE" and finding_set == "BATCH_COMPLETE":
        errors.append("INCOMPLETE cannot be paired with BATCH_COMPLETE.")

    if blockers and finding_set == "BATCH_COMPLETE" and report.get(
        "continuedAfterFirstBlocker"
    ) is not True:
        errors.append(
            "A blocker-bearing BATCH_COMPLETE report must confirm continued review "
            "after the first blocker."
        )

    if counterfactual == "PASS_UNDER_ASSUMPTIONS":
        if actual != "BLOCKED":
            errors.append(
                "PASS_UNDER_ASSUMPTIONS requires actualCandidateVerdict BLOCKED."
            )
        if finding_set != "BATCH_COMPLETE":
            errors.append("PASS_UNDER_ASSUMPTIONS requires BATCH_COMPLETE.")
        if not assumptions:
            errors.append("PASS_UNDER_ASSUMPTIONS requires at least one assumption.")
        missing_assumptions = blockers - assumed_finding_ids
        if missing_assumptions:
            errors.append(
                "PASS_UNDER_ASSUMPTIONS does not assume away every blocking finding: "
                + ", ".join(sorted(missing_assumptions))
            )
    elif counterfactual == "NOT_NEEDED" and assumptions:
        errors.append("NOT_NEEDED cannot include synthetic repair assumptions.")
    elif counterfactual == "UNRESOLVED" and actual == "PASS":
        errors.append("UNRESOLVED cannot be paired with actual PASS.")

    if blockers and finding_set == "BATCH_COMPLETE" and counterfactual == "NOT_NEEDED":
        warnings.append(
            "The actual candidate is blocked, but no counterfactual closure verdict was "
            "recorded. Use UNRESOLVED when closure could not be reached."
        )

    return errors, warnings


def _validate_report(args: argparse.Namespace) -> int:
    wave_path = Path(args.wave)
    report_path = Path(args.report)
    wave = _load_json(wave_path, "review wave")
    report = _load_json(report_path, "review report")

    wave_shape_errors = _validate_wave_shape(wave)
    errors = list(wave_shape_errors)
    if isinstance(wave, dict) and not wave_shape_errors:
        errors.extend(_verify_bound_artifacts(wave))

    matrix: dict[str, Any] = {}
    if isinstance(wave, dict) and not wave_shape_errors:
        matrix_artifact = wave.get("coverageMatrix")
        if isinstance(matrix_artifact, dict) and _is_nonempty_string(
            matrix_artifact.get("path")
        ):
            try:
                loaded_matrix = _load_json(
                    Path(matrix_artifact["path"]), "bound coverage matrix"
                )
                matrix_errors = _validate_matrix(loaded_matrix)
                errors.extend(matrix_errors)
                if isinstance(loaded_matrix, dict):
                    matrix = loaded_matrix
            except GateInputError as exc:
                errors.append(str(exc))

    semantic_errors: list[str] = []
    warnings: list[str] = []
    if isinstance(wave, dict) and not wave_shape_errors and matrix:
        semantic_errors, warnings = _validate_report_semantics(report, matrix, wave)
        errors.extend(semantic_errors)

    result = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "reviewWaveId": wave.get("reviewWaveId") if isinstance(wave, dict) else None,
        "actualCandidateVerdict": (
            report.get("actualCandidateVerdict") if isinstance(report, dict) else None
        ),
        "findingSetStatus": (
            report.get("findingSetStatus") if isinstance(report, dict) else None
        ),
        "counterfactualVerdict": (
            report.get("counterfactualVerdict") if isinstance(report, dict) else None
        ),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


def _load_current_wave_and_matrix(
    wave_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    wave = _load_json(wave_path, "review wave")
    errors = _validate_wave_shape(wave)
    matrix: dict[str, Any] = {}
    if not isinstance(wave, dict) or errors:
        return wave if isinstance(wave, dict) else {}, matrix, errors
    errors.extend(_verify_bound_artifacts(wave))
    matrix_artifact = wave.get("coverageMatrix")
    if isinstance(matrix_artifact, dict) and _is_nonempty_string(
        matrix_artifact.get("path")
    ):
        loaded = _load_json(Path(matrix_artifact["path"]), "bound coverage matrix")
        errors.extend(_validate_matrix(loaded))
        if isinstance(loaded, dict):
            matrix = loaded
    else:
        errors.append("Review wave coverageMatrix artifact is invalid.")
    return wave, matrix, errors


def _validate_audit_evidence(value: Any, prefix: str, errors: list[str]) -> None:
    _validate_evidence_list(value, prefix, errors, require=True)


def _report_finding_ids(report: Any) -> set[str]:
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        return set()
    return {
        finding["id"]
        for finding in report["findings"]
        if isinstance(finding, dict) and _is_nonempty_string(finding.get("id"))
    }


def _report_reviewer_id(report: Any) -> str | None:
    if not isinstance(report, dict) or not isinstance(report.get("reviewer"), dict):
        return None
    reviewer_id = report["reviewer"].get("id")
    return reviewer_id if _is_nonempty_string(reviewer_id) else None


def _report_blocking_finding_ids(report: Any) -> set[str]:
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        return set()
    return {
        finding["id"]
        for finding in report["findings"]
        if isinstance(finding, dict)
        and _is_nonempty_string(finding.get("id"))
        and finding.get("blocksGate") is True
    }


def _report_coverage_by_cell(report: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(report, dict) or not isinstance(report.get("coverage"), list):
        return {}
    return {
        item["cellId"]: item
        for item in report["coverage"]
        if isinstance(item, dict) and _is_nonempty_string(item.get("cellId"))
    }


def _validate_cross_audit_semantics(
    audit: Any,
    wave: dict[str, Any],
    own_report_sha: str,
    peer_report_sha: str,
    matrix_ids: set[str],
    known_finding_ids: set[str],
    *,
    expected_mode: str | None = None,
    expected_auditor_id: str | None = None,
    peer_has_blockers: bool = False,
) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    all_challenge_ids: set[str] = set()
    unresolved_by_disposition: set[str] = set()
    if not isinstance(audit, dict):
        return ["Cross-audit must be a JSON object."], set(), set()
    if audit.get("schemaVersion") != "batch-review-cross-audit.v1":
        errors.append(
            "Cross-audit schemaVersion must be 'batch-review-cross-audit.v1'."
        )
    audit_mode = audit.get("auditMode")
    if audit_mode not in {"NARROW", "RECIPROCAL"}:
        errors.append("Cross-audit auditMode is invalid.")
    elif expected_mode is not None and audit_mode != expected_mode:
        errors.append(
            f"Cross-audit auditMode must be {expected_mode} for the selected topology."
        )
    binding = audit.get("binding")
    if not isinstance(binding, dict):
        errors.append("Cross-audit binding must be an object.")
    else:
        expected = {
            "reviewWaveId": wave.get("reviewWaveId"),
            "ownReportSha256": own_report_sha,
            "peerReportSha256": peer_report_sha,
        }
        for field, expected_value in expected.items():
            actual = binding.get(field)
            if not isinstance(actual, str) or actual.lower() != str(
                expected_value
            ).lower():
                errors.append(
                    f"Cross-audit binding {field} does not match its bound artifact."
                )
    auditor = audit.get("auditor")
    if not isinstance(auditor, dict):
        errors.append("Cross-audit auditor must be an object.")
    else:
        if not _is_nonempty_string(auditor.get("id")):
            errors.append("Cross-audit auditor.id must be a non-empty string.")
        elif (
            expected_auditor_id is not None
            and auditor.get("id") != expected_auditor_id
        ):
            errors.append(
                "Cross-audit auditor.id must match the owner of ownReportSha256."
            )
        if auditor.get("independentPass") is not True:
            errors.append("Cross-audit independentPass must be true.")
    for field in ("peerContinuedAfterFirstBlocker", "peerFixedPointStable"):
        if not isinstance(audit.get(field), bool):
            errors.append(f"Cross-audit {field} must be a boolean.")

    coverage_challenges = audit.get("coverageChallenges")
    if not isinstance(coverage_challenges, list):
        errors.append("Cross-audit coverageChallenges must be an array.")
        coverage_challenges = []
    for index, challenge in enumerate(coverage_challenges):
        prefix = f"Cross-audit coverageChallenges[{index}]"
        if not isinstance(challenge, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        challenge_id = challenge.get("id")
        if not _is_nonempty_string(challenge_id):
            errors.append(f"{prefix}.id must be a non-empty string.")
        elif challenge_id in all_challenge_ids:
            errors.append(f"Cross-audit contains duplicate challenge id {challenge_id!r}.")
        else:
            all_challenge_ids.add(challenge_id)
        if challenge.get("kind") not in {
            "UNSUPPORTED_CLOSURE",
            "WRONG_TIER",
            "MISSED_SIBLING",
            "INCOMPLETE_REPAIR_POSTCONDITION",
            "UNSTABLE_FIXED_POINT",
            "HASH_OR_BINDING_FAILURE",
        }:
            errors.append(f"{prefix}.kind is invalid.")
        cell_ids = challenge.get("cellIds")
        if not _string_list(cell_ids) or not cell_ids:
            errors.append(f"{prefix}.cellIds must be a non-empty string array.")
            cell_ids = []
        for cell_id in cell_ids:
            if cell_id not in matrix_ids:
                errors.append(f"{prefix}.cellIds references unknown cell {cell_id!r}.")
        for field in ("challenge", "requiredSynthesisAction"):
            if not _is_nonempty_string(challenge.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string.")
        _validate_audit_evidence(challenge.get("evidence"), f"{prefix}.evidence", errors)
        disposition = challenge.get("disposition")
        if disposition not in {
            "SUPPORTED_BY_UNION",
            "REJECTED_WITH_EVIDENCE",
            "UNRESOLVED",
        }:
            errors.append(f"{prefix}.disposition is invalid.")
        elif disposition == "UNRESOLVED" and _is_nonempty_string(challenge_id):
            unresolved_by_disposition.add(challenge_id)

    finding_challenges = audit.get("findingChallenges")
    if not isinstance(finding_challenges, list):
        errors.append("Cross-audit findingChallenges must be an array.")
        finding_challenges = []
    for index, challenge in enumerate(finding_challenges):
        prefix = f"Cross-audit findingChallenges[{index}]"
        if not isinstance(challenge, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        challenge_id = challenge.get("id")
        if not _is_nonempty_string(challenge_id):
            errors.append(f"{prefix}.id must be a non-empty string.")
        elif challenge_id in all_challenge_ids:
            errors.append(f"Cross-audit contains duplicate challenge id {challenge_id!r}.")
        else:
            all_challenge_ids.add(challenge_id)
        finding_refs = challenge.get("findingIds")
        if not _string_list(finding_refs) or not finding_refs:
            errors.append(f"{prefix}.findingIds must be a non-empty string array.")
            finding_refs = []
        for finding_id in finding_refs:
            if finding_id not in known_finding_ids:
                errors.append(
                    f"{prefix}.findingIds references unknown finding {finding_id!r}."
                )
        if challenge.get("assessment") not in {
            "SUPPORTED",
            "UNSUPPORTED",
            "SEVERITY_CHALLENGE",
            "MISSED_SIBLING",
            "INCOMPLETE_REPAIR_POSTCONDITION",
            "DUPLICATE",
        }:
            errors.append(f"{prefix}.assessment is invalid.")
        if not _is_nonempty_string(challenge.get("challenge")):
            errors.append(f"{prefix}.challenge must be a non-empty string.")
        _validate_audit_evidence(challenge.get("evidence"), f"{prefix}.evidence", errors)
        disposition = challenge.get("disposition")
        if disposition not in {
            "SUPPORTED_BY_UNION",
            "REJECTED_WITH_EVIDENCE",
            "UNRESOLVED",
        }:
            errors.append(f"{prefix}.disposition is invalid.")
        elif disposition == "UNRESOLVED" and _is_nonempty_string(challenge_id):
            unresolved_by_disposition.add(challenge_id)

    new_findings = audit.get("newFindings")
    new_finding_ids: set[str] = set()
    if not isinstance(new_findings, list):
        errors.append("Cross-audit newFindings must be an array.")
        new_findings = []
    for index, finding in enumerate(new_findings):
        prefix = f"Cross-audit newFindings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        finding_id = finding.get("id")
        if not _is_nonempty_string(finding_id):
            errors.append(f"{prefix}.id must be a non-empty string.")
        elif finding_id in known_finding_ids or finding_id in new_finding_ids:
            errors.append(f"{prefix}.id duplicates an existing finding.")
        else:
            new_finding_ids.add(finding_id)
        if finding.get("severity") not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            errors.append(f"{prefix}.severity is invalid.")
        if not isinstance(finding.get("blocking"), bool):
            errors.append(f"{prefix}.blocking must be a boolean.")
        for field in ("summary", "firstUnsafeOperation", "impact"):
            if not _is_nonempty_string(finding.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string.")
        for field in (
            "contractIds",
            "cellIds",
            "preconditions",
            "executionPath",
            "requiredRepairProperties",
            "requiredRegressionCellIds",
        ):
            value = finding.get(field)
            if not _string_list(value) or not value:
                errors.append(f"{prefix}.{field} must be a non-empty string array.")
        for field in ("cellIds", "requiredRegressionCellIds"):
            for cell_id in finding.get(field, []):
                if cell_id not in matrix_ids:
                    errors.append(
                        f"{prefix}.{field} references unknown cell {cell_id!r}."
                    )
        _validate_audit_evidence(finding.get("evidence"), f"{prefix}.evidence", errors)

    all_known_findings = known_finding_ids | new_finding_ids
    clusters = audit.get("duplicateClusters")
    if not isinstance(clusters, list):
        errors.append("Cross-audit duplicateClusters must be an array.")
        clusters = []
    cluster_ids: list[str] = []
    for index, cluster in enumerate(clusters):
        prefix = f"Cross-audit duplicateClusters[{index}]"
        if not isinstance(cluster, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if _is_nonempty_string(cluster.get("id")):
            cluster_ids.append(cluster["id"])
        else:
            errors.append(f"{prefix}.id must be a non-empty string.")
        finding_refs = cluster.get("findingIds")
        if not _string_list(finding_refs) or not finding_refs:
            errors.append(f"{prefix}.findingIds must be a non-empty string array.")
            finding_refs = []
        for finding_id in finding_refs:
            if finding_id not in all_known_findings:
                errors.append(f"{prefix} references unknown finding {finding_id!r}.")
        if cluster.get("relationship") not in {
            "FULL_DUPLICATE_PRIMITIVE",
            "PARTIAL_OVERLAP_RETAIN_DISTINCT_AXES",
            "RELATED_FAMILY_NOT_DUPLICATE",
            "UNIQUE",
        }:
            errors.append(f"{prefix}.relationship is invalid.")
        if not _is_nonempty_string(cluster.get("synthesisRule")):
            errors.append(f"{prefix}.synthesisRule must be a non-empty string.")
    for duplicate in _duplicate_values(cluster_ids):
        errors.append(f"Cross-audit contains duplicate cluster id {duplicate!r}.")

    unresolved = audit.get("unresolvedChallengeIds")
    if not _string_list(unresolved):
        errors.append("Cross-audit unresolvedChallengeIds must be a string array.")
        unresolved = []
    if set(unresolved) != unresolved_by_disposition:
        errors.append(
            "Cross-audit unresolvedChallengeIds must exactly match challenges with "
            "disposition UNRESOLVED."
        )
    recommendation = audit.get("recommendation")
    if recommendation not in {
        "READY_FOR_SYNTHESIS",
        "THIRD_REVIEW_REQUIRED",
        "INCOMPLETE",
    }:
        errors.append("Cross-audit recommendation is invalid.")
    if recommendation == "READY_FOR_SYNTHESIS" and unresolved:
        errors.append("READY_FOR_SYNTHESIS cannot retain unresolved challenges.")
    if recommendation == "THIRD_REVIEW_REQUIRED" and not unresolved:
        errors.append(
            "THIRD_REVIEW_REQUIRED must name at least one unresolved challenge."
        )
    if recommendation == "READY_FOR_SYNTHESIS" and audit.get(
        "peerContinuedAfterFirstBlocker"
    ) is not True and peer_has_blockers:
        errors.append(
            "READY_FOR_SYNTHESIS requires the peer to have continued after its first "
            "blocker."
        )
    if not _is_nonempty_string(audit.get("recommendationRationale")):
        errors.append("Cross-audit recommendationRationale must be a non-empty string.")
    return errors, all_challenge_ids, set(unresolved)


def _validate_audit(args: argparse.Namespace) -> int:
    wave, matrix, errors = _load_current_wave_and_matrix(Path(args.wave))
    warnings: list[str] = []
    own_path = Path(args.own_report)
    peer_path = Path(args.peer_report)
    audit_path = Path(args.audit)
    own_report = _load_json(own_path, "own sealed report")
    peer_report = _load_json(peer_path, "peer sealed report")
    audit = _load_json(audit_path, "cross-audit")
    own_sha = _sha256(own_path.resolve(strict=True))
    peer_sha = _sha256(peer_path.resolve(strict=True))
    if isinstance(own_report, dict):
        report_errors, report_warnings = _validate_report_semantics(
            own_report, matrix, wave
        )
        errors.extend(f"Own report: {error}" for error in report_errors)
        warnings.extend(f"Own report: {warning}" for warning in report_warnings)
    else:
        errors.append("Own sealed report must be a JSON object.")
    if isinstance(peer_report, dict):
        report_errors, report_warnings = _validate_report_semantics(
            peer_report, matrix, wave
        )
        errors.extend(f"Peer report: {error}" for error in report_errors)
        warnings.extend(f"Peer report: {warning}" for warning in report_warnings)
    else:
        errors.append("Peer sealed report must be a JSON object.")
    own_reviewer_id = _report_reviewer_id(own_report)
    peer_reviewer_id = _report_reviewer_id(peer_report)
    if own_sha == peer_sha:
        errors.append("A reciprocal cross-audit requires two distinct sealed reports.")
    if own_reviewer_id is not None and own_reviewer_id == peer_reviewer_id:
        errors.append("A reciprocal cross-audit requires distinct reviewer identities.")
    matrix_ids = {
        cell["cellId"]
        for cell in matrix.get("cells", [])
        if isinstance(cell, dict) and _is_nonempty_string(cell.get("cellId"))
    }
    known_finding_ids = _report_finding_ids(own_report) | _report_finding_ids(
        peer_report
    )
    audit_errors, _, unresolved = _validate_cross_audit_semantics(
        audit,
        wave,
        own_sha,
        peer_sha,
        matrix_ids,
        known_finding_ids,
        expected_mode="RECIPROCAL",
        expected_auditor_id=own_reviewer_id,
        peer_has_blockers=bool(_report_blocking_finding_ids(peer_report)),
    )
    errors.extend(audit_errors)
    print(
        json.dumps(
            {
                "valid": not errors,
                "errors": errors,
                "warnings": warnings,
                "reviewWaveId": wave.get("reviewWaveId"),
                "recommendation": audit.get("recommendation")
                if isinstance(audit, dict)
                else None,
                "unresolvedChallengeIds": sorted(unresolved),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


def _load_synthesis_artifact(
    item: Any, prefix: str, errors: list[str]
) -> tuple[str | None, Path | None, dict[str, Any] | None]:
    if not isinstance(item, dict):
        errors.append(f"{prefix} must be an object.")
        return None, None, None
    artifact_id = item.get("id")
    if not _is_nonempty_string(artifact_id):
        errors.append(f"{prefix}.id must be a non-empty string.")
        artifact_id = None
    if not _is_nonempty_string(item.get("path")):
        errors.append(f"{prefix}.path must be a non-empty string.")
        return artifact_id, None, None
    path = Path(item["path"])
    if not path.is_file():
        errors.append(f"{prefix} file does not exist: {path}")
        return artifact_id, path, None
    data = path.read_bytes()
    if item.get("length") != len(data):
        errors.append(f"{prefix}.length does not match current bytes.")
    digest = hashlib.sha256(data).hexdigest()
    if not isinstance(item.get("sha256"), str) or item["sha256"].lower() != digest:
        errors.append(f"{prefix}.sha256 does not match current bytes.")
    try:
        value = json.loads(data)
    except json.JSONDecodeError as exc:
        errors.append(
            f"{prefix} is invalid JSON at line {exc.lineno}, column {exc.colno}."
        )
        return artifact_id, path, None
    if not isinstance(value, dict):
        errors.append(f"{prefix} JSON must be an object.")
        return artifact_id, path, None
    return artifact_id, path, value


def _validate_synthesis(args: argparse.Namespace) -> int:
    wave, matrix, errors = _load_current_wave_and_matrix(Path(args.wave))
    warnings: list[str] = []
    synthesis = _load_json(Path(args.synthesis), "review synthesis")
    if not isinstance(synthesis, dict):
        errors.append("Review synthesis must be a JSON object.")
        synthesis = {}
    if synthesis.get("schemaVersion") != "batch-review-synthesis.v1":
        errors.append(
            "Review synthesis schemaVersion must be 'batch-review-synthesis.v1'."
        )
    if str(synthesis.get("reviewWaveId", "")).lower() != str(
        wave.get("reviewWaveId", "")
    ).lower():
        errors.append("Review synthesis is not bound to the current review wave.")

    topology = synthesis.get("topology")
    if topology not in {
        "SINGLE_FIXED_POINT",
        "SINGLE_PLUS_NARROW_AUDITOR",
        "TWO_BLIND_RECIPROCAL",
    }:
        errors.append("Review synthesis topology is invalid.")

    lane_items = synthesis.get("laneReports")
    if not isinstance(lane_items, list):
        errors.append("Review synthesis laneReports must be an array.")
        lane_items = []
    lane_reports: dict[str, dict[str, Any]] = {}
    lane_shas: dict[str, str] = {}
    lane_reviewer_ids: dict[str, str] = {}
    for index, item in enumerate(lane_items):
        lane_id, path, report = _load_synthesis_artifact(
            item, f"Review synthesis laneReports[{index}]", errors
        )
        if lane_id and lane_id in lane_reports:
            errors.append(f"Review synthesis contains duplicate lane id {lane_id!r}.")
        elif lane_id and report is not None and path is not None:
            lane_reports[lane_id] = report
            lane_shas[lane_id] = _sha256(path).lower()
            report_errors, report_warnings = _validate_report_semantics(
                report, matrix, wave
            )
            errors.extend(f"Lane {lane_id}: {error}" for error in report_errors)
            warnings.extend(
                f"Lane {lane_id}: {warning}" for warning in report_warnings
            )
            reviewer_id = _report_reviewer_id(report)
            if reviewer_id is not None:
                lane_reviewer_ids[lane_id] = reviewer_id

    audit_items = synthesis.get("auditReports")
    if not isinstance(audit_items, list):
        errors.append("Review synthesis auditReports must be an array.")
        audit_items = []
    audit_reports: dict[str, dict[str, Any]] = {}
    audit_paths: dict[str, Path] = {}
    for index, item in enumerate(audit_items):
        audit_id, audit_path, audit = _load_synthesis_artifact(
            item, f"Review synthesis auditReports[{index}]", errors
        )
        if audit_id and audit_id in audit_reports:
            errors.append(f"Review synthesis contains duplicate audit id {audit_id!r}.")
        elif audit_id and audit is not None and audit_path is not None:
            audit_reports[audit_id] = audit
            audit_paths[audit_id] = audit_path

    overlapping_artifact_ids = set(lane_reports) & set(audit_reports)
    if overlapping_artifact_ids:
        errors.append(
            "Review synthesis artifact ids must be globally unique: "
            + ", ".join(sorted(overlapping_artifact_ids))
        )

    if topology == "SINGLE_FIXED_POINT" and (
        len(lane_reports) != 1 or audit_reports
    ):
        errors.append("SINGLE_FIXED_POINT requires one lane and no audit reports.")
    if topology == "SINGLE_PLUS_NARROW_AUDITOR" and (
        len(lane_reports) != 1 or len(audit_reports) != 1
    ):
        errors.append(
            "SINGLE_PLUS_NARROW_AUDITOR requires one lane and one narrow audit."
        )
    if topology == "TWO_BLIND_RECIPROCAL" and (
        len(lane_reports) != 2 or len(audit_reports) != 2
    ):
        errors.append(
            "TWO_BLIND_RECIPROCAL requires exactly two lanes and two reciprocal audits."
        )
    if topology == "TWO_BLIND_RECIPROCAL":
        if len(set(lane_shas.values())) != len(lane_shas):
            errors.append(
                "TWO_BLIND_RECIPROCAL requires distinct sealed lane report bytes."
            )
        if len(set(lane_reviewer_ids.values())) != len(lane_reviewer_ids):
            errors.append(
                "TWO_BLIND_RECIPROCAL requires distinct reviewer identities."
            )

    matrix_ids = {
        cell["cellId"]
        for cell in matrix.get("cells", [])
        if isinstance(cell, dict) and _is_nonempty_string(cell.get("cellId"))
    }
    required_ids = {
        cell["cellId"]
        for cell in matrix.get("cells", [])
        if isinstance(cell, dict)
        and _is_nonempty_string(cell.get("cellId"))
        and cell.get("required") is True
    }
    lane_finding_ids: set[str] = set()
    finding_blocking: dict[str, bool] = {}
    finding_owner_ids: dict[str, str] = {}
    finding_required_cells: dict[str, set[str]] = {}
    lane_coverage = {
        lane_id: _report_coverage_by_cell(report)
        for lane_id, report in lane_reports.items()
    }
    for lane_id, report in lane_reports.items():
        for finding in report.get("findings", []):
            if not isinstance(finding, dict) or not _is_nonempty_string(
                finding.get("id")
            ):
                continue
            finding_id = finding["id"]
            if finding_id in lane_finding_ids:
                errors.append(
                    f"Finding id {finding_id!r} is duplicated across sealed lanes."
                )
            lane_finding_ids.add(finding_id)
            finding_blocking[finding_id] = finding.get("blocksGate") is True
            finding_owner_ids[finding_id] = lane_id
            finding_required_cells[finding_id] = {
                cell_id
                for cell_id in finding.get("requiredRegressionCellIds", [])
                if isinstance(cell_id, str)
            }

    audit_unresolved: set[str] = set()
    audit_challenge_ids: set[str] = set()
    coverage_challenge_cells: dict[str, set[str]] = {}
    reciprocal_pairs: set[tuple[str, str]] = set()
    lane_sha_values = set(lane_shas.values())
    lane_ids_by_sha = {sha: lane_id for lane_id, sha in lane_shas.items()}
    audit_new_finding_ids: dict[str, set[str]] = {}
    seen_audit_new_finding_ids: set[str] = set()
    audit_recommendations: dict[str, str | None] = {}
    for audit_id, audit in audit_reports.items():
        binding = audit.get("binding") if isinstance(audit, dict) else None
        if not isinstance(binding, dict):
            errors.append(f"Audit {audit_id!r} binding must be an object.")
            continue
        own_sha = str(binding.get("ownReportSha256", "")).lower()
        peer_sha = str(binding.get("peerReportSha256", "")).lower()
        if own_sha not in lane_sha_values or peer_sha not in lane_sha_values:
            errors.append(f"Audit {audit_id!r} is not bound to the synthesis lanes.")
        reciprocal_pairs.add((own_sha, peer_sha))
        own_lane_id = lane_ids_by_sha.get(own_sha)
        peer_lane_id = lane_ids_by_sha.get(peer_sha)
        expected_auditor_id = (
            lane_reviewer_ids.get(own_lane_id)
            if topology == "TWO_BLIND_RECIPROCAL" and own_lane_id is not None
            else None
        )
        expected_mode = (
            "RECIPROCAL"
            if topology == "TWO_BLIND_RECIPROCAL"
            else "NARROW"
            if topology == "SINGLE_PLUS_NARROW_AUDITOR"
            else None
        )
        if topology == "SINGLE_PLUS_NARROW_AUDITOR":
            only_lane_id = next(iter(lane_reports), None)
            only_lane_sha = lane_shas.get(only_lane_id) if only_lane_id else None
            if own_sha != only_lane_sha or peer_sha != only_lane_sha:
                errors.append(
                    f"Audit {audit_id!r} narrow binding must reference the single "
                    "sealed primary report in both report hash fields."
                )
            narrow_auditor_id = (
                audit.get("auditor", {}).get("id")
                if isinstance(audit.get("auditor"), dict)
                else None
            )
            if narrow_auditor_id == lane_reviewer_ids.get(only_lane_id):
                errors.append(
                    f"Audit {audit_id!r} narrow auditor must be independent from "
                    "the primary reviewer."
                )
        peer_has_blockers = bool(
            _report_blocking_finding_ids(lane_reports.get(peer_lane_id, {}))
        )
        audit_errors, challenge_ids, unresolved = _validate_cross_audit_semantics(
            audit,
            wave,
            own_sha,
            peer_sha,
            matrix_ids,
            lane_finding_ids,
            expected_mode=expected_mode,
            expected_auditor_id=expected_auditor_id,
            peer_has_blockers=peer_has_blockers,
        )
        errors.extend(f"Audit {audit_id}: {error}" for error in audit_errors)
        duplicate_challenges = audit_challenge_ids & challenge_ids
        if duplicate_challenges:
            errors.append(
                f"Audit {audit_id!r} reuses challenge ids from another audit: "
                + ", ".join(sorted(duplicate_challenges))
            )
        audit_challenge_ids.update(challenge_ids)
        audit_unresolved.update(unresolved)
        audit_recommendations[audit_id] = audit.get("recommendation")
        for challenge in audit.get("coverageChallenges", []):
            if not isinstance(challenge, dict) or not _is_nonempty_string(
                challenge.get("id")
            ):
                continue
            coverage_challenge_cells.setdefault(challenge["id"], set()).update(
                cell_id
                for cell_id in challenge.get("cellIds", [])
                if isinstance(cell_id, str)
            )
        audit_new_finding_ids[audit_id] = set()
        for finding in audit.get("newFindings", []):
            if isinstance(finding, dict) and _is_nonempty_string(finding.get("id")):
                finding_id = finding["id"]
                if finding_id in seen_audit_new_finding_ids:
                    errors.append(
                        f"Cross-audit finding id {finding_id!r} is duplicated across "
                        "audit reports."
                    )
                seen_audit_new_finding_ids.add(finding_id)
                audit_new_finding_ids[audit_id].add(finding_id)
                finding_blocking[finding_id] = finding.get("blocking") is True
                finding_owner_ids[finding_id] = audit_id
                finding_required_cells[finding_id] = {
                    cell_id
                    for cell_id in finding.get("requiredRegressionCellIds", [])
                    if isinstance(cell_id, str)
                }
    known_finding_ids = lane_finding_ids | seen_audit_new_finding_ids
    blocker_finding_ids = {
        finding_id
        for finding_id, blocking in finding_blocking.items()
        if blocking
    }
    if topology == "TWO_BLIND_RECIPROCAL" and len(lane_sha_values) == 2:
        first, second = sorted(lane_sha_values)
        if {(first, second), (second, first)} - reciprocal_pairs:
            errors.append(
                "TWO_BLIND_RECIPROCAL audits must bind both lane directions exactly."
            )

    closure = synthesis.get("matrixClosure")
    if not isinstance(closure, list):
        errors.append("Review synthesis matrixClosure must be an array.")
        closure = []
    closure_by_id: dict[str, dict[str, Any]] = {}
    referenced_challenges: set[str] = set()
    challenge_cells_in_synthesis: dict[str, set[str]] = {}
    for index, item in enumerate(closure):
        prefix = f"Review synthesis matrixClosure[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        cell_id = item.get("cellId")
        if not _is_nonempty_string(cell_id):
            errors.append(f"{prefix}.cellId must be a non-empty string.")
            continue
        if cell_id in closure_by_id:
            errors.append(f"Review synthesis has duplicate closure cell {cell_id!r}.")
        closure_by_id[cell_id] = item
        if cell_id not in matrix_ids:
            errors.append(f"{prefix} references unknown cell {cell_id!r}.")
        if item.get("status") not in {"SUPPORTED", "NOT_APPLICABLE", "OPEN"}:
            errors.append(f"{prefix}.status is invalid.")
        report_ids = item.get("supportingReportIds")
        if not _string_list(report_ids):
            errors.append(f"{prefix}.supportingReportIds must be a string array.")
            report_ids = []
        else:
            for report_id in report_ids:
                if report_id not in lane_reports and report_id not in audit_reports:
                    errors.append(
                        f"{prefix}.supportingReportIds references unknown report "
                        f"{report_id!r}."
                    )
        if item.get("status") in {"SUPPORTED", "NOT_APPLICABLE"} and not report_ids:
            errors.append(
                f"{prefix} requires at least one supporting report for a closed cell."
            )
        challenge_ids = item.get("challengeIds")
        if not _string_list(challenge_ids):
            errors.append(f"{prefix}.challengeIds must be a string array.")
        else:
            referenced_challenges.update(challenge_ids)
            for challenge_id in challenge_ids:
                challenge_cells_in_synthesis.setdefault(challenge_id, set()).add(
                    cell_id
                )
            for challenge_id in challenge_ids:
                if challenge_id not in audit_challenge_ids:
                    errors.append(
                        f"{prefix}.challengeIds references unknown challenge "
                        f"{challenge_id!r}."
                    )
    if set(closure_by_id) != matrix_ids:
        errors.append(
            "Review synthesis matrixClosure must contain every matrix cell exactly once."
        )
    if audit_challenge_ids - referenced_challenges:
        errors.append(
            "Review synthesis matrixClosure omits audit challenges: "
            + ", ".join(sorted(audit_challenge_ids - referenced_challenges))
        )
    for challenge_id, expected_cells in coverage_challenge_cells.items():
        actual_cells = challenge_cells_in_synthesis.get(challenge_id, set())
        if actual_cells != expected_cells:
            errors.append(
                f"Coverage challenge {challenge_id!r} must be attached to exactly "
                f"its challenged cells: {', '.join(sorted(expected_cells))}."
            )

    clusters = synthesis.get("findingClusters")
    if not isinstance(clusters, list):
        errors.append("Review synthesis findingClusters must be an array.")
        clusters = []
    clustered_findings: set[str] = set()
    accepted_blockers: set[str] = set()
    accepted_audit_support_cells: dict[str, set[str]] = {
        audit_id: set() for audit_id in audit_reports
    }
    cluster_ids: list[str] = []
    for index, cluster in enumerate(clusters):
        prefix = f"Review synthesis findingClusters[{index}]"
        if not isinstance(cluster, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if _is_nonempty_string(cluster.get("id")):
            cluster_ids.append(cluster["id"])
        else:
            errors.append(f"{prefix}.id must be a non-empty string.")
        refs = cluster.get("findingIds")
        if not _string_list(refs) or not refs:
            errors.append(f"{prefix}.findingIds must be a non-empty string array.")
            refs = []
        for finding_id in refs:
            if finding_id in clustered_findings:
                errors.append(
                    f"Review synthesis finding {finding_id!r} appears in more than "
                    "one cluster."
                )
            clustered_findings.add(finding_id)
            if finding_id not in known_finding_ids:
                errors.append(f"{prefix} references unknown finding {finding_id!r}.")
        relationship = cluster.get("relationship")
        if relationship not in {
            "FULL_DUPLICATE_PRIMITIVE",
            "PARTIAL_OVERLAP_RETAIN_DISTINCT_AXES",
            "RELATED_FAMILY_NOT_DUPLICATE",
            "UNIQUE",
        }:
            errors.append(f"{prefix}.relationship is invalid.")
        elif relationship == "UNIQUE" and len(refs) != 1:
            errors.append(f"{prefix} with relationship UNIQUE needs one finding.")
        elif relationship != "UNIQUE" and len(refs) < 2:
            errors.append(
                f"{prefix} with relationship {relationship} needs at least two "
                "findings."
            )
        disposition = cluster.get("disposition")
        if disposition not in {"ACCEPTED", "REJECTED_WITH_EVIDENCE"}:
            errors.append(f"{prefix}.disposition is invalid.")
        blocking = cluster.get("blocking")
        if not isinstance(blocking, bool):
            errors.append(f"{prefix}.blocking must be a boolean.")
        expected_blocking = any(finding_blocking.get(ref, False) for ref in refs)
        if disposition == "ACCEPTED":
            if isinstance(blocking, bool) and blocking != expected_blocking:
                errors.append(
                    f"{prefix}.blocking must preserve the blocking status of its "
                    "accepted member findings."
                )
            if blocking is True:
                accepted_blockers.update(refs)
        _validate_audit_evidence(
            cluster.get("dispositionEvidence"),
            f"{prefix}.dispositionEvidence",
            errors,
        )
        for field in ("repairProperties", "regressionCellIds"):
            value = cluster.get(field)
            if not _string_list(value) or not value:
                errors.append(f"{prefix}.{field} must be a non-empty string array.")
        for cell_id in cluster.get("regressionCellIds", []):
            if cell_id not in matrix_ids:
                errors.append(
                    f"{prefix}.regressionCellIds references unknown cell {cell_id!r}."
                )
        cluster_regression_cells = set(cluster.get("regressionCellIds", []))
        required_member_cells: set[str] = set()
        for finding_id in refs:
            required_member_cells.update(finding_required_cells.get(finding_id, set()))
        missing_member_cells = required_member_cells - cluster_regression_cells
        if missing_member_cells:
            errors.append(
                f"{prefix}.regressionCellIds omits member finding cells: "
                + ", ".join(sorted(missing_member_cells))
            )
        if disposition == "ACCEPTED":
            regression_cells = {
                cell_id
                for cell_id in cluster.get("regressionCellIds", [])
                if cell_id in matrix_ids
            }
            for finding_id in refs:
                owner_id = finding_owner_ids.get(finding_id)
                if owner_id in accepted_audit_support_cells:
                    accepted_audit_support_cells[owner_id].update(regression_cells)
    for duplicate in _duplicate_values(cluster_ids):
        errors.append(f"Review synthesis has duplicate cluster id {duplicate!r}.")
    if known_finding_ids - clustered_findings:
        errors.append(
            "Review synthesis findingClusters omit findings: "
            + ", ".join(sorted(known_finding_ids - clustered_findings))
        )

    for cell_id, item in closure_by_id.items():
        status = item.get("status")
        supporting_ids = item.get("supportingReportIds", [])
        if not _string_list(supporting_ids):
            continue
        supported_by_any = False
        for report_id in supporting_ids:
            if report_id in lane_reports:
                lane_cell = lane_coverage.get(report_id, {}).get(cell_id)
                if status == "SUPPORTED":
                    valid = bool(
                        isinstance(lane_cell, dict)
                        and lane_cell.get("closureSupport") == "SUPPORTED"
                        and lane_cell.get("status")
                        in {"COVERED_NO_FINDING", "FINDING"}
                    )
                elif status == "NOT_APPLICABLE":
                    valid = bool(
                        isinstance(lane_cell, dict)
                        and lane_cell.get("closureSupport") == "NOT_APPLICABLE"
                        and lane_cell.get("status") == "NOT_APPLICABLE"
                    )
                else:
                    valid = True
                if not valid:
                    errors.append(
                        f"Matrix cell {cell_id!r} cites lane {report_id!r}, but that "
                        "lane does not support the synthesized closure."
                    )
                supported_by_any = supported_by_any or valid
            elif report_id in audit_reports:
                valid = bool(
                    status == "SUPPORTED"
                    and cell_id in accepted_audit_support_cells.get(report_id, set())
                )
                if not valid:
                    errors.append(
                        f"Matrix cell {cell_id!r} cites audit {report_id!r} without "
                        "an accepted new finding mapped to that cell."
                    )
                supported_by_any = supported_by_any or valid
        if status in {"SUPPORTED", "NOT_APPLICABLE"} and not supported_by_any:
            errors.append(
                f"Matrix cell {cell_id!r} has no mechanically supported synthesized "
                "closure."
            )

    unresolved = synthesis.get("unresolvedChallengeIds")
    if not _string_list(unresolved):
        errors.append("Review synthesis unresolvedChallengeIds must be a string array.")
        unresolved = []
    unresolved_set = set(unresolved)
    if unresolved_set != audit_unresolved:
        errors.append(
            "Review synthesis unresolvedChallengeIds must exactly match unresolved "
            "audit challenges."
        )
    actual = synthesis.get("actualCandidateVerdict")
    finding_status = synthesis.get("findingSetStatus")
    counterfactual = synthesis.get("counterfactualVerdict")
    third_required = synthesis.get("thirdReviewerRequired")
    if actual not in ACTUAL_VERDICTS:
        errors.append("Review synthesis actualCandidateVerdict is invalid.")
    if finding_status not in {"AUDITED_BATCH_COMPLETE", "INCOMPLETE"}:
        errors.append("Review synthesis findingSetStatus is invalid.")
    if counterfactual not in COUNTERFACTUAL_VERDICTS:
        errors.append("Review synthesis counterfactualVerdict is invalid.")
    if not isinstance(third_required, bool):
        errors.append("Review synthesis thirdReviewerRequired must be a boolean.")
    if not _is_nonempty_string(synthesis.get("rationale")):
        errors.append("Review synthesis rationale must be a non-empty string.")

    open_required = {
        cell_id
        for cell_id in required_ids
        if cell_id not in closure_by_id or closure_by_id[cell_id].get("status") == "OPEN"
    }
    incomplete_lanes = {
        lane_id
        for lane_id, report in lane_reports.items()
        if report.get("findingSetStatus") != "BATCH_COMPLETE"
        or report.get("actualCandidateVerdict") == "INCOMPLETE"
    }
    nonready_audits = {
        audit_id
        for audit_id, recommendation in audit_recommendations.items()
        if recommendation != "READY_FOR_SYNTHESIS"
    }
    if finding_status == "AUDITED_BATCH_COMPLETE":
        if open_required or unresolved_set:
            errors.append(
                "AUDITED_BATCH_COMPLETE requires no open required cell or unresolved "
                "challenge."
            )
        if incomplete_lanes:
            errors.append(
                "AUDITED_BATCH_COMPLETE requires every sealed lane to be complete: "
                + ", ".join(sorted(incomplete_lanes))
            )
        if nonready_audits:
            errors.append(
                "AUDITED_BATCH_COMPLETE requires every selected audit to be ready "
                "for synthesis: "
                + ", ".join(sorted(nonready_audits))
            )
        if third_required is not False:
            errors.append(
                "AUDITED_BATCH_COMPLETE requires thirdReviewerRequired false."
            )
        if actual == "INCOMPLETE":
            errors.append(
                "AUDITED_BATCH_COMPLETE cannot use actualCandidateVerdict INCOMPLETE."
            )
    elif finding_status == "INCOMPLETE" and actual != "INCOMPLETE":
        errors.append(
            "An incomplete audited finding set requires actualCandidateVerdict "
            "INCOMPLETE."
        )
    if unresolved_set and third_required is not True:
        errors.append(
            "Unresolved synthesis challenges require thirdReviewerRequired true."
        )
    if actual == "PASS":
        if accepted_blockers:
            errors.append("Synthesis PASS cannot retain an accepted blocking cluster.")
        if counterfactual != "NOT_NEEDED":
            errors.append("Synthesis PASS requires counterfactualVerdict NOT_NEEDED.")
    if actual == "BLOCKED" and not accepted_blockers:
        errors.append("Synthesis BLOCKED requires an accepted blocking cluster.")
    if actual == "BLOCKED" and counterfactual == "NOT_NEEDED":
        errors.append(
            "Synthesis BLOCKED requires a counterfactual closure result, not "
            "NOT_NEEDED."
        )
    if counterfactual == "PASS_UNDER_ASSUMPTIONS":
        if actual != "BLOCKED":
            errors.append(
                "Synthesis PASS_UNDER_ASSUMPTIONS requires actualCandidateVerdict "
                "BLOCKED."
            )
        if finding_status != "AUDITED_BATCH_COMPLETE":
            errors.append(
                "Synthesis PASS_UNDER_ASSUMPTIONS requires AUDITED_BATCH_COMPLETE."
            )
    if actual == "INCOMPLETE" and counterfactual != "UNRESOLVED":
        errors.append(
            "Synthesis INCOMPLETE requires counterfactualVerdict UNRESOLVED."
        )
    if blocker_finding_ids and not blocker_finding_ids.issubset(clustered_findings):
        errors.append("Synthesis does not disposition every lane blocker.")

    print(
        json.dumps(
            {
                "valid": not errors,
                "errors": errors,
                "warnings": warnings,
                "reviewWaveId": wave.get("reviewWaveId"),
                "actualCandidateVerdict": actual,
                "findingSetStatus": finding_status,
                "thirdReviewerRequired": third_required,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bind and validate batch-complete independent review gates."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bind = subparsers.add_parser(
        "bind", help="Freeze the four review inputs into a hash-bound review wave."
    )
    bind.add_argument("--candidate-manifest", required=True)
    bind.add_argument("--evidence-index", required=True)
    bind.add_argument("--review-plan", required=True)
    bind.add_argument("--coverage-matrix", required=True)
    bind.add_argument("--output", required=True)
    bind.set_defaults(handler=_bind)

    validate = subparsers.add_parser(
        "validate-report",
        help="Validate a reviewer report against a current frozen review wave.",
    )
    validate.add_argument("--wave", required=True)
    validate.add_argument("--report", required=True)
    validate.set_defaults(handler=_validate_report)

    validate_audit = subparsers.add_parser(
        "validate-audit",
        help=(
            "Validate one reciprocal cross-audit against two distinct sealed lane "
            "reports."
        ),
    )
    validate_audit.add_argument("--wave", required=True)
    validate_audit.add_argument("--own-report", required=True)
    validate_audit.add_argument("--peer-report", required=True)
    validate_audit.add_argument("--audit", required=True)
    validate_audit.set_defaults(handler=_validate_audit)

    validate_synthesis = subparsers.add_parser(
        "validate-synthesis",
        help=(
            "Validate final matrix closure and finding synthesis across all sealed "
            "lanes and selected audits."
        ),
    )
    validate_synthesis.add_argument("--wave", required=True)
    validate_synthesis.add_argument("--synthesis", required=True)
    validate_synthesis.set_defaults(handler=_validate_synthesis)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (GateInputError, FileNotFoundError, OSError) as exc:
        print(
            json.dumps(
                {"valid": False, "errors": [str(exc)], "warnings": []},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
