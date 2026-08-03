#!/usr/bin/env python3
"""Fail-closed exporter and validator for the public Codex App Plus bundle."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


MANIFEST_SCHEMA = "codex-plus-public-sources.v1"
LOCK_SCHEMA = "codex-plus-public-lock.v1"

FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "attachments",
    "auth.json",
    "automations",
    "history.jsonl",
    "logs",
    "memories",
    "sessions",
}

FORBIDDEN_CONTENT = (
    (
        "personal Windows home path",
        re.compile(r"[A-Za-z]:" + r"\\Users\\(?!<)[^\\\s]+", re.IGNORECASE),
    ),
    (
        "private workspace path",
        re.compile(r"[A-Za-z]:" + r"\\Warehouse(?:\\|\b)", re.IGNORECASE),
    ),
    (
        "project-specific runtime marker",
        re.compile(r"\.agent-" + r"harness", re.IGNORECASE),
    ),
    (
        "private documentation marker",
        re.compile(r"docs[\\/]\.private", re.IGNORECASE),
    ),
    (
        "GitHub OAuth token",
        re.compile(r"gho_" + r"[A-Za-z0-9]{20,}"),
    ),
    (
        "GitHub personal access token",
        re.compile(r"github_pat_" + r"[A-Za-z0-9_]{20,}"),
    ),
    (
        "OpenAI-style secret key",
        re.compile(r"sk-" + r"[A-Za-z0-9_-]{20,}"),
    ),
    (
        "bearer credential",
        re.compile(r"Bearer\s+" + r"[A-Za-z0-9._~-]{16,}", re.IGNORECASE),
    ),
)

SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:token|secret|password|api[_-]?key|credential)\s*[:=]\s*"
    r"[\"']([^\"']{8,})[\"']"
)
SAFE_PLACEHOLDER_PREFIXES = (
    "${",
    "$env:",
    "<",
    "example",
    "replace-",
    "smoke-",
    "test-",
    "fixture-",
    "dummy-",
    "your_",
    "your-",
)
ALLOWABLE_PUBLIC_FINDINGS = {"project-specific runtime marker"}


class SyncError(ValueError):
    """A deterministic public-safety or manifest error."""


def _json_load(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SyncError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SyncError(
            f"{label} is invalid JSON at line {exc.lineno}, column {exc.colno}: {path}"
        ) from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_resolve(root: Path, relative: str, label: str) -> Path:
    candidate = (root / relative).resolve()
    if not _is_relative_to(candidate, root.resolve()):
        raise SyncError(f"{label} escapes its allowed root: {relative!r}")
    return candidate


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _normalized_text_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if b"\x00" in raw:
        raise SyncError(f"Binary input is not allowed in the public bundle: {path}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SyncError(f"Input is not UTF-8 text: {path}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _scan_text(
    relative: str, text: str, allowed_findings: set[str] | None = None
) -> list[str]:
    errors: list[str] = []
    allowed_findings = allowed_findings or set()
    for label, pattern in FORBIDDEN_CONTENT:
        if pattern.search(text) and label not in allowed_findings:
            errors.append(f"{relative}: contains {label}")
    for match in SECRET_ASSIGNMENT.finditer(text):
        value = match.group(1).lower()
        if not value.startswith(SAFE_PLACEHOLDER_PREFIXES):
            errors.append(f"{relative}: contains a non-placeholder secret assignment")
            break
    return errors


def _scan_path(relative: Path) -> list[str]:
    lowered = {part.lower() for part in relative.parts}
    errors: list[str] = []
    forbidden = sorted(lowered & FORBIDDEN_PARTS)
    if forbidden:
        errors.append(
            f"{relative.as_posix()}: forbidden path component(s): {', '.join(forbidden)}"
        )
    if relative.suffix.lower() in {".bak", ".key", ".pem", ".pfx", ".pyc"}:
        errors.append(f"{relative.as_posix()}: forbidden public file type")
    if relative.name.lower() == ".env":
        errors.append(f"{relative.as_posix()}: raw .env files are forbidden")
    return errors


def _validate_manifest(manifest: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["Manifest must be a JSON object."]
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        errors.append(f"Manifest schemaVersion must be {MANIFEST_SCHEMA!r}.")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        errors.append("Manifest components must be a non-empty array.")
        return errors
    ids: set[str] = set()
    destinations: set[str] = set()
    for index, component in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id:
            errors.append(f"{prefix}.id must be a non-empty string.")
        elif component_id in ids:
            errors.append(f"Duplicate component id: {component_id}")
        else:
            ids.add(component_id)
        mode = component.get("mode")
        if mode == "vendor":
            if component.get("sourceRoot") not in {"codex", "agents"}:
                errors.append(f"{prefix}.sourceRoot must be codex or agents.")
            for field in ("source", "destination"):
                if not isinstance(component.get(field), str) or not component[field]:
                    errors.append(f"{prefix}.{field} must be a non-empty string.")
            destination = component.get("destination")
            if isinstance(destination, str):
                if destination in destinations:
                    errors.append(f"Duplicate vendor destination: {destination}")
                destinations.add(destination)
            if not isinstance(component.get("include", []), list):
                errors.append(f"{prefix}.include must be an array.")
            if not isinstance(component.get("exclude", []), list):
                errors.append(f"{prefix}.exclude must be an array.")
            public_exceptions = component.get("publicExceptions", [])
            if not isinstance(public_exceptions, list):
                errors.append(f"{prefix}.publicExceptions must be an array.")
            else:
                for exception_index, exception in enumerate(public_exceptions):
                    exception_prefix = (
                        f"{prefix}.publicExceptions[{exception_index}]"
                    )
                    if not isinstance(exception, dict):
                        errors.append(f"{exception_prefix} must be an object.")
                        continue
                    if not isinstance(exception.get("path"), str):
                        errors.append(f"{exception_prefix}.path must be a string.")
                    if exception.get("finding") not in ALLOWABLE_PUBLIC_FINDINGS:
                        errors.append(
                            f"{exception_prefix}.finding is not an allowable public "
                            "exception. Credential findings can never be exempted."
                        )
                    if not isinstance(exception.get("reason"), str) or not exception[
                        "reason"
                    ].strip():
                        errors.append(
                            f"{exception_prefix}.reason must be a non-empty string."
                        )
        elif mode == "pointer":
            for field in ("canonicalUrl", "version", "commit", "license"):
                if not isinstance(component.get(field), str) or not component[field]:
                    errors.append(f"{prefix}.{field} must be a non-empty string.")
            commit = component.get("commit")
            if isinstance(commit, str) and not re.fullmatch(r"[0-9a-f]{40}", commit):
                errors.append(f"{prefix}.commit must be a full lowercase Git SHA.")
        else:
            errors.append(f"{prefix}.mode must be vendor or pointer.")
    return errors


def _collect_desired(
    manifest: dict[str, Any],
    repository_root: Path,
    source_roots: dict[str, Path],
) -> tuple[dict[str, tuple[bytes, str]], list[dict[str, str]], list[str]]:
    desired: dict[str, tuple[bytes, str]] = {}
    pointers: list[dict[str, str]] = []
    errors: list[str] = []
    for component in manifest["components"]:
        if component["mode"] == "pointer":
            pointers.append(
                {
                    key: component[key]
                    for key in ("id", "canonicalUrl", "version", "commit", "license")
                }
            )
            continue

        component_id = component["id"]
        source_base = source_roots[component["sourceRoot"]].resolve()
        try:
            source = _safe_resolve(source_base, component["source"], "source")
            destination = _safe_resolve(
                repository_root, component["destination"], "destination"
            )
        except SyncError as exc:
            errors.append(f"{component_id}: {exc}")
            continue
        if not source.is_dir():
            errors.append(f"{component_id}: source directory is missing: {source}")
            continue
        include = component.get("include") or ["*", "**/*"]
        exclude = component.get("exclude") or []
        exception_map: dict[str, set[str]] = {}
        for exception in component.get("publicExceptions", []):
            exception_map.setdefault(exception["path"], set()).add(
                exception["finding"]
            )
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                errors.append(f"{component_id}: symlinks are not vendored: {path}")
                continue
            if not path.is_file():
                continue
            relative_source = path.relative_to(source).as_posix()
            if not _matches(relative_source, include) or _matches(
                relative_source, exclude
            ):
                continue
            relative_destination = (
                destination.relative_to(repository_root) / relative_source
            )
            errors.extend(_scan_path(relative_destination))
            try:
                data = _normalized_text_bytes(path)
            except SyncError as exc:
                errors.append(f"{component_id}: {exc}")
                continue
            errors.extend(
                _scan_text(
                    relative_destination.as_posix(),
                    data.decode("utf-8"),
                    exception_map.get(relative_source, set()),
                )
            )
            key = relative_destination.as_posix()
            if key in desired:
                errors.append(f"Two components produce the same file: {key}")
            else:
                desired[key] = (data, component_id)
    pointers.sort(key=lambda item: item["id"])
    return desired, pointers, errors


def _lock_payload(
    desired: dict[str, tuple[bytes, str]], pointers: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "schemaVersion": LOCK_SCHEMA,
        "files": [
            {
                "path": path,
                "componentId": component_id,
                "bytes": len(data),
                "sha256": _sha256(data),
            }
            for path, (data, component_id) in sorted(desired.items())
        ],
        "pointers": pointers,
    }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _current_vendor_files(
    manifest: dict[str, Any], repository_root: Path
) -> set[str]:
    files: set[str] = set()
    for component in manifest["components"]:
        if component["mode"] != "vendor":
            continue
        destination = _safe_resolve(
            repository_root, component["destination"], "destination"
        )
        if not destination.exists():
            continue
        for path in destination.rglob("*"):
            if path.is_file() or path.is_symlink():
                files.add(path.relative_to(repository_root).as_posix())
    return files


def _remove_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        try:
            path.rmdir()
        except OSError:
            pass


def _repository_exception_map(
    manifest: dict[str, Any], repository_root: Path
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for component in manifest.get("components", []):
        if not isinstance(component, dict) or component.get("mode") != "vendor":
            continue
        destination = component.get("destination")
        if not isinstance(destination, str):
            continue
        for exception in component.get("publicExceptions", []):
            if not isinstance(exception, dict):
                continue
            relative = (Path(destination) / exception.get("path", "")).as_posix()
            result.setdefault(relative, set()).add(exception.get("finding", ""))
    return result


def _scan_repository(
    repository_root: Path, exception_map: dict[str, set[str]] | None = None
) -> list[str]:
    errors: list[str] = []
    exception_map = exception_map or {}
    for path in sorted(repository_root.rglob("*")):
        relative = path.relative_to(repository_root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            errors.append(f"{relative.as_posix()}: public repository symlink is forbidden")
            continue
        if not path.is_file():
            continue
        errors.extend(_scan_path(relative))
        try:
            data = _normalized_text_bytes(path)
        except SyncError as exc:
            errors.append(str(exc))
            continue
        errors.extend(
            _scan_text(
                relative.as_posix(),
                data.decode("utf-8"),
                exception_map.get(relative.as_posix(), set()),
            )
        )
        if path.suffix.lower() == ".json":
            try:
                json.loads(data)
            except json.JSONDecodeError as exc:
                errors.append(
                    f"{relative.as_posix()}: invalid JSON at line {exc.lineno}, "
                    f"column {exc.colno}"
                )
    return errors


def _validate_lock(repository_root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = repository_root / "manifest" / "public-sources.json"
    lock_path = repository_root / "manifest" / "public-lock.json"
    try:
        manifest = _json_load(manifest_path, "public source manifest")
        lock = _json_load(lock_path, "public lock")
    except SyncError as exc:
        return [str(exc)]
    errors.extend(_validate_manifest(manifest))
    if not isinstance(lock, dict) or lock.get("schemaVersion") != LOCK_SCHEMA:
        errors.append(f"Public lock schemaVersion must be {LOCK_SCHEMA!r}.")
        return errors
    files = lock.get("files")
    if not isinstance(files, list):
        errors.append("Public lock files must be an array.")
        return errors
    locked_paths: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"Public lock files[{index}] is invalid.")
            continue
        relative = item["path"]
        if relative in locked_paths:
            errors.append(f"Public lock contains duplicate path: {relative}")
            continue
        locked_paths.add(relative)
        try:
            path = _safe_resolve(repository_root, relative, "locked file")
        except SyncError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"Locked public file is missing: {relative}")
            continue
        data = path.read_bytes()
        if item.get("bytes") != len(data) or item.get("sha256") != _sha256(data):
            errors.append(f"Locked public file drifted: {relative}")
    actual_skill_files = {
        path.relative_to(repository_root).as_posix()
        for path in (repository_root / "skills").rglob("*")
        if path.is_file() or path.is_symlink()
    } if (repository_root / "skills").exists() else set()
    extras = actual_skill_files - locked_paths
    if extras:
        errors.append("Untracked public skill files: " + ", ".join(sorted(extras)))
    expected_pointers = sorted(
        (
            {
                key: component[key]
                for key in ("id", "canonicalUrl", "version", "commit", "license")
            }
            for component in manifest.get("components", [])
            if isinstance(component, dict) and component.get("mode") == "pointer"
        ),
        key=lambda item: item["id"],
    )
    if lock.get("pointers") != expected_pointers:
        errors.append("Public lock pointer set does not match the source manifest.")
    return errors


def _validate_command(args: argparse.Namespace) -> int:
    repository_root = Path(args.repo_root).resolve()
    manifest_path = repository_root / "manifest" / "public-sources.json"
    try:
        manifest = _json_load(manifest_path, "public source manifest")
        exception_map = _repository_exception_map(manifest, repository_root)
    except SyncError:
        exception_map = {}
    errors = _scan_repository(repository_root, exception_map)
    errors.extend(_validate_lock(repository_root))
    payload = {"valid": not errors, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


def _sync_command(args: argparse.Namespace) -> int:
    repository_root = Path(args.repo_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = _json_load(manifest_path, "public source manifest")
    manifest_errors = _validate_manifest(manifest)
    if manifest_errors:
        print(json.dumps({"valid": False, "errors": manifest_errors}, sort_keys=True))
        return 2
    source_roots = {
        "codex": Path(args.codex_home).resolve(),
        "agents": Path(args.agents_home).resolve(),
    }
    desired, pointers, errors = _collect_desired(
        manifest, repository_root, source_roots
    )
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, sort_keys=True))
        return 2

    lock = _lock_payload(desired, pointers)
    lock_relative = "manifest/public-lock.json"
    desired_lock_bytes = _json_bytes(lock)
    current_files = _current_vendor_files(manifest, repository_root)
    desired_files = set(desired)
    changes: list[dict[str, str]] = []
    for relative, (data, _) in sorted(desired.items()):
        path = repository_root / relative
        if not path.exists():
            changes.append({"status": "ADD", "path": relative})
        elif path.read_bytes() != data:
            changes.append({"status": "MODIFY", "path": relative})
    for relative in sorted(current_files - desired_files):
        changes.append({"status": "DELETE", "path": relative})
    lock_path = repository_root / lock_relative
    if not lock_path.exists():
        changes.append({"status": "ADD", "path": lock_relative})
    elif lock_path.read_bytes() != desired_lock_bytes:
        changes.append({"status": "MODIFY", "path": lock_relative})

    if not args.apply:
        print(
            json.dumps(
                {"valid": True, "inSync": not changes, "changes": changes},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if not changes else 1

    for relative, (data, _) in sorted(desired.items()):
        _write_atomic(repository_root / relative, data)
    for relative in sorted(current_files - desired_files):
        path = _safe_resolve(repository_root, relative, "stale vendor file")
        path.unlink()
    _remove_empty_directories(repository_root / "skills")
    _write_atomic(lock_path, desired_lock_bytes)

    exception_map = _repository_exception_map(manifest, repository_root)
    validation_errors = _scan_repository(repository_root, exception_map)
    validation_errors.extend(_validate_lock(repository_root))
    print(
        json.dumps(
            {
                "valid": not validation_errors,
                "applied": True,
                "changes": changes,
                "errors": validation_errors,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not validation_errors else 2


def _default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def _parser() -> argparse.ArgumentParser:
    repository_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Export and validate the public-safe Codex App Plus bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Compare or apply allow-listed sources.")
    sync.add_argument("--repo-root", default=str(repository_default))
    sync.add_argument(
        "--manifest",
        default=str(repository_default / "manifest" / "public-sources.json"),
    )
    sync.add_argument("--codex-home", default=str(_default_codex_home()))
    sync.add_argument("--agents-home", default=str(Path.home() / ".agents"))
    sync.add_argument("--apply", action="store_true")
    sync.set_defaults(handler=_sync_command)

    validate = subparsers.add_parser(
        "validate", help="Scan public hygiene and verify the generated lock."
    )
    validate.add_argument("--repo-root", default=str(repository_default))
    validate.set_defaults(handler=_validate_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (SyncError, OSError) as exc:
        print(
            json.dumps(
                {"valid": False, "errors": [str(exc)]},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
