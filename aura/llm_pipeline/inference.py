"""Ollama HTTP inference, streaming and model fallback, without storage access."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import time
import httpx

@dataclass
class InferenceObservation:
    used_model: str
    usage: dict = field(default_factory=dict)
    first_token_at: float | None = None
    completed: bool = False

async def inference_exchange(transport, settings, profile, memory_plan, messages,
                             missing_models, on_token, observation):
    first_token_at = None
    completed = False
    used_model = settings.ollama_model
    usage = {}
    try:
        chunks = []
        usage = {}
        preferred = (settings.ollama_fast_model if profile.name == 'fast'
                     else settings.ollama_deep_model if profile.name == 'deep'
                     else '')
        base_model = settings.ollama_model
        chosen = preferred if preferred and preferred not in missing_models else base_model
        used_model = chosen
        try:
            client = transport()
            payload = {
                'model': chosen,
                'messages': messages,
                'stream': on_token is not None,
                'keep_alive': memory_plan.keep_alive,
                'options': {
                    'num_predict': memory_plan.max_predict,
                    'num_ctx': memory_plan.num_ctx,
                    'temperature': 0.35 if profile.name == 'fast' else 0.45,
                },
            }
            # Disable hidden thinking only for self-contained FAST definitions.
            # Other profiles leave the model's default reasoning behavior intact.
            if profile.name == 'fast':
                payload['think'] = False
            # A missing optional fast/deep model must not break the chat.
            # Remember failures only for the lifetime of this process.
            candidates = [chosen] + ([base_model] if chosen != base_model else [])
            if on_token is None:
                for model in candidates:
                    used_model = model
                    payload['model'] = model
                    resp = await client.post(settings.ollama_url + '/api/chat', json=payload)
                    if resp.status_code == 404 and model != base_model:
                        missing_models.add(model)
                        continue
                    if resp.status_code == 404:
                        return (f'O modelo {base_model} não está instalado. '
                                f'Executa: ollama pull {base_model}.')
                    resp.raise_for_status()
                    usage = resp.json()
                    answer = usage.get('message', {}).get('content', '').strip()
                    completed = bool(answer)
                    return answer or 'O modelo respondeu sem texto. Tenta novamente.'
            else:
                for model in candidates:
                    used_model = model
                    payload['model'] = model
                    async with client.stream('POST', settings.ollama_url + '/api/chat',
                                             json=payload) as resp:
                        if resp.status_code == 404 and model != base_model:
                            missing_models.add(model)
                            continue
                        if resp.status_code == 404:
                            return (f'O modelo {base_model} não está instalado. '
                                    f'Executa: ollama pull {base_model}.')
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.strip():
                                continue
                            event = json.loads(line)
                            if event.get('error'):
                                raise ValueError('Ollama streaming failed')
                            if event.get('done'):
                                usage = event
                            piece = event.get('message', {}).get('content', '')
                            if isinstance(piece, str) and piece:
                                chunks.append(piece)
                                if first_token_at is None:
                                    first_token_at = time.perf_counter()
                                await on_token(piece)
                    break
                completed = bool(chunks)
                return ''.join(chunks).strip() or 'O modelo respondeu sem texto. Tenta novamente.'
        except httpx.ConnectError:
            if chunks and on_token is not None:
                raise  # Partial response: never persist as a completed exchange.
            return ('Não consigo contactar o Ollama. Abre o Ollama, confirma que '
                    'está a executar e tenta novamente. Os comandos da interface '
                    'e a memória local continuam disponíveis.')
        except httpx.TimeoutException:
            if chunks and on_token is not None:
                raise
            return ('Ollama excedeu o tempo de resposta. Experimenta um modelo '
                    'mais pequeno ou verifica a memória RAM e a utilização da CPU.')
        except (httpx.HTTPError, ValueError):
            if chunks and on_token is not None:
                raise  # Do not mark partial output as a completed response.
            return 'Ocorreu um erro na comunicação com o modelo local. Verifica os diagnósticos.'
    finally:
        observation.used_model = used_model
        observation.usage = usage
        observation.first_token_at = first_token_at
        observation.completed = completed
