#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from a2a_superhub.client import HubClient, HubClientError


PROFILE_SCHEMA = "a2a-superhub.connection.v1"
SUBJECT_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


class ConnectionProfileError(RuntimeError):
    pass


def _is_link(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _validate_url(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectionProfileError("connection profile URL must be a string")
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
        raise ConnectionProfileError(
            "connection profile URL must be an HTTP(S) origin without credentials, query, or fragment"
        )
    return value.rstrip("/")


def load_profile(path_value: str | None) -> dict[str, str]:
    if not path_value:
        raise ConnectionProfileError("set A2A_SUPERHUB_CONNECTION_FILE to a private connection profile")
    raw_path = Path(path_value)
    if not raw_path.is_absolute():
        raise ConnectionProfileError("connection profile path must be absolute")
    if _is_link(raw_path):
        raise ConnectionProfileError("connection profile must not be a symlink or junction")
    path = raw_path.resolve(strict=False)
    if not path.is_file():
        raise ConnectionProfileError("connection profile is missing or is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConnectionProfileError("connection profile is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {"schema", "subject", "token", "url"}:
        raise ConnectionProfileError("connection profile fields do not match the supported schema")
    if value.get("schema") != PROFILE_SCHEMA:
        raise ConnectionProfileError("connection profile schema is unsupported")
    subject = value.get("subject")
    token = value.get("token")
    if not isinstance(subject, str) or not SUBJECT_PATTERN.fullmatch(subject):
        raise ConnectionProfileError("connection profile subject is invalid")
    if not isinstance(token, str) or len(token) < 16:
        raise ConnectionProfileError("connection profile token is missing or invalid")
    return {"subject": subject, "token": token, "url": _validate_url(value.get("url"))}


def verify_profile(profile: dict[str, str]) -> dict[str, object]:
    capabilities = HubClient(profile["url"], profile["token"]).negotiate()
    if capabilities.get("compatibility") != "current":
        raise ConnectionProfileError("hub does not expose the current authenticated capability surface")
    principal = capabilities.get("principal")
    actual_subject = principal.get("subject") if isinstance(principal, dict) else None
    if actual_subject != profile["subject"]:
        raise ConnectionProfileError("authenticated hub subject does not match the connection profile")
    if capabilities.get("memoryFoundation") is not True:
        raise ConnectionProfileError("hub memory foundation is not enabled")
    return {
        "schema": "a2a-superhub.connection-check.v1",
        "ok": True,
        "subject": actual_subject,
        "url": profile["url"],
        "compatibility": capabilities["compatibility"],
        "memoryFoundation": True,
        "secretsPrinted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Launch the A2A Superhub MCP sidecar from a private connection profile"
    )
    parser.add_argument("--connection-file", help="Absolute profile path; defaults to A2A_SUPERHUB_CONNECTION_FILE")
    parser.add_argument("--check", action="store_true", help="Verify identity and capabilities, then exit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        profile = load_profile(args.connection_file or os.environ.get("A2A_SUPERHUB_CONNECTION_FILE"))
        result = verify_profile(profile)
        if args.check:
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"Ready: {result['subject']}")
            return 0
        os.environ["A2A_SUPERHUB_URL"] = profile["url"]
        os.environ["A2A_SUPERHUB_TOKEN"] = profile["token"]
        from a2a_superhub.mcp_server import main as mcp_main

        return mcp_main([])
    except ConnectionProfileError as exc:
        payload = {
            "schema": "a2a-superhub.connection-check.v1",
            "ok": False,
            "error": {"kind": "configuration", "message": str(exc)},
        }
        print(json.dumps(payload) if args.json else f"connection failed: {exc}", file=sys.stderr)
        return 2
    except HubClientError as exc:
        payload = {
            "schema": "a2a-superhub.connection-check.v1",
            "ok": False,
            "error": {"kind": exc.kind, "status": exc.status, "message": str(exc)},
        }
        print(json.dumps(payload) if args.json else f"connection failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
