"""Episodic capture, extraction, indexing and conversation search.

Unrecognized commands return None for deterministic dispatch fallthrough.
"""
from __future__ import annotations
import re


async def handle_episode_commands(engine, original: str, key: str, respond):
    if key in ('ativa memoria automatica','ativa a memoria automatica','liga a memoria automatica'):
        engine.db.set_option('episodic_capture','true')
        return respond('Ativei a gravação local de conversas. Podes desativá-la quando quiseres.')
    if key in ('desativa memoria automatica','desativa a memoria automatica','para de guardar conversas'):
        engine.db.set_option('episodic_capture','false')
        return respond('Desativei a gravação automática. As memórias antigas continuam guardadas até pedires para apagar.')
    if key in ('ativa extracao automatica', 'ativa aprendizagem da memoria', 'ativa memoria inteligente'):
        engine.db.set_option('auto_extract_memory','true')
        return respond('Ativei a extração automática local de conhecimentos a partir das conversas gravadas.')
    if key in ('desativa extracao automatica', 'desativa aprendizagem da memoria', 'desativa memoria inteligente'):
        engine.db.set_option('auto_extract_memory','false')
        return respond('Desativei a extração automática. As memórias já guardadas não são apagadas.')
    if key in ('analisa conversas pendentes','extrai conhecimento das conversas'):
        result = await engine.extractor.extract_one()
        return respond(f"Analisei {result['processed']} conversa e guardei {result['added']} novos conhecimentos. {result['reason']}")
    if key in ('indexa as conversas','indexa conversas antigas'):
        result = await engine.memory.index_episode_pending(engine.settings.episodic_lookback_months, 20)
        return respond(f"Indexei {result['indexed']} mensagens. Pendentes nesta amostra: {result['pending']}. {result['reason']}")
    if key in ('apaga historico de conversas', 'esquece todas as conversas'):
        removed = engine.db.erase_episodes()
        return respond(f'Apaguei {removed} mensagens da memória ativa. Backups e exportações antigos não são apagados.')
    m = re.match(r'^(?:esquece|apaga) (?:a )?conversa ([a-f0-9]{12})$', key)
    if m:
        ok = engine.db.delete_episode(m.group(1))
        return respond('Mensagem removida da memória de conversas.' if ok else 'Não encontrei essa mensagem.')
    m = re.match(r'^(?:procura|pesquisa|encontra) (?:uma )?conversa (?:sobre )?(.+)$', key)
    if m:
        found = await engine.memory.recall_episodes(m.group(1), engine.settings.episodic_lookback_months, 20)
        rows = [{**e,'category':'conversation',
                 'content':('TU: ' if e['role']=='user' else 'AURA: ')+e['content']} for e in found]
        return respond(f'Encontrei {len(rows)} mensagens relacionadas nos últimos {engine.settings.episodic_lookback_months} meses.',
                     action={'type':'open','panel':'memory'},data=rows)
    m = re.match(r'^(?:o que (?:falamos|conversamos)|mostra (?:as )?conversas)(?: de)? ha (um|dois|tres|quatro|cinco|seis|[1-9][0-9]?) mes(?:es)?$', key)
    if m:
        number = {'um':1,'dois':2,'tres':3,'quatro':4,'cinco':5,'seis':6}.get(m.group(1))
        number = number or int(m.group(1))
        if number > engine.settings.episodic_lookback_months:
            return respond('A pesquisa está configurada para os últimos '
                         f'{engine.settings.episodic_lookback_months} meses. O conteúdo antigo não é apagado.')
        items = engine.db.episodes_months_ago(number)
        rows = [{**e,'category':'conversation',
                 'content':('TU: ' if e['role']=='user' else 'AURA: ')+e['content']} for e in items]
        return respond(f'Encontrei {len(rows)} mensagens de há cerca de {number} meses.',
                     action={'type':'open','panel':'memory'},data=rows)
    if key in ('mostra as conversas antigas','mostra o historico de conversas'):
        rows = engine.db.combined_memory_panel(engine.settings.episodic_lookback_months)
        return respond(f'Tenho {engine.db.episode_count(engine.settings.episodic_lookback_months)} mensagens recuperáveis dos últimos {engine.settings.episodic_lookback_months} meses.',
                     action={'type':'open','panel':'memory'},data=rows)
    return None
