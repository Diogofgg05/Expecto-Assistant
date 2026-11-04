"""Explicit relationship and knowledge graph commands.

Unrecognized commands return None for deterministic dispatch fallthrough.
"""
from __future__ import annotations
import re


async def handle_relationship_commands(engine, original: str, key: str, respond):
    # v2.5 relational memory: deterministic, user-authorized graph operations.
    if key in ('ativa relacoes automaticas','ativa a memoria relacional'):
        engine.db.set_option('auto_link_memory','true')
        return respond('Ativei a identificação conservadora de relações nas novas conversas gravadas.')
    if key in ('desativa relacoes automaticas','desativa a memoria relacional'):
        engine.db.set_option('auto_link_memory','false')
        return respond('Desativei a criação automática de relações. As existentes permanecem guardadas.')
    if key in ('organiza relacoes das conversas','relaciona conversas antigas'):
        allowed=(engine.db.capture_enabled(engine.settings.episodic_capture) and
            engine.db.get_option('auto_extract_memory',str(engine.settings.auto_extract_memory).lower())=='true' and
            engine.db.get_option('auto_link_memory',str(engine.settings.auto_link_memory).lower())=='true')
        if not allowed:
            return respond('Ativa a gravação, a extração e as relações automáticas para analisar conversas antigas.')
        result=engine.relations.backfill(engine.settings.episodic_lookback_months,50)
        return respond(f"Analisei {result['examined']} mensagens anteriores e identifiquei "
                     f"{result['linked']} novas relações verificáveis pela mensagem original.",
                     action={'type':'open','panel':'memory'},
                     data=engine.db.combined_memory_panel(engine.settings.episodic_lookback_months))
    relationship_patterns = (
        (r'^associa (?:a )?tecnologia (.+?) ao projeto (.+)$',
         lambda m: ('project',m.group(2),'uses_technology','technology',m.group(1))),
        (r'^liga (?:o )?projeto (.+?) (?:à|a) tecnologia (.+)$',
         lambda m: ('project',m.group(1),'uses_technology','technology',m.group(2))),
        (r'^associa (?:o )?problema (.+?) ao projeto (.+)$',
         lambda m: ('project',m.group(2),'has_problem','problem',m.group(1))),
        (r'^associa (?:a )?decis[aã]o (.+?) ao projeto (.+)$',
         lambda m: ('project',m.group(2),'has_decision','decision',m.group(1))),
        (r'^associa (?:a )?solu[cç][aã]o (.+?) ao problema (.+)$',
         lambda m: ('solution',m.group(1),'resolves_problem','problem',m.group(2))),
        (r'^associa (?:a )?solu[cç][aã]o (.+?) ao projeto (.+)$',
         lambda m: ('solution',m.group(1),'solution_for','project',m.group(2))),
    )
    for pattern, build in relationship_patterns:
        match=re.match(pattern,original,flags=re.I)
        if match:
            try:
                fk,fn,rel,tk,tn=build(match)
                record=engine.relations.add_link(fk,fn,rel,tk,tn)
            except ValueError as ex:
                return respond('Não guardei essa ligação: '+str(ex))
            return respond('Relação guardada com proveniência explícita.' if record['created']
                         else 'Essa relação já estava guardada.',
                         action={'type':'open','panel':'memory'},
                         data=engine.db.combined_memory_panel(engine.settings.episodic_lookback_months))
    m=re.match(r'^(?:esquece|apaga) (?:a )?rela[cç][aã]o ([a-f0-9]{12})$',key)
    if m:
        removed=engine.relations.remove_link(m.group(1),include_auto=True)
        return respond('Relação eliminada da base ativa.' if removed else
                     'Não encontrei essa relação. Os backups não foram alterados.',
                     action={'type':'open','panel':'memory'},
                     data=engine.db.combined_memory_panel(engine.settings.episodic_lookback_months))
    m=re.match(r'^(?:mostra|consulta|abre) (?:as )?rela[cç][oõ]es (?:do|da|de) (?:projeto|problema|tecnologia|solu[cç][aã]o|decis[aã]o) (.+)$',original,flags=re.I)
    if not m:
        m=re.match(r'^(?:que tecnologias usa|quais os problemas do|quais as decis[oõ]es do) projeto (.+)$',original,flags=re.I)
    if m:
        name=m.group(1).strip().rstrip('.!?')
        linked=engine.relations.list_links(name=name,months=engine.settings.episodic_lookback_months)
        if not linked:
            return respond('Não encontrei ligações registadas para '+name+'.')
        panel=[engine._relational_row(x) for x in linked]
        return respond(f'Encontrei {len(panel)} relações associadas a {name}. '
                     'São declarações guardadas, não factos confirmados.',
                     action={'type':'open','panel':'memory'},data=panel)
    return None
