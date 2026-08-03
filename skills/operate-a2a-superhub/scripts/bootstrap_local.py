#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse


PROFILE_SCHEMA = "a2a-superhub.connection.v1"
SUBJECT_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
AGENT_SCOPES = [
    "task.read",
    "task.write",
    "memory.read",
    "memory.write",
    "memory.share",
]


class BootstrapError(RuntimeError):
    pass


def _is_link(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _validate_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise BootstrapError("hub URL must be an explicit HTTP(S) origin without credentials, query, or fragment")
    return value.rstrip("/")


def _validate_subject(value: str) -> str:
    if not SUBJECT_PATTERN.fullmatch(value):
        raise BootstrapError(f"invalid principal subject: {value!r}")
    return value


def _token_id(subject: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]", "_", subject)[:44].strip("_")
    suffix = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:8]
    return f"tok_{normalized}_{suffix}"


def _write_private_json(path: Path, value: object) -> None:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def bootstrap(root_value: str, url_value: str, agents: list[str]) -> dict[str, object]:
    raw_root = Path(root_value)
    if not raw_root.is_absolute():
        raise BootstrapError("runtime root must be an absolute path")
    if raw_root.exists() and _is_link(raw_root):
        raise BootstrapError("runtime root must not be a symlink or junction")
    root = raw_root.resolve(strict=False)
    if root == Path(root.anchor):
        raise BootstrapError("filesystem roots are not valid runtime roots")
    url = _validate_url(url_value)
    subjects = [_validate_subject(value) for value in agents]
    if not subjects:
        raise BootstrapError("at least one agent subject is required")
    if len(set(subjects)) != len(subjects):
        raise BootstrapError("agent subjects must be unique")
    operator_subject = "local.operator"
    if operator_subject in subjects:
        raise BootstrapError(f"{operator_subject!r} is reserved for the operator profile")

    registry_path = root / "principals.json"
    connection_root = root / "connections"
    profile_paths = {subject: connection_root / f"{subject}.json" for subject in subjects}
    operator_profile = connection_root / f"{operator_subject}.json"
    targets = [registry_path, operator_profile, *profile_paths.values()]
    existing = [path.name for path in targets if path.exists()]
    if existing:
        raise BootstrapError("refusing to overwrite existing runtime credentials")

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if _is_link(root):
        raise BootstrapError("runtime root became a symlink or junction")
    connection_root.mkdir(exist_ok=True, mode=0o700)
    if _is_link(connection_root):
        raise BootstrapError("connection directory must not be a symlink or junction")
    try:
        os.chmod(root, 0o700)
        os.chmod(connection_root, 0o700)
    except OSError:
        pass

    credentials: dict[str, str] = {
        subject: secrets.token_urlsafe(32) for subject in [*subjects, operator_subject]
    }
    registry: dict[str, dict[str, object]] = {}
    for subject in subjects:
        registry[credentials[subject]] = {
            "kind": "agent",
            "scopes": AGENT_SCOPES,
            "subject": subject,
            "tokenId": _token_id(subject),
        }
    registry[credentials[operator_subject]] = {
        "kind": "operator",
        "scopes": ["hub.admin"],
        "subject": operator_subject,
        "tokenId": _token_id(operator_subject),
    }

    created: list[Path] = []
    try:
        _write_private_json(registry_path, registry)
        created.append(registry_path)
        for subject, profile_path in [*profile_paths.items(), (operator_subject, operator_profile)]:
            _write_private_json(
                profile_path,
                {
                    "schema": PROFILE_SCHEMA,
                    "subject": subject,
                    "token": credentials[subject],
                    "url": url,
                },
            )
            created.append(profile_path)
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise

    return {
        "schema": "a2a-superhub.local-bootstrap.v1",
        "ok": True,
        "root": str(root),
        "principalRegistry": str(registry_path),
        "connections": {
            subject: str(path) for subject, path in [*profile_paths.items(), (operator_subject, operator_profile)]
        },
        "secretsPrinted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a private local principal registry and per-agent connection profiles"
    )
    parser.add_argument("--root", required=True, help="Absolute private runtime directory")
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    parser.add_argument("--agent", action="append", dest="agents")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = bootstrap(args.root, args.url, args.agents or ["agent.alpha", "agent.beta"])
    except (BootstrapError, OSError) as exc:
        payload = {
            "schema": "a2a-superhub.local-bootstrap.v1",
            "ok": False,
            "error": {"kind": "configuration", "message": str(exc)},
        }
        print(json.dumps(payload) if args.json else f"bootstrap failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"Created {result['root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
