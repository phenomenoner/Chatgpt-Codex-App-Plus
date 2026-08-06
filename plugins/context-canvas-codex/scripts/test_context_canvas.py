from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
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
        self.assertIn("No Context Canvas checkpoint exists", resume["hookSpecificOutput"]["additionalContext"])
        self.assertFalse(self.root.exists())

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
        self.assertIn("checkpoint truncated at safe bound", summary)

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
        self.assertIn("unavailable or invalid", context)
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

    def test_plugin_exposes_session_restore_and_bundled_mcp_without_tool_capture(self) -> None:
        payload = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload["hooks"]), {"SessionStart"})
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
        mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp_config["mcpServers"]["context-canvas"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["-B", "-I", "./scripts/context_canvas_mcp.py"])
        self.assertEqual(server["cwd"], ".")
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertFalse((PLUGIN_ROOT / ".app.json").exists())
        self.assertFalse((PLUGIN_ROOT / "assets").exists())

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
        run("uninstall", home=pristine_home)

        _, installed = run("install")
        self.assertTrue(installed["ok"])
        self.assertTrue(installed["changed"])
        installed_script = codex_home / "context-canvas-codex" / "context_canvas.py"
        self.assertEqual(installed_script.read_bytes(), SCRIPT.read_bytes())
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(hooks["hooks"]["SessionStart"][0], existing_group)
        self.assertEqual(len(hooks["hooks"]["SessionStart"]), 2)
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
        run("install")

        _, removed = run("uninstall")
        self.assertTrue(removed["ok"])
        self.assertTrue(removed["changed"])
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(hooks["hooks"]["SessionStart"], [existing_group])
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

    def test_v1_canvas_migrates_in_memory_then_persists_v2_on_mutation(self) -> None:
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

    def test_mcp_stdio_server_exposes_pointer_only_canvas_tools(self) -> None:
        self.assertTrue(MCP_SCRIPT.is_file())
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
                {"canvas_start", "canvas_upsert_node", "canvas_read", "canvas_search", "canvas_closeout"}
                <= names
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
