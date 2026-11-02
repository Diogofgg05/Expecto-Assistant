"""Explicit, deterministic holographic layout actions.

Only user commands reach this module. Model-generated output is never
allowed to invoke control commands or grant privileges.
"""
from __future__ import annotations
import re
import asyncio


async def handle_interface_command(engine, original: str, key: str, respond):
    # Explicit user-intent actions, never LLM-inferred actions.
    if key in ('fecha tudo', 'fechar tudo', 'volta ao normal', 'limpa o ecra', 'volta ao inicio'):
        return respond('Regressei ao modo central.', action={'type': 'close_all'})
    # Voice-driven layout changes, without buttons.
    m = re.match(r'^(aumenta|expande|reduz|encolhe) (?:a|o|os)?\s*(memoria|pesquisa|browser|diagnosticos|projetos)$', key)
    if m:
        panel = {'memoria':'memory','pesquisa':'research','browser':'browser',
                 'diagnosticos':'diagnostics','projetos':'projects'}[m.group(2)]
        size = 'large' if m.group(1) in ('aumenta','expande') else 'normal'
        return respond('Ajustei o espaço do ecrã.', action={'type':'resize', 'panel':panel, 'size':size})
    m = re.match(r'^coloca (?:a|o|os)?\s*(memoria|pesquisa|browser|diagnosticos|projetos) (?:a|ao) direita$', key)
    if m:
        panel = {'memoria':'memory','pesquisa':'research','browser':'browser',
                 'diagnosticos':'diagnostics','projetos':'projects'}[m.group(1)]
        return respond('Reorganizei os espaços.', action={'type':'move', 'panel':panel})

    for term, panel in [('memoria','memory'), ('pesquisa','research'),
                        ('investigacoes','jobs'), ('diagnosticos','diagnostics'),
                        ('estado','diagnostics'), ('projetos','projects'),
                        ('browser','browser'), ('navegador','browser')]:
        if key in (f'abre a {term}', f'abre o {term}', f'mostra a {term}',
                   f'mostra o {term}', f'mostra os {term}', f'abre os {term}',
                   f'abrir {term}', f'abre {term}'):
            return respond(f'Abri {term}.', action={'type': 'open', 'panel': panel},
                         data=await engine.panel_data(panel))
        if key in (f'fecha a {term}', f'fecha o {term}', f'fecha os {term}',
                   f'fechar {term}'):
            return respond(f'Fechei {term}.', action={'type': 'close', 'panel': panel})

    return None
