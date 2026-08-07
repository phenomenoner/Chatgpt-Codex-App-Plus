#!/usr/bin/env python3
"""Install Context Canvas lifecycle and snapshot adapters as Codex user hooks.

Some Codex releases expose plugin MCP servers and skills while not executing
plugin-bundled lifecycle hooks. This installer keeps the same audited hook code
in a stable user-level location and merges the exact lifecycle and capture
handlers into hooks.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import stat
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "context-canvas-codex-hook-install.v2"
LEGACY_SCHEMA = "context-canvas-codex-hook-install.v1"
SOURCE_SCRIPT = Path(__file__).with_name("context_canvas.py")
INSTALL_DIR_NAME = "context-canvas-codex"
INSTALLED_SCRIPT_NAME = "context_canvas.py"
INSTALL_MANIFEST_NAME = "hook-install.json"
HOOKS_FILE_NAME = "hooks.json"
SESSION_STATUS_MESSAGE = "Restoring Context Canvas [context-canvas-codex user hook]"
SNAPSHOT_STATUS_MESSAGE = "Archiving tool snapshot [context-canvas-codex user hook]"
SESSION_MATCHER = "^(startup|resume|clear|compact)$"
POST_TOOL_MATCHER = ".*"
MAX_JSON_BYTES = 1024 * 1024


class InstallerError(RuntimeError):
    pass


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _require_plain_directory(path: Path, label: str) -> None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError as exc:
        raise InstallerError(f"{label} is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
        raise InstallerError(f"{label} must not be an alias or reparse point")
    if not stat.S_ISDIR(metadata.st_mode):
        raise InstallerError(f"{label} must be a directory")


def _ensure_plain_directory(path: Path, label: str) -> None:
    if not _lexists(path):
        _require_plain_directory(path.parent, f"{label} parent")
        try:
            path.mkdir()
        except FileExistsError:
            pass
    _require_plain_directory(path, label)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _regular_file_bytes(path: Path, label: str) -> bytes:
    if not _lexists(path):
        raise InstallerError(f"{label} is missing")
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
        raise InstallerError(f"{label} must be a regular non-symlink file")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise InstallerError(f"{label} must have one regular-file link")
    if metadata.st_size > MAX_JSON_BYTES:
        raise InstallerError(f"{label} exceeds its bounded size")
    return path.read_bytes()


def _load_json(path: Path, label: str, *, missing: Any = None) -> Any:
    if not _lexists(path):
        return missing
    raw = _regular_file_bytes(path, label)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InstallerError(f"{label} must contain valid UTF-8 JSON") from exc


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_write(path: Path, value: bytes) -> None:
    _ensure_plain_directory(path.parent, f"{path.name} parent directory")
    if _lexists(path):
        _regular_file_bytes(path, os.fspath(path))
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=os.fspath(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if _lexists(temporary):
            temporary.unlink()


def _codex_home(raw: str | None) -> Path:
    candidate = raw or os.environ.get("CODEX_HOME")
    path = Path(candidate).expanduser() if candidate else Path.home() / ".codex"
    if not path.is_absolute():
        raise InstallerError("Codex home must be an absolute path")
    resolved = path.resolve(strict=False)
    if resolved.parent == resolved:
        raise InstallerError("Codex home cannot be a filesystem root")
    if _lexists(resolved) and (resolved.is_symlink() or not resolved.is_dir()):
        raise InstallerError("Codex home must be a real directory")
    return resolved


def _powershell_quote(path: Path) -> str:
    return "'" + os.fspath(path).replace("'", "''") + "'"


def _expected_groups(installed_script: Path) -> dict[str, dict[str, Any]]:
    return {
        "SessionStart": {
            "matcher": SESSION_MATCHER,
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        f"python3 -I {shlex.quote(installed_script.as_posix())} hook-session-start"
                    ),
                    "commandWindows": (
                        f"python -I {_powershell_quote(installed_script)} hook-session-start"
                    ),
                    "timeout": 10,
                    "statusMessage": SESSION_STATUS_MESSAGE,
                    "additionalContextLimit": 5000,
                }
            ],
        },
        "PostToolUse": {
            "matcher": POST_TOOL_MATCHER,
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        f"python3 -I {shlex.quote(installed_script.as_posix())} hook-post-tool-use"
                    ),
                    "commandWindows": (
                        f"python -I {_powershell_quote(installed_script)} hook-post-tool-use"
                    ),
                    "timeout": 30,
                    "statusMessage": SNAPSHOT_STATUS_MESSAGE,
                }
            ],
        },
    }


def _hooks_document(path: Path) -> dict[str, Any]:
    payload = _load_json(path, "Codex hooks.json", missing=None)
    if payload is None:
        payload = {
            "description": "User-level Codex lifecycle hooks.",
            "hooks": {},
        }
    if not isinstance(payload, dict):
        raise InstallerError("Codex hooks.json must contain an object")
    hooks = payload.get("hooks")
    if hooks is None:
        payload["hooks"] = {}
    elif not isinstance(hooks, dict):
        raise InstallerError("Codex hooks.json field hooks must contain an object")
    for event_name in ("SessionStart", "PostToolUse"):
        groups = payload["hooks"].get(event_name)
        if groups is None:
            payload["hooks"][event_name] = []
        elif not isinstance(groups, list):
            raise InstallerError(f"Codex {event_name} hooks must contain an array")
    return payload


def _managed_group_index(
    groups: list[Any], expected: dict[str, Any], *, marker: str
) -> int | None:
    matches: list[int] = []
    marker_matches: list[int] = []
    for index, group in enumerate(groups):
        if group == expected:
            matches.append(index)
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            continue
        if any(
            isinstance(handler, dict) and handler.get("statusMessage") == marker
            for handler in handlers
        ):
            marker_matches.append(index)
    if len(matches) > 1 or len(marker_matches) > 1:
        raise InstallerError("duplicate Context Canvas user-hook handlers were found")
    if marker_matches and not matches:
        raise InstallerError("Context Canvas user-hook marker exists with a drifted definition")
    return matches[0] if matches else None


def _manifest_payload(
    source_hash: str, groups: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source_sha256": source_hash,
        "installed_sha256": source_hash,
        "handlers_sha256": {
            event_name: _sha256_bytes(_json_bytes(group))
            for event_name, group in sorted(groups.items())
        },
        "hooks_file": HOOKS_FILE_NAME,
        "installed_script": f"{INSTALL_DIR_NAME}/{INSTALLED_SCRIPT_NAME}",
    }


def _load_owned_manifest(path: Path) -> dict[str, Any] | None:
    payload = _load_json(path, "Context Canvas hook install manifest", missing=None)
    if payload is None:
        return None
    if not isinstance(payload, dict) or payload.get("schema") not in {SCHEMA, LEGACY_SCHEMA}:
        raise InstallerError("Context Canvas hook install manifest is foreign or invalid")
    if payload.get("installed_script") != f"{INSTALL_DIR_NAME}/{INSTALLED_SCRIPT_NAME}":
        raise InstallerError("Context Canvas hook install manifest target is invalid")
    for field in ("source_sha256", "installed_sha256"):
        value = payload.get(field)
        if not isinstance(value, str) or len(value) != 64:
            raise InstallerError(f"Context Canvas hook install manifest field {field} is invalid")
    if payload.get("schema") == LEGACY_SCHEMA:
        value = payload.get("handler_sha256")
        if not isinstance(value, str) or len(value) != 64:
            raise InstallerError("legacy Context Canvas handler digest is invalid")
    else:
        handler_hashes = payload.get("handlers_sha256")
        if (
            not isinstance(handler_hashes, dict)
            or set(handler_hashes) != {"SessionStart", "PostToolUse"}
            or any(not isinstance(value, str) or len(value) != 64 for value in handler_hashes.values())
        ):
            raise InstallerError("Context Canvas handler digests are invalid")
    return payload


def _backup_existing_hooks(hooks_path: Path, install_dir: Path) -> str | None:
    if not _lexists(hooks_path):
        return None
    value = _regular_file_bytes(hooks_path, "Codex hooks.json")
    digest = _sha256_bytes(value)
    destination = install_dir / "backups" / f"hooks-{digest}.json"
    if _lexists(destination):
        if _regular_file_bytes(destination, "Context Canvas hooks backup") != value:
            raise InstallerError("Context Canvas hooks backup hash collision")
    else:
        _atomic_write(destination, value)
    return f"{INSTALL_DIR_NAME}/backups/{destination.name}"


def _state(codex_home: Path) -> dict[str, Any]:
    install_dir = codex_home / INSTALL_DIR_NAME
    if _lexists(codex_home):
        _require_plain_directory(codex_home, "Codex home")
    if _lexists(install_dir):
        _require_plain_directory(install_dir, "Context Canvas install directory")
    installed_script = install_dir / INSTALLED_SCRIPT_NAME
    manifest_path = install_dir / INSTALL_MANIFEST_NAME
    hooks_path = codex_home / HOOKS_FILE_NAME
    source = _regular_file_bytes(SOURCE_SCRIPT, "Context Canvas source script")
    source_hash = _sha256_bytes(source)
    expected = _expected_groups(installed_script)
    return {
        "install_dir": install_dir,
        "installed_script": installed_script,
        "manifest_path": manifest_path,
        "hooks_path": hooks_path,
        "source": source,
        "source_hash": source_hash,
        "expected": expected,
    }


def check(codex_home: Path) -> dict[str, Any]:
    state = _state(codex_home)
    errors: list[str] = []
    try:
        manifest = _load_owned_manifest(state["manifest_path"])
        if manifest is None:
            errors.append("install manifest is missing")
        installed = _regular_file_bytes(
            state["installed_script"], "installed Context Canvas hook script"
        )
        if _sha256_bytes(installed) != state["source_hash"]:
            errors.append("installed hook script drifted from the current source")
        hooks = _hooks_document(state["hooks_path"])
        markers = {
            "SessionStart": SESSION_STATUS_MESSAGE,
            "PostToolUse": SNAPSHOT_STATUS_MESSAGE,
        }
        for event_name, expected_group in state["expected"].items():
            groups = hooks["hooks"][event_name]
            if _managed_group_index(
                groups, expected_group, marker=markers[event_name]
            ) is None:
                errors.append(f"Context Canvas {event_name} user-hook handler is missing")
        if manifest is not None and manifest != _manifest_payload(
            state["source_hash"], state["expected"]
        ):
            errors.append("install manifest drifted from the current source and handler")
    except InstallerError as exc:
        errors.append(str(exc))
    return {
        "ok": not errors,
        "action": "check",
        "changed": False,
        "source_sha256": state["source_hash"],
        "errors": errors,
    }


def install(codex_home: Path) -> dict[str, Any]:
    _ensure_plain_directory(codex_home, "Codex home")
    state = _state(codex_home)
    _ensure_plain_directory(state["install_dir"], "Context Canvas install directory")
    manifest = _load_owned_manifest(state["manifest_path"])
    hooks = _hooks_document(state["hooks_path"])
    if _lexists(state["installed_script"]) and manifest is None:
        interrupted_hash = _sha256_bytes(
            _regular_file_bytes(
                state["installed_script"], "unmanifested Context Canvas hook script"
            )
        )
        if interrupted_hash != state["source_hash"]:
            raise InstallerError("refusing to overwrite a foreign Context Canvas hook script")

    markers = {
        "SessionStart": SESSION_STATUS_MESSAGE,
        "PostToolUse": SNAPSHOT_STATUS_MESSAGE,
    }
    group_indexes = {
        event_name: _managed_group_index(
            hooks["hooks"][event_name],
            expected_group,
            marker=markers[event_name],
        )
        for event_name, expected_group in state["expected"].items()
    }
    installed_hash = None
    if _lexists(state["installed_script"]):
        installed_hash = _sha256_bytes(
            _regular_file_bytes(state["installed_script"], "installed Context Canvas hook script")
        )
    if manifest is not None and manifest["schema"] == LEGACY_SCHEMA:
        expected_legacy_handler_hash = _sha256_bytes(
            _json_bytes(state["expected"]["SessionStart"])
        )
        if manifest["handler_sha256"] != expected_legacy_handler_hash:
            raise InstallerError(
                "legacy Context Canvas SessionStart handler digest does not match the managed hook"
            )
        if installed_hash != manifest["installed_sha256"]:
            raise InstallerError(
                "legacy Context Canvas installed script digest does not match the owned file"
            )
    expected_manifest = _manifest_payload(state["source_hash"], state["expected"])
    changed = (
        installed_hash != state["source_hash"]
        or any(index is None for index in group_indexes.values())
        or manifest != expected_manifest
    )
    backup = None
    if changed:
        backup = _backup_existing_hooks(state["hooks_path"], state["install_dir"])
        _atomic_write(state["installed_script"], state["source"])
        for event_name, expected_group in state["expected"].items():
            if group_indexes[event_name] is None:
                hooks["hooks"][event_name].append(expected_group)
        _atomic_write(state["hooks_path"], _json_bytes(hooks))
        _atomic_write(state["manifest_path"], _json_bytes(expected_manifest))

    verified = check(codex_home)
    if not verified["ok"]:
        raise InstallerError("post-install verification failed: " + "; ".join(verified["errors"]))
    return {
        "ok": True,
        "action": "install",
        "changed": changed,
        "source_sha256": state["source_hash"],
        "backup": backup,
        "errors": [],
    }


def _archive_owned(path: Path, install_dir: Path, label: str) -> str | None:
    if not _lexists(path):
        return None
    value = _regular_file_bytes(path, label)
    digest = _sha256_bytes(value)
    retired = install_dir / "retired"
    _ensure_plain_directory(retired, "Context Canvas retirement directory")
    candidate = retired / f"{path.stem}-{digest}{path.suffix}"
    counter = 1
    while _lexists(candidate):
        candidate = retired / f"{path.stem}-{digest}-{counter}{path.suffix}"
        counter += 1
    os.replace(path, candidate)
    return f"{INSTALL_DIR_NAME}/retired/{candidate.name}"


def uninstall(codex_home: Path) -> dict[str, Any]:
    state = _state(codex_home)
    manifest = _load_owned_manifest(state["manifest_path"])
    hooks = _hooks_document(state["hooks_path"])
    markers = {
        "SessionStart": SESSION_STATUS_MESSAGE,
        "PostToolUse": SNAPSHOT_STATUS_MESSAGE,
    }
    group_indexes = {
        event_name: _managed_group_index(
            hooks["hooks"][event_name],
            expected_group,
            marker=markers[event_name],
        )
        for event_name, expected_group in state["expected"].items()
    }
    target_exists = _lexists(state["installed_script"])
    if target_exists:
        installed_hash = _sha256_bytes(
            _regular_file_bytes(state["installed_script"], "installed Context Canvas hook script")
        )
        allowed_hashes = {state["source_hash"]}
        if manifest is not None:
            allowed_hashes.add(manifest["installed_sha256"])
        if installed_hash not in allowed_hashes:
            raise InstallerError("refusing to retire a drifted Context Canvas hook script")
    changed = any(index is not None for index in group_indexes.values()) or target_exists or manifest is not None
    archived: list[str] = []
    for event_name, group_index in group_indexes.items():
        if group_index is not None:
            del hooks["hooks"][event_name][group_index]
    if any(index is not None for index in group_indexes.values()):
        _atomic_write(state["hooks_path"], _json_bytes(hooks))
    archived_target = _archive_owned(
        state["installed_script"], state["install_dir"], "installed Context Canvas hook script"
    )
    if archived_target:
        archived.append(archived_target)
    archived_manifest = _archive_owned(
        state["manifest_path"], state["install_dir"], "Context Canvas hook install manifest"
    )
    if archived_manifest:
        archived.append(archived_manifest)
    return {
        "ok": True,
        "action": "uninstall",
        "changed": changed,
        "source_sha256": state["source_hash"],
        "archived": archived,
        "errors": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install, check, or retire the Context Canvas user-level "
            "SessionStart and PostToolUse hooks"
        )
    )
    parser.add_argument("action", choices=("install", "check", "uninstall"))
    parser.add_argument("--codex-home", help="Absolute Codex home override for tests or profiles")
    args = parser.parse_args(argv)
    try:
        home = _codex_home(args.codex_home)
        if args.action == "install":
            result = install(home)
        elif args.action == "uninstall":
            result = uninstall(home)
        else:
            result = check(home)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    except (InstallerError, OSError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "action": args.action,
                    "changed": False,
                    "errors": [str(exc)],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
