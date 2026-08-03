import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "public_sync.py"


class PublicSyncTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repo = self.root / "repo"
        self.codex = self.root / "codex"
        self.agents = self.root / "agents"
        (self.repo / "manifest").mkdir(parents=True)
        (self.codex / "skills" / "sample").mkdir(parents=True)
        self.agents.mkdir()
        (self.codex / "skills" / "sample" / "SKILL.md").write_text(
            "---\nname: sample\ndescription: Safe sample.\n---\n\n# Sample\n",
            encoding="utf-8",
        )
        self.manifest = self.repo / "manifest" / "public-sources.json"
        self._write_manifest()

    def tearDown(self):
        self.tempdir.cleanup()

    def _write_manifest(self, source="skills/sample", include=None):
        value = {
            "schemaVersion": "codex-plus-public-sources.v1",
            "components": [
                {
                    "id": "sample",
                    "mode": "vendor",
                    "sourceRoot": "codex",
                    "source": source,
                    "destination": "skills/sample",
                    "include": include or ["SKILL.md"],
                    "exclude": [],
                },
                {
                    "id": "upstream-only",
                    "mode": "pointer",
                    "canonicalUrl": "https://example.com/upstream",
                    "version": "v1.0.0",
                    "commit": "a" * 40,
                    "license": "MIT",
                },
            ],
        }
        self.manifest.write_text(json.dumps(value), encoding="utf-8")

    def _run(self, command, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                command,
                "--repo-root",
                str(self.repo),
                *( ["--manifest", str(self.manifest), "--codex-home", str(self.codex), "--agents-home", str(self.agents)] if command == "sync" else [] ),
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_apply_copies_only_allowlisted_files_and_generates_lock(self):
        (self.codex / "skills" / "sample" / "private-note.txt").write_text(
            "This unlisted file must stay local.", encoding="utf-8"
        )
        result = self._run("sync", "--apply")

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertTrue((self.repo / "skills" / "sample" / "SKILL.md").is_file())
        self.assertFalse(
            (self.repo / "skills" / "sample" / "private-note.txt").exists()
        )
        lock = json.loads(
            (self.repo / "manifest" / "public-lock.json").read_text(encoding="utf-8")
        )
        self.assertEqual(lock["files"][0]["path"], "skills/sample/SKILL.md")
        self.assertEqual(lock["pointers"][0]["id"], "upstream-only")

    def test_secret_in_allowlisted_source_fails_closed(self):
        fixture_path = self.codex / "skills" / "sample" / "secret.txt"
        fixture_path.write_text(
            "access_token = " + "gho_" + "a" * 36, encoding="utf-8"
        )
        self._write_manifest(include=["*"])
        result = self._run("sync", "--apply")

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(any("token" in error.lower() for error in payload["errors"]))
        self.assertFalse((self.repo / "skills" / "sample" / "secret.txt").exists())

    def test_source_path_escape_is_rejected(self):
        self._write_manifest(source="../outside")
        result = self._run("sync", "--apply")

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertTrue(any("escapes" in error for error in payload["errors"]))

    def test_validate_detects_locked_file_drift(self):
        applied = self._run("sync", "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr or applied.stdout)
        (self.repo / "skills" / "sample" / "SKILL.md").write_text(
            "drift\n", encoding="utf-8"
        )
        result = self._run("validate")

        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertTrue(any("drifted" in error for error in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
