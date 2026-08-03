#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from a2a_superhub.adapter import select_agent_transport
from a2a_superhub.client import HubCapabilityError, HubClient, HubClientError


async def _probe_mcp(url: str, token: str | None) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    child_env = {"A2A_SUPERHUB_URL": url}
    if token:
        child_env["A2A_SUPERHUB_TOKEN"] = token
    if os.environ.get("PYTHONPATH"):
        child_env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "a2a_superhub.mcp_server"],
        env=child_env,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            resources = initialized.capabilities.resources
            return {
                "protocolVersion": initialized.protocolVersion,
                "resourceSubscribe": bool(resources and resources.subscribe),
                "tools": [tool.name for tool in tools.tools],
            }


def inspect_hub(url: str, token: str | None, *, requested_transport: str = "auto") -> dict:
    client = HubClient(url, token=token)
    result = {
        "schema": "a2a-superhub.skill-doctor.v1",
        "target": url,
        "readOnly": True,
        "health": client.health(),
        "ready": client.ready(),
    }
    capabilities = client.negotiate()
    result["capabilities"] = capabilities
    result["compatibility"] = capabilities.get("compatibility")
    mcp_probe = None
    mcp_error = None
    if requested_transport != "http" and capabilities.get("compatibility") == "current":
        try:
            mcp_probe = asyncio.run(_probe_mcp(url, token))
        except Exception as exc:
            mcp_error = type(exc).__name__
            if requested_transport == "mcp":
                raise HubCapabilityError(f"MCP negotiation failed ({mcp_error})") from None
    selection = select_agent_transport(
        mcp_protocol_version=mcp_probe.get("protocolVersion") if mcp_probe else None,
        mcp_resources_subscribe=bool(mcp_probe and mcp_probe.get("resourceSubscribe")),
        http_compatibility=str(capabilities.get("compatibility") or "current"),
    )
    result["transport"] = {
        "requested": requested_transport,
        "selected": selection.transport,
        "resourceRefresh": selection.resource_refresh,
        "compatibility": selection.compatibility,
        "readOnly": selection.read_only,
    }
    if mcp_probe:
        result["transport"]["mcp"] = mcp_probe
    elif mcp_error:
        result["transport"]["fallbackReason"] = mcp_error
    principal = capabilities.get("principal") if isinstance(capabilities, dict) else None
    scopes = principal.get("scopes", []) if isinstance(principal, dict) else []
    if capabilities.get("operationalDiagnostics") and "hub.admin" in scopes:
        result["operations"] = client.request("GET", "/v1/operations/diagnostics")
    elif "memory.admin" in scopes:
        result["memoryStats"] = client.request("GET", "/v1/memory/stats")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only A2A Superhub capability and health doctor")
    parser.add_argument("--url", default=os.environ.get("A2A_SUPERHUB_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--token-env", default="A2A_SUPERHUB_TOKEN")
    parser.add_argument("--transport", choices=("auto", "http", "mcp"), default="auto")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)
    token = os.environ.get(args.token_env)
    try:
        result = inspect_hub(args.url, token, requested_transport=args.transport)
    except HubClientError as exc:
        result = {
            "schema": "a2a-superhub.skill-doctor.v1",
            "ok": False,
            "readOnly": True,
            "error": {"kind": exc.kind, "status": exc.status, "code": exc.code, "message": str(exc)},
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if exc.kind == "auth" else 4 if exc.kind == "connection" else 2
    result["ok"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
