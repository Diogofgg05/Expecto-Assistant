"""Measure perceived latency with local Ollama, without touching Expecto memory.

Run:
    python -m scripts.benchmark_ollama_streaming --runs 20 --warmup 2

Measurements are actual local timings, not estimates. Uses only loopback Ollama.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

import httpx

from aura.config import Settings


def loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Ollama must be HTTP loopback without credentials.')
    try:
        trusted = ip_address(parsed.hostname).is_loopback
    except ValueError:
        trusted = parsed.hostname == 'localhost'
    if not trusted:
        raise ValueError('This benchmark only connects to locally running Ollama.')
    return value.rstrip('/')


def percentile(samples: list[float], p: float) -> float | None:
    if not samples:
        return None
    values = sorted(samples)
    return round(values[max(0, math.ceil(p * len(values)) - 1)], 1)


def summary(measures: list[dict]) -> dict:
    metrics = {}
    for name in ('ttft_ms', 'total_ms', 'tokens_per_s'):
        values = [row[name] for row in measures if row.get(name) is not None]
        metrics[name] = {
            'p50': round(statistics.median(values), 1) if values else None,
            'p95': percentile(values, 0.95),
        }
    metrics['runs'] = len(measures)
    return metrics


async def measure(client: httpx.AsyncClient, url: str, model: str,
                  prompt: str, keep_alive: str, *, streamed: bool) -> dict:
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'stream': streamed,
        'keep_alive': keep_alive,
        'options': {'temperature': 0, 'num_predict': 90},
    }
    began = time.perf_counter()
    first = None
    final = {}
    if streamed:
        async with client.stream('POST', url + '/api/chat', json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get('error'):
                    raise RuntimeError(str(data['error']))
                piece = data.get('message', {}).get('content', '')
                if piece and first is None:
                    first = time.perf_counter()
                if data.get('done'):
                    final = data
    else:
        response = await client.post(url + '/api/chat', json=payload)
        response.raise_for_status()
        final = response.json()
    ended = time.perf_counter()
    eval_count = final.get('eval_count')
    eval_duration = final.get('eval_duration')
    speed = (eval_count * 1e9 / eval_duration
             if isinstance(eval_count, (int, float)) and
             isinstance(eval_duration, (int, float)) and eval_duration > 0 else None)
    return {
        'ttft_ms': round((first - began) * 1000, 1) if first else None,
        'total_ms': round((ended - began) * 1000, 1),
        'tokens_per_s': round(speed, 2) if speed is not None else None,
    }


async def benchmark(args):
    settings = Settings.from_env()
    endpoint = loopback_url(settings.ollama_url)
    model = args.model or settings.ollama_model
    prompt = 'Responde em português de Portugal: explica de forma simples a diferença entre memória RAM e armazenamento.'
    results = {'streaming': [], 'standard': []}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3)) as client:
        for index in range(args.warmup + args.runs):
            # Alternate order to avoid always giving the warmed model to one mode.
            modes = [True, False] if index % 2 == 0 else [False, True]
            for streamed in modes:
                row = await measure(client, endpoint, model, prompt, settings.ollama_keep_alive, streamed=streamed)
                if index >= args.warmup:
                    results['streaming' if streamed else 'standard'].append(row)
    result = {
        'model': model,
        'runs_per_mode': args.runs,
        'warmup_pairs': args.warmup,
        'streaming': summary(results['streaming']),
        'standard': summary(results['standard']),
        'limitations': 'Local timings only; no model accuracy claims. Standard mode first visible output occurs at total completion.',
    }
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description='Compare Ollama streaming and standard response latency')
    parser.add_argument('--runs', type=int, default=20)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--model', default=None)
    parser.add_argument('--output', default='')
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 100 or args.warmup < 0 or args.warmup > 10:
        parser.error('runs must be 1–100 and warmup 0–10')
    try:
        asyncio.run(benchmark(args))
    except (httpx.HTTPError, RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, 'Benchmark failed: ' + str(exc) + '\\n')


if __name__ == '__main__':
    main()
