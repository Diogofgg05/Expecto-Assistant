"""Anonymous environment information and per-profile measured distributions."""
import math
import os
import platform
import statistics


def environment():
    return {'os': platform.system(), 'release': platform.release(),
            'architecture': platform.machine(), 'python': platform.python_version(),
            'logical_cpus': os.cpu_count()}


def choose_installed(configured, names):
    names = sorted(set(names))
    if configured in names:
        return configured
    if configured and ':' not in configured.rsplit('/', 1)[-1] and configured + ':latest' in names:
        return configured + ':latest'
    if len(names) == 1:
        return names[0]
    raise ValueError('Escolha ambígua ou nenhum modelo instalado. Usa --model NOME:TAG. Modelos: ' + ', '.join(names))


def distribution(values):
    values = sorted(v for v in values if type(v) in (int, float) and math.isfinite(v) and v >= 0)
    return {'samples': len(values), 'median': statistics.median(values) if values else None,
            'p95': values[math.ceil(.95*len(values))-1] if values else None}


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['profile'], row['pipeline']), []).append(row)
    result = []
    for (profile, pipeline), data in sorted(groups.items()):
        calls = [call for row in data for call in row.get('calls', [])]
        result.append({'profile': profile, 'pipeline': pipeline, 'responses': len(data),
            'correct': sum(bool(r['correct']) for r in data),
            'failures': sum(not r['ok'] for r in data),
            'response_total_ms': distribution([r['total_ms'] for r in data]),
            'response_first_visible_ms': distribution([r.get('first_visible_ms') for r in data]),
            'call_preparation_ms': distribution([c.get('prep_ms') for c in calls]),
            'call_tokens_per_second': distribution([c.get('tokens_per_second') for c in calls]),
            'call_sampled_peak_bytes': {key: distribution([
                (c.get('resources') or {}).get('sampled_peak_bytes', {}).get(key) for c in calls])
                for key in ('app_rss_bytes', 'ollama_rss_bytes', 'loaded_vram_bytes')}})
    return result
