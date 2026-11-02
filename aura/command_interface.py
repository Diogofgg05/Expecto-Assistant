"""Voice-only panel commands. Deterministic mapping; no model authorization."""
from __future__ import annotations
import re

PANELS = {
    'memoria': 'memory', 'pesquisa': 'research',
    'investigacoes': 'jobs', 'diagnosticos': 'diagnostics',
    'estado': 'diagnostics', 'projetos': 'projects',
    'browser': 'browser', 'navegador': 'browser',
}
LAYOUT = r'(?:memoria|pesquisa|browser|diagnosticos|projetos)'
PANEL = '(?:' + '|'.join(PANELS) + ')'


async def handle_interface_command(engine, original: str, key: str, respond):
    if key in ('fecha tudo', 'fechar tudo', 'volta ao normal', 'limpa o ecra', 'volta ao inicio'):
        return respond('Regressei ao modo central.', action={'type': 'close_all'})

    match = re.fullmatch(r'(aumenta|expande|reduz|encolhe) (?:a|o|os)?\s*(' + LAYOUT + r')', key)
    if match:
        return respond('Ajustei o espaço do ecrã.', action={
            'type': 'resize', 'panel': PANELS[match.group(2)],
            'size': 'large' if match.group(1) in ('aumenta', 'expande') else 'normal',
        })

    match = re.fullmatch(r'coloca (?:a|o|os)?\s*(' + LAYOUT + r') (?:a|ao) direita', key)
    if match:
        return respond('Reorganizei os espaços.', action={
            'type': 'move', 'panel': PANELS[match.group(1)],
        })

    match = re.fullmatch(r'(abre|abrir|mostra|fecha|fechar)(?: (?:a|o|os))? (' + PANEL + r')', key)
    if match:
        term, panel = match.group(2), PANELS[match.group(2)]
        if match.group(1) in ('abre', 'abrir', 'mostra'):
            return respond(f'Abri {term}.', action={'type': 'open', 'panel': panel},
                           data=await engine.panel_data(panel))
        return respond(f'Fechei {term}.', action={'type': 'close', 'panel': panel})
    return None
