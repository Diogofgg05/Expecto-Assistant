"""Reproducible proxy benchmark for cold construction of Expecto services.

No external requests or Ollama inference. Measures lazy construction vs
forced eager construction *in the same code version*, not a prior-commit A/B.
Usage: python scripts/benchmark_chiplets.py --runs 5
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

# Allow direct invocation from the repository root on all CI runners.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _peak_rss_kib() -> float | None:
    """OS peak RSS (KiB) where available; unlike tracemalloc includes native heap."""
    try:
        import resource
    except ImportError:  # Windows: resource is not part of the standard library.
        return None
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / 1024 if sys.platform == 'darwin' else float(raw), 1)


def sample(mode: str) -> dict:
    tracemalloc.start()
    start = time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix='expecto-chiplet-bench-') as directory:
        from aura.config import Settings
        from aura.database import Database
        from aura.engine import AuraEngine
        settings = Settings(data_dir=Path(directory), database_encryption_required=False,
                            auto_extract_memory=False, episodic_capture=False)
        engine = AuraEngine(settings, Database(Path(directory) / 'test.sqlite3'))
        if mode == 'eager':
            for name in engine._CHIPLET_CLASSES:
                getattr(engine, name)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        result = {'mode': mode, 'elapsed_ms': round(elapsed_ms, 3),
                  'python_alloc_current_kib': round(current_bytes / 1024, 1),
                  'python_alloc_peak_kib': round(peak_bytes / 1024, 1),
                  'process_rss_peak_kib': _peak_rss_kib(),
                  'active': engine.chiplet_status()['active_count']}
    tracemalloc.stop()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--worker', choices=['lazy', 'eager'])
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(sample(args.worker)))
        return
    if not (1 <= args.runs <= 50):
        parser.error('runs must be between 1 and 50')
    output = {}
    for mode in ('lazy', 'eager'):
        rows = []
        for _ in range(args.runs):
            process = subprocess.run(
                [sys.executable, __file__, '--worker', mode],
                check=True, text=True, capture_output=True, timeout=90,
            )
            rows.append(json.loads(process.stdout))
        output[mode] = {
            'runs': len(rows),
            'median_construction_ms': round(
                statistics.median(item['elapsed_ms'] for item in rows), 3),
            'median_python_allocation_peak_kib': round(
                statistics.median(item['python_alloc_peak_kib'] for item in rows), 1),
            'median_python_allocation_current_kib': round(
                statistics.median(item['python_alloc_current_kib'] for item in rows), 1),
            'median_process_rss_peak_kib': (
                round(statistics.median(item['process_rss_peak_kib'] for item in rows), 1)
                if all(item['process_rss_peak_kib'] is not None for item in rows) else None),
            'active_last_run': rows[-1]['active'],
        }
    print(json.dumps({
        'caveat': 'Proxy only: lazy/eager of same code; Same-version proxy; RSS is peak process memory, not VRAM or energy',
        'results': output
    }, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
