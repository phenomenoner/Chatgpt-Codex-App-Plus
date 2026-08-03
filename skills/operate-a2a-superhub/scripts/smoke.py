#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from a2a_superhub.client import HubClient, HubClientError
from a2a_superhub.server import make_server


@contextmanager
def ephemeral_hub():
    state = tempfile.TemporaryDirectory(prefix="a2a-superhub-smoke-")
    sender_token = "smoke-sender-" + uuid.uuid4().hex
    receiver_token = "smoke-receiver-" + uuid.uuid4().hex
    principals = {
        sender_token: {
            "subject": "smoke.sender", "kind": "agent", "tokenId": "tok_smoke_sender",
            "scopes": ["memory.read", "memory.write", "memory.share"],
        },
        receiver_token: {
            "subject": "smoke.receiver", "kind": "agent", "tokenId": "tok_smoke_receiver",
            "scopes": ["memory.read"],
        },
    }
    server = make_server(state.name, port=0, enable_memory=True, enable_delivery=True, principals=principals)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        yield HubClient(base, token=sender_token), HubClient(base, token=receiver_token)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        state.cleanup()


def run_flow(sender: HubClient, receiver: HubClient, *, existing: bool = False) -> dict:
    capabilities = sender.negotiate()
    required = ["memoryFoundation", "memorySharing", "safeWakeup"]
    missing = [name for name in required if capabilities.get(name) is not True]
    if missing:
        raise HubClientError("missing required smoke capabilities: " + ", ".join(missing), kind="capability")
    identity = capabilities.get("principal") or {}
    sender_subject = identity.get("subject")
    receiver_capabilities = receiver.negotiate()
    receiver_subject = (receiver_capabilities.get("principal") or {}).get("subject")
    if not sender_subject or not receiver_subject:
        raise HubClientError("current authenticated principal identity is required", kind="capability")
    key = "smoke:" + uuid.uuid4().hex
    created = sender.create_note(
        {
            "type": "observation",
            "title": "A2A Superhub smoke fixture",
            "body": "Ephemeral transport and authorization smoke fixture.",
            "visibility": f"direct:{receiver_subject}",
            "participants": [sender_subject, receiver_subject],
            "about": [receiver_subject],
            "tags": ["smoke"],
        },
        key,
    )
    fetched = receiver.inbox("smoke-runtime")
    wakeup = receiver.wakeup("smoke-runtime")
    if "cursor" in wakeup:
        raise HubClientError(
            "wakeup preview unexpectedly exposed an ACK cursor",
            kind="contract",
        )
    receiver.ack_inbox("smoke-runtime", fetched["cursor"])
    after = receiver.inbox("smoke-runtime")
    return {
        "schema": "a2a-superhub.skill-smoke.v1",
        "ok": True,
        "ephemeral": not existing,
        "createdNoteId": created["id"],
        "readBack": receiver.read_note(created["id"])["id"] == created["id"],
        "searchHit": any(item["id"] == created["id"] for item in receiver.search("ephemeral transport")["items"]),
        "inboxItems": len(fetched["items"]),
        "wakeupRole": wakeup["role"],
        "unreadAfterAck": len(after["items"]),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Safe A2A Superhub Skill smoke flow")
    parser.add_argument("--url", help="Existing hub target; omitted uses disposable local state")
    parser.add_argument("--receiver-token-env", default="A2A_SUPERHUB_RECEIVER_TOKEN")
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.url:
            if not args.allow_write:
                raise HubClientError("existing-hub smoke requires --allow-write and an explicit target", kind="authority")
            sender_token = os.environ.get("A2A_SUPERHUB_TOKEN")
            receiver_token = os.environ.get(args.receiver_token_env)
            if not sender_token or not receiver_token:
                raise HubClientError("existing-hub smoke requires sender and receiver token environment handles", kind="auth")
            result = run_flow(HubClient(args.url, sender_token), HubClient(args.url, receiver_token), existing=True)
        else:
            with ephemeral_hub() as clients:
                result = run_flow(*clients)
    except HubClientError as exc:
        print(json.dumps({"schema": "a2a-superhub.skill-smoke.v1", "ok": False, "error": {"kind": exc.kind, "message": str(exc)}}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
