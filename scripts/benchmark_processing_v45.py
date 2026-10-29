"""Repeatable same-host 4.4 -> 4.5 A/B for semantic retrieval preparation.

Reads exact old aura/memory.py from pinned 4.4 Git SHA. No real Ollama:
embedding latency and SQLite-like I/O are explicitly SYNTHETIC. Checks exact
ranking equivalence and reports both a slow-embedding and instant-embedding
scenario to expose any regression due to thread scheduling.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aura.config import Settings
from aura import memory as current

BASELINE = "f46d190790289ccf321cbe85093d270f5238febb"


def old_memory_module():
    source = subprocess.check_output(
        ["git", "show", BASELINE + ":aura/memory.py"], text=True, encoding="utf-8")
    module = types.ModuleType("aura._benchmark_memory45")
    module.__package__ = "aura"
    sys.modules[module.__name__] = module
    exec(compile(source, "aura/memory.py@" + BASELINE, "exec"), module.__dict__)
    return module


class SyntheticDatabase:
    """Identical ordered rows for both implementations; deterministic delays."""

    def __init__(self, db_delay: float):
        self.db_delay = db_delay
        self.notes = [
            {"id": "n" + str(i), "content": "Synthetic note",
             "category": "note", "importance": 3, "created_at": "2026-01-01",
             "vector_json": "[1.0,0.0]"}
            for i in range(100)
        ]
        self.episodes = [
            {"id": "e" + str(i), "role": "user", "content": "Synthetic episode",
             "created_at": "2026-01-01", "vector_json": "[1.0,0.0]"}
            for i in range(100)
        ]

    def search_memories(self, question, limit):
        time.sleep(self.db_delay)
        return []

    def search_episodes(self, question, months, limit):
        time.sleep(self.db_delay)
        return []

    def vectors(self, model, limit):
        time.sleep(self.db_delay)
        return self.notes

    def episode_vectors_in_window(self, model, months):
        time.sleep(self.db_delay)
        return self.episodes


def pct(values: list[float], q: float):
    sorted_values = sorted(values)
    return round(sorted_values[max(0, math.ceil(q * len(values)) - 1)], 3)


def summary(values: list[float]):
    return {
        "runs": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": pct(values, .95),
        "mean_ms": round(statistics.mean(values), 3),
    }


async def scenario(old_class, new_class, *, embedding_delay: float,
                   db_delay: float, runs: int, warmup: int):
    settings = Settings(embedding_model="synthetic-model", database_encryption_required=False)
    old = old_class(settings, SyntheticDatabase(db_delay))
    new = new_class(settings, SyntheticDatabase(db_delay))
    async def fake_embedding(text):
        await asyncio.sleep(embedding_delay)
        return [1.0, 0.0]
    old._embed = fake_embedding
    new._embed = fake_embedding

    # Compare both note and episode ranking, exact ordering, and cosine scores.
    assert await old.recall_pair("synthetic query") == await new.recall_pair(
        "synthetic query"), "A/B changes retrieval results"

    for _ in range(warmup):
        await old.recall_pair("synthetic query")
        await new.recall_pair("synthetic query")

    series = {"baseline": [], "optimized": []}
    generator = random.Random(45)
    for _ in range(runs):
        order = [("baseline", old), ("optimized", new)]
        if generator.random() < 0.5:
            order.reverse()
        for key, model in order:
            start = time.perf_counter_ns()
            await model.recall_pair("synthetic query")
            series[key].append((time.perf_counter_ns() - start) / 1e6)
    return {key: summary(values) for key, values in series.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=24)
    parser.add_argument("--warmup", type=int, default=4)
    parser.add_argument("--output", type=Path, default=Path("benchmark_results_v45.json"))
    args = parser.parse_args()
    if not (8 <= args.runs <= 100 and 2 <= args.warmup <= 20):
        parser.error("runs 8..100 and warmup 2..20 required")
    old = old_memory_module()

    # Compare a simulated 15ms embed + 2ms per SQLite stage against
    # an instant embedding, where extra scheduling can make 4.5 slower.
    async def run():
        return {
            "synthetic_15ms_embed_2ms_db": await scenario(
                old.MemoryEngine, current.MemoryEngine,
                embedding_delay=.015, db_delay=.002, runs=args.runs,
                warmup=args.warmup),
            "instant_embed_0ms_db": await scenario(
                old.MemoryEngine, current.MemoryEngine,
                embedding_delay=0, db_delay=0, runs=args.runs,
                warmup=args.warmup),
        }
    results = asyncio.run(run())
    report = {
        "schema": "expecto-processing-ab-v45",
        "baseline_revision": BASELINE,
        "optimized_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": sys.version.split()[0],
        "data_type": "fully synthetic; no private prompts",
        "ollama_real_model_executed": False,
        "real_sqlite_used": False,
        "output_equivalence_asserted": True,
        "runs": args.runs,
        "benchmarks": results,
        "limitations": [
            "Embedding latency and DB delays are synthetic, not observed hardware latencies.",
            "Python overhead may dominate when the embedding model is instant.",
            "No claim of faster end-to-end Ollama generation or Windows speedups.",
            "GitHub runner scheduling and load may change between runs.",
        ],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for name, result in results.items():
        a = result["baseline"]; b = result["optimized"]
        print(f"{name}: 4.4 p50={a['p50_ms']:.3f}ms, 4.5 p50={b['p50_ms']:.3f}ms"
              f" | 4.4 p95={a['p95_ms']:.3f}ms, 4.5 p95={b['p95_ms']:.3f}ms"
              f" | ratio={a['p50_ms']/max(b['p50_ms'], .000001):.2f}x")
    print("SYNTHETIC I/O. Never interpret as Ollama tokens/second.")
    print("Saved", args.output)


if __name__ == "__main__":
    main()
