"""Local Ollama benchmark: real requests only, no invented latency figures.

Run: python -m aura.ollama_benchmark --model MODEL --runs 20 --warmup 2
Streaming TTFT means first content received by client, not server-first-token.
No prompts or model responses are written to the result file.
"""
import argparse
import asyncio
import json
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .multilayer_reasoning import OllamaMultiLayerAdapter


def percentile(values, p):
    """Linear interpolated percentile using sorted observed samples."""
    if not values:
        return None
    a = sorted(values)
    position = (len(a) - 1) * p / 100
    lo = int(position)
    hi = min(lo + 1, len(a) - 1)
    return round(a[lo] + (a[hi] - a[lo]) * (position - lo), 3)


def summarize(rows):
    fields = ("elapsed_ms", "ttft_ms", "total_ms", "load_ms",
              "prompt_eval_ms", "generation_ms", "tokens_per_second")
    result = {}
    for key in fields:
        values = [r[key] for r in rows if isinstance(r.get(key), (int, float))
                  and not isinstance(r.get(key), bool)]
        result[key] = {"samples": len(values), "p50": percentile(values, 50),
                       "p95": percentile(values, 95), "p99": percentile(values, 99)}
    return result


async def benchmark(model, url, runs, warmup, streaming):
    if not 1 <= runs <= 200 or not 0 <= warmup <= 20:
        raise ValueError("Runs must be 1..200 and warmup 0..20")
    rows = []
    async with OllamaMultiLayerAdapter(url, model) as adapter:
        for index in range(warmup + runs):
            prompt = 'Responde em JSON: {"answer":"OK"}.'
            if streaming:
                await adapter.stream_json(prompt)
            else:
                await adapter(prompt)
            if index >= warmup:
                rows.append(dict(adapter.last_metrics))
    return {"model": model, "url": url, "streaming": streaming,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "platform": platform.platform(),
            "runs": runs, "warmup": warmup, "summary": summarize(rows),
            "samples": rows}


def main():
    parser = argparse.ArgumentParser(description="Benchmark real Ollama em ms")
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = asyncio.run(benchmark(args.model,args.url,args.runs,args.warmup,args.stream))
    report = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
