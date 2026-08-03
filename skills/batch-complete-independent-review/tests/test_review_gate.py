import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "review_gate.py"


class ReviewGateCliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.candidate = self._write_json(
            "candidate-manifest.json",
            {"schemaVersion": "candidate-manifest.v1", "files": []},
        )
        self.evidence = self._write_json(
            "evidence-index.json",
            {"schemaVersion": "evidence-index.v1", "receipts": []},
        )
        self.plan = self._write_json(
            "review-plan.json",
            {"schemaVersion": "review-plan.v1", "risk": "L2"},
        )
        self.matrix = self._write_json(
            "coverage-matrix.json",
            {
                "schemaVersion": "batch-review-coverage-matrix.v1",
                "cells": [
                    {
                        "cellId": "authority/commit/windows",
                        "contractId": "authority-single-owner",
                        "entrypoint": "control::commit",
                        "operation": "commit authority-owned state",
                        "lifecyclePhase": "commit",
                        "variant": "windows",
                        "expectedBehavior": "reject stale authority before mutation",
                        "required": True,
                        "requiredTier": "T2",
                    },
                    {
                        "cellId": "authority/rollback/windows",
                        "contractId": "authority-single-owner",
                        "entrypoint": "control::rollback",
                        "operation": "restore authority-owned state",
                        "lifecyclePhase": "rollback",
                        "variant": "windows",
                        "expectedBehavior": "restore only with exact current authority",
                        "required": True,
                        "requiredTier": "T2",
                    },
                ],
            },
        )
        self.wave = self.root / "review-wave.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def _write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=SKILL_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def _bind(self):
        result = self._run(
            "bind",
            "--candidate-manifest",
            self.candidate,
            "--evidence-index",
            self.evidence,
            "--review-plan",
            self.plan,
            "--coverage-matrix",
            self.matrix,
            "--output",
            self.wave,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(self.wave.read_text(encoding="utf-8"))

    def _evidence(self, claim, tier="T2"):
        return {
            "kind": "SOURCE",
            "path": "src/control.rs",
            "locator": "control::operation",
            "claim": claim,
            "tier": tier,
        }

    def _sha256(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _artifact(self, artifact_id, path):
        return {
            "id": artifact_id,
            "path": str(path),
            "length": path.stat().st_size,
            "sha256": self._sha256(path),
        }

    def _second_report(self, first_report):
        payload = json.dumps(first_report)
        payload = payload.replace("reviewer-1", "reviewer-2")
        payload = payload.replace("F-001", "F-002")
        payload = payload.replace("A-001", "A-002")
        return json.loads(payload)

    def _cross_audit(self, wave, own_path, peer_path, own_report, peer_report):
        return {
            "schemaVersion": "batch-review-cross-audit.v1",
            "auditMode": "RECIPROCAL",
            "binding": {
                "reviewWaveId": wave["reviewWaveId"],
                "ownReportSha256": self._sha256(own_path),
                "peerReportSha256": self._sha256(peer_path),
            },
            "auditor": {
                "id": own_report["reviewer"]["id"],
                "independentPass": True,
            },
            "peerContinuedAfterFirstBlocker": peer_report[
                "continuedAfterFirstBlocker"
            ],
            "peerFixedPointStable": peer_report["fixedPoint"]["stable"],
            "coverageChallenges": [],
            "findingChallenges": [],
            "newFindings": [],
            "duplicateClusters": [],
            "unresolvedChallengeIds": [],
            "recommendation": "READY_FOR_SYNTHESIS",
            "recommendationRationale": (
                "The sealed peer lane is ready for union synthesis."
            ),
        }

    def _two_blind_artifacts(self, wave):
        report_a = self._base_report(wave)
        report_b = self._second_report(report_a)
        report_a_path = self._write_json("report-a.json", report_a)
        report_b_path = self._write_json("report-b.json", report_b)
        audit_a = self._cross_audit(
            wave, report_a_path, report_b_path, report_a, report_b
        )
        audit_b = self._cross_audit(
            wave, report_b_path, report_a_path, report_b, report_a
        )
        audit_a_path = self._write_json("audit-a.json", audit_a)
        audit_b_path = self._write_json("audit-b.json", audit_b)
        return {
            "report_a": report_a,
            "report_b": report_b,
            "report_a_path": report_a_path,
            "report_b_path": report_b_path,
            "audit_a": audit_a,
            "audit_b": audit_b,
            "audit_a_path": audit_a_path,
            "audit_b_path": audit_b_path,
        }

    def _two_blind_synthesis(self, wave, artifacts):
        return {
            "schemaVersion": "batch-review-synthesis.v1",
            "reviewWaveId": wave["reviewWaveId"],
            "topology": "TWO_BLIND_RECIPROCAL",
            "laneReports": [
                self._artifact("lane-a", artifacts["report_a_path"]),
                self._artifact("lane-b", artifacts["report_b_path"]),
            ],
            "auditReports": [
                self._artifact("audit-a", artifacts["audit_a_path"]),
                self._artifact("audit-b", artifacts["audit_b_path"]),
            ],
            "matrixClosure": [
                {
                    "cellId": "authority/commit/windows",
                    "status": "SUPPORTED",
                    "supportingReportIds": ["lane-a", "lane-b"],
                    "challengeIds": [],
                },
                {
                    "cellId": "authority/rollback/windows",
                    "status": "SUPPORTED",
                    "supportingReportIds": ["lane-a", "lane-b"],
                    "challengeIds": [],
                },
            ],
            "findingClusters": [
                {
                    "id": "cluster-a",
                    "findingIds": ["F-001"],
                    "relationship": "UNIQUE",
                    "disposition": "ACCEPTED",
                    "dispositionEvidence": [
                        self._evidence("The first blocking primitive is supported.")
                    ],
                    "blocking": True,
                    "repairProperties": [
                        "rollback reacquires and validates current authority"
                    ],
                    "regressionCellIds": [
                        "authority/commit/windows",
                        "authority/rollback/windows",
                    ],
                },
                {
                    "id": "cluster-b",
                    "findingIds": ["F-002"],
                    "relationship": "UNIQUE",
                    "disposition": "ACCEPTED",
                    "dispositionEvidence": [
                        self._evidence("The second blocking primitive is supported.")
                    ],
                    "blocking": True,
                    "repairProperties": [
                        "rollback reacquires and validates current authority"
                    ],
                    "regressionCellIds": [
                        "authority/commit/windows",
                        "authority/rollback/windows",
                    ],
                },
            ],
            "unresolvedChallengeIds": [],
            "actualCandidateVerdict": "BLOCKED",
            "findingSetStatus": "AUDITED_BATCH_COMPLETE",
            "counterfactualVerdict": "PASS_UNDER_ASSUMPTIONS",
            "thirdReviewerRequired": False,
            "rationale": "Both reciprocal lanes and audits reached union closure.",
        }

    def _base_report(self, wave):
        return {
            "schemaVersion": "batch-independent-review-report.v1",
            "binding": {
                "reviewWaveId": wave["reviewWaveId"],
                "candidateManifestSha256": wave["candidateManifest"]["sha256"],
                "evidenceIndexSha256": wave["evidenceIndex"]["sha256"],
                "reviewPlanSha256": wave["reviewPlan"]["sha256"],
                "coverageMatrixSha256": wave["coverageMatrix"]["sha256"],
            },
            "reviewer": {
                "id": "reviewer-1",
                "role": "PRIMARY_FIXED_POINT",
                "model": "independent-reviewer",
                "effort": "high",
                "independentPass": True,
            },
            "actualCandidateVerdict": "BLOCKED",
            "findingSetStatus": "BATCH_COMPLETE",
            "counterfactualVerdict": "PASS_UNDER_ASSUMPTIONS",
            "continuedAfterFirstBlocker": True,
            "coverage": [
                {
                    "cellId": "authority/commit/windows",
                    "status": "FINDING",
                    "closureSupport": "SUPPORTED",
                    "highestEvidenceTier": "T1",
                    "evidence": [
                        self._evidence("The unsafe rollback path is reachable.", "T1")
                    ],
                    "findingIds": ["F-001"],
                },
                {
                    "cellId": "authority/rollback/windows",
                    "status": "COVERED_NO_FINDING",
                    "closureSupport": "SUPPORTED",
                    "highestEvidenceTier": "T2",
                    "evidence": [
                        self._evidence("The sibling path is exact-owner fenced.", "T2")
                    ],
                    "findingIds": [],
                },
            ],
            "findings": [
                {
                    "id": "F-001",
                    "severity": "HIGH",
                    "blocksGate": True,
                    "contractIds": ["authority-single-owner"],
                    "preconditions": ["commit fails after authority is acquired"],
                    "executionPath": ["acquire", "commit", "rollback"],
                    "firstUnsafeOperation": "rollback reuses stale authority",
                    "impact": "rollback can act without current ownership",
                    "evidence": [
                        self._evidence("The rollback uses stale authority.", "T1")
                    ],
                    "siblingCellDisposition": [
                        {
                            "cellId": "authority/rollback/windows",
                            "status": "SAFE_WITH_EVIDENCE",
                            "reason": "separate fenced path was inspected",
                        }
                    ],
                    "requiredRepairProperties": [
                        "rollback reacquires and validates current authority"
                    ],
                    "requiredRegressionCellIds": [
                        "authority/commit/windows",
                        "authority/rollback/windows",
                    ],
                }
            ],
            "assumptions": [
                {
                    "id": "A-001",
                    "findingIds": ["F-001"],
                    "repairPostcondition": (
                        "rollback uses only freshly reacquired, identity-validated authority"
                    ),
                    "affectedCellIds": ["authority/commit/windows"],
                    "reopenedCellIds": ["authority/rollback/windows"],
                    "requiredRegressionCellIds": [
                        "authority/commit/windows",
                        "authority/rollback/windows",
                    ],
                    "conflictsWith": [],
                    "falsificationCondition": (
                        "a rollback mutation can occur with stale authority"
                    ),
                }
            ],
            "verificationGaps": [],
            "fixedPoint": {
                "iterationCount": 2,
                "stable": True,
                "reopenObligations": [
                    {
                        "id": "RO-F-001",
                        "triggerKind": "FINDING",
                        "triggerId": "F-001",
                        "cellIds": [
                            "authority/commit/windows",
                            "authority/rollback/windows",
                        ],
                        "disposition": "REVIEWED",
                        "evidence": [
                            self._evidence(
                                "Both required regression cells were revisited.", "T2"
                            )
                        ],
                    },
                    {
                        "id": "RO-A-001",
                        "triggerKind": "ASSUMPTION",
                        "triggerId": "A-001",
                        "cellIds": ["authority/rollback/windows"],
                        "disposition": "REVIEWED",
                        "evidence": [
                            self._evidence(
                                "The dependent rollback cell was reopened.", "T2"
                            )
                        ],
                    },
                ],
                "adversarialChecks": [
                    {
                        "dimension": dimension,
                        "applicable": True,
                        "completed": True,
                        "note": "The applicable attack was completed.",
                        "evidence": [self._evidence("Attack evidence recorded.", "T2")],
                    }
                    for dimension in (
                        "SIBLING_CALL_SITES",
                        "LIFECYCLE_PHASES",
                        "CURRENT_LIVE_THIRD_STATE",
                        "EVIDENCE_ALTITUDE",
                        "REPAIR_POSTCONDITION_COMPLETENESS",
                    )
                ],
                "unresolvedChallengeIds": [],
            },
            "stopping": {
                "reason": "COVERAGE_COMPLETE",
                "unvisitedRequiredCellIds": [],
                "note": "All required cells were inspected after assumption closure.",
            },
        }

    def _validate(self, report):
        report_path = self._write_json("report.json", report)
        return self._run(
            "validate-report", "--wave", self.wave, "--report", report_path
        )

    def test_bind_creates_hash_bound_review_wave(self):
        wave = self._bind()

        self.assertEqual(wave["schemaVersion"], "batch-review-wave.v1")
        self.assertEqual(
            wave["protocolVersion"], "batch-complete-independent-review/v1"
        )
        self.assertEqual(len(wave["reviewWaveId"]), 64)
        self.assertEqual(wave["coverageMatrix"]["path"], str(self.matrix.resolve()))

    def test_bind_rejects_non_atomic_matrix_cell(self):
        matrix = json.loads(self.matrix.read_text(encoding="utf-8"))
        del matrix["cells"][0]["expectedBehavior"]
        self.matrix = self._write_json("coverage-matrix.json", matrix)

        result = self._run(
            "bind",
            "--candidate-manifest",
            self.candidate,
            "--evidence-index",
            self.evidence,
            "--review-plan",
            self.plan,
            "--coverage-matrix",
            self.matrix,
            "--output",
            self.wave,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expectedBehavior", result.stdout)

    def test_accepts_blocked_report_with_incomplete_evidence_closure(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["findingSetStatus"] = "EVIDENCE_CLOSURE_INCOMPLETE"
        report["counterfactualVerdict"] = "UNRESOLVED"
        report["coverage"][1] = {
            "cellId": "authority/rollback/windows",
            "status": "EVIDENCE_GAP",
            "closureSupport": "WRONG_TIER",
            "highestEvidenceTier": "T1",
            "evidence": [
                self._evidence("Only source-level sibling evidence exists.", "T1")
            ],
            "findingIds": [],
        }
        report["verificationGaps"] = [
            {
                "id": "GAP-T2-ROLLBACK",
                "cellIds": ["authority/rollback/windows"],
                "blocksGate": True,
                "reason": "The required rollback sibling has only T1 evidence.",
                "requiredAction": "Acquire the matrix-required T2 evidence.",
            }
        ]
        report["fixedPoint"]["stable"] = False
        report["fixedPoint"]["unresolvedChallengeIds"] = ["GAP-T2-ROLLBACK"]
        for check in report["fixedPoint"]["adversarialChecks"]:
            if check["dimension"] == "EVIDENCE_ALTITUDE":
                check["completed"] = False
                check["note"] = "The required evidence altitude remains open."
        report["stopping"] = {
            "reason": "EVIDENCE_CLOSURE_INCOMPLETE",
            "unvisitedRequiredCellIds": ["authority/rollback/windows"],
            "note": "A supported blocker exists, but required evidence closure is open.",
        }

        result = self._validate(report)

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["actualCandidateVerdict"], "BLOCKED")
        self.assertEqual(
            payload["findingSetStatus"], "EVIDENCE_CLOSURE_INCOMPLETE"
        )

    def test_accepts_batch_complete_blocked_report_with_synthetic_pass(self):
        wave = self._bind()
        result = self._validate(self._base_report(wave))

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["actualCandidateVerdict"], "BLOCKED")
        self.assertEqual(
            payload["counterfactualVerdict"], "PASS_UNDER_ASSUMPTIONS"
        )

    def test_accepts_actual_pass_only_without_blockers_or_assumptions(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["actualCandidateVerdict"] = "PASS"
        report["counterfactualVerdict"] = "NOT_NEEDED"
        report["continuedAfterFirstBlocker"] = False
        report["coverage"][0]["status"] = "COVERED_NO_FINDING"
        report["coverage"][0]["closureSupport"] = "SUPPORTED"
        report["coverage"][0]["highestEvidenceTier"] = "T2"
        report["coverage"][0]["evidence"] = [
            self._evidence("The commit path is safe at the required tier.", "T2")
        ]
        report["coverage"][0]["findingIds"] = []
        report["findings"] = []
        report["assumptions"] = []
        report["fixedPoint"]["reopenObligations"] = []
        result = self._validate(report)

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["actualCandidateVerdict"], "PASS")

    def test_rejects_actual_pass_when_blocker_and_assumption_exist(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["actualCandidateVerdict"] = "PASS"
        result = self._validate(report)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(
            any("Actual PASS" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_batch_complete_with_unvisited_required_cell(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["coverage"][1]["status"] = "UNVISITED"
        report["coverage"][1]["closureSupport"] = "OPEN"
        report["coverage"][1]["highestEvidenceTier"] = "NONE"
        report["coverage"][1]["evidence"] = []
        report["fixedPoint"]["stable"] = False
        report["stopping"]["unvisitedRequiredCellIds"] = [
            "authority/rollback/windows"
        ]
        result = self._validate(report)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(
            any("BATCH_COMPLETE" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_visited_safe_cell_closed_below_required_evidence_tier(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["coverage"][1]["highestEvidenceTier"] = "T1"
        report["coverage"][1]["evidence"] = [
            self._evidence("Only source-level evidence was gathered.", "T1")
        ]
        result = self._validate(report)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("required tier" in error.lower() for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_batch_complete_when_fixed_point_is_unstable(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["fixedPoint"]["stable"] = False
        result = self._validate(report)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("fixed point" in error.lower() for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_finding_without_complete_reopen_obligation(self):
        wave = self._bind()
        report = self._base_report(wave)
        report["fixedPoint"]["reopenObligations"][0]["cellIds"] = [
            "authority/commit/windows"
        ]
        result = self._validate(report)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("reopen obligation" in error.lower() for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_hash_drift_after_binding(self):
        wave = self._bind()
        report = self._base_report(wave)
        self.candidate.write_text(
            '{"schemaVersion":"candidate-manifest.v1","files":["drift"]}\n',
            encoding="utf-8",
        )
        result = self._validate(report)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(
            any("hash drift" in error.lower() for error in payload["errors"]),
            payload["errors"],
        )

    def test_accepts_hash_bound_reciprocal_cross_audit(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        result = self._run(
            "validate-audit",
            "--wave",
            self.wave,
            "--own-report",
            artifacts["report_a_path"],
            "--peer-report",
            artifacts["report_b_path"],
            "--audit",
            artifacts["audit_a_path"],
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["recommendation"], "READY_FOR_SYNTHESIS")

    def test_rejects_ready_audit_with_unresolved_challenge(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        audit = artifacts["audit_a"]
        audit["coverageChallenges"] = [
            {
                "id": "challenge-1",
                "kind": "WRONG_TIER",
                "cellIds": ["authority/rollback/windows"],
                "challenge": "The claimed closure is below the required tier.",
                "evidence": [self._evidence("Only source evidence exists.", "T1")],
                "disposition": "UNRESOLVED",
                "requiredSynthesisAction": "Acquire T2 evidence or leave the cell open.",
            }
        ]
        audit["unresolvedChallengeIds"] = ["challenge-1"]
        audit_path = self._write_json("audit-a-unresolved.json", audit)
        result = self._run(
            "validate-audit",
            "--wave",
            self.wave,
            "--own-report",
            artifacts["report_a_path"],
            "--peer-report",
            artifacts["report_b_path"],
            "--audit",
            audit_path,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("READY_FOR_SYNTHESIS" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_cross_audit_finding_without_actionable_shape(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        audit = artifacts["audit_a"]
        audit["newFindings"] = [
            {
                "id": "F-AUDIT-001",
                "severity": "HIGH",
                "blocking": True,
                "summary": "A new current-live third-state overwrite is reachable.",
                "evidence": [self._evidence("The unsafe write is reachable.", "T1")],
            }
        ]
        audit_path = self._write_json("audit-a-thin-finding.json", audit)
        result = self._run(
            "validate-audit",
            "--wave",
            self.wave,
            "--own-report",
            artifacts["report_a_path"],
            "--peer-report",
            artifacts["report_b_path"],
            "--audit",
            audit_path,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any(
                "requiredRepairProperties" in error
                or "firstUnsafeOperation" in error
                for error in payload["errors"]
            ),
            payload["errors"],
        )

    def test_accepts_two_blind_reciprocal_synthesis(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        synthesis = self._two_blind_synthesis(wave, artifacts)
        synthesis_path = self._write_json("synthesis.json", synthesis)
        result = self._run(
            "validate-synthesis",
            "--wave",
            self.wave,
            "--synthesis",
            synthesis_path,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["findingSetStatus"], "AUDITED_BATCH_COMPLETE")

    def test_accepts_single_lane_plus_independent_narrow_audit(self):
        wave = self._bind()
        report = self._base_report(wave)
        report_path = self._write_json("primary-report.json", report)
        audit = self._cross_audit(
            wave, report_path, report_path, report, report
        )
        audit["auditMode"] = "NARROW"
        audit["auditor"]["id"] = "coverage-auditor"
        audit_path = self._write_json("narrow-audit.json", audit)
        synthesis = {
            "schemaVersion": "batch-review-synthesis.v1",
            "reviewWaveId": wave["reviewWaveId"],
            "topology": "SINGLE_PLUS_NARROW_AUDITOR",
            "laneReports": [self._artifact("primary", report_path)],
            "auditReports": [self._artifact("narrow-audit", audit_path)],
            "matrixClosure": [
                {
                    "cellId": cell_id,
                    "status": "SUPPORTED",
                    "supportingReportIds": ["primary"],
                    "challengeIds": [],
                }
                for cell_id in (
                    "authority/commit/windows",
                    "authority/rollback/windows",
                )
            ],
            "findingClusters": [
                {
                    "id": "cluster-primary",
                    "findingIds": ["F-001"],
                    "relationship": "UNIQUE",
                    "disposition": "ACCEPTED",
                    "dispositionEvidence": [
                        self._evidence("The primary blocker remains supported.")
                    ],
                    "blocking": True,
                    "repairProperties": [
                        "rollback reacquires and validates current authority"
                    ],
                    "regressionCellIds": [
                        "authority/commit/windows",
                        "authority/rollback/windows",
                    ],
                }
            ],
            "unresolvedChallengeIds": [],
            "actualCandidateVerdict": "BLOCKED",
            "findingSetStatus": "AUDITED_BATCH_COMPLETE",
            "counterfactualVerdict": "PASS_UNDER_ASSUMPTIONS",
            "thirdReviewerRequired": False,
            "rationale": "The primary lane and narrow audit reached closure.",
        }
        synthesis_path = self._write_json("narrow-synthesis.json", synthesis)
        result = self._run(
            "validate-synthesis",
            "--wave",
            self.wave,
            "--synthesis",
            synthesis_path,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue(json.loads(result.stdout)["valid"])

    def test_rejects_audited_batch_complete_with_open_required_cell(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        synthesis = self._two_blind_synthesis(wave, artifacts)
        synthesis["matrixClosure"][1]["status"] = "OPEN"
        synthesis["matrixClosure"][1]["supportingReportIds"] = []
        synthesis_path = self._write_json("synthesis-open.json", synthesis)
        result = self._run(
            "validate-synthesis",
            "--wave",
            self.wave,
            "--synthesis",
            synthesis_path,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("AUDITED_BATCH_COMPLETE" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_synthesis_cluster_without_disposition_evidence(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        synthesis = self._two_blind_synthesis(wave, artifacts)
        del synthesis["findingClusters"][0]["dispositionEvidence"]
        synthesis_path = self._write_json("synthesis-no-disposition-evidence.json", synthesis)
        result = self._run(
            "validate-synthesis",
            "--wave",
            self.wave,
            "--synthesis",
            synthesis_path,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("dispositionEvidence" in error for error in payload["errors"]),
            payload["errors"],
        )

    def test_rejects_two_blind_synthesis_without_reciprocal_direction(self):
        wave = self._bind()
        artifacts = self._two_blind_artifacts(wave)
        synthesis = self._two_blind_synthesis(wave, artifacts)
        synthesis["auditReports"] = synthesis["auditReports"][:1]
        synthesis_path = self._write_json("synthesis-one-audit.json", synthesis)
        result = self._run(
            "validate-synthesis",
            "--wave",
            self.wave,
            "--synthesis",
            synthesis_path,
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(
            any("reciprocal" in error.lower() for error in payload["errors"]),
            payload["errors"],
        )

    def test_malformed_wave_returns_structured_error_instead_of_crashing(self):
        self._write_json("malformed-wave.json", {})
        self._write_json("malformed-report.json", {})
        result = self._run(
            "validate-report",
            "--wave",
            self.root / "malformed-wave.json",
            "--report",
            self.root / "malformed-report.json",
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(payload["errors"])


if __name__ == "__main__":
    unittest.main()
