"""Explicit checked-answer commands; no private drafts streamed to the user."""
import re


async def handle_reasoning_command(engine, original, reply):
    # Exact user expression: no model extraction, no generated-code execution.
    from .reasoning_engine72 import exact_request
    exact = exact_request(original)
    if exact is not None:
        return reply(exact, data={'verification': 'exact_arithmetic'})

    checked = re.fullmatch(r'resolve com verificação\s*:\s*(.+)', original, re.I | re.S)
    if checked:
        import httpx
        from .reasoning_engine72 import ReasoningEngine72, LocalReasoningModel
        from scripts.benchmark_ollama_streaming import loopback_url
        question = checked.group(1)
        domain = 'programming' if re.search(r'código|python|programa', question, re.I) else 'math'
        specialist = engine.settings.reasoning_code_model if domain == 'programming' else engine.settings.reasoning_math_model
        model = specialist or engine.settings.ollama_deep_model or engine.settings.ollama_model
        reviewer = engine.settings.reasoning_review_model
        try:
            url = loopback_url(engine.settings.ollama_url)
            async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
                tags = await client.get(url + '/api/tags')
                tags.raise_for_status()
                installed = {item['name']: item.get('digest') for item in tags.json().get('models', [])}
                if model not in installed or (reviewer and reviewer not in installed):
                    return reply('Configura nomes exatos de modelos já instalados, incluindo a tag.')
                if reviewer and installed.get(model) and installed[model] == installed.get(reviewer):
                    return reply('O modelo revisor tem os mesmos pesos que o gerador; escolhe outro modelo.')
                def adapter(name):
                    return LocalReasoningModel(client, url, name, metrics=engine.llm.metrics,
                        resource_probe=engine.llm.loaded_models if engine.settings.response_resource_sampling else None)
                result = await ReasoningEngine72(
                    adapter(model), model=model,
                    review=adapter(reviewer) if reviewer else None,
                    review_model=reviewer).run(question, domain=domain)
            text = result['answer'] or 'Não consegui verificar suficientemente a resposta.'
            if result['answer']:
                text += '\n\n' + ('Revisão por outro modelo; não constitui prova.' if result['status'] == 'reviewed_proposal' else 'Proposta sem verificação independente completa.')
            return reply(text, data=result)
        except (ValueError, KeyError, httpx.HTTPError):
            return reply('A verificação local está indisponível. Confirma os modelos e o Ollama.')

    return None
