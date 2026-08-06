#!/usr/bin/env python3
"""Small, repeatable latency probe for the Context Canvas local surfaces."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("context_canvas.py")
MCP_SCRIPT = Path(__file__).with_name("context_canvas_mcp.py")
SPEC = importlib.util.spec_from_file_location("context_canvas_benchmark", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("context canvas store could not be loaded")
canvas = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canvas)


def _summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
        return ordered[index]

    return {
        "count": float(len(samples)),
        "min_ms": round(ordered[0], 3),
        "p50_ms": round(percentile(0.50), 3),
        "p95_ms": round(percentile(0.95), 3),
        "max_ms": round(ordered[-1], 3),
    }


def _measure(iterations: int, action: Callable[[], Any]) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        action()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return samples


def _mcp_samples(environment: dict[str, str], canvas_id: str, iterations: int) -> list[float]:
    process = subprocess.Popen(
        [sys.executable, "-B", "-I", str(MCP_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    assert process.stdin is not None and process.stdout is not None
    request_id = 0

    def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        nonlocal request_id
        request_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server ended before replying")
        return json.loads(line)

    stderr = ""
    try:
        request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "benchmark", "version": "1"},
            },
        )
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        request("tools/call", {"name": "canvas_read", "arguments": {"canvas_id": canvas_id}})
        return _measure(
            iterations,
            lambda: request(
                "tools/call", {"name": "canvas_read", "arguments": {"canvas_id": canvas_id}}
            ),
        )
    finally:
        process.stdin.close()
        process.wait(timeout=20)
        if process.stderr is not None:
            stderr = process.stderr.read()
            process.stderr.close()
        process.stdout.close()
        if process.returncode != 0:
            raise RuntimeError(f"MCP benchmark server exited {process.returncode}: {stderr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Context Canvas local read surfaces")
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--cold-cli-iterations", type=int, default=5)
    args = parser.parse_args(argv)
    if not 3 <= args.iterations <= 500:
        parser.error("--iterations must be between 3 and 500")
    if not 1 <= args.cold_cli_iterations <= 20:
        parser.error("--cold-cli-iterations must be between 1 and 20")

    with tempfile.TemporaryDirectory(prefix="context-canvas-codex-benchmark-") as temporary:
        root = Path(temporary) / "data"
        environment = os.environ.copy()
        environment[canvas.TEST_MODE_ENV] = "1"
        environment[canvas.TEST_ROOT_ENV] = str(root)
        store = canvas.CanvasStore(root=root)
        canvas_id = canvas.derive_canvas_id("benchmark-session")
        store.initialize(canvas_id, goal="Benchmark bounded Context Canvas reads")
        for index in range(12):
            store.add_node(
                canvas_id,
                kind="plan",
                status_value="planned",
                summary=f"benchmark plan {index}",
            )
        store.read(canvas_id)
        in_process = _measure(args.iterations, lambda: store.read(canvas_id))
        search = _measure(
            args.iterations,
            lambda: store.search("benchmark plan", canvas_id=canvas_id, limit=10),
        )

        def cold_cli() -> None:
            completed = subprocess.run(
                [sys.executable, "-B", "-I", str(SCRIPT), "show", "--canvas-id", canvas_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                timeout=30,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr)

        cli = _measure(args.cold_cli_iterations, cold_cli)
        mcp = _mcp_samples(environment, canvas_id, args.iterations)
        report = {
            "schema": "context-canvas-codex-benchmark.v1",
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "node_count": 13,
            "results": {
                "in_process_read": _summary(in_process),
                "in_process_search": _summary(search),
                "persistent_mcp_read": _summary(mcp),
                "cold_cli_read": _summary(cli),
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
