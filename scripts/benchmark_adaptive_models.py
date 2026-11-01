"""Run a real, paired local-Ollama speed comparison for an optional fast model.

Usage:
  python -m scripts.benchmark_adaptive_models --fast qwen3:0.6b --runs 12 --output adaptive.json

This performs no external requests and uses only neutral, non-personal prompts.
It does not claim answer quality is equivalent to the main model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path

import httpx

from aura.config import Settings
from scripts.benchmark_ollama_streaming import loopback_url, measure, summary


async def run(args):
    settings = Settings.from_env()
    url = loopback_url(settings.ollama_url)
    primary = args.baseline or settings.ollama_model
    alternative = args.fast or settings.ollama_fast_model
    if not alternative:
        raise ValueError('Indica --fast ou configura AURA_OLLAMA_FAST_MODEL no .env.')
    if alternative == primary:
        raise ValueError('É necessário comparar dois modelos diferentes.')

    prompts = [
        'Define um compilador em duas frases, em português de Portugal.',
        'O que é a memória RAM? Responde em duas frases.',
        'Define uma variável em programação, com um exemplo curto.',
        'Explica brevemente o que é um algoritmo.',
    ]
    records = {primary: [], alternative: []}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3),
                                 trust_env=False) as client:
        tags = await client.get(url + '/api/tags')
        tags.raise_for_status()
        installed = {m.get('name') for m in tags.json().get('models', [])}
        for model in (primary, alternative):
            if model not in installed:
                raise ValueError(f'Modelo não instalado: {model}. Executa ollama pull {model}.')
        for i in range(args.warmup + args.runs):
            prompt = prompts[i % len(prompts)]
            # Alternate to limit systematic cold-cache bias.
            ordered = (primary, alternative) if i % 2 == 0 else (alternative, primary)
            for model in ordered:
                result = await measure(client, url, model, prompt,
                                       settings.ollama_keep_alive, streamed=True)
                if i >= args.warmup:
                    records[model].append(result)
    baseline = summary(records[primary])
    candidate = summary(records[alternative])
    b = baseline['ttft_ms']['p50']
    c = candidate['ttft_ms']['p50']
    report = {
        'status': 'measured_on_local_hardware',
        'primary_model': primary,
        'fast_model': alternative,
        'runs_per_model': args.runs,
        'warmup_pairs': args.warmup,
        'primary': baseline,
        'fast': candidate,
        'median_ttft_change_pct': round(100 * (c-b)/b, 1) if b and c is not None else None,
        'notes': [
            'Negative TTFT change means the fast model returned the first token earlier.',
            'Quality, correctness and factual accuracy were not measured.',
            'Model warmup, hardware contention and installed quantization affect timings.',
        ],
    }
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description='Paired adaptive-model TTFT benchmark')
    parser.add_argument('--fast', default='')
    parser.add_argument('--baseline', default='')
    parser.add_argument('--runs', type=int, default=12)
    parser.add_argument('--warmup', type=int, default=2)
    parser.add_argument('--output', default='adaptive_benchmark.json')
    args = parser.parse_args()
    if not 1 <= args.runs <= 100 or not 0 <= args.warmup <= 10:
        parser.error('runs 1–100; warmup 0–10')
    try:
        asyncio.run(run(args))
    except (ValueError, httpx.HTTPError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
