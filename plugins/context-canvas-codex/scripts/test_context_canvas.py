from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("context_canvas.py")
MCP_SCRIPT = Path(__file__).with_name("context_canvas_mcp.py")
HOOK_INSTALLER_SCRIPT = Path(__file__).with_name("install_context_canvas_hook.py")
PLUGIN_ROOT = SCRIPT.parent.parent
SPEC = importlib.util.spec_from_file_location("context_canvas_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
canvas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canvas)


class ContextCanvasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="context-canvas-codex-test-")
        self.base = Path(self.temp.name)
        self.root = self.base / "data"
        self.environment = mock.patch.dict(
            os.environ,
            {
                canvas.TEST_MODE_ENV: "1",
                canvas.TEST_ROOT_ENV: str(self.root),
            },
            clear=False,
        )
        self.environment.start()
        self.store = canvas.CanvasStore()
        self.session_id = "thread-test-alpha"
        self.canvas_id = canvas.derive_canvas_id(self.session_id)

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def initialize(self, goal: str = "Keep the candidate hash and blockers authoritative") -> None:
        self.store.initialize(self.canvas_id, goal=goal, project_cwd=str(self.base))

    def test_lifecycle_summary_is_scoped_and_read_only(self) -> None:
        self.initialize()
        blocker = self.store.add_node(
            self.canvas_id,
            kind="blocker",
            status_value="active",
            summary="Independent review is still blocked",
        )
        self.store.add_node(
            self.canvas_id,
            kind="decision",
            status_value="done",
            summary="Keep the repository WAL authoritative",
            evidence_pointer="wal.md",
            evidence_sha256="1" * 64,
        )
        self.store.add_node(
            self.canvas_id,
            kind="verification",
            status_value="done",
            summary="Focused Windows regression passed",
            evidence_pointer=r"D:\evidence\receipt.json",
            evidence_sha256="a" * 64,
        )
        self.store.set_status(
            self.canvas_id,
            node_id=blocker["node_id"],
            status_value="superseded",
            evidence_refs=[{"pointer": "blocker-resolution.md", "sha256": "2" * 64}],
        )
        self.store.add_node(
            self.canvas_id,
            kind="blocker",
            status_value="active",
            summary="Natural provider receipt is pending",
        )

        output = canvas.session_start_output(
            {"session_id": self.session_id, "source": "resume", "cwd": "ignored"},
            self.store,
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("Natural provider receipt is pending", context)
        self.assertNotIn("Independent review is still blocked", context)
        self.assertIn("Keep the repository WAL authoritative", context)
        self.assertIn("Focused Windows regression passed", context)
        self.assertIn("untrusted-pointer=", context)
        self.assertNotIn(str(self.base), context)
        self.assertLessEqual(len(context.encode("utf-8")), canvas.MAX_ADDITIONAL_CONTEXT_BYTES)

    def test_resume_hook_does_not_mutate_checkpoint_tree(self) -> None:
        self.initialize()
        self.store.add_node(
            self.canvas_id,
            kind="blocker",
            status_value="active",
            summary="Read-only hook proof",
        )

        def snapshot() -> dict[str, tuple[int, int, bytes]]:
            result: dict[str, tuple[int, int, bytes]] = {}
            for path in sorted(self.root.rglob("*")):
                if path.is_file():
                    metadata = path.stat()
                    result[str(path.relative_to(self.root))] = (
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        path.read_bytes(),
                    )
            return result

        before = snapshot()
        output = canvas.session_start_output(
            {"session_id": self.session_id, "source": "resume"},
            self.store,
        )
        self.assertIn("Read-only hook proof", output["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(snapshot(), before)

    def test_startup_and_missing_resume_do_not_create_data(self) -> None:
        startup = canvas.session_start_output(
            {"session_id": self.session_id, "source": "startup"},
            self.store,
        )
        self.assertIn(self.canvas_id, startup["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", startup)
        self.assertFalse(self.root.exists())

        with mock.patch.dict(os.environ, {canvas.HOOK_DIAGNOSTIC_ENV: "1"}, clear=False):
            diagnostic = canvas.session_start_output(
                {"session_id": self.session_id, "source": "startup"},
                self.store,
            )
        self.assertEqual(
            diagnostic["systemMessage"],
            f"Context Canvas diagnostic: source=startup canvas_id={self.canvas_id}",
        )
        self.assertFalse(self.root.exists())

        resume = canvas.session_start_output(
            {"session_id": self.session_id, "source": "compact"},
            self.store,
        )
        self.assertIn("state=absent", resume["hookSpecificOutput"]["additionalContext"])
        self.assertIn("does not block", resume["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(self.root.exists())

    def test_user_prompt_hook_recovers_identity_without_session_start(self) -> None:
        output = canvas.user_prompt_submit_output(
            {
                "session_id": self.session_id,
                "turn_id": "turn-recovery",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Continue the current task",
            },
            self.store,
        )

        self.assertEqual(
            output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn(self.canvas_id, context)
        self.assertIn("turn binding", context.lower())
        self.assertFalse(self.root.exists(), "identity recovery must remain read-only")

    def test_missing_canvas_binding_is_optional_and_non_governing(self) -> None:
        output = canvas.user_prompt_submit_output(
            {
                "session_id": self.session_id,
                "turn_id": "turn-optional-binding",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Continue without a Canvas",
            },
            self.store,
        )

        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("state=absent", context)
        self.assertIn("does not block", context)
        self.assertNotIn("do not create one automatically", context)
        self.assertNotIn("WAL", context)
        self.assertNotIn("blocker", context.lower())
        self.assertFalse(self.root.exists(), "optional binding must remain read-only")

    def test_explicit_reference_round_trip_search_and_delete(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        secret = "REF_" + "TOKEN_123456789"
        original = ("探索摘要\n" * 128) + "authorization=Bearer " + secret + "\nNEEDLE"
        created_at = datetime(2026, 8, 18, tzinfo=timezone.utc)

        stored = references.put(
            self.canvas_id,
            summary="Large exploration result",
            content=original,
            source="mcp__example__research",
            now=created_at,
        )

        self.assertTrue(stored["created"])
        self.assertGreater(stored["redaction_count"], 0)
        first = references.read(
            self.canvas_id,
            stored["reference_id"],
            offset=0,
            max_bytes=257,
        )
        chunks = [first["chunk"]]
        cursor = first["next_offset"]
        while cursor is not None:
            part = references.read(
                self.canvas_id,
                stored["reference_id"],
                offset=cursor,
                max_bytes=257,
            )
            chunks.append(part["chunk"])
            cursor = part["next_offset"]
        reconstructed = "".join(chunks)
        self.assertNotIn(secret, reconstructed)
        self.assertIn("[REDACTED]", reconstructed)
        self.assertIn("NEEDLE", reconstructed)
        self.assertEqual(
            hashlib.sha256(reconstructed.encode("utf-8")).hexdigest(),
            stored["content_sha256"],
        )
        duplicate = references.put(
            self.canvas_id,
            summary="Large exploration result",
            content=original,
            source="mcp__example__research",
            now=created_at + timedelta(hours=1),
        )
        self.assertFalse(duplicate["created"])
        self.assertEqual(duplicate["created_at"], stored["created_at"])
        with self.assertRaisesRegex(canvas.CanvasError, "too small"):
            references.read(
                self.canvas_id,
                stored["reference_id"],
                offset=0,
                max_bytes=1,
            )

        search = references.search(self.canvas_id, "needle")
        self.assertEqual(search["hits"][0]["reference_id"], stored["reference_id"])
        self.assertIn("NEEDLE", search["hits"][0]["preview"])
        self.assertEqual(search["skipped_count"], 0)

        deleted = references.delete(self.canvas_id, stored["reference_id"])
        self.assertTrue(deleted["deleted"])
        self.assertFalse(references.delete(self.canvas_id, stored["reference_id"])["deleted"])
        with self.assertRaisesRegex(canvas.CanvasError, "not found"):
            references.read(self.canvas_id, stored["reference_id"])

    def test_reference_put_recovers_verified_body_only_interruption(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        original_write_json = canvas._atomic_write_json

        def interrupt_manifest(path: Path, payload: object, *, maximum_bytes: int) -> None:
            if path.name.startswith("ref-") and path.suffix == ".json":
                raise KeyboardInterrupt("simulated stop after body commit")
            original_write_json(path, payload, maximum_bytes=maximum_bytes)

        with mock.patch.object(canvas, "_atomic_write_json", side_effect=interrupt_manifest):
            with self.assertRaisesRegex(KeyboardInterrupt, "simulated stop"):
                references.put(
                    self.canvas_id,
                    summary="Interrupted reference",
                    content="recoverable body NEEDLE",
                    source="test:interrupted-put",
                )

        search_before_retry = references.search(self.canvas_id, "needle")
        self.assertEqual(search_before_retry["hits"], [])
        self.assertEqual(search_before_retry["skipped_count"], 1)
        self.assertEqual(search_before_retry["skipped"][0]["reason"], "incomplete_pair")

        recovered = references.put(
            self.canvas_id,
            summary="Interrupted reference",
            content="recoverable body NEEDLE",
            source="test:interrupted-put",
        )
        self.assertTrue(recovered["created"])
        self.assertEqual(
            references.read(self.canvas_id, recovered["reference_id"])["chunk"],
            "recoverable body NEEDLE",
        )
        self.assertEqual(references.search(self.canvas_id, "needle")["skipped_count"], 0)

        with references._locked(create=False) as reference_root:
            assert reference_root is not None
            manifest_path = references._entry_path(
                reference_root,
                self.canvas_id,
                recovered["reference_id"],
                create=False,
            )
            body_path = references._content_path(
                reference_root,
                self.canvas_id,
                recovered["reference_id"],
                create=False,
            )
            assert manifest_path is not None and body_path is not None
            manifest_path.unlink()
            body_path.write_bytes(canvas.gzip.compress(b"foreign body", mtime=0))
            unproven_bytes = body_path.read_bytes()
        with self.assertRaisesRegex(
            canvas.CorruptCanvasError, "does not match the deterministic retry"
        ):
            references.put(
                self.canvas_id,
                summary="Interrupted reference",
                content="recoverable body NEEDLE",
                source="test:interrupted-put",
            )
        self.assertEqual(body_path.read_bytes(), unproven_bytes)
        self.assertEqual(references.search(self.canvas_id, "needle")["skipped_count"], 1)

    def test_reference_search_returns_digest_bound_unicode_byte_ranges(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        fixtures = (
            ("ASCII", "before ASCII-Needle after", "ascii-needle", "ASCII-Needle"),
            ("CJK", "before 漢字 after", "漢字", "漢字"),
            ("emoji", "before 🙂 after", "🙂", "🙂"),
            ("combining", "before E\u0301 after", "e\u0301", "E\u0301"),
            ("casefold expansion", "before Straße after", "STRASSE", "Straße"),
            ("partial casefold expansion", "before ß after", "s", "ß"),
        )

        for index, (label, content, query, matched_text) in enumerate(fixtures):
            with self.subTest(label=label):
                stored = references.put(
                    self.canvas_id,
                    summary=f"Byte range fixture {index}",
                    content=content,
                    source=f"fixture:{index}",
                )
                search = references.search(self.canvas_id, query)
                hit = next(
                    item
                    for item in search["hits"]
                    if item["reference_id"] == stored["reference_id"]
                )
                hint = hit["read_hint"]
                raw = content.encode("utf-8")
                expected = matched_text.encode("utf-8")
                expected_start = raw.index(expected)
                expected_end = expected_start + len(expected)

                self.assertEqual(
                    hint["schema"],
                    "context-canvas-codex.reference-match-range.v1",
                )
                self.assertEqual(hint["basis"], "unicode_casefold_v1")
                self.assertTrue(hint["unicode_version"])
                self.assertEqual(hint["match_start_byte"], expected_start)
                self.assertEqual(hint["match_end_byte"], expected_end)
                self.assertEqual(raw[expected_start:expected_end], expected)
                self.assertLessEqual(hint["suggested_offset"], expected_start)
                self.assertGreaterEqual(
                    hint["suggested_offset"] + hint["suggested_max_bytes"],
                    expected_end,
                )
                self.assertLessEqual(
                    hint["suggested_max_bytes"], canvas.MAX_REFERENCE_READ_BYTES
                )
                self.assertEqual(
                    hint["source"],
                    {
                        "schema": (
                            "context-canvas-codex.reference-source-receipt.v1"
                        ),
                        "canvas_id": self.canvas_id,
                        "reference_id": stored["reference_id"],
                        "content_sha256": stored["content_sha256"],
                        "total_bytes": len(raw),
                    },
                )

                reread = references.read(
                    self.canvas_id,
                    stored["reference_id"],
                    offset=hint["suggested_offset"],
                    max_bytes=hint["suggested_max_bytes"],
                )
                reread_raw = reread["chunk"].encode("utf-8")
                relative_start = expected_start - hint["suggested_offset"]
                relative_end = expected_end - hint["suggested_offset"]
                self.assertEqual(reread_raw[relative_start:relative_end], expected)

        self.assertEqual(
            references.search(self.canvas_id, "é")["hits"],
            [],
            "search must not silently add Unicode normalization",
        )

    def test_reference_summary_hit_does_not_read_body_for_range_receipt(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        stored = references.put(
            self.canvas_id,
            summary="Unique summary-only token",
            content="This body must not be read for a summary-only hit.",
        )

        with mock.patch.object(
            references,
            "_read_content_unlocked",
            side_effect=AssertionError("summary-only search read the body"),
        ):
            search = references.search(self.canvas_id, "summary-only")

        self.assertEqual(search["hits"][0]["reference_id"], stored["reference_id"])
        self.assertEqual(search["hits"][0]["match_scope"], "summary")
        self.assertIsNone(search["hits"][0]["read_hint"])

    def test_reference_search_range_respects_canvas_and_scan_budget(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        other_canvas_id = canvas.derive_canvas_id("other-reference-canvas")
        stored = references.put(
            other_canvas_id,
            summary="Isolated range fixture",
            content="body-only-range-token",
        )

        self.assertEqual(
            references.search(self.canvas_id, "body-only-range-token")["hits"],
            [],
        )
        with self.assertRaisesRegex(canvas.CanvasError, "not found"):
            references.preview(
                self.canvas_id,
                stored["reference_id"],
                lens="log-v1",
            )
        with mock.patch.object(
            canvas,
            "MAX_REFERENCE_SEARCH_SCAN_BYTES",
            stored["byte_length"] - 1,
        ):
            limited = references.search(other_canvas_id, "body-only-range-token")

        self.assertEqual(limited["hits"], [])
        self.assertEqual(
            limited["skipped"],
            [{"reference_id": stored["reference_id"], "reason": "scan_limit"}],
        )

    def test_reference_log_preview_is_exact_deterministic_and_ephemeral(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        content = (
            "BOOT sequence\r\n"
            + "ordinary noise line\n" * 180
            + "query context before\r\n"
            + "Exact Probe reached 🙂\r\n"
            + "\x1b[31mERROR\x1b[0m worker failed\r\n"
            + '  File "worker.py", line 7, in run\r\n'
            + "    raise RuntimeError('boom')\r\n"
            + "WARNING retry is disabled\n"
            + "ordinary tail noise\r\n" * 120
            + "SHUTDOWN complete\n"
        )
        stored = references.put(
            self.canvas_id,
            summary="Deterministic log lens fixture",
            content=content,
        )
        raw = content.encode("utf-8")

        def data_tree() -> list[tuple[str, str]]:
            return [
                (
                    path.relative_to(self.root).as_posix(),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in sorted(self.root.rglob("*"))
                if path.is_file()
            ]

        before = data_tree()
        first = references.preview(
            self.canvas_id,
            stored["reference_id"],
            lens="log-v1",
            query="Exact Probe",
            max_output_bytes=4096,
        )
        second = references.preview(
            self.canvas_id,
            stored["reference_id"],
            lens="log-v1",
            query="Exact Probe",
            max_output_bytes=4096,
        )

        self.assertEqual(first, second)
        self.assertEqual(before, data_tree(), "preview must not persist derived state")
        self.assertEqual(first["status"], "preview")
        self.assertEqual(first["lens"], {"name": "log", "version": 1})
        self.assertEqual(
            first["source"]["content_sha256"], stored["content_sha256"]
        )
        self.assertLessEqual(len(first["segments"]), 24)
        self.assertNotIn("preview", first, "segments are the only preview payload")
        self.assertEqual(
            first["serialized_bytes"], len(canvas._canonical_snapshot_bytes(first))
        )
        self.assertLessEqual(first["serialized_bytes"], 4096)
        self.assertLess(
            first["serialized_bytes"], first["ordinary_chunk_serialized_bytes"]
        )
        ordinary_same_budget = references.read(
            self.canvas_id,
            stored["reference_id"],
            max_bytes=4096,
        )
        self.assertEqual(
            first["ordinary_chunk_serialized_bytes"],
            len(canvas._canonical_snapshot_bytes(ordinary_same_budget)),
        )

        reason_set: set[str] = set()
        selected_bytes = 0
        coverage: list[tuple[int, int]] = []
        previous_end = 0
        for segment in first["segments"]:
            self.assertGreaterEqual(segment["start_byte"], previous_end)
            self.assertGreater(segment["end_byte"], segment["start_byte"])
            exact = raw[segment["start_byte"] : segment["end_byte"]]
            self.assertEqual(segment["text"].encode("utf-8"), exact)
            previous_end = segment["end_byte"]
            selected_bytes += len(exact)
            reason_set.update(segment["reasons"])
            coverage.append((segment["start_byte"], segment["end_byte"]))
        coverage.extend(
            (item["start_byte"], item["end_byte"])
            for item in first["omitted_ranges"]
        )
        cursor = 0
        for start, end in sorted(coverage):
            self.assertEqual(start, cursor)
            self.assertGreater(end, start)
            cursor = end
        self.assertEqual(cursor, len(raw))
        self.assertEqual(first["selected_bytes"], selected_bytes)
        self.assertEqual(first["omitted_bytes"], len(raw) - selected_bytes)
        self.assertTrue(
            {"query", "error", "stack", "warning", "first", "last"}
            <= reason_set
        )

        ordinary = references.read(self.canvas_id, stored["reference_id"])
        self.assertIn("BOOT sequence", ordinary["chunk"])

    def test_reference_search_results_preview_supports_windows_and_diversity(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        content = (
            "C:\\src\\a.py:10:5:A-FIRST target "
            + "a" * 120
            + "\r\n"
            + "C:\\src\\a.py:11:A-SECOND target "
            + "x" * 1_500
            + "\n"
            + "/src/b.py:3:B-FIRST TARGET "
            + "b" * 120
            + "\n"
            + "not a parseable result: target\n"
        )
        stored = references.put(
            self.canvas_id,
            summary="Search result diversity fixture",
            content=content,
        )

        result = references.preview(
            self.canvas_id,
            stored["reference_id"],
            lens="search-results-v1",
            query="target",
            max_output_bytes=1500,
        )

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["lens"], {"name": "search-results", "version": 1})
        selected = "".join(segment["text"] for segment in result["segments"])
        self.assertIn("C:\\src\\a.py:10:5:A-FIRST target", selected)
        self.assertIn("/src/b.py:3:B-FIRST TARGET", selected)
        self.assertNotIn("A-SECOND", selected)
        self.assertLessEqual(result["serialized_bytes"], 1500)
        self.assertTrue(
            all("query" in segment["reasons"] for segment in result["segments"])
        )

    def test_reference_preview_returns_bounded_statuses_and_validates_inputs(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        small = references.put(
            self.canvas_id,
            summary="Small preview fixture",
            content="ERROR already fits",
        )
        self.assertEqual(
            references.preview(
                self.canvas_id,
                small["reference_id"],
                lens="log-v1",
            )["status"],
            "not_needed",
        )

        unstructured = references.put(
            self.canvas_id,
            summary="Unstructured preview fixture",
            content="plain body with no recognized signal " * 80,
        )
        self.assertEqual(
            references.preview(
                self.canvas_id,
                unstructured["reference_id"],
                lens="log-v1",
                max_output_bytes=1024,
            )["status"],
            "no_signal",
        )
        self.assertEqual(
            references.preview(
                self.canvas_id,
                unstructured["reference_id"],
                lens="search-results-v1",
                query="recognized",
                max_output_bytes=1024,
            )["status"],
            "unsupported_format",
        )

        parseable = references.put(
            self.canvas_id,
            summary="Parseable no-hit fixture",
            content="src/file.py:7:ordinary content\n" * 80,
        )
        self.assertEqual(
            references.preview(
                self.canvas_id,
                parseable["reference_id"],
                lens="search-results-v1",
                query="absent-token",
                max_output_bytes=1024,
            )["status"],
            "no_signal",
        )

        oversized_signal = references.put(
            self.canvas_id,
            summary="Oversized signal fixture",
            content="ERROR " + "z" * 2_000,
        )
        not_smaller = references.preview(
            self.canvas_id,
            oversized_signal["reference_id"],
            lens="log-v1",
            max_output_bytes=1024,
        )
        self.assertEqual(not_smaller["status"], "not_smaller")
        self.assertEqual(not_smaller["segments"], [])

        with self.assertRaisesRegex(canvas.CanvasError, "lens"):
            references.preview(
                self.canvas_id,
                oversized_signal["reference_id"],
                lens="unknown-v1",
            )
        with self.assertRaisesRegex(canvas.CanvasError, "query"):
            references.preview(
                self.canvas_id,
                oversized_signal["reference_id"],
                lens="search-results-v1",
            )
        with self.assertRaisesRegex(canvas.CanvasError, "budget"):
            references.preview(
                self.canvas_id,
                oversized_signal["reference_id"],
                lens="log-v1",
                max_output_bytes=canvas.MAX_REFERENCE_PREVIEW_BYTES + 1,
            )

    def test_reference_store_enforces_its_per_canvas_capacity(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        with mock.patch.object(canvas, "MAX_REFERENCES_PER_CANVAS", 1):
            references.put(
                self.canvas_id,
                summary="First bounded reference",
                content="first",
            )
            with self.assertRaisesRegex(canvas.CanvasError, "per-canvas limit"):
                references.put(
                    self.canvas_id,
                    summary="Second bounded reference",
                    content="second",
                )

    def test_reference_read_rejects_corrupt_content(self) -> None:
        references = canvas.ReferenceStore(root=self.root)
        stored = references.put(
            self.canvas_id,
            summary="Integrity-bound reference",
            content="content that must remain hash-bound",
        )
        content_path = (
            self.root
            / "_references"
            / "canvases"
            / self.canvas_id
            / f"{stored['reference_id']}.txt.gz"
        )
        content_path.write_bytes(b"not-a-gzip-object")

        with self.assertRaisesRegex(canvas.CorruptCanvasError, "unreadable"):
            references.read(self.canvas_id, stored["reference_id"])
        with self.assertRaisesRegex(canvas.CorruptCanvasError, "unreadable"):
            references.preview(
                self.canvas_id,
                stored["reference_id"],
                lens="log-v1",
            )
        search = references.search(self.canvas_id, "must remain")
        self.assertEqual(search["hits"], [])
        self.assertEqual(
            search["skipped"],
            [{"reference_id": stored["reference_id"], "reason": "corrupt_content"}],
        )
        self.assertEqual(search["skipped_count"], 1)

    def test_reopen_mismatch_is_nonfatal_and_read_only(self) -> None:
        self.initialize(goal="Original durable objective")
        canvas_path = self.root / self.canvas_id / "canvas.json"
        before = canvas_path.read_bytes()

        reopened = self.store.initialize(
            self.canvas_id,
            goal="A rephrased objective must not replace stored state",
            project_cwd=str(self.base / "different-workspace"),
            title="Different title",
        )

        self.assertTrue(reopened["ok"])
        self.assertFalse(reopened["created"])
        self.assertFalse(reopened["matched"])
        self.assertEqual(
            {item["field"] for item in reopened["conflicts"]},
            {"goal", "project_cwd", "title"},
        )
        self.assertEqual(canvas_path.read_bytes(), before)

    def test_goal_block_is_rejected_and_legacy_blocked_goal_stays_continuable(self) -> None:
        self.initialize(goal="The objective stays active while blockers are open")
        with self.assertRaisesRegex(canvas.CanvasError, "blocker node"):
            self.store.set_status(
                self.canvas_id,
                node_id="N000001",
                status_value="blocked",
                evidence_refs=[{"pointer": "blocked.md", "sha256": "b" * 64}],
            )

        canvas_path = self.root / self.canvas_id / "canvas.json"
        legacy = json.loads(canvas_path.read_text(encoding="utf-8"))
        legacy["version"] = 2
        for field in (
            "lineage_id",
            "predecessor_canvas_id",
            "predecessor_canvas_sha256",
            "objective_state",
        ):
            legacy.pop(field, None)
        legacy["nodes"][0]["status"] = "blocked"
        legacy["nodes"][0]["evidence_refs"] = [
            {"pointer": "legacy-blocked.md", "sha256": "c" * 64}
        ]
        canvas_path.write_text(json.dumps(legacy), encoding="utf-8")

        loaded = self.store.read(self.canvas_id)
        assert loaded is not None
        self.assertEqual(loaded["objective_state"], "active")
        self.assertEqual(loaded["nodes"][0]["status"], "active")

    def test_continue_creates_hash_bound_lineage_without_mutating_predecessor(self) -> None:
        self.initialize(goal="Carry the semantic task map into a fresh session")
        self.store.add_node(
            self.canvas_id,
            kind="blocker",
            status_value="active",
            summary="Live lifecycle pickup still needs field observation",
        )
        predecessor_path = self.root / self.canvas_id / "canvas.json"
        predecessor_before = predecessor_path.read_bytes()
        successor_id = canvas.derive_canvas_id("thread-test-successor")

        continued = self.store.continue_from(
            successor_id,
            predecessor_canvas_id=self.canvas_id,
        )

        self.assertTrue(continued["created"])
        self.assertEqual(predecessor_path.read_bytes(), predecessor_before)
        successor = self.store.read(successor_id)
        predecessor = self.store.read(self.canvas_id)
        assert successor is not None and predecessor is not None
        self.assertEqual(successor["lineage_id"], predecessor["lineage_id"])
        self.assertEqual(successor["predecessor_canvas_id"], self.canvas_id)
        self.assertEqual(
            successor["predecessor_canvas_sha256"],
            canvas.canvas_sha256(predecessor),
        )
        self.assertEqual(successor["nodes"], predecessor["nodes"])

        listed = self.store.list_canvases(limit=8)
        self.assertEqual(listed["canvases"][0]["canvas_id"], successor_id)
        by_id = {item["canvas_id"]: item for item in listed["canvases"]}
        self.assertEqual(by_id[self.canvas_id]["session_state"], "continued")
        self.assertEqual(by_id[successor_id]["session_state"], "available")
        self.assertTrue(by_id[successor_id]["continuable"])

    def test_lifecycle_summary_is_bounded_to_less_than_five_kibibytes(self) -> None:
        self.initialize(goal="目標" * 190)
        for index in range(8):
            self.store.add_node(
                self.canvas_id,
                kind="blocker",
                status_value="active",
                summary=f"blocker-{index}-" + ("界" * 580),
            )
            self.store.add_node(
                self.canvas_id,
                kind="decision",
                status_value="done",
                summary=f"decision-{index}-" + ("定" * 580),
                evidence_pointer=f"decision-{index}.json",
                evidence_sha256=f"{index:x}" * 64,
            )
        payload = self.store.read(self.canvas_id)
        assert payload is not None
        summary = canvas.render_lifecycle_summary(payload)
        self.assertLessEqual(len(summary.encode("utf-8")), canvas.MAX_ADDITIONAL_CONTEXT_BYTES)
        self.assertIn("task map truncated at safe bound", summary)

    def test_sensitive_sentinel_is_rejected_before_disk_write(self) -> None:
        sentinel = "Authorization: " + "Bearer " + "TEST_TOKEN_DO_NOT_STORE"
        with self.assertRaises(canvas.SecurityBoundaryError):
            self.store.initialize(self.canvas_id, goal=sentinel, project_cwd=str(self.base))
        self.assertFalse(self.root.exists())

        self.initialize()
        with self.assertRaises(canvas.SecurityBoundaryError):
            self.store.add_node(
                self.canvas_id,
                kind="decision",
                status_value="done",
                summary="Safe summary",
                evidence_pointer=sentinel,
                evidence_sha256="b" * 64,
            )
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn("TEST_TOKEN_DO_NOT_STORE", path.read_text(encoding="utf-8", errors="ignore"))

    def test_session_ids_hash_to_collision_free_opaque_ids(self) -> None:
        values = {canvas.derive_canvas_id(f"thread-{index}") for index in range(2_000)}
        self.assertEqual(len(values), 2_000)
        self.assertTrue(all(canvas.CANVAS_ID_RE.fullmatch(value) for value in values))
        self.assertNotEqual(canvas.derive_canvas_id("same"), canvas.derive_canvas_id("Same"))

    def test_default_data_root_is_local_app_data_and_does_not_create_it(self) -> None:
        local_app_data = self.base / "LocalAppData"
        local_app_data.mkdir()
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False):
            os.environ.pop(canvas.TEST_MODE_ENV, None)
            os.environ.pop(canvas.TEST_ROOT_ENV, None)
            expected = local_app_data / "Codex" / canvas.DATA_DIR_NAME
            self.assertEqual(canvas.data_root(), expected)
            self.assertFalse(expected.exists())

    @unittest.skipUnless(os.name == "nt", "Windows ACL cache behavior")
    def test_repeated_reads_reuse_unchanged_acl_verification(self) -> None:
        self.initialize()
        canvas._ACL_VERIFICATION_CACHE.clear()
        canvas._WINDOWS_IDENTITY_CACHE = None
        original = canvas._verify_windows_acl
        calls: list[Path] = []

        def counting_verify(path: Path, account: str) -> None:
            calls.append(path)
            original(path, account)

        with mock.patch.object(canvas, "_verify_windows_acl", side_effect=counting_verify):
            self.store.read(self.canvas_id)
            first_count = len(calls)
            self.store.read(self.canvas_id)
            self.assertEqual(len(calls), first_count)
        self.assertGreaterEqual(first_count, 2)

    @unittest.skipUnless(os.name == "nt", "Windows ACL replacement behavior")
    def test_windows_hardening_replaces_preexisting_explicit_acl(self) -> None:
        directory = self.base / "preexisting-explicit-acl"
        directory.mkdir()
        account, sid = canvas._current_windows_identity()
        seeded = canvas._run_os_command(
            [
                "icacls.exe",
                os.fspath(directory),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(OI)(CI)F",
                "/grant:r",
                "*S-1-5-18:(OI)(CI)F",
            ]
        )
        self.assertEqual(seeded.returncode, 0, seeded.stderr or seeded.stdout)

        canvas._harden_and_verify_directory_acl(directory)
        canvas._verify_windows_acl(directory, account)

    def test_cross_process_writes_keep_all_nodes_and_unique_ids(self) -> None:
        self.initialize()
        environment = os.environ.copy()
        workers: list[subprocess.Popen[str]] = []
        for index in range(8):
            workers.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-I",
                        str(SCRIPT),
                        "add",
                        "--canvas-id",
                        self.canvas_id,
                        "--kind",
                        "decision",
                        "--status",
                        "done",
                        "--summary",
                        f"worker-{index}",
                        "--evidence-pointer",
                        f"worker-{index}.json",
                        "--evidence-sha256",
                        f"{index:x}" * 64,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
                )
            )
        failures = []
        for process in workers:
            stdout, stderr = process.communicate(timeout=60)
            if process.returncode != 0:
                failures.append((process.returncode, stdout, stderr))
        self.assertEqual(failures, [])
        payload = self.store.read(self.canvas_id)
        assert payload is not None
        worker_nodes = [node for node in payload["nodes"] if node["summary"].startswith("worker-")]
        self.assertEqual(len(worker_nodes), 8)
        self.assertEqual(len({node["id"] for node in payload["nodes"]}), len(payload["nodes"]))
        json.loads((self.root / self.canvas_id / "canvas.json").read_text(encoding="utf-8"))

    def test_directory_substitute_fails_closed(self) -> None:
        self.initialize()
        path = self.root / self.canvas_id / "canvas.json"
        path.unlink()
        path.mkdir()
        with self.assertRaises(canvas.SecurityBoundaryError):
            self.store.read(self.canvas_id)

    def test_hard_link_alias_fails_closed(self) -> None:
        self.initialize()
        path = self.root / self.canvas_id / "canvas.json"
        backing = self.root / self.canvas_id / "canvas.backing"
        path.replace(backing)
        os.link(backing, path)
        with self.assertRaises(canvas.SecurityBoundaryError):
            self.store.read(self.canvas_id)

    def test_nonregular_file_substitute_fails_closed_when_supported(self) -> None:
        self.initialize()
        path = self.root / self.canvas_id / "canvas.json"
        path.unlink()
        if os.name == "nt":
            target = self.root / self.canvas_id / "symlink-target.json"
            target.write_text("{}", encoding="utf-8")
            try:
                path.symlink_to(target)
            except OSError:
                def wsl_path(value: Path) -> str:
                    converted = subprocess.run(
                        ["wsl.exe", "-e", "wslpath", "-a", "-u", str(value)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    if converted.returncode != 0 or not converted.stdout.strip():
                        raise OSError("WSL path conversion unavailable")
                    return converted.stdout.strip()

                try:
                    created = subprocess.run(
                        ["wsl.exe", "-e", "ln", "-s", "--", wsl_path(target), wsl_path(path)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except (OSError, subprocess.SubprocessError):
                    self.skipTest("Windows file symlink fixture is unavailable")
                if created.returncode != 0 or not os.path.lexists(path):
                    self.skipTest("Windows file symlink fixture is unavailable")
        else:
            os.mkfifo(path)
        with self.assertRaises(canvas.SecurityBoundaryError):
            self.store.read(self.canvas_id)

    def test_junction_or_symlink_session_alias_fails_closed(self) -> None:
        self.initialize()
        alias_id = canvas.derive_canvas_id("alias-session")
        alias = self.root / alias_id
        target = self.base / "alias-target"
        target.mkdir()
        if os.name == "nt":
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(target)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if result.returncode != 0:
                self.skipTest("Windows junction fixture is unavailable")
        else:
            alias.symlink_to(target, target_is_directory=True)
        try:
            with self.assertRaises(canvas.SecurityBoundaryError):
                self.store.initialize(alias_id, goal="Alias must fail closed")
        finally:
            if os.path.lexists(alias):
                os.rmdir(alias) if os.name == "nt" else alias.unlink()

    def test_invalid_json_fails_closed_without_injection(self) -> None:
        self.initialize()
        path = self.root / self.canvas_id / "canvas.json"
        path.write_text('{"nodes":["MALICIOUS INSTRUCTION"]', encoding="utf-8")
        output = canvas.session_start_output(
            {"session_id": self.session_id, "source": "compact"},
            self.store,
        )
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("state=unavailable", context)
        self.assertIn("does not block", context)
        self.assertNotIn("MALICIOUS INSTRUCTION", context)

    def test_schema_rejects_excess_nodes_and_unknown_fields(self) -> None:
        self.initialize()
        payload = self.store.read(self.canvas_id)
        assert payload is not None
        payload["unexpected"] = True
        with self.assertRaises(canvas.CorruptCanvasError):
            canvas._validate_canvas(payload, self.canvas_id)
        del payload["unexpected"]
        payload["nodes"] = payload["nodes"] * (canvas.MAX_NODES + 1)
        with self.assertRaises(canvas.CorruptCanvasError):
            canvas._validate_canvas(payload, self.canvas_id)

    def test_executable_has_no_network_import_or_url_surface(self) -> None:
        banned_modules = {"socket", "urllib", "http", "requests", "ftplib", "smtplib", "webbrowser"}
        for script in (SCRIPT, MCP_SCRIPT, HOOK_INSTALLER_SCRIPT):
            source = script.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", 1)[0])
            self.assertEqual(imported & banned_modules, set(), script)
            self.assertNotIn("http://", source.lower())
            self.assertNotIn("https://", source.lower())
            self.assertNotIn("urlopen", source)
            self.assertNotIn("create_connection", source)

    def test_hook_cli_emits_valid_schema_and_does_not_create_data(self) -> None:
        hook_input = json.dumps({"session_id": self.session_id, "source": "startup"})
        result = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-session-start"],
            input=hook_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertLessEqual(
            len(output["hookSpecificOutput"]["additionalContext"].encode("utf-8")),
            canvas.MAX_ADDITIONAL_CONTEXT_BYTES,
        )
        self.assertFalse(self.root.exists())

        prompt_sentinel = "PROMPT_SECRET_MUST_NOT_BE_ECHOED_123456"
        prompt_result = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-user-prompt-submit"],
            input=json.dumps(
                {
                    "session_id": self.session_id,
                    "turn_id": "turn-hook-cli",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Bearer " + prompt_sentinel,
                }
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(prompt_result.returncode, 0, prompt_result.stderr)
        prompt_output = json.loads(prompt_result.stdout)
        self.assertEqual(
            prompt_output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )
        self.assertIn(
            self.canvas_id,
            prompt_output["hookSpecificOutput"]["additionalContext"],
        )
        self.assertNotIn(prompt_sentinel, prompt_result.stdout + prompt_result.stderr)
        self.assertFalse(self.root.exists())

    def test_plugin_exposes_turn_binding_session_restore_capture_and_bundled_mcp(self) -> None:
        payload = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload["hooks"]),
            {"SessionStart", "UserPromptSubmit", "PostToolUse"},
        )
        group = payload["hooks"]["SessionStart"]
        self.assertEqual(len(group), 1)
        self.assertEqual(group[0]["matcher"], "^(startup|resume|clear|compact)$")
        handler = group[0]["hooks"][0]
        self.assertEqual(handler["type"], "command")
        self.assertIn("${PLUGIN_ROOT}", handler["command"])
        self.assertIn("$env:PLUGIN_ROOT", handler["commandWindows"])
        self.assertIn(" -I ", handler["command"])
        self.assertIn(" -I ", handler["commandWindows"])
        self.assertEqual(handler["additionalContextLimit"], 5000)
        capture_group = payload["hooks"]["PostToolUse"]
        self.assertEqual(len(capture_group), 1)
        self.assertEqual(capture_group[0]["matcher"], ".*")
        capture_handler = capture_group[0]["hooks"][0]
        self.assertIn("hook-post-tool-use", capture_handler["command"])
        self.assertIn("hook-post-tool-use", capture_handler["commandWindows"])
        self.assertNotIn("additionalContextLimit", capture_handler)
        prompt_group = payload["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(prompt_group), 1)
        self.assertNotIn("matcher", prompt_group[0])
        prompt_handler = prompt_group[0]["hooks"][0]
        self.assertIn("hook-user-prompt-submit", prompt_handler["command"])
        self.assertIn("hook-user-prompt-submit", prompt_handler["commandWindows"])
        self.assertLessEqual(prompt_handler["additionalContextLimit"], 1000)
        mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["context-canvas"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["-B", "-I", "./scripts/context_canvas_mcp.py"])
        self.assertEqual(server["cwd"], ".")
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        default_prompts = manifest["interface"]["defaultPrompt"]
        self.assertEqual(len(default_prompts), 3)
        self.assertIn("when navigation or offload would add value", default_prompts[0])
        self.assertIn("continue", default_prompts[1])
        self.assertIn("references", default_prompts[2])
        agent_config = (
            PLUGIN_ROOT
            / "skills"
            / "context-canvas-checkpoint"
            / "agents"
            / "openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("manual approval", agent_config)
        self.assertIn("/hooks", agent_config)
        self.assertFalse((PLUGIN_ROOT / ".app.json").exists())
        self.assertFalse((PLUGIN_ROOT / "assets").exists())
        readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("codex mcp add context-canvas -- $python -B -I $server", readme)
        self.assertIn("absolute paths for both `command` and the server script", readme)
        self.assertIn("Keep one MCP registration authority", readme)
        self.assertRegex(readme, r"Never\s+leave both registrations active")

    def test_skill_declares_optional_value_triggered_initialization_contract(self) -> None:
        skill = (PLUGIN_ROOT / "skills" / "context-canvas-checkpoint" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("navigation or long-context offload", skill)
        self.assertIn("explicit", skill)
        self.assertNotIn("more than five minutes", skill)
        self.assertNotRegex(skill, r"create a\s+Canvas automatically")
        self.assertIn("manual approval of newly installed hooks", skill)
        self.assertIn("inspect `/hooks`", skill)

    def test_user_hook_installer_preserves_peers_checks_drift_and_uninstalls_exactly(self) -> None:
        codex_home = self.base / "codex-home"
        codex_home.mkdir()
        existing_group = {
            "matcher": "^resume$",
            "hooks": [
                {
                    "type": "command",
                    "command": "python existing-session-hook.py",
                    "statusMessage": "Existing hook",
                }
            ],
        }
        hooks_path = codex_home / "hooks.json"
        hooks_path.write_text(
            json.dumps(
                {
                    "description": "Existing user hooks",
                    "hooks": {"SessionStart": [existing_group]},
                }
            ),
            encoding="utf-8",
        )

        def run(
            action: str,
            expected: int = 0,
            *,
            home: Path = codex_home,
        ) -> tuple[subprocess.CompletedProcess[str], dict]:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-I",
                    str(HOOK_INSTALLER_SCRIPT),
                    action,
                    "--codex-home",
                    str(home),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            self.assertEqual(completed.returncode, expected, completed.stderr or completed.stdout)
            return completed, json.loads(completed.stdout)

        pristine_home = self.base / "pristine-codex-home"
        _, pristine = run("install", home=pristine_home)
        self.assertTrue(pristine["ok"])
        pristine_hooks = json.loads(
            (pristine_home / "hooks.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(pristine_hooks["hooks"]["SessionStart"]), 1)
        self.assertEqual(len(pristine_hooks["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(pristine_hooks["hooks"]["PostToolUse"]), 1)
        run("uninstall", home=pristine_home)

        interrupted_home = self.base / "interrupted-codex-home"
        interrupted_dir = interrupted_home / "context-canvas-codex"
        interrupted_dir.mkdir(parents=True)
        interrupted_script = interrupted_dir / "context_canvas.py"
        interrupted_script.write_bytes(SCRIPT.read_bytes())
        _, recovered = run("install", home=interrupted_home)
        self.assertTrue(recovered["ok"])
        self.assertTrue(recovered["changed"])
        _, recovered_check = run("check", home=interrupted_home)
        self.assertTrue(recovered_check["ok"])

        foreign_interrupted_home = self.base / "foreign-interrupted-codex-home"
        foreign_interrupted_dir = foreign_interrupted_home / "context-canvas-codex"
        foreign_interrupted_dir.mkdir(parents=True)
        foreign_interrupted_script = foreign_interrupted_dir / "context_canvas.py"
        foreign_interrupted_script.write_text("foreign bytes", encoding="utf-8")
        run("install", expected=1, home=foreign_interrupted_home)
        self.assertEqual(
            foreign_interrupted_script.read_text(encoding="utf-8"), "foreign bytes"
        )

        v2_home = self.base / "v2-codex-home"
        run("install", home=v2_home)
        v2_hooks_path = v2_home / "hooks.json"
        v2_hooks = json.loads(v2_hooks_path.read_text(encoding="utf-8"))
        v2_hooks["hooks"]["UserPromptSubmit"] = []
        v2_hooks_path.write_text(json.dumps(v2_hooks), encoding="utf-8")
        v2_manifest_path = v2_home / "context-canvas-codex" / "hook-install.json"
        v2_manifest = json.loads(v2_manifest_path.read_text(encoding="utf-8"))
        v2_manifest["schema"] = "context-canvas-codex-hook-install.v2"
        v2_manifest["handlers_sha256"].pop("UserPromptSubmit")
        v2_manifest_path.write_text(json.dumps(v2_manifest), encoding="utf-8")
        _, migrated_v2 = run("install", home=v2_home)
        self.assertTrue(migrated_v2["changed"])
        self.assertEqual(
            json.loads(v2_manifest_path.read_text(encoding="utf-8"))["schema"],
            "context-canvas-codex-hook-install.v3",
        )
        self.assertEqual(
            len(json.loads(v2_hooks_path.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]),
            1,
        )

        prior_v04_home = self.base / "prior-v04-codex-home"
        run("install", home=prior_v04_home)
        prior_v04_hooks_path = prior_v04_home / "hooks.json"
        prior_v04_hooks = json.loads(prior_v04_hooks_path.read_text(encoding="utf-8"))
        prior_markers = {
            "SessionStart": "Restoring Context Canvas [context-canvas-codex user hook]",
            "UserPromptSubmit": "Refreshing Context Canvas identity [context-canvas-codex user hook]",
            "PostToolUse": "Archiving tool snapshot [context-canvas-codex user hook]",
        }
        for event_name, status_message in prior_markers.items():
            prior_v04_hooks["hooks"][event_name][0]["hooks"][0][
                "statusMessage"
            ] = status_message
        peer_group = {
            "hooks": [
                {
                    "type": "command",
                    "command": "python peer-hook.py",
                    "statusMessage": "Unrelated peer",
                }
            ]
        }
        prior_v04_hooks["hooks"]["UserPromptSubmit"].insert(0, peer_group)
        prior_v04_hooks_path.write_text(json.dumps(prior_v04_hooks), encoding="utf-8")
        prior_v04_manifest_path = (
            prior_v04_home / "context-canvas-codex" / "hook-install.json"
        )
        prior_v04_manifest = json.loads(
            prior_v04_manifest_path.read_text(encoding="utf-8")
        )
        prior_v04_manifest["handlers_sha256"] = {
            event_name: hashlib.sha256(
                (
                    json.dumps(
                        next(
                            group
                            for group in prior_v04_hooks["hooks"][event_name]
                            if group is not peer_group
                        ),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            ).hexdigest()
            for event_name in ("SessionStart", "UserPromptSubmit", "PostToolUse")
        }
        prior_v04_manifest_path.write_text(
            json.dumps(prior_v04_manifest), encoding="utf-8"
        )

        _, upgraded_v04 = run("install", home=prior_v04_home)
        self.assertTrue(upgraded_v04["changed"])
        upgraded_v04_hooks = json.loads(
            prior_v04_hooks_path.read_text(encoding="utf-8")
        )["hooks"]
        self.assertEqual(len(upgraded_v04_hooks["SessionStart"]), 1)
        self.assertEqual(len(upgraded_v04_hooks["UserPromptSubmit"]), 2)
        self.assertEqual(upgraded_v04_hooks["UserPromptSubmit"][0], peer_group)
        self.assertEqual(len(upgraded_v04_hooks["PostToolUse"]), 1)
        for event_name, status_message in (
            ("SessionStart", "Restoring optional Context Canvas map [context-canvas-codex user hook]"),
            ("UserPromptSubmit", "Refreshing optional Canvas binding [context-canvas-codex user hook]"),
            ("PostToolUse", "Checking explicit Canvas capture request [context-canvas-codex user hook]"),
        ):
            owned = [
                group
                for group in upgraded_v04_hooks[event_name]
                if group != peer_group
            ]
            self.assertEqual(owned[0]["hooks"][0]["statusMessage"], status_message)
        run("uninstall", home=prior_v04_home)
        retired_v04_hooks = json.loads(
            prior_v04_hooks_path.read_text(encoding="utf-8")
        )["hooks"]
        self.assertEqual(retired_v04_hooks["SessionStart"], [])
        self.assertEqual(retired_v04_hooks["UserPromptSubmit"], [peer_group])
        self.assertEqual(retired_v04_hooks["PostToolUse"], [])

        ambiguous_home = self.base / "ambiguous-owned-hooks-home"
        run("install", home=ambiguous_home)
        ambiguous_hooks_path = ambiguous_home / "hooks.json"
        ambiguous_hooks = json.loads(
            ambiguous_hooks_path.read_text(encoding="utf-8")
        )
        duplicate_prior = json.loads(
            json.dumps(ambiguous_hooks["hooks"]["SessionStart"][0])
        )
        duplicate_prior["hooks"][0]["statusMessage"] = prior_markers["SessionStart"]
        ambiguous_hooks["hooks"]["SessionStart"].append(duplicate_prior)
        ambiguous_hooks_path.write_text(json.dumps(ambiguous_hooks), encoding="utf-8")
        ambiguous_before = ambiguous_hooks_path.read_bytes()
        run("install", expected=1, home=ambiguous_home)
        self.assertEqual(ambiguous_hooks_path.read_bytes(), ambiguous_before)

        legacy_home = self.base / "legacy-codex-home"
        run("install", home=legacy_home)
        legacy_hooks_path = legacy_home / "hooks.json"
        legacy_hooks = json.loads(legacy_hooks_path.read_text(encoding="utf-8"))
        legacy_hooks["hooks"]["PostToolUse"] = []
        legacy_hooks_path.write_text(json.dumps(legacy_hooks), encoding="utf-8")
        legacy_manifest_path = (
            legacy_home / "context-canvas-codex" / "hook-install.json"
        )
        current_manifest = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
        legacy_manifest_path.write_text(
            json.dumps(
                {
                    "schema": "context-canvas-codex-hook-install.v1",
                    "source_sha256": current_manifest["source_sha256"],
                    "installed_sha256": current_manifest["installed_sha256"],
                    "handler_sha256": hashlib.sha256(
                        (
                            json.dumps(
                                legacy_hooks["hooks"]["SessionStart"][0],
                                ensure_ascii=False,
                                indent=2,
                                sort_keys=True,
                            )
                            + "\n"
                        ).encode("utf-8")
                    ).hexdigest(),
                    "hooks_file": "hooks.json",
                    "installed_script": "context-canvas-codex/context_canvas.py",
                }
            ),
            encoding="utf-8",
        )
        _, migrated = run("install", home=legacy_home)
        self.assertTrue(migrated["changed"])
        migrated_manifest = json.loads(
            legacy_manifest_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            migrated_manifest["schema"], "context-canvas-codex-hook-install.v3"
        )
        self.assertTrue(run("check", home=legacy_home)[1]["ok"])

        bad_legacy_home = self.base / "bad-legacy-codex-home"
        run("install", home=bad_legacy_home)
        bad_legacy_hooks_path = bad_legacy_home / "hooks.json"
        bad_legacy_hooks = json.loads(
            bad_legacy_hooks_path.read_text(encoding="utf-8")
        )
        bad_legacy_hooks["hooks"]["PostToolUse"] = []
        bad_legacy_hooks_path.write_text(
            json.dumps(bad_legacy_hooks), encoding="utf-8"
        )
        bad_legacy_manifest_path = (
            bad_legacy_home / "context-canvas-codex" / "hook-install.json"
        )
        bad_current_manifest = json.loads(
            bad_legacy_manifest_path.read_text(encoding="utf-8")
        )
        bad_legacy_manifest_path.write_text(
            json.dumps(
                {
                    "schema": "context-canvas-codex-hook-install.v1",
                    "source_sha256": bad_current_manifest["source_sha256"],
                    "installed_sha256": bad_current_manifest["installed_sha256"],
                    "handler_sha256": "0" * 64,
                    "hooks_file": "hooks.json",
                    "installed_script": "context-canvas-codex/context_canvas.py",
                }
            ),
            encoding="utf-8",
        )
        run("install", expected=1, home=bad_legacy_home)
        self.assertEqual(
            json.loads(bad_legacy_manifest_path.read_text(encoding="utf-8"))["schema"],
            "context-canvas-codex-hook-install.v1",
        )

        _, installed = run("install")
        self.assertTrue(installed["ok"])
        self.assertTrue(installed["changed"])
        installed_script = codex_home / "context-canvas-codex" / "context_canvas.py"
        self.assertEqual(installed_script.read_bytes(), SCRIPT.read_bytes())
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(hooks["hooks"]["SessionStart"][0], existing_group)
        self.assertEqual(len(hooks["hooks"]["SessionStart"]), 2)
        self.assertEqual(len(hooks["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(hooks["hooks"]["PostToolUse"]), 1)
        handler = hooks["hooks"]["SessionStart"][1]["hooks"][0]
        canonical_script = codex_home.resolve(strict=False) / "context-canvas-codex" / "context_canvas.py"
        self.assertIn(str(canonical_script), handler["commandWindows"])

        _, checked = run("check")
        self.assertTrue(checked["ok"])
        self.assertFalse(checked["changed"])
        _, repeated = run("install")
        self.assertFalse(repeated["changed"])

        installed_script.write_text("tampered", encoding="utf-8")
        _, drifted = run("check", expected=1)
        self.assertFalse(drifted["ok"])
        self.assertIn("drift", " ".join(drifted["errors"]).lower())
        run("uninstall", expected=1)
        self.assertTrue(installed_script.exists())
        run("install")

        _, removed = run("uninstall")
        self.assertTrue(removed["ok"])
        self.assertTrue(removed["changed"])
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(hooks["hooks"]["SessionStart"], [existing_group])
        self.assertEqual(hooks["hooks"]["UserPromptSubmit"], [])
        self.assertEqual(hooks["hooks"]["PostToolUse"], [])
        self.assertFalse(installed_script.exists())

    def test_user_hook_installer_rejects_aliased_install_directory(self) -> None:
        codex_home = self.base / "alias-codex-home"
        codex_home.mkdir()
        foreign = self.base / "foreign-hook-target"
        foreign.mkdir()
        install_dir = codex_home / "context-canvas-codex"
        try:
            install_dir.symlink_to(foreign, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"directory symlink unavailable: {exc}")
            linked = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(install_dir), str(foreign)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if linked.returncode != 0:
                self.skipTest("directory alias fixture is unavailable")

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-I",
                str(HOOK_INSTALLER_SCRIPT),
                "install",
                "--codex-home",
                str(codex_home),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 1, completed.stderr or completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertFalse((foreign / "context_canvas.py").exists())

    def test_manual_cli_init_add_and_show_smoke(self) -> None:
        environment = os.environ.copy()

        def run(*arguments: str) -> dict:
            result = subprocess.run(
                [sys.executable, "-B", "-I", str(SCRIPT), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        initialized = run(
            "init",
            "--canvas-id",
            self.canvas_id,
            "--goal",
            "CLI smoke goal",
            "--cwd",
            str(self.base),
        )
        self.assertTrue(initialized["created"])
        added = run(
            "add",
            "--canvas-id",
            self.canvas_id,
            "--kind",
            "verification",
            "--status",
            "done",
            "--summary",
            "CLI smoke verified",
            "--evidence-pointer",
            "receipt.json",
            "--evidence-sha256",
            "c" * 64,
        )
        self.assertEqual(added["node_id"], "N000002")
        shown = run("show", "--canvas-id", self.canvas_id)
        self.assertFalse(shown["raw_evidence_supported"])
        self.assertEqual(len(shown["canvas"]["nodes"]), 2)

        reference_path = self.base / "cli-preview.log"
        reference_path.write_text(
            "CLI first line\r\n"
            + "ordinary CLI noise\n" * 80
            + "ERROR CLI exact preview marker 🙂\r\n"
            + "CLI last line\n",
            encoding="utf-8",
            newline="",
        )
        stored_reference = run(
            "reference-put",
            "--canvas-id",
            self.canvas_id,
            "--summary",
            "CLI explicit preview fixture",
            "--content-file",
            str(reference_path),
        )
        cli_preview = run(
            "reference-preview",
            "--canvas-id",
            self.canvas_id,
            "--reference-id",
            stored_reference["reference_id"],
            "--lens",
            "log-v1",
            "--max-output-bytes",
            "1024",
        )
        self.assertEqual(cli_preview["status"], "preview")
        self.assertTrue(
            any(
                "ERROR CLI exact preview" in item["text"]
                for item in cli_preview["segments"]
            )
        )

    def test_v1_canvas_migrates_in_memory_then_persists_current_schema_on_mutation(self) -> None:
        self.initialize()
        path = self.root / self.canvas_id / "canvas.json"
        current = json.loads(path.read_text(encoding="utf-8"))
        legacy = {
            "version": 1,
            "canvas_id": current["canvas_id"],
            "project_cwd": current["project_cwd"],
            "created_at": current["created_at"],
            "updated_at": current["updated_at"],
            "nodes": [
                {
                    "id": node["id"],
                    "kind": node["kind"],
                    "status": node["status"],
                    "summary": node["summary"],
                    "evidence": node["evidence_refs"][0] if node["evidence_refs"] else None,
                    "created_at": node["created_at"],
                    "updated_at": node["updated_at"],
                }
                for node in current["nodes"]
            ],
        }
        path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        legacy_bytes = path.read_bytes()

        loaded = self.store.read(self.canvas_id)

        assert loaded is not None
        self.assertEqual(loaded["version"], canvas.CANVAS_VERSION)
        self.assertEqual(loaded["nodes"][0]["evidence_refs"], [])
        self.assertEqual(loaded["nodes"][0]["depends_on"], [])
        self.assertEqual(path.read_bytes(), legacy_bytes, "read-only restore must not rewrite legacy bytes")

        self.store.add_node(
            self.canvas_id,
            kind="plan",
            status_value="planned",
            summary="Persist the upgraded schema only on an intentional mutation",
        )
        persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["version"], canvas.CANVAS_VERSION)
        self.assertEqual(persisted["nodes"][-1]["kind"], "plan")

    def test_factual_terminal_node_requires_hash_bound_evidence(self) -> None:
        self.initialize()

        with self.assertRaisesRegex(canvas.CanvasError, "evidence"):
            self.store.add_node(
                self.canvas_id,
                kind="decision",
                status_value="done",
                summary="An unverified decision must not look complete",
            )

        planned = self.store.add_node(
            self.canvas_id,
            kind="plan",
            status_value="planned",
            summary="Plans may remain explicitly nonfactual",
        )
        self.assertEqual(planned["node_id"], "N000002")

    def test_canonical_factual_terminal_state_without_evidence_is_corrupt(self) -> None:
        self.initialize()
        path = self.root / self.canvas_id / "canvas.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["nodes"][0]["status"] = "done"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(canvas.CorruptCanvasError, "evidence"):
            self.store.read(self.canvas_id)

    def test_upsert_dependencies_search_mermaid_and_closeout_are_pointer_only(self) -> None:
        self.initialize()
        first = self.store.upsert_node(
            self.canvas_id,
            kind="finding",
            status_value="done",
            summary="Persistent MCP avoids one Python launch per canvas operation",
            evidence_refs=[{"pointer": "benchmarks/mcp.json", "sha256": "d" * 64}],
        )
        second = self.store.upsert_node(
            self.canvas_id,
            kind="verification",
            status_value="verify",
            summary="Codex App and CLI use the same canonical store",
            evidence_refs=[{"pointer": "receipts/integration.json", "sha256": "e" * 64}],
            depends_on=[first["node_id"]],
        )
        updated = self.store.upsert_node(
            self.canvas_id,
            node_id=second["node_id"],
            kind="verification",
            status_value="done",
            summary="Codex App and CLI exercised the same canonical store",
            evidence_refs=[{"pointer": "receipts/integration.json", "sha256": "e" * 64}],
            depends_on=[first["node_id"]],
        )

        self.assertFalse(updated["created"])
        result = self.store.search("persistent mcp", canvas_id=self.canvas_id)
        self.assertEqual(result["skipped_count"], 0)
        self.assertEqual(result["hits"][0]["node_id"], first["node_id"])

        payload = self.store.read(self.canvas_id)
        assert payload is not None
        mermaid = canvas.render_mermaid(payload)
        self.assertIn(f"{first['node_id']} --> {second['node_id']}", mermaid)
        self.assertNotIn("raw evidence", mermaid.lower())

        closeout = self.store.closeout(self.canvas_id, write=False)
        self.assertIsNone(closeout["export_path"])
        self.assertIn("receipts/integration.json", closeout["closeout"])
        self.assertIn("sha256=" + ("e" * 64), closeout["closeout"])
        self.assertFalse(closeout["raw_evidence_supported"])

    def test_search_skips_corrupt_canvas_and_never_reads_evidence_targets(self) -> None:
        self.initialize()
        self.store.add_node(
            self.canvas_id,
            kind="finding",
            status_value="done",
            summary="Needle remains searchable from bounded metadata",
            evidence_pointer="missing/needle-evidence.txt",
            evidence_sha256="f" * 64,
        )
        corrupt_id = canvas.derive_canvas_id("corrupt-search")
        self.store.initialize(corrupt_id, goal="Corrupt search fixture")
        corrupt_path = self.root / corrupt_id / "canvas.json"
        corrupt_path.write_text("{not-json", encoding="utf-8")

        result = self.store.search("needle")

        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["skipped_canvases"][0]["canvas_id"], corrupt_id)
        self.assertEqual(len(result["hits"]), 1)
        self.assertFalse((self.base / "missing" / "needle-evidence.txt").exists())

    def test_mcp_stdio_server_exposes_bounded_map_reference_and_snapshot_tools(self) -> None:
        self.assertTrue(MCP_SCRIPT.is_file())
        captured = canvas.SnapshotStore(root=self.root).capture_post_tool_use(
            {
                "session_id": self.session_id,
                "turn_id": "turn-mcp-snapshot",
                "transcript_path": None,
                "cwd": str(self.base),
                "hook_event_name": "PostToolUse",
                "model": "gpt-5.6-sol",
                "permission_mode": "default",
                "tool_name": "mcp__web__open",
                "tool_use_id": "call-mcp-snapshot",
                "tool_input": {"url": "https://example.invalid/mcp-snapshot"},
                "tool_response": {"text": "MCP explicit bounded snapshot body"},
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-B", "-I", str(MCP_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        assert process.stdin is not None and process.stdout is not None

        def request(payload: dict) -> dict:
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            self.assertTrue(line, "MCP server closed stdout before replying")
            return json.loads(line)

        try:
            initialized = request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                }
            )
            self.assertEqual(initialized["result"]["serverInfo"]["name"], "context-canvas-codex")
            self.assertEqual(initialized["result"]["serverInfo"]["version"], "0.6.0")
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            process.stdin.flush()

            resources = request(
                {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}}
            )
            self.assertEqual(resources["result"], {"resources": []})
            templates = request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "resources/templates/list",
                    "params": {},
                }
            )
            self.assertEqual(templates["result"], {"resourceTemplates": []})

            listed = request({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
            names = {item["name"] for item in listed["result"]["tools"]}
            self.assertTrue(
                {
                    "canvas_start",
                    "canvas_continue",
                    "canvas_list",
                    "canvas_upsert_node",
                    "canvas_read",
                    "canvas_search",
                    "canvas_closeout",
                    "snapshot_list",
                    "snapshot_read",
                    "snapshot_capture_next",
                    "snapshot_capture_cancel",
                    "snapshot_pin",
                    "snapshot_gc",
                    "reference_put",
                    "reference_read",
                    "reference_search",
                    "reference_preview",
                    "reference_delete",
                }
                <= names
            )
            capture_tool = next(
                item
                for item in listed["result"]["tools"]
                if item["name"] == "snapshot_capture_next"
            )
            self.assertIn("tool_name", capture_tool["inputSchema"]["required"])
            self.assertEqual(
                capture_tool["inputSchema"]["properties"]["tool_name"]["minLength"], 1
            )
            for request_id, arguments in (
                (41, {"canvas_id": self.canvas_id}),
                (42, {"canvas_id": self.canvas_id, "tool_name": ""}),
            ):
                rejected_capture = request(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {
                            "name": "snapshot_capture_next",
                            "arguments": arguments,
                        },
                    }
                )
                self.assertTrue(rejected_capture["result"]["isError"])
            self.assertFalse(
                canvas.CaptureRequestStore(root=self.root).cancel(self.canvas_id)[
                    "cancelled"
                ]
            )

            started = request(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "canvas_start",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "goal": "MCP parity smoke",
                            "cwd": str(self.base),
                        },
                    },
                }
            )
            self.assertFalse(started["result"]["isError"])
            self.assertTrue(started["result"]["structuredContent"]["created"])

            read = request(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "canvas_read", "arguments": {"canvas_id": self.canvas_id}},
                }
            )
            self.assertFalse(read["result"]["structuredContent"]["raw_evidence_supported"])

            snapshot_list = request(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "snapshot_list",
                        "arguments": {"canvas_id": self.canvas_id, "limit": 10},
                    },
                }
            )
            listed_snapshot = snapshot_list["result"]["structuredContent"]["events"][0]
            self.assertEqual(listed_snapshot["event_id"], captured["event_id"])
            self.assertNotIn("payload", listed_snapshot)
            snapshot_read = request(
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "snapshot_read",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "event_id": captured["event_id"],
                        },
                    },
                }
            )
            manifest_result = snapshot_read["result"]["structuredContent"]
            self.assertNotIn("payload", manifest_result)
            self.assertNotIn(
                "MCP explicit bounded snapshot body",
                json.dumps(manifest_result, ensure_ascii=False),
            )
            snapshot_payload = request(
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "snapshot_read",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "event_id": captured["event_id"],
                            "include_payload": True,
                            "offset": 0,
                            "max_bytes": 4096,
                        },
                    },
                }
            )
            payload_result = snapshot_payload["result"]["structuredContent"]
            self.assertIn("MCP explicit bounded snapshot body", payload_result["payload_chunk"])
            self.assertTrue(payload_result["eof"])

            reference_put = request(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "name": "reference_put",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "summary": "MCP native reference",
                            "content": (
                                "Native reference NEEDLE\n"
                                + "".join(
                                    (
                                        ("ordinary escaped noise \\\" \\\\ line\n" * 5)
                                        + f"ERROR item {index} \\\"quoted\\\" \\\\ path 🙂\n"
                                        + ("ordinary escaped tail \\\" \\\\ line\n" * 5)
                                    )
                                    for index in range(40)
                                )
                            ),
                            "source": "mcp-parity-test",
                        },
                    },
                }
            )
            stored_reference = reference_put["result"]["structuredContent"]
            self.assertTrue(stored_reference["created"])
            reference_read = request(
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "name": "reference_read",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "reference_id": stored_reference["reference_id"],
                            "max_bytes": 128,
                        },
                    },
                }
            )
            self.assertIn(
                "Native reference NEEDLE",
                reference_read["result"]["structuredContent"]["chunk"],
            )
            reference_search = request(
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {
                        "name": "reference_search",
                        "arguments": {"canvas_id": self.canvas_id, "query": "needle"},
                    },
                }
            )
            search_result = reference_search["result"]["structuredContent"]
            self.assertEqual(
                search_result["hits"][0]["reference_id"],
                stored_reference["reference_id"],
            )
            self.assertEqual(
                search_result["hits"][0]["read_hint"]["source"]["content_sha256"],
                stored_reference["content_sha256"],
            )
            self.assertLess(
                len(json.dumps(reference_search, ensure_ascii=False).encode("utf-8")),
                1024 * 1024,
            )
            reference_preview = request(
                {
                    "jsonrpc": "2.0",
                    "id": 13,
                    "method": "tools/call",
                    "params": {
                        "name": "reference_preview",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "reference_id": stored_reference["reference_id"],
                            "lens": "log-v1",
                            "max_output_bytes": 8192,
                        },
                    },
                }
            )
            preview_result = reference_preview["result"]["structuredContent"]
            self.assertEqual(preview_result["status"], "preview")
            self.assertLessEqual(len(preview_result["segments"]), 24)
            self.assertLessEqual(preview_result["serialized_bytes"], 8192)
            self.assertNotIn("preview", preview_result)
            self.assertLess(
                len(json.dumps(reference_preview, ensure_ascii=False).encode("utf-8")),
                1024 * 1024,
            )
            reference_delete = request(
                {
                    "jsonrpc": "2.0",
                    "id": 14,
                    "method": "tools/call",
                    "params": {
                        "name": "reference_delete",
                        "arguments": {
                            "canvas_id": self.canvas_id,
                            "reference_id": stored_reference["reference_id"],
                        },
                    },
                }
            )
            self.assertTrue(reference_delete["result"]["structuredContent"]["deleted"])
            snapshot_pin = request(
                {
                    "jsonrpc": "2.0",
                    "id": 15,
                    "method": "tools/call",
                    "params": {
                        "name": "snapshot_pin",
                        "arguments": {
                            "sha256": captured["sha256"],
                            "reason": "MCP bounded pin smoke",
                        },
                    },
                }
            )
            self.assertTrue(snapshot_pin["result"]["structuredContent"]["pinned"])
            snapshot_gc = request(
                {
                    "jsonrpc": "2.0",
                    "id": 16,
                    "method": "tools/call",
                    "params": {"name": "snapshot_gc", "arguments": {}},
                }
            )
            self.assertFalse(snapshot_gc["result"]["structuredContent"]["apply"])
        finally:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=20)
            stderr = process.stderr.read() if process.stderr is not None else ""
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            if process.returncode != 0:
                self.fail(f"MCP server exited {process.returncode}: {stderr}")


class ContextCanvasSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="context-canvas-snapshot-test-")
        self.base = Path(self.temp.name)
        self.root = self.base / "data"
        self.environment = mock.patch.dict(
            os.environ,
            {
                canvas.TEST_MODE_ENV: "1",
                canvas.TEST_ROOT_ENV: str(self.root),
            },
            clear=False,
        )
        self.environment.start()
        self.session_id = "thread-snapshot-alpha"
        self.canvas_id = canvas.derive_canvas_id(self.session_id)
        self.snapshots = (
            canvas.SnapshotStore(root=self.root) if hasattr(canvas, "SnapshotStore") else None
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def hook_payload(
        self,
        *,
        tool_use_id: str = "call-001",
        tool_name: str = "mcp__web__open",
        response: object | None = None,
    ) -> dict:
        return {
            "session_id": self.session_id,
            "turn_id": "turn-001",
            "transcript_path": None,
            "cwd": str(self.base),
            "hook_event_name": "PostToolUse",
            "model": "gpt-5.6-sol",
            "permission_mode": "default",
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
            "tool_input": {"url": "https://example.invalid/snapshot"},
            "tool_response": response
            if response is not None
            else {"status": 200, "text": "完整歷史資料"},
        }

    def test_snapshot_codec_redacts_recursively_and_round_trips_data_urls(self) -> None:
        sensitive_value = "CODEC_" + "SECRET_123456789"
        binary = b"\x00codec-blob\xff"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(binary).decode(
            "ascii"
        )
        sanitized, redactions, blobs, references = canvas._sanitize_snapshot_payload(
            {
                "schema": canvas.SNAPSHOT_OBJECT_SCHEMA,
                "tool_input": {
                    "author" + "ization": "Bearer " + sensitive_value,
                    "nested": ["Bearer " + sensitive_value, {"image": data_url}],
                },
                "tool_response": None,
            }
        )
        sanitized["blob_references"] = references
        self.assertEqual(redactions, 2)
        self.assertNotIn(sensitive_value, json.dumps(sanitized, ensure_ascii=False))
        self.assertEqual(len(blobs), 1)
        digest, blob = next(iter(blobs.items()))
        self.assertEqual(digest, canvas.hashlib.sha256(binary).hexdigest())
        self.assertEqual(blob["media_type"], "application/octet-stream")
        self.assertEqual(blob["bytes"], binary)
        self.assertEqual(blob["content_policy"], "opaque-uninspected")
        rehydrated = canvas._rehydrate_snapshot_payload(
            sanitized, lambda requested: blobs[requested]["bytes"]
        )
        self.assertEqual(rehydrated["tool_input"]["nested"][1]["image"], data_url)
        uppercase_reference = json.loads(json.dumps(sanitized))
        uppercase_reference["blob_references"][0]["sha256"] = digest.upper()
        with self.assertRaises(canvas.CanvasError):
            canvas._rehydrate_snapshot_payload(
                uppercase_reference, lambda requested: blobs[requested]["bytes"]
            )
        with self.assertRaises(canvas.CorruptCanvasError):
            canvas.SnapshotStore._blob_descriptors(uppercase_reference)
        first = canvas._canonical_snapshot_bytes(sanitized)
        second = canvas._canonical_snapshot_bytes(dict(reversed(list(sanitized.items()))))
        self.assertEqual(first, second)

    def test_snapshot_blob_provenance_preserves_literal_marker_shaped_json(self) -> None:
        binary = b"literal-marker-collision"
        digest = hashlib.sha256(binary).hexdigest()
        data_url = "data:application/octet-stream;base64," + base64.b64encode(
            binary
        ).decode("ascii")
        literal = {
            "$snapshot_blob": {
                "sha256": digest,
                "media_type": "application/octet-stream",
                "byte_length": len(binary),
                "content_policy": "opaque-uninspected",
            }
        }
        captured_at = datetime(2026, 8, 18, tzinfo=timezone.utc)
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-literal-marker-collision",
                response={"literal": literal, "attachment": data_url},
            ),
            retention_days=1,
            now=captured_at,
        )

        event = self.snapshots.read_event(
            self.canvas_id, captured["event_id"], include_payload=True
        )
        self.assertEqual(event["payload"]["tool_response"]["literal"], literal)
        self.assertEqual(event["payload"]["tool_response"]["attachment"], data_url)

        export_path = self.base / "literal-marker-collision.json"
        self.snapshots.export_event(
            self.canvas_id, captured["event_id"], output_path=export_path
        )
        exported = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(exported["tool_response"]["literal"], literal)
        self.assertEqual(exported["tool_response"]["attachment"], data_url)

        self.snapshots.pin(
            captured["sha256"],
            canvas_id=self.canvas_id,
            node_id="N000002",
            reason="literal provenance regression",
        )
        gc_result = self.snapshots.gc(
            now=captured_at + timedelta(days=2), apply=True
        )
        self.assertNotIn(digest, gc_result["candidate_blobs"])
        self.assertEqual(
            self.snapshots.read_event(
                self.canvas_id, captured["event_id"], include_payload=True
            )["payload"]["tool_response"]["literal"],
            literal,
        )

    def test_legacy_blob_markers_fail_closed_while_markerless_payloads_remain_readable(self) -> None:
        markerless = {
            "schema": canvas.LEGACY_SNAPSHOT_OBJECT_SCHEMA,
            "tool_input": {"ordinary": "value"},
            "tool_response": None,
        }
        self.assertEqual(
            canvas._rehydrate_snapshot_payload(markerless, lambda _: b""), markerless
        )

        legacy_blob = {
            "schema": canvas.LEGACY_SNAPSHOT_OBJECT_SCHEMA,
            "tool_input": {
                "attachment": {
                    "$snapshot_blob": {
                        "sha256": "a" * 64,
                        "media_type": "application/octet-stream",
                        "byte_length": 1,
                        "content_policy": "opaque-uninspected",
                    }
                }
            },
            "tool_response": None,
        }
        with self.assertRaisesRegex(
            canvas.CorruptCanvasError, "provenance is ambiguous"
        ):
            canvas._rehydrate_snapshot_payload(legacy_blob, lambda _: b"x")

    def test_textual_data_url_is_redacted_before_blob_persistence(self) -> None:
        sensitive_value = "DATA_URL_" + "TOKEN_123456789"
        raw_text = "api" + "_key=" + sensitive_value
        quoted_json = json.dumps(
            {
                "api" + "_key": sensitive_value,
                "author" + "ization": "Bearer " + sensitive_value,
            },
            separators=(",", ":"),
        )
        fixtures = [
            "data:text/plain;charset=utf-8;base64,"
            + base64.b64encode(raw_text.encode("utf-8")).decode("ascii"),
            "data:application/json;charset=utf-8,"
            + "api_key%3D"
            + sensitive_value,
            "data:application/json;charset=utf-8,"
            + canvas._percent_encode_parameter(quoted_json),
        ]

        for index, data_url in enumerate(fixtures):
            with self.subTest(index=index):
                captured = self.snapshots.capture_post_tool_use(
                    self.hook_payload(
                        tool_use_id=f"call-text-data-{index}",
                        response={"attachment": data_url},
                    )
                )
                event = self.snapshots.read_event(
                    self.canvas_id, captured["event_id"], include_payload=True
                )
                self.assertGreaterEqual(event["manifest"]["redaction_count"], 1)
                descriptor = event["manifest"]["blobs"][0]
                self.assertEqual(descriptor["content_policy"], "text-redacted")
                blob_path = next(
                    path
                    for path in (self.root / "_snapshots" / "blobs" / "sha256").rglob(
                        f"{descriptor['sha256']}.bin.gz"
                    )
                )
                blob_bytes = canvas._read_gzip_bounded(
                    blob_path,
                    maximum_bytes=canvas.MAX_SNAPSHOT_OBJECT_BYTES,
                    label="test snapshot blob",
                )
                self.assertNotIn(sensitive_value.encode("utf-8"), blob_bytes)
                self.assertIn(b"[REDACTED]", blob_bytes)
                restored = event["payload"]["tool_response"]["attachment"]
                self.assertIn(";charset=utf-8;base64,", restored)
                decoded = base64.b64decode(restored.split(",", 1)[1])
                self.assertNotIn(sensitive_value.encode("utf-8"), decoded)
                self.assertIn(b"[REDACTED]", decoded)
                export_path = self.base / f"text-data-{index}.json"
                self.snapshots.export_event(
                    self.canvas_id, captured["event_id"], output_path=export_path
                )
                self.assertNotIn(
                    sensitive_value.encode("utf-8"), export_path.read_bytes()
                )

    def test_quoted_text_secret_assignments_are_redacted_before_storage(self) -> None:
        sensitive_value = "QUOTED_" + "TOKEN_123456789"
        quoted_json = json.dumps(
            {
                "api" + "_key": sensitive_value,
                "pass" + "word": "escaped-quote-\\\"-" + sensitive_value,
            },
            separators=(",", ":"),
        )
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-quoted-secret",
                response={"text": quoted_json},
            )
        )
        event = self.snapshots.read_event(
            self.canvas_id, captured["event_id"], include_payload=True
        )
        self.assertGreaterEqual(event["manifest"]["redaction_count"], 2)
        self.assertNotIn(
            sensitive_value,
            event["payload"]["tool_response"]["text"],
        )
        export_path = self.base / "quoted-secret.json"
        self.snapshots.export_event(
            self.canvas_id, captured["event_id"], output_path=export_path
        )
        self.assertNotIn(sensitive_value.encode("utf-8"), export_path.read_bytes())
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(sensitive_value.encode("utf-8"), path.read_bytes())

    def test_suffix_qualified_text_keys_share_structured_secret_classifier(self) -> None:
        sensitive_value = "SUFFIX_" + "TOKEN_123456789"
        protected_keys = [
            "my_api_key",
            "database-password",
            "serviceAccessToken",
            "session.cookie",
            "custom-secret",
            "tenant/privateKey",
            "legacyPwd",
            "proxyAuthorization",
        ]
        self.assertTrue(all(canvas._snapshot_secret_key(key) for key in protected_keys))
        quoted_text = json.dumps(
            {key: sensitive_value for key in protected_keys},
            separators=(",", ":"),
        )
        data_url = (
            "data:application/json;charset=utf-8,"
            + canvas._percent_encode_parameter(quoted_text)
        )
        semantic_encodings = [
            "service%5Faccess%5Ftoken" + "=" + sensitive_value,
            "access_token[]" + "=" + sensitive_value,
            '{"api\\u005fkey":"' + sensitive_value + '"}',
            '{\\"database_password\\":\\"' + sensitive_value + '\\"}',
            "service%5Faccess%5Ftoken%3D" + sensitive_value,
        ]
        payload = self.hook_payload(
            tool_use_id="call-suffix-keys",
            response={
                "text": quoted_text,
                "attachment": data_url,
                "semantic_encodings": semantic_encodings,
            },
        )
        payload["tool_input"] = {
            "url": (
                "https://example.invalid/?foo=bar&service%5Faccess%5Ftoken"
                + "="
                + sensitive_value
            )
        }
        captured = self.snapshots.capture_post_tool_use(payload)
        event = self.snapshots.read_event(
            self.canvas_id, captured["event_id"], include_payload=True
        )
        self.assertNotIn(
            sensitive_value,
            json.dumps(event["payload"], ensure_ascii=False),
        )
        self.assertNotIn(sensitive_value, event["manifest"]["source_identity"])
        export_path = self.base / "suffix-qualified-secret.json"
        self.snapshots.export_event(
            self.canvas_id, captured["event_id"], output_path=export_path
        )
        self.assertNotIn(sensitive_value.encode("utf-8"), export_path.read_bytes())
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(sensitive_value.encode("utf-8"), path.read_bytes())

    def test_semantic_key_encodings_never_persist_across_capture_export_and_gc(self) -> None:
        sensitive_value = "SEMANTIC_" + "SECRET_123456789"
        secondary_value = "SECONDARY_" + "SECRET_987654321"
        encoded_keys = [
            "database%2Dpassword",
            "service%5Faccess%5Ftoken",
            "service%5faccess%5ftoken",
            "service+access+token",
            "access_token[]",
            "headers[api_key]",
            "credentials[password]",
            "tokens[0][access_token]",
            "token[0]",
            "authorization[1]",
            "password[0]",
            "access_token%3X",
            "api%ZZkey",
            "pass%Gword",
            "private%key",
            "authori%ZZzation",
            "coo%ZZkie",
        ]
        query = "&".join(
            [
                "safe_neighbor=SAFE_QUERY_VALUE",
                *[key + "=" + sensitive_value for key in encoded_keys],
                "public_tokenizer=SAFE_TOKENIZER_VALUE",
            ]
        )
        unicode_escaped_json = (
            '{"api\\u005fkey":' + json.dumps(sensitive_value) + "}"
        )
        escaped_wrapper = json.dumps(
            {"database_password": sensitive_value}, separators=(",", ":")
        ).replace('"', '\\"')
        bracket_assignment = "headers[api_key]" + "=" + sensitive_value
        mixed_assignment = (
            "api_key"
            + "="
            + sensitive_value
            + ";service%5Faccess%5Ftoken%3D"
            + secondary_value
        )
        mixed_bearer = (
            "Bearer FIXTUREVALUE123 "
            + "service%5Faccess%5Ftoken%3D"
            + secondary_value
        )
        stray_percent_mixed = (
            "discount 50% service%5Faccess%5Ftoken%3D" + secondary_value
        )
        invalid_byte_percent_mixed = (
            "opaque%FF service%5Faccess%5Ftoken%3D" + secondary_value
        )
        double_encoded_mixed = (
            "service%255Faccess%255Ftoken%253D" + secondary_value
        )
        semantic_values = [
            key + "=" + sensitive_value for key in encoded_keys
        ] + [
            unicode_escaped_json,
            escaped_wrapper,
            bracket_assignment,
            mixed_assignment,
            mixed_bearer,
            stray_percent_mixed,
            invalid_byte_percent_mixed,
            double_encoded_mixed,
        ]
        data_urls = [
            "data:application/json;charset=utf-8,"
            + canvas._percent_encode_parameter(unicode_escaped_json),
            "data:text/plain;charset=utf-8;base64,"
            + base64.b64encode(escaped_wrapper.encode("utf-8")).decode("ascii"),
            "data:text/plain;charset=utf-8;base64,"
            + base64.b64encode(bracket_assignment.encode("utf-8")).decode("ascii"),
            "data:text/plain;charset=utf-8;base64,"
            + base64.b64encode(mixed_bearer.encode("utf-8")).decode("ascii"),
            "data:text/plain;charset=utf-8;base64,"
            + base64.b64encode(stray_percent_mixed.encode("utf-8")).decode("ascii"),
        ]
        payload = self.hook_payload(
            tool_use_id="call-semantic-key-encodings",
            response={
                "semantic_values": semantic_values,
                "attachments": data_urls,
                "structured_keys": {
                    ("api" + "%5F" + "key"): sensitive_value,
                    ("api" + "%ZZ" + "key"): sensitive_value,
                    ("token" + "[0]"): secondary_value,
                },
            },
        )
        payload["tool_input"] = {"url": "https://example.invalid/?" + query}
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        captured = self.snapshots.capture_post_tool_use(
            payload, retention_days=1, now=captured_at
        )
        event = self.snapshots.read_event(
            self.canvas_id, captured["event_id"], include_payload=True
        )
        serialized = json.dumps(event, ensure_ascii=False).encode("utf-8")
        for forbidden in (sensitive_value, secondary_value):
            self.assertNotIn(forbidden.encode("utf-8"), serialized)
        sanitized_url = event["payload"]["tool_input"]["url"]
        self.assertIn("safe_neighbor=SAFE_QUERY_VALUE", sanitized_url)
        self.assertIn("public_tokenizer=SAFE_TOKENIZER_VALUE", sanitized_url)
        self.assertNotIn(sensitive_value, event["manifest"]["source_identity"])

        export_path = self.base / "semantic-key-encodings.json"
        self.snapshots.export_event(
            self.canvas_id, captured["event_id"], output_path=export_path
        )
        for forbidden in (sensitive_value, secondary_value):
            self.assertNotIn(forbidden.encode("utf-8"), export_path.read_bytes())
        preview = self.snapshots.gc(
            now=captured_at + timedelta(days=2), apply=False
        )
        self.assertIn(
            {"canvas_id": self.canvas_id, "event_id": captured["event_id"]},
            preview["candidate_events"],
        )
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            content = path.read_bytes()
            if path.suffix == ".gz":
                content = canvas.gzip.decompress(content)
            for forbidden in (sensitive_value, secondary_value):
                self.assertNotIn(forbidden.encode("utf-8"), content, str(path))

    def test_semantic_key_encoding_controls_preserve_safe_neighbors(self) -> None:
        controls = [
            "https://example.invalid/?safe_neighbor=SAFE&public_tokenizer=VALUE",
            "headers[accessibility]" + "=" + "public",
            "monkey" + "=" + "banana",
            json.dumps({"api_version": "v1", "tokenizer": "public"}),
        ]
        for control in controls:
            with self.subTest(control=control):
                self.assertEqual(canvas._redact_snapshot_text(control), (control, 0))

    def test_representation_fixed_point_survives_unrelated_percent_text(self) -> None:
        protected_value = "FIXED_POINT_" + "SECRET_123456789"
        fixtures = [
            "discount 50% service%5Faccess%5Ftoken%3D" + protected_value,
            "opaque%FF service%5Faccess%5Ftoken%3D" + protected_value,
            "service%255Faccess%255Ftoken%253D" + protected_value,
        ]
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                redacted, redaction_count = canvas._redact_snapshot_text(fixture)
                self.assertGreaterEqual(redaction_count, 1)
                self.assertNotIn(protected_value, redacted)

        for key in ("api%5Fkey", "api%ZZkey", "token[0]", "authorization[1]"):
            with self.subTest(key=key):
                sanitized, redaction_count, blobs, references = (
                    canvas._sanitize_snapshot_payload({key: protected_value})
                )
                self.assertEqual(sanitized[key], "[REDACTED]")
                self.assertEqual(redaction_count, 1)
                self.assertEqual(blobs, {})
                self.assertEqual(references, [])

    def test_redacted_mime_parameters_round_trip_and_do_not_poison_gc(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        named_secret = "MIME_" + "TOKEN_123456789"
        patterned_secret = "github" + "_pat_" + "FIXTURETOKEN123456789"
        prefixed_secret = "ghp" + "_FIXTURETOKEN123456789"
        suffixed_secret = "sk" + "-FIXTURETOKEN123456789"
        embedded_secret = "xoxb" + "-FIXTURETOKEN123456789"
        fixtures = [
            (
                named_secret,
                "data:text/plain;"
                + ("api" + "_key")
                + "="
                + named_secret
                + ",hello",
            ),
            (
                patterned_secret,
                "data:text/plain;label=" + patterned_secret + ",hello",
            ),
            (
                prefixed_secret,
                "data:text/plain;label=x-" + prefixed_secret + ",hello",
            ),
            (
                suffixed_secret,
                "data:text/plain;label=" + suffixed_secret + ".suffix,hello",
            ),
            (
                embedded_secret,
                "data:text/plain;label=prefix-"
                + embedded_secret
                + ".tail,hello",
            ),
        ]
        captured_events: list[dict] = []
        for index, (secret, data_url) in enumerate(fixtures):
            with self.subTest(index=index):
                captured = self.snapshots.capture_post_tool_use(
                    self.hook_payload(
                        tool_use_id=f"call-mime-redaction-{index}",
                        response={"attachment": data_url},
                    ),
                    retention_days=1,
                    now=captured_at,
                )
                captured_events.append(captured)
                event = self.snapshots.read_event(
                    self.canvas_id, captured["event_id"], include_payload=True
                )
                self.assertGreaterEqual(event["manifest"]["redaction_count"], 1)
                descriptor = event["manifest"]["blobs"][0]
                self.assertIn("=%5BREDACTED%5D", descriptor["media_type"])
                restored = event["payload"]["tool_response"]["attachment"]
                self.assertIn("=%5BREDACTED%5D;base64,", restored)
                self.assertNotIn(secret, restored)
                export_path = self.base / f"mime-redaction-{index}.json"
                self.snapshots.export_event(
                    self.canvas_id, captured["event_id"], output_path=export_path
                )
                self.assertNotIn(secret.encode("utf-8"), export_path.read_bytes())

        preview = self.snapshots.gc(
            now=captured_at + timedelta(days=2), apply=False
        )
        self.assertEqual(preview["candidate_event_count"], len(captured_events))
        self.assertEqual(
            {item["event_id"] for item in preview["candidate_events"]},
            {item["event_id"] for item in captured_events},
        )
        for path in self.root.rglob("*"):
            if path.is_file():
                for secret, _ in fixtures:
                    self.assertNotIn(secret.encode("utf-8"), path.read_bytes())

    def test_malformed_or_unsupported_data_url_aborts_whole_capture(self) -> None:
        fixtures = [
            "data:text/plain;charset=\"utf-8\",secret",
            "data:text/plain;base64;charset=utf-8,c2VjcmV0",
            "data:text/plain,secret%ZZ",
            "data:;base64,%%%",
        ]
        for index, data_url in enumerate(fixtures):
            with self.subTest(index=index):
                with self.assertRaises(canvas.CanvasError):
                    self.snapshots.capture_post_tool_use(
                        self.hook_payload(
                            tool_use_id=f"call-invalid-data-{index}",
                            response={"attachment": data_url},
                        )
                    )
        snapshot_root = self.root / "_snapshots"
        self.assertFalse(
            snapshot_root.exists()
            and any(
                path.is_file()
                for child in ("events", "objects", "blobs")
                for path in (snapshot_root / child).rglob("*")
            )
        )

    def test_full_sanitized_round_trip_extracts_blob_and_never_persists_secret(self) -> None:
        sensitive_value = "TEST_" + "TOKEN_DO_NOT_STORE_123456789"
        binary = b"\x00snapshot-image\xff"
        data_url = "data:image/png;base64," + base64.b64encode(binary).decode("ascii")
        payload = self.hook_payload(
            response={
                "text": "完整歷史資料",
                "author" + "ization": "Bearer " + sensitive_value,
                "nested": [data_url, {"pass" + "word": sensitive_value}],
            }
        )
        captured = self.snapshots.capture_post_tool_use(payload)

        self.assertEqual(captured["capture_status"], "stored")
        self.assertRegex(captured["snapshot_uri"], r"^snapshot://sha256/[0-9a-f]{64}$")
        event = self.snapshots.read_event(
            self.canvas_id, captured["event_id"], include_payload=True
        )
        self.assertFalse(event["manifest"]["truncated"])
        self.assertEqual(event["manifest"]["fidelity"], "codex-post-tool-use-model-facing")
        self.assertEqual(
            event["manifest"]["sensitivity_class"], "sanitized-with-opaque-media"
        )
        self.assertGreaterEqual(event["manifest"]["redaction_count"], 2)
        self.assertEqual(event["payload"]["tool_response"]["text"], "完整歷史資料")
        self.assertEqual(event["payload"]["tool_response"]["nested"][0], data_url)
        exported_path = self.base / "exported-snapshot.json"
        exported = self.snapshots.export_event(
            self.canvas_id, captured["event_id"], output_path=exported_path
        )
        self.assertEqual(Path(exported["output_path"]), exported_path)
        exported_payload = json.loads(exported_path.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload["tool_response"]["nested"][0], data_url)
        self.assertNotIn(sensitive_value, exported_path.read_text(encoding="utf-8"))
        cli_export_path = self.base / "cli-exported-snapshot.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-I",
                str(SCRIPT),
                "snapshot-export",
                "--canvas-id",
                self.canvas_id,
                "--event-id",
                captured["event_id"],
                "--output",
                str(cli_export_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt"
            else 0,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(cli_export_path.read_text(encoding="utf-8")), exported_payload
        )
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(sensitive_value.encode("utf-8"), path.read_bytes(), path)

    def test_content_addressed_dedupe_and_event_idempotency(self) -> None:
        first_payload = self.hook_payload(response={"text": "same result"})
        first = self.snapshots.capture_post_tool_use(first_payload)
        repeated = self.snapshots.capture_post_tool_use(first_payload)
        second_payload = self.hook_payload(
            tool_use_id="call-002", response={"text": "same result"}
        )
        second = self.snapshots.capture_post_tool_use(second_payload)

        self.assertEqual(first["event_id"], repeated["event_id"])
        self.assertEqual(first["sha256"], repeated["sha256"])
        self.assertFalse(first["deduplicated"])
        self.assertTrue(repeated["deduplicated"])
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual(first["sha256"], second["sha256"])
        objects = list((self.root / "_snapshots" / "objects" / "sha256").rglob("*.json.gz"))
        self.assertEqual(len(objects), 1)

    def test_warm_snapshot_capture_revalidates_private_root_acl_once(self) -> None:
        self.snapshots.capture_post_tool_use(
            self.hook_payload(tool_use_id="call-acl-prime", response={"text": "prime"})
        )
        canvas._ACL_VERIFICATION_CACHE.clear()
        with mock.patch.object(
            canvas, "_verify_directory_acl", wraps=canvas._verify_directory_acl
        ) as verify_acl:
            self.snapshots.capture_post_tool_use(
                self.hook_payload(
                    tool_use_id="call-acl-warm", response={"text": "warm"}
                )
            )
        self.assertEqual(verify_acl.call_count, 1)
        self.assertEqual(verify_acl.call_args.args[0], self.root)

    def test_context_canvas_tool_capture_is_metadata_only(self) -> None:
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_name="mcp__context-canvas__canvas_read",
                response={"text": "must not recursively snapshot"},
            )
        )
        self.assertEqual(captured["capture_status"], "metadata_only")
        self.assertIsNone(captured["sha256"])
        event = self.snapshots.read_event(self.canvas_id, captured["event_id"])
        self.assertEqual(event["manifest"]["capture_policy"], "metadata_only_self")
        self.assertNotIn("payload", event)

    def test_pin_preserves_expired_object_while_gc_removes_unpinned_object(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        pinned_binary = b"pinned-transitive-blob"
        pinned_data_url = "data:application/octet-stream;base64," + base64.b64encode(
            pinned_binary
        ).decode("ascii")
        pinned = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-pin", response={"attachment": pinned_data_url}
            ),
            retention_days=1,
            now=captured_at,
        )
        expired = self.snapshots.capture_post_tool_use(
            self.hook_payload(tool_use_id="call-expire", response={"text": "expire"}),
            retention_days=1,
            now=captured_at,
        )
        self.snapshots.pin(
            pinned["sha256"],
            canvas_id=self.canvas_id,
            node_id="N000002",
            reason="verification evidence",
        )
        future = captured_at + timedelta(days=2)
        preview = self.snapshots.gc(now=future, apply=False)
        self.assertEqual(preview["candidate_event_count"], 1)
        self.assertEqual(
            preview["candidate_events"],
            [{"canvas_id": self.canvas_id, "event_id": expired["event_id"]}],
        )
        self.assertEqual(preview["candidate_objects"], [expired["sha256"]])
        self.assertTrue(self.snapshots.read_event(self.canvas_id, expired["event_id"]))
        applied = self.snapshots.gc(now=future, apply=True)
        self.assertEqual(applied["removed_event_count"], 1)
        with self.assertRaises(canvas.CanvasError):
            self.snapshots.read_event(self.canvas_id, expired["event_id"])
        self.assertTrue(
            self.snapshots.read_event(self.canvas_id, pinned["event_id"])["manifest"]["pinned"]
        )
        pinned_event = self.snapshots.read_event(
            self.canvas_id, pinned["event_id"], include_payload=True
        )
        self.assertEqual(
            pinned_event["payload"]["tool_response"]["attachment"], pinned_data_url
        )
        pinned_blob_digest = hashlib.sha256(pinned_binary).hexdigest()
        self.assertTrue(
            any(
                (self.root / "_snapshots" / "blobs" / "sha256").rglob(
                    f"{pinned_blob_digest}.bin.gz"
                )
            )
        )

    def test_gc_preflights_corrupt_graph_before_deleting_provenance(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(tool_use_id="call-corrupt-gc", response={"text": "expire"}),
            retention_days=1,
            now=captured_at,
        )
        event_path = next(
            (self.root / "_snapshots" / "events" / self.canvas_id).glob("*.json")
        )
        object_path = next(
            (self.root / "_snapshots" / "objects" / "sha256").rglob("*.json.gz")
        )
        object_path.write_bytes(b"not-a-gzip-object")

        with self.assertRaises(canvas.CorruptCanvasError):
            self.snapshots.gc(now=captured_at + timedelta(days=2), apply=True)

        self.assertTrue(event_path.exists())
        self.assertEqual(event_path.name, f"{captured['event_id']}.json")

    def test_gc_preflights_corrupt_blob_and_event_before_any_delete(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        binary = b"corrupt-gc-blob"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(
            binary
        ).decode("ascii")
        first = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-corrupt-blob",
                response={"attachment": data_url},
            ),
            retention_days=1,
            now=captured_at,
        )
        second = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-other-expired", response={"text": "other"}
            ),
            retention_days=1,
            now=captured_at,
        )
        event_root = self.root / "_snapshots" / "events" / self.canvas_id
        blob_path = next(
            (self.root / "_snapshots" / "blobs" / "sha256").rglob("*.bin.gz")
        )
        original_blob = blob_path.read_bytes()
        blob_path.write_bytes(b"not-a-gzip-blob")
        with self.assertRaises(canvas.CorruptCanvasError):
            self.snapshots.gc(now=captured_at + timedelta(days=2), apply=True)
        self.assertTrue((event_root / f"{first['event_id']}.json").exists())
        self.assertTrue((event_root / f"{second['event_id']}.json").exists())

        blob_path.write_bytes(original_blob)
        corrupt_event = event_root / f"{first['event_id']}.json"
        corrupt_event.write_text("not-json", encoding="utf-8")
        with self.assertRaises(canvas.CorruptCanvasError):
            self.snapshots.gc(now=captured_at + timedelta(days=2), apply=True)
        self.assertTrue(corrupt_event.exists())
        self.assertTrue((event_root / f"{second['event_id']}.json").exists())

    def test_gc_sweeps_capture_orphans_and_reports_exact_plan(self) -> None:
        binary = b"orphan-binary"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(binary).decode(
            "ascii"
        )
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-orphan", response={"attachment": data_url}
            )
        )
        event_path = next(
            (self.root / "_snapshots" / "events" / self.canvas_id).glob("*.json")
        )
        event_path.unlink()
        blob_digest = canvas.hashlib.sha256(binary).hexdigest()

        preview = self.snapshots.gc(apply=False)
        self.assertEqual(preview["candidate_events"], [])
        self.assertEqual(preview["candidate_objects"], [captured["sha256"]])
        self.assertEqual(preview["candidate_blobs"], [blob_digest])
        applied = self.snapshots.gc(apply=True)
        self.assertEqual(applied["removed_object_count"], 1)
        self.assertEqual(applied["removed_blob_count"], 1)

    def test_gc_recovers_pending_plan_after_event_unlink_interruption(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        binary = b"pending-plan-binary"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(
            binary
        ).decode("ascii")
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-pending-plan",
                response={"attachment": data_url},
            ),
            retention_days=1,
            now=captured_at,
        )
        future = captured_at + timedelta(days=2)
        preview = self.snapshots.gc(now=future, apply=False)
        journal = {
            "schema": canvas.SNAPSHOT_GC_SCHEMA,
            "plan_id": preview["plan_id"],
            "created_at": canvas._snapshot_iso(future),
            "candidate_events": preview["candidate_events"],
            "candidate_objects": preview["candidate_objects"],
            "candidate_blobs": preview["candidate_blobs"],
        }
        with self.snapshots._locked(create=True) as snapshot_root:
            self.assertIsNotNone(snapshot_root)
            gc_root = self.snapshots._subdirectory(snapshot_root, "gc", create=True)
            self.assertIsNotNone(gc_root)
            canvas._atomic_write_json(
                gc_root / "current.json",
                journal,
                maximum_bytes=canvas.MAX_SNAPSHOT_MANIFEST_BYTES,
            )

        event_path = next(
            (self.root / "_snapshots" / "events" / self.canvas_id).glob("*.json")
        )
        event_path.unlink()

        recovered = self.snapshots.gc(now=future, apply=False)
        self.assertTrue(recovered["pending_plan_recovered"])
        self.assertEqual(recovered["candidate_events"], [])
        self.assertEqual(recovered["candidate_objects"], [captured["sha256"]])
        self.assertEqual(
            recovered["candidate_blobs"], [canvas.hashlib.sha256(binary).hexdigest()]
        )
        self.assertEqual(recovered["pending_remaining_event_count"], 0)
        self.assertEqual(recovered["pending_remaining_object_count"], 1)
        self.assertEqual(recovered["pending_remaining_blob_count"], 1)

        object_path = next(
            (self.root / "_snapshots" / "objects" / "sha256").rglob("*.json.gz")
        )
        object_path.unlink()
        recovered_after_object = self.snapshots.gc(now=future, apply=False)
        self.assertTrue(recovered_after_object["pending_plan_recovered"])
        self.assertEqual(recovered_after_object["candidate_objects"], [])
        self.assertEqual(recovered_after_object["pending_remaining_object_count"], 0)
        self.assertEqual(recovered_after_object["pending_remaining_blob_count"], 1)
        applied = self.snapshots.gc(now=future, apply=True)
        self.assertTrue(applied["pending_plan_recovered"])
        self.assertEqual(applied["removed_object_count"], 0)
        self.assertEqual(applied["removed_blob_count"], 1)
        self.assertFalse(
            (self.root / "_snapshots" / "gc" / "current.json").exists()
        )

    def test_gc_rejects_noncanonical_or_unbound_pending_journal(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(2):
            self.snapshots.capture_post_tool_use(
                self.hook_payload(
                    tool_use_id=f"call-journal-{index}", response={"text": str(index)}
                ),
                retention_days=1,
                now=captured_at,
            )
        future = captured_at + timedelta(days=2)
        preview = self.snapshots.gc(now=future, apply=False)
        base_journal = {
            "schema": canvas.SNAPSHOT_GC_SCHEMA,
            "plan_id": preview["plan_id"],
            "created_at": canvas._snapshot_iso(future),
            "candidate_events": preview["candidate_events"],
            "candidate_objects": preview["candidate_objects"],
            "candidate_blobs": preview["candidate_blobs"],
        }
        with self.snapshots._locked(create=True) as snapshot_root:
            self.assertIsNotNone(snapshot_root)
            gc_root = self.snapshots._subdirectory(snapshot_root, "gc", create=True)
            self.assertIsNotNone(gc_root)
            journal_path = gc_root / "current.json"

        variants: list[tuple[str, dict]] = []
        bad_plan_id = dict(base_journal)
        bad_plan_id["plan_id"] = "0" * 64
        variants.append(("plan-id", bad_plan_id))
        malformed = json.loads(json.dumps(base_journal))
        malformed["candidate_events"][0]["event_id"] = "invalid"
        variants.append(("malformed-event", malformed))
        duplicate = json.loads(json.dumps(base_journal))
        duplicate["candidate_events"].append(dict(duplicate["candidate_events"][0]))
        variants.append(("duplicate-event", duplicate))
        reversed_events = json.loads(json.dumps(base_journal))
        reversed_events["candidate_events"].reverse()
        variants.append(("unsorted-events", reversed_events))
        uppercase_digest = json.loads(json.dumps(base_journal))
        uppercase_digest["candidate_objects"][0] = uppercase_digest[
            "candidate_objects"
        ][0].upper()
        variants.append(("uppercase-object", uppercase_digest))

        for label, journal in variants:
            with self.subTest(label=label):
                canvas._atomic_write_json(
                    journal_path,
                    journal,
                    maximum_bytes=canvas.MAX_SNAPSHOT_MANIFEST_BYTES,
                )
                with self.assertRaises(canvas.CorruptCanvasError):
                    self.snapshots.gc(now=future, apply=False)

        for event in preview["candidate_events"]:
            self.assertTrue(
                (
                    self.root
                    / "_snapshots"
                    / "events"
                    / event["canvas_id"]
                    / f"{event['event_id']}.json"
                ).exists()
            )

    def test_snapshot_reference_promotes_pin_without_entering_semantic_search(self) -> None:
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(response={"text": "SNAPSHOT_BODY_NEEDLE"})
        )
        store = canvas.CanvasStore(root=self.root)
        store.initialize(self.canvas_id, goal="Promote only intentional evidence")
        node = store.upsert_node(
            self.canvas_id,
            kind="verification",
            status_value="done",
            summary="Historical receipt preserved",
            evidence_refs=[
                {"pointer": captured["snapshot_uri"], "sha256": captured["sha256"]}
            ],
        )
        event = self.snapshots.read_event(self.canvas_id, captured["event_id"])
        self.assertTrue(event["manifest"]["pinned"])
        self.assertEqual(event["manifest"]["pin_references"][0]["node_id"], node["node_id"])
        search = store.search("SNAPSHOT_BODY_NEEDLE", canvas_id=self.canvas_id)
        self.assertEqual(search["hits"], [])
        self.assertEqual(search["skipped_count"], 0)

    def test_invalid_semantic_mutation_does_not_disable_independent_snapshot_capture(self) -> None:
        store = canvas.CanvasStore(root=self.root)
        store.initialize(self.canvas_id, goal="Keep independent history available")

        with self.assertRaisesRegex(canvas.CanvasError, "evidence"):
            store.add_node(
                self.canvas_id,
                kind="decision",
                status_value="done",
                summary="This invalid terminal mutation must not be committed",
            )

        checkpoint = store.add_node(
            self.canvas_id,
            kind="plan",
            status_value="planned",
            summary="A later valid checkpoint remains allowed",
        )
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(tool_use_id="call-after-invalid-mutation")
        )

        self.assertEqual(checkpoint["node_id"], "N000002")
        self.assertEqual(captured["capture_status"], "stored")
        listed = self.snapshots.list_events(canvas_id=self.canvas_id)
        self.assertEqual(
            [event["event_id"] for event in listed["events"]], [captured["event_id"]]
        )

    def test_snapshot_promotion_rejects_missing_transitive_blob(self) -> None:
        binary = b"promotion-blob"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(binary).decode(
            "ascii"
        )
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(response={"attachment": data_url})
        )
        blob_path = next(
            (self.root / "_snapshots" / "blobs" / "sha256").rglob("*.bin.gz")
        )
        blob_path.unlink()
        store = canvas.CanvasStore(root=self.root)
        store.initialize(self.canvas_id, goal="Reject incomplete evidence")

        with self.assertRaises(canvas.CanvasError):
            store.upsert_node(
                self.canvas_id,
                kind="verification",
                status_value="done",
                summary="Must not commit unexportable evidence",
                evidence_refs=[
                    {"pointer": captured["snapshot_uri"], "sha256": captured["sha256"]}
                ],
            )

        pins_root = self.root / "_snapshots" / "pins"
        self.assertFalse(pins_root.exists() and any(pins_root.rglob("*.json")))

    def test_post_tool_hook_cli_requires_one_shot_opt_in_and_fails_open(self) -> None:
        payload = self.hook_payload(response={"text": "hook subprocess receipt"})

        unarmed = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-post-tool-use"],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(unarmed.returncode, 0, unarmed.stderr)
        self.assertEqual(unarmed.stdout, "")
        self.assertEqual(self.snapshots.list_events(canvas_id=self.canvas_id)["events"], [])

        armed = canvas.CaptureRequestStore(root=self.root).arm(
            self.canvas_id,
            tool_name="mcp__web__open",
            retention_days=7,
        )
        self.assertTrue(armed["armed"])
        captured = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-post-tool-use"],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertEqual(captured.stdout, "")
        listed = self.snapshots.list_events(canvas_id=self.canvas_id)
        self.assertEqual(len(listed["events"]), 1)

        after_one_shot = self.hook_payload(
            tool_use_id="call-after-one-shot",
            response={"text": "must not be captured"},
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-post-tool-use"],
            input=json.dumps(after_one_shot),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(self.snapshots.list_events(canvas_id=self.canvas_id)["events"]), 1)

        malformed = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-post-tool-use"],
            input="{not-json",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(malformed.returncode, 0)
        self.assertEqual(malformed.stdout, "")
        self.assertIn("capture unavailable", malformed.stderr.lower())

    def test_capture_request_matches_once_ignores_self_tools_and_can_expire_or_cancel(self) -> None:
        requests = canvas.CaptureRequestStore(root=self.root)
        now = datetime(2026, 8, 18, tzinfo=timezone.utc)
        requests.arm(
            self.canvas_id,
            tool_name="mcp__web__open",
            ttl_minutes=2,
            now=now,
        )

        self_tool = requests.consume_for_hook(
            self.hook_payload(tool_name="mcp__context_canvas__canvas_read"),
            now=now,
        )
        self.assertEqual(self_tool["reason"], "self_tool")
        mismatch = requests.consume_for_hook(
            self.hook_payload(tool_name="mcp__web__search"),
            now=now,
        )
        self.assertEqual(mismatch["reason"], "tool_mismatch")
        matched = requests.consume_for_hook(self.hook_payload(), now=now)
        self.assertTrue(matched["capture"])
        self.assertEqual(
            requests.consume_for_hook(self.hook_payload(), now=now)["reason"],
            "not_armed",
        )

        requests.arm(self.canvas_id, tool_name="mcp__web__open", ttl_minutes=1, now=now)
        expired = requests.consume_for_hook(
            self.hook_payload(), now=now + timedelta(minutes=1)
        )
        self.assertEqual(expired["reason"], "expired")
        requests.arm(self.canvas_id, tool_name="mcp__web__open", now=now)
        self.assertTrue(requests.cancel(self.canvas_id)["cancelled"])
        self.assertFalse(requests.cancel(self.canvas_id)["cancelled"])

    def test_oversize_hook_input_fails_open_without_partial_snapshot(self) -> None:
        payload = self.hook_payload(response={"text": "x" * 4096})
        environment = os.environ.copy()
        environment[canvas.SNAPSHOT_HOOK_LIMIT_ENV] = "1024"
        completed = subprocess.run(
            [sys.executable, "-B", "-I", str(SCRIPT), "hook-post-tool-use"],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertIn("capture unavailable", completed.stderr.lower())
        self.assertEqual(self.snapshots.list_events(canvas_id=self.canvas_id)["events"], [])

    def test_snapshot_list_filters_and_cursor_keep_large_history_findable(self) -> None:
        first = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-filter-1",
                tool_name="shell_command",
                response={"text": "first"},
            )
        )
        second = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-filter-2",
                tool_name="mcp__web__open",
                response={"text": "second"},
            )
        )
        third = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-filter-3",
                tool_name="shell_command",
                response={"text": "third"},
            )
        )
        self.snapshots.pin(third["sha256"], reason="cursor filter test")

        shell_events = self.snapshots.list_events(
            canvas_id=self.canvas_id,
            tool_name="shell_command",
            capture_status="stored",
            limit=10,
        )
        self.assertEqual(shell_events["count"], 2)
        self.assertTrue(
            all(item["tool_name"] == "shell_command" for item in shell_events["events"])
        )
        pinned = self.snapshots.list_events(
            canvas_id=self.canvas_id,
            pinned=True,
            limit=10,
        )
        self.assertEqual([item["event_id"] for item in pinned["events"]], [third["event_id"]])

        page_one = self.snapshots.list_events(canvas_id=self.canvas_id, limit=1)
        self.assertEqual(page_one["returned_count"], 1)
        self.assertIsNotNone(page_one["next_cursor"])
        page_two = self.snapshots.list_events(
            canvas_id=self.canvas_id,
            cursor=page_one["next_cursor"],
            limit=1,
        )
        self.assertEqual(page_two["returned_count"], 1)
        self.assertNotEqual(
            page_one["events"][0]["event_id"], page_two["events"][0]["event_id"]
        )
        self.assertEqual(
            {first["event_id"], second["event_id"], third["event_id"]},
            {
                page_one["events"][0]["event_id"],
                page_two["events"][0]["event_id"],
                self.snapshots.list_events(
                    canvas_id=self.canvas_id,
                    cursor=page_two["next_cursor"],
                    limit=1,
                )["events"][0]["event_id"],
            },
        )

    def test_concurrent_hook_processes_consume_one_capture_request_exactly_once(self) -> None:
        canvas.CaptureRequestStore(root=self.root).arm(
            self.canvas_id,
            tool_name="mcp__web__open",
        )
        processes: list[subprocess.Popen[str]] = []
        for index in range(4):
            payload = self.hook_payload(
                tool_use_id=f"call-concurrent-{index}",
                response={"text": "shared concurrent response"},
            )
            process = subprocess.Popen(
                [sys.executable, "-B", "-I", str(SCRIPT), "hook-post-tool-use"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=os.environ.copy(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload))
            process.stdin.close()
            processes.append(process)
        receipts: list[tuple[int | None, str, str]] = []
        for process in processes:
            process.wait(timeout=30)
            stdout = process.stdout.read() if process.stdout is not None else ""
            stderr = process.stderr.read() if process.stderr is not None else ""
            receipts.append((process.returncode, stdout, stderr))
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        for returncode, stdout, stderr in receipts:
            self.assertEqual(returncode, 0, stderr)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
        listed = self.snapshots.list_events(canvas_id=self.canvas_id, limit=10)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(len({event["sha256"] for event in listed["events"]}), 1)
        objects = list((self.root / "_snapshots" / "objects" / "sha256").rglob("*.json.gz"))
        self.assertEqual(len(objects), 1)

    def test_snapshot_promotion_rejects_corrupt_transitive_blob_without_node_or_pin(self) -> None:
        binary = b"promotion-corrupt-blob"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(
            binary
        ).decode("ascii")
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(
                tool_use_id="call-corrupt-promotion",
                response={"attachment": data_url},
            )
        )
        blob_path = next(
            (self.root / "_snapshots" / "blobs" / "sha256").rglob("*.bin.gz")
        )
        blob_path.write_bytes(b"not-a-gzip-blob")
        store = canvas.CanvasStore(root=self.root)
        store.initialize(self.canvas_id, goal="Reject corrupt evidence")

        with self.assertRaises(canvas.CorruptCanvasError):
            store.upsert_node(
                self.canvas_id,
                kind="verification",
                status_value="done",
                summary="Must not accept corrupt evidence",
                evidence_refs=[
                    {"pointer": captured["snapshot_uri"], "sha256": captured["sha256"]}
                ],
            )

        self.assertEqual(len(store.read(self.canvas_id)["nodes"]), 1)
        pins_root = self.root / "_snapshots" / "pins"
        self.assertFalse(pins_root.exists() and any(pins_root.rglob("*.json")))

    def test_corrupt_snapshot_object_fails_hash_verified_read(self) -> None:
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(response={"text": "integrity receipt"})
        )
        object_path = next(
            (self.root / "_snapshots" / "objects" / "sha256").rglob("*.json.gz")
        )
        object_path.write_bytes(b"not-a-gzip-object")
        with self.assertRaises(canvas.CorruptCanvasError):
            self.snapshots.read_event(
                self.canvas_id, captured["event_id"], include_payload=True
            )

    def test_event_manifest_is_bound_to_canvas_event_and_session_identity(self) -> None:
        captured = self.snapshots.capture_post_tool_use(self.hook_payload())
        event_path = next(
            (self.root / "_snapshots" / "events" / self.canvas_id).glob("*.json")
        )
        original = json.loads(event_path.read_text(encoding="utf-8"))
        captured_at = canvas._parse_snapshot_iso(original["captured_at"])
        mutations = {
            "canvas_id": canvas.derive_canvas_id("foreign-session"),
            "event_id": "obs-" + "0" * 64,
            "session_id_sha256": "0" * 64,
            "session_id_sha256_upper": original["session_id_sha256"].upper(),
            "sha256_upper": original["sha256"].upper(),
            "expires_too_soon": canvas._snapshot_iso(
                captured_at + timedelta(hours=12)
            ),
            "expires_too_late": canvas._snapshot_iso(
                captured_at + timedelta(days=canvas.MAX_SNAPSHOT_RETENTION_DAYS + 1)
            ),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                manifest = dict(original)
                if field.startswith("expires_"):
                    manifest["expires_at"] = value
                elif field.endswith("_upper"):
                    manifest[field.removesuffix("_upper")] = value
                else:
                    manifest[field] = value
                event_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(canvas.CorruptCanvasError):
                    self.snapshots.read_event(self.canvas_id, captured["event_id"])
        event_path.write_text(json.dumps(original), encoding="utf-8")

    def test_event_manifest_declared_object_length_is_verified_on_read_and_gc(self) -> None:
        captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(tool_use_id="call-length", response={"text": "bound"}),
            retention_days=1,
            now=captured_at,
        )
        event_path = next(
            (self.root / "_snapshots" / "events" / self.canvas_id).glob("*.json")
        )
        manifest = json.loads(event_path.read_text(encoding="utf-8"))
        manifest["sanitized_bytes"] += 1
        event_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(canvas.CorruptCanvasError):
            self.snapshots.read_event(
                self.canvas_id, captured["event_id"], include_payload=True
            )
        with self.assertRaises(canvas.CorruptCanvasError):
            self.snapshots.gc(now=captured_at + timedelta(days=2), apply=True)
        self.assertTrue(event_path.exists())

    def test_event_manifest_blob_declarations_are_bound_to_object_graph(self) -> None:
        binary = b"declared-blob"
        data_url = "data:application/octet-stream;base64," + base64.b64encode(binary).decode(
            "ascii"
        )
        captured = self.snapshots.capture_post_tool_use(
            self.hook_payload(response={"attachment": data_url})
        )
        event_path = next(
            (self.root / "_snapshots" / "events" / self.canvas_id).glob("*.json")
        )
        original = json.loads(event_path.read_text(encoding="utf-8"))
        mutations = [
            ("byte-length", lambda manifest: manifest["blobs"][0].__setitem__("byte_length", manifest["blobs"][0]["byte_length"] + 1)),
            ("uppercase-digest", lambda manifest: manifest["blobs"][0].__setitem__("sha256", manifest["blobs"][0]["sha256"].upper())),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                manifest = json.loads(json.dumps(original))
                mutate(manifest)
                event_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(canvas.CorruptCanvasError):
                    self.snapshots.read_event(self.canvas_id, captured["event_id"])

    def test_gc_rejects_aliased_canvas_event_directory_without_foreign_delete(self) -> None:
        self.snapshots.capture_post_tool_use(
            self.hook_payload(tool_use_id="bootstrap", response={"text": "bootstrap"})
        )
        foreign_root = self.base / "foreign-store"
        foreign_store = canvas.SnapshotStore(root=foreign_root)
        foreign_session = "foreign-gc-session"
        foreign_canvas = canvas.derive_canvas_id(foreign_session)
        payload = self.hook_payload(tool_use_id="foreign-expired", response={"text": "foreign"})
        payload["session_id"] = foreign_session
        foreign = foreign_store.capture_post_tool_use(
            payload,
            retention_days=1,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        foreign_events = foreign_root / "_snapshots" / "events" / foreign_canvas
        alias = self.root / "_snapshots" / "events" / foreign_canvas
        try:
            alias.symlink_to(foreign_events, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"directory symlink unavailable: {exc}")
            linked = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(foreign_events)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if linked.returncode != 0:
                self.skipTest("directory alias fixture is unavailable")
        try:
            with self.assertRaises(canvas.SecurityBoundaryError):
                self.snapshots.gc(
                    now=datetime(2026, 1, 3, tzinfo=timezone.utc), apply=True
                )
            self.assertTrue(
                (foreign_events / f"{foreign['event_id']}.json").exists()
            )
        finally:
            if os.path.lexists(alias):
                os.rmdir(alias) if os.name == "nt" else alias.unlink()

    def test_snapshot_directory_alias_is_rejected_before_capture(self) -> None:
        self.root.mkdir()
        foreign = self.base / "foreign-snapshots"
        foreign.mkdir()
        alias = self.root / "_snapshots"
        try:
            alias.symlink_to(foreign, target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"directory symlink unavailable: {exc}")
            linked = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(foreign)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if linked.returncode != 0:
                self.skipTest("snapshot directory alias fixture is unavailable")
        with self.assertRaises(canvas.SecurityBoundaryError):
            self.snapshots.capture_post_tool_use(self.hook_payload())
        self.assertEqual(list(foreign.iterdir()), [])

    def test_snapshot_uri_hash_mismatch_is_rejected_without_pin(self) -> None:
        captured = self.snapshots.capture_post_tool_use(self.hook_payload())
        store = canvas.CanvasStore(root=self.root)
        store.initialize(self.canvas_id, goal="Reject mismatched snapshot evidence")
        with self.assertRaisesRegex(canvas.CanvasError, "do not match"):
            store.upsert_node(
                self.canvas_id,
                kind="verification",
                status_value="done",
                summary="Mismatched evidence must fail",
                evidence_refs=[
                    {"pointer": captured["snapshot_uri"], "sha256": "f" * 64}
                ],
            )
        event = self.snapshots.read_event(self.canvas_id, captured["event_id"])
        self.assertFalse(event["manifest"]["pinned"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
