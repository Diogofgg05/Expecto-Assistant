"""Temporal fact revisions, history and as-of queries.

Unrecognized commands return None for deterministic dispatch fallthrough.
"""
from __future__ import annotations
import re


async def handle_temporal_commands(engine, original: str, key: str, respond):
    # Explicit temporal facts: preserve revisions rather than overwriting history.
    forget = re.match(r'^esquece (?:todas as versoes d[ao] |o meu |a minha )?(.+)$', key)
    if forget:
        from ..temporal import canonical_subject
        subject=canonical_subject(forget.group(1))
        if subject:
            count=engine.db.erase_temporal_subject(subject)
            return respond(f'Eliminei {count} versões temporais desse assunto da base ativa. '
                         'Os backups anteriores não são alterados.')
    m = re.match(r'^(?:atualiza|muda|corrige) (?:o meu|a minha)?\s*(.+?) para (.+)$', original, re.I)
    if m:
        from ..temporal import canonical_subject
        subject=canonical_subject(m.group(1))
        if subject:
            try:
                result=engine.db.set_temporal_fact(subject,m.group(2))
                return respond('Atualizei a informação atual e preservei a versão anterior no histórico.',
                             action={'type':'open','panel':'memory'},
                             data=engine.db.combined_memory_panel(engine.settings.episodic_lookback_months))
            except ValueError:
                return respond('Não consegui guardar esse valor. Verifica o assunto e evita informações sensíveis.')
    m = re.match(r'^(?:(?:mostra|consulta|abre)\s+)?(?:o\s+)?historico\s+(?:do meu\s+|da minha\s+|de\s+|do\s+|da\s+)?(.+)$', key)
    if m:
        from ..temporal import canonical_subject, DISPLAY
        subj=canonical_subject(m.group(1))
        if subj:
            hist=engine.db.temporal_history(subj,engine.settings.episodic_lookback_months)
            entries=[{**x,'category':'temporal',
                      'content':DISPLAY.get(subj,subj)+': '+x['value']+
                                (' (ATUAL)' if x['valid_to'] is None else ' (ANTERIOR)'),
                      'created_at':x['valid_from'], 'updated_at':x['valid_from']} for x in hist]
            return respond(f'Encontrei {len(hist)} versões registadas para {DISPLAY.get(subj,subj)}. '
                         'As datas indicam quando tomei conhecimento da alteração.',
                         action={'type':'open','panel':'memory'},data=entries)
    m = re.match(r'^(?:qual e|qual era|o que e) (?:o meu|a minha)?\s*(browser|navegador|sistema operativo|distribuicao linux|editor|editor de codigo|ide|modelo ollama)(?: atual)?$',key)
    if m:
        from ..temporal import canonical_subject
        rows=engine.db.temporal_current(m.group(1))
        if not rows:
            return respond('Ainda não tenho uma informação atual confirmada para esse assunto.')
        return respond('A última informação que me deste foi: '+rows[0]['value']+'. '
                     'Podes pedir o histórico para consultar versões anteriores.')
    m = re.match(r'^(?:como era|qual era) (?:o meu|a minha)?\s*(.+?) em (\d{4}-\d{2}-\d{2})$',key)
    if m:
        from ..temporal import canonical_subject
        subject=canonical_subject(m.group(1))
        if subject:
            try:
                entry=engine.db.temporal_as_of(subject,m.group(2)+'T23:59:59+00:00')
            except ValueError:
                return respond('Data inválida. Usa AAAA-MM-DD.')
            return respond(('Nessa data eu tinha registado: '+entry['value']+'.' if entry else
                          'Não tenho registos suficientes para confirmar o estado nessa data.'))
    return None
