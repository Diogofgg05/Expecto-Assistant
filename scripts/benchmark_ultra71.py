"""Run real paired ECO/BALANCED/MAX correctness and resource experiments."""
import argparse
import asyncio
import json
import secrets
import httpx
from aura.config import Settings
from aura.performance_laboratory import run_laboratory, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--per-domain', type=int, default=5)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--model', default='' , help='Exact installed model name including tag')
    parser.add_argument('--eco-model', default='')
    parser.add_argument('--max-model', default='')
    parser.add_argument('--review-model', default='', help='Distinct installed model; enables paired raw/reviewed trials')
    parser.add_argument('--output', default='ultra71-results.json')
    args = parser.parse_args()
    if args.diagnose:
        from scripts.benchmark_ollama_streaming import loopback_url
        async def diagnose():
            url = loopback_url(Settings.from_env().ollama_url)
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(url + '/api/tags')
                response.raise_for_status()
                return {'available': True, 'models': [m['name'] for m in response.json().get('models', [])]}
        try:
            print(json.dumps(asyncio.run(diagnose()), indent=2))
        except (httpx.HTTPError, ValueError, KeyError):
            parser.exit(1, 'Ollama indisponível. Inicia o Ollama neste computador e confirma AURA_OLLAMA_URL. Nenhum benchmark foi executado.\n')
        return
    if not args.model:
        from aura.laboratory_summary import choose_installed
        from scripts.benchmark_ollama_streaming import loopback_url
        async def discover():
            settings = Settings.from_env()
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(loopback_url(settings.ollama_url) + '/api/tags')
                response.raise_for_status()
                return choose_installed(settings.ollama_model,
                    [m['name'] for m in response.json().get('models', [])])
        try:
            args.model = asyncio.run(discover())
            print('Modelo selecionado:', args.model)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            parser.exit(1, f'Não foi possível selecionar um modelo local: {exc}\n')
    seed = args.seed if args.seed is not None else secrets.randbits(63)
    try:
        result = asyncio.run(run_laboratory(Settings.from_env(), seed=seed, per_domain=args.per_domain,
            repeats=args.repeats, warmup=args.warmup,
            models={'eco': args.eco_model or args.model, 'balanced': args.model, 'max': args.max_model or args.model},
            review_model=args.review_model, output=args.output))
        write_report(args.output, result)
        print(json.dumps({'seed': seed, 'output': args.output, 'summary': result['summary'], 'recommendation': result['recommendation']}, indent=2))
    except (httpx.HTTPError, OSError, ValueError) as exc:
        parser.exit(1, f'Laboratory could not complete: {type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
