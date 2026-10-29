"""Reproducible Expecto 4.3 -> 4.4 A/B benchmark on the SAME host.

This tests actual Python work from a pinned Git baseline vs current checkout:
SQLite reads, 384-dimensional cosine, lexical-only preparation, and an
OPEN circuit with a mocked 10ms local-context call. It does NOT run an
Ollama model or measure the user's GPU, RAM residency, speech or latency.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time
import types

BASELINE = "0ad21c90c79ceef069ef861abf35a10e3f9f1bc4"
RESULT_PATH = Path("benchmark_results_v44.json")


def old_module(path: str, suffix: str):
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:{path}"], text=True, encoding="utf-8")
    module = types.ModuleType("aura._benchmark_" + suffix)
    module.__package__ = "aura"
    sys.modules[module.__name__] = module
    exec(compile(source, path + "@" + BASELINE, "exec"), module.__dict__)
    return module


def stats(samples: list[float]) -> dict:
    data = sorted(samples)
    return {
        "p50_ms": round(statistics.median(data), 5),
        "p95_ms": round(data[max(0, math.ceil(0.95 * len(data)) - 1)], 5),
        "mean_ms": round(statistics.mean(data), 5),
        "n": len(data),
    }


def compare_calls(before, after, *, iterations: int, warmup: int):
    # Alternate the order to limit drift due to thermal/CPU noise.
    rng = random.Random(44)
    for i in range(warmup):
        if i % 2:
            before(); after()
        else:
            after(); before()
    values = {"baseline": [], "optimized": []}
    for i in range(iterations):
        for name, action in (
                (("baseline", before), ("optimized", after))
                if rng.randrange(2) == 0
                else (("optimized", after), ("baseline", before))):
            started = time.perf_counter_ns()
            action()
            values[name].append((time.perf_counter_ns() - started) / 1e6)
    return {key: stats(rows) for key, rows in values.items()}


def benchmark_sqlite(db_old, db_new, *, iterations: int, warmup: int):
    def op(db):
        with db.connect() as conn:
            return conn.execute("SELECT count(*) FROM memories").fetchone()[0]
    assert op(db_old) == op(db_new)
    return compare_calls(lambda: op(db_old), lambda: op(db_new),
                         iterations=iterations, warmup=warmup)


def benchmark_cosine(old_cosine, new_cosine, *, iterations: int, warmup: int):
    rng = random.Random(452)
    query = [rng.uniform(-1, 1) for _ in range(384)]
    corpus = [[rng.uniform(-1, 1) for _ in range(384)] for _ in range(400)]
    norm = math.sqrt(sum(x * x for x in query))
    def action(fn):
        return sum(fn(query, row, left_norm=norm) for row in corpus)
    a, b = action(old_cosine), action(new_cosine)
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10), (a, b)
    return compare_calls(
        lambda: action(old_cosine), lambda: action(new_cosine),
        iterations=max(14, iterations // 6), warmup=max(3, warmup // 4))


class EmptyMemory:
    model = ""
    async def recall(self, question, limit):
        return []
    async def recall_episodes(self, question, months, limit):
        return []


async def measure_context(old_llm, new_llm, *, iterations: int, warmup: int):
    from aura.config import Settings

    cfg = Settings(database_encryption_required=False)
    models = [old_llm.Ollama(cfg, object(), EmptyMemory()),
              new_llm.Ollama(cfg, object(), EmptyMemory())]
    for model in models:
        model._local_context_parts = lambda _: ([], [], [], [], [], "", "")
    old_result = await models[0]._personal_context("Como está o meu projeto?")
    new_result = await models[1]._personal_context("Como está o meu projeto?")
    assert old_result == new_result
    async def sample(model, times):
        for _ in range(times):
            await model._personal_context("Como está o meu projeto?")
    for model in models:
        await sample(model, warmup)
    result = {"baseline": [], "optimized": []}
    rng = random.Random(444)
    for _ in range(iterations):
        for key, model in (
                (("baseline", models[0]), ("optimized", models[1]))
                if rng.randrange(2) == 0
                else (("optimized", models[1]), ("baseline", models[0]))):
            start = time.perf_counter_ns()
            await model._personal_context("Como está o meu projeto?")
            result[key].append((time.perf_counter_ns() - start) / 1e6)
    return {k: stats(v) for k, v in result.items()}


async def measure_open_circuit(old_llm, new_llm, *, iterations: int, warmup: int):
    from aura.config import Settings
    from aura.ollama_resilience import OllamaCircuitBreaker
    cfg = Settings(database_encryption_required=False)
    old = old_llm.Ollama(cfg, object(), EmptyMemory())
    new = new_llm.Ollama(cfg, object(), EmptyMemory())
    calls = {"baseline": 0, "optimized": 0}
    for key, model in [("baseline", old), ("optimized", new)]:
        model._circuit = OllamaCircuitBreaker(threshold=1, cooldown_s=3600)
        model._circuit.failure()
        async def fake_context(question, label=key):
            calls[label] += 1
            await asyncio.sleep(0.01)  # SYNTHETIC 10ms, not measured device latency
            return "context", "", ""
        model._personal_context = fake_context

    async def once(model):
        return await model.reply("Qual era o meu projeto?")
    a, b = await once(old), await once(new)
    assert a == b
    for _ in range(warmup):
        await once(old)
        await once(new)
    data = {"baseline": [], "optimized": []}
    rng = random.Random(42)
    for _ in range(max(12, iterations // 15)):
        for key, model in (
                (("baseline", old), ("optimized", new))
                if rng.randrange(2) == 0
                else (("optimized", new), ("baseline", old))):
            start = time.perf_counter_ns()
            await once(model)
            data[key].append((time.perf_counter_ns() - start) / 1e6)
    assert calls["baseline"] > 0 and calls["optimized"] == 0
    return {**{k: stats(v) for k, v in data.items()},
            "unnecessary_context_calls": calls,
            "synthetic_context_delay_ms": 10}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=220)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--output", type=Path, default=RESULT_PATH)
    args = parser.parse_args()
    if not (20 <= args.iterations <= 2000 and 2 <= args.warmup <= 150):
        parser.error("Out-of-range iterations or warmup")

    from aura.database import Database
    from aura import memory as new_memory, llm as new_llm
    old_database = old_module("aura/database.py", "database")
    old_memory = old_module("aura/memory.py", "memory")
    old_llm = old_module("aura/llm.py", "llm")
    with tempfile.TemporaryDirectory(prefix="expecto-benchmark-") as d:
        path = Path(d) / "benchmark.sqlite3"
        base_db = old_database.Database(path)
        current_db = Database(path)
        with current_db.connect() as db:
            db.executemany(
                "INSERT INTO memories(id,content,created_at,updated_at,category,importance,status) "
                "VALUES (?,?,?,?,?,?,?)",
                [(f"bench-{i}", "Synthetic benchmark only", "2026-01-01",
                  "2026-01-01", "note", 3, "active")
                 for i in range(1000)])
        sqlite = benchmark_sqlite(
            base_db, current_db, iterations=args.iterations, warmup=args.warmup)
        cosine = benchmark_cosine(
            old_memory.cosine, new_memory.cosine,
            iterations=args.iterations, warmup=args.warmup)
        lexical = asyncio.run(measure_context(
            old_llm, new_llm, iterations=args.iterations, warmup=args.warmup))
        breaker = asyncio.run(measure_open_circuit(
            old_llm, new_llm, iterations=args.iterations, warmup=args.warmup))
    result = {
        "schema": "expecto-processing-ab-v44",
        "benchmark_type": "same-host pinned-Git-code A/B (offline, synthetic)",
        "ollama_real_model_executed": False,
        "baseline_git_revision": BASELINE,
        "optimized_git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "iterations": args.iterations,
        "warmup": args.warmup,
        "benchmarks": {
            "sqlite_1000rows_read": sqlite,
            "cosine_400vectors_384dimensions": cosine,
            "lexical_context_without_embeddings": lexical,
            "open_circuit_simulated_10ms_context": breaker,
        },
        "warnings": [
            "No actual Ollama model or voice generation was run.",
            "Synthetic 10 ms delay is injected into the old, open-circuit context path.",
            "Python microbenchmarks do not imply equivalent end-to-end acceleration.",
            "CI runner CPU and load vary between executions.",
            "Actual Windows results must be benchmarked separately.",
        ],
    }
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("Expecto Performance 4.4 pinned Git A/B")
    print(f"Baseline {BASELINE[:12]} -> current {result['optimized_git_revision'][:12]}")
    for name, data in result["benchmarks"].items():
        prior, now = data["baseline"], data["optimized"]
        speedup = prior["p50_ms"] / max(now["p50_ms"], 1e-7)
        print(f"{name}: old p50={prior['p50_ms']:.5f} ms; "
              f"new p50={now['p50_ms']:.5f} ms; "
              f"old p95={prior['p95_ms']:.5f} ms; "
              f"new p95={now['p95_ms']:.5f} ms; "
              f"p50 ratio={speedup:.2f}x")
    print("WARN: offline Python microbenchmarks, not actual model inference.")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
