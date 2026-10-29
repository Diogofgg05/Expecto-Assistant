"""Expecto 4.5 vs 4.6: real localhost HTTP transport A/B.

The request/response is a synthetic in-process *mock Ollama* HTTP server,
NOT a model inference benchmark. Measures real loopback TCP connections and
their per-call Python/HTTPX overhead, with a fixed Git 4.5 baseline.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import socket
from pathlib import Path
import random
import statistics
import subprocess
import sys
import threading
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aura.config import Settings
from aura.memory import MemoryEngine

BASELINE = "f70296847be02ad95d674e148faebbd2606b4d98"


def old_memory_engine():
    source = subprocess.check_output(
        ["git", "show", BASELINE + ":aura/memory.py"], encoding="utf-8")
    module = types.ModuleType("aura._benchmark_memory_v46_baseline")
    module.__package__ = "aura"
    sys.modules[module.__name__] = module
    exec(compile(source, "aura/memory.py@" + BASELINE, "exec"), module.__dict__)
    return module.MemoryEngine


class MeasuredServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *, tcp_nodelay: bool):
        self.accepted_connections = 0
        self.post_requests = 0
        self.tcp_nodelay = tcp_nodelay
        super().__init__(("127.0.0.1", 0), Handler)

    def get_request(self):
        client, address = super().get_request()
        self.accepted_connections += 1
        return client, address


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        # A tiny payload written as separate HTTP header/body packets may
        # trigger ~40ms delayed ACK on localhost, unlike Go's Ollama server
        # which configures TCP_NODELAY. Benchmark *both* transport cases.
        if self.server.tcp_nodelay:
            self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        super().setup()

    def log_message(self, *args):
        return

    def do_POST(self):
        if self.path != "/api/embed":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", "0"))
        if not 0 < n < 10000:
            self.send_error(413)
            return
        content = json.loads(self.rfile.read(n))
        inputs = content.get("input")
        vectors = [[1.0, 0.0]] if isinstance(inputs, str) else [
            [1.0, 0.0] for _ in inputs
        ]
        response = json.dumps({"embeddings": vectors}).encode("ascii")
        self.server.post_requests += 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


@contextmanager
def two_mock_servers(*, tcp_nodelay: bool):
    a, b = (MeasuredServer(tcp_nodelay=tcp_nodelay),
            MeasuredServer(tcp_nodelay=tcp_nodelay))
    threads = [
        threading.Thread(target=a.serve_forever, daemon=True),
        threading.Thread(target=b.serve_forever, daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        yield a, b
    finally:
        a.shutdown()
        b.shutdown()
        a.server_close()
        b.server_close()
        for t in threads:
            t.join(timeout=3)


def summary(values):
    values = sorted(values)
    return {
        "n": len(values),
        "p50_ms": round(statistics.median(values), 4),
        "p95_ms": round(values[max(0, math.ceil(.95 * len(values)) - 1)], 4),
    }


async def compare(old_type, *, runs: int, warmup: int,
                  tcp_nodelay: bool):
    with two_mock_servers(tcp_nodelay=tcp_nodelay) as (before_server, after_server):
        before = old_type(
            Settings(embedding_model="mock", database_encryption_required=False,
                     ollama_url=f"http://127.0.0.1:{before_server.server_port}"),
            object())
        after = MemoryEngine(
            Settings(embedding_model="mock", database_encryption_required=False,
                     ollama_url=f"http://127.0.0.1:{after_server.server_port}"),
            object())
        values = {"baseline": [], "optimized": []}
        rng = random.Random(46)
        try:
            # The same validation and warm-up for both versions.
            for _ in range(warmup):
                assert await before._embed("synthetic local embedding") == [1., 0.]
                assert await after._embed("synthetic local embedding") == [1., 0.]
            for _ in range(runs):
                tasks = [
                    ("baseline", before),
                    ("optimized", after),
                ]
                if rng.randrange(2):
                    tasks.reverse()
                for key, client in tasks:
                    start = time.perf_counter_ns()
                    result = await client._embed("synthetic local embedding")
                    values[key].append((time.perf_counter_ns() - start) / 1e6)
                    assert result == [1., 0.]
        finally:
            await after.close()
            close_old = getattr(before, "close", None)
            if close_old is not None:
                await close_old()

        assert before_server.post_requests == after_server.post_requests == runs + warmup
        assert before_server.accepted_connections == runs + warmup
        assert after_server.accepted_connections < before_server.accepted_connections
        return {
            "baseline": {**summary(values["baseline"]),
                         "tcp_connections_total": before_server.accepted_connections,
                         "http_requests_total": before_server.post_requests},
            "optimized": {**summary(values["optimized"]),
                          "tcp_connections_total": after_server.accepted_connections,
                          "http_requests_total": after_server.post_requests},
            "response_vectors_equal": True,
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=30)
    p.add_argument("--warmup", type=int, default=4)
    p.add_argument("--output", type=Path,
                   default=Path("benchmark_results_v46.json"))
    args = p.parse_args()
    if not 10 <= args.runs <= 150 or not 1 <= args.warmup <= 20:
        p.error("runs 10..150 and warmup 1..20 required")

    old_type = old_memory_engine()
    async def run_both():
        return {
            "default_http11_mock": await compare(
                old_type, runs=args.runs, warmup=args.warmup, tcp_nodelay=False),
            "tcp_nodelay_mock": await compare(
                old_type, runs=args.runs, warmup=args.warmup, tcp_nodelay=True),
        }
    measured = asyncio.run(run_both())
    report = {
        "schema": "expecto-embedding-transport-ab-v46",
        "baseline_git_revision": BASELINE,
        "optimized_git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "endpoint": "127.0.0.1 ephemeral mock Ollama HTTP/1.1",
        "actual_tcp_connections": True,
        "ollama_model_executed": False,
        "real_ollama_inference_measured": False,
        "response_vectors_equal": True,
        "benchmarks": measured,
        "limitations": [
            "This is a local mock HTTP server, not actual Ollama embedding inference.",
            "The time improvement depends on OS TCP and concurrent load.",
            "Old code opens a new HTTPX connection for each embedding; "
            "the optimized code reuses a bounded keep-alive socket.",
            "Only embedding HTTP transport, not the full Expecto response, is tested.",
        ],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",
                           encoding="utf-8")
    for case_name, result in measured.items():
        a = result["baseline"]
        b = result["optimized"]
        print(f"{case_name}: HTTP requests each={a['http_requests_total']}")
        print(f"{case_name}: TCP connections old={a['tcp_connections_total']}"
              f" new={b['tcp_connections_total']}")
        print(f"{case_name}: p50 old={a['p50_ms']}ms new={b['p50_ms']}ms"
              f" ratio={a['p50_ms']/max(b['p50_ms'], .00001):.2f}x")
        print(f"{case_name}: p95 old={a['p95_ms']}ms new={b['p95_ms']}ms")
    print("MOCK OLLAMA: no real model or Windows hardware inference.")
    print("Saved:", args.output)


if __name__ == "__main__":
    main()
