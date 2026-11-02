"""Synthetic comparison: old full-list SQLite vector scan vs streamed top-k.

Never reads user memory or contacts Ollama. Timing includes SQLite fetch and
cosine ranking. Peak Python allocations measured with tracemalloc (not RSS).
"""
from __future__ import annotations
import argparse
import json
import random
import statistics
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory

from aura.database import Database
from aura.db_shared import now
from aura.memory import cosine, top_semantic


def _measure(fn):
    tracemalloc.start()
    start = time.perf_counter()
    result = fn()
    elapsed = (time.perf_counter() - start) * 1000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak


def run(rows: int = 1200, dims: int = 64, runs: int = 3, batch: int = 128) -> dict:
    if not (1 <= rows <= 20000 and 2 <= dims <= 1024 and 1 <= runs <= 20
            and 1 <= batch <= 256):
        raise ValueError("Invalid benchmark limits")
    rng = random.Random(705)
    query = [rng.uniform(-1, 1) for _ in range(dims)]
    with TemporaryDirectory(prefix="expecto-vector-bench-") as tmp:
        db = Database(Path(tmp) / "synthetic.sqlite3")
        timestamp = now()
        records = []
        for i in range(rows):
            vector = [rng.uniform(-1, 1) for _ in range(dims)]
            records.append((f"n{i:06d}", f"Synthetic note {i}", timestamp,
                            json.dumps(vector, separators=(",", ":"))))
        with db.connect() as con:
            con.executemany(
                "INSERT INTO memories(id,content,created_at,updated_at,category,topic,"
                "source,status,importance) VALUES(?,?,?,?,?,?,?,?,?)",
                [(ident, content, stamp, stamp, 'note', '', 'explicit_user', 'active', 3)
                 for ident, content, stamp, _ in records])
            con.executemany(
                "INSERT INTO memory_vectors(memory_id,model,vector_json,updated_at) "
                "VALUES(?,?,?,?)",
                [(ident, 'synthetic', vector, stamp)
                 for ident, _, stamp, vector in records])

        def baseline():
            items = db.vectors('synthetic', rows)
            scores = [(cosine(query, json.loads(item['vector_json'])), idx,
                       item['id']) for idx, item in enumerate(items)]
            return [(ident, round(score, 12)) for score, idx, ident in sorted(
                scores, key=lambda item: item[0], reverse=True)[:12]]

        def streaming():
            winners, _ = top_semantic(
                query, db.iter_memory_vectors('synthetic', rows, batch),
                threshold=-1.0, limit=12)
            return [(ident, round(score, 12)) for ident, score, _ in winners]

        base_times, stream_times, base_peaks, stream_peaks = [], [], [], []
        for _ in range(runs):
            expected, t, mem = _measure(baseline)
            base_times.append(t)
            base_peaks.append(mem)
            actual, t, mem = _measure(streaming)
            stream_times.append(t)
            stream_peaks.append(mem)
            if actual != expected:
                raise AssertionError("Streaming candidate ranking changed the baseline top-12")
        median_base, median_stream = map(statistics.median, (base_times, stream_times))
        return {
            "benchmark": "synthetic SQLite vector scan + cosine exact top-k",
            "rows": rows, "dimensions": dims, "runs": runs,
            "batch_size": batch, "same_top12": True,
            "baseline_median_ms": round(median_base, 3),
            "stream_median_ms": round(median_stream, 3),
            "baseline_peak_python_kib": round(statistics.median(base_peaks)/1024, 1),
            "stream_peak_python_kib": round(statistics.median(stream_peaks)/1024, 1),
            "stream_peak_python_reduction_pct": round(
                (1-statistics.median(stream_peaks)/max(1, statistics.median(base_peaks)))*100, 1),
            "notes": [
                "Measured Python allocations, not total resident RAM, GPU VRAM or power",
                "Does not measure Ollama inference, embeddings generation or answer quality",
                "Identical synthetic top-12 candidates, not a production latency promise",
            ],
        }


def main():
    p = argparse.ArgumentParser(description="Compare list vs streaming SQLite retrieval")
    p.add_argument("--rows", type=int, default=1200)
    p.add_argument("--dims", type=int, default=64)
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--output", default="")
    args = p.parse_args()
    report = run(args.rows, args.dims, args.runs, args.batch)
    printed = json.dumps(report, ensure_ascii=False, indent=2)
    print(printed)
    if args.output:
        Path(args.output).write_text(printed + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
