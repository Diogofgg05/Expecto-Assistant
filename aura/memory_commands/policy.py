"""Privacy, memory panel and non-destructive consolidation.

Unrecognized commands return None for deterministic dispatch fallthrough.
"""
from __future__ import annotations
import re


async def handle_policy_commands(engine, original: str, key: str, respond):
    if key in ('o que sabes sobre mim', 'o que te lembras', 'mostra as minhas memorias'):
        mems = engine.db.combined_memory_panel(engine.settings.episodic_lookback_months)
        return respond(f'Tenho {engine.db.memory_count()} notas e {engine.db.episode_count(engine.settings.episodic_lookback_months)} mensagens na memória dos últimos {engine.settings.episodic_lookback_months} meses.',
                     action={'type': 'open', 'panel': 'memory'}, data=mems)

    # v2.7: private mode stops automatic capture/index/extraction, preserving old notes.
    if key in ('ativa modo privado','ativa o modo privado','modo privado'):
        engine.db.set_option('private_mode', 'true')
        return respond('Modo privado ligado: novas conversas deixam de ser registadas automaticamente. ' 
                     'As memórias existentes permanecem até pedires para as apagar.')
    if key in ('desativa modo privado','desativa o modo privado','sai do modo privado'):
        engine.db.set_option('private_mode', 'false')
        return respond('Modo privado desligado. A gravação obedece à configuração de memória automática.')
    if key in ('estado da privacidade','estado da seguranca da memoria'):
        private = engine.db.get_option('private_mode','false') == 'true'
        return respond(('Modo privado ativo. ' if private else 'Modo privado inativo. ')+
                     ('Backup cifrado disponível.' if engine.secure_backups.enabled else
                      'Backup cifrado indisponível até definires uma frase-passe no arranque.')+
                     ' A base SQLite ativa continua sem cifragem de disco.')

    # v2.6: evidence-linked, non-destructive consolidation.
    if key in ('ativa consolidacao automatica','ativa a consolidacao automatica'):
        engine.db.set_option('auto_consolidate_memory','true')
        return respond('Ativei a consolidação automática local, sem apagar ou fundir memórias.')
    if key in ('desativa consolidacao automatica','desativa a consolidacao automatica'):
        engine.db.set_option('auto_consolidate_memory','false')
        return respond('Desativei a consolidação automática. Os resumos já criados continuam disponíveis.')
    if key in ('consolida a memoria','organiza a memoria','cria resumos da memoria'):
        output=engine.consolidation.consolidate(engine.settings.episodic_lookback_months)
        rows=engine._summary_rows(engine.consolidation.summaries())
        return respond(f"Criei {output['summaries']} sínteses por temas com fontes associadas. "
                     'Não fundi nem apaguei memórias.',action={'type':'open','panel':'memory'},data=rows)
    if key in ('mostra resumos da memoria','mostra as sinteses da memoria'):
        rows=engine._summary_rows(engine.consolidation.summaries())
        return respond(f'Encontrei {len(rows)} sínteses guardadas com referências às origens.',
                     action={'type':'open','panel':'memory'},data=rows)
    m=re.match(r'^(?:resume|resumo de|mostra resumo de) (?:a minha |a )?memoria sobre (.+)$',key)
    if m:
        rows=engine._summary_rows(engine.consolidation.summaries(m.group(1)))
        return respond(f'Encontrei {len(rows)} sínteses sobre {m.group(1)}. ' +
                     ('Pede «consolida a memória» para atualizar os resumos.' if not rows else
                      'Cada excerto inclui a origem.'),
                     action={'type':'open','panel':'memory'},data=rows)
    if key in ('mostra memorias repetidas','mostra duplicados da memoria'):
        groups=engine.consolidation.duplicate_candidates()
        rows=[{'id':str(i),'category':'duplicate','content':
                'Possível duplicado (não apagado): '+ ' / '.join(g['examples']) +
                ' | IDs: '+', '.join(g.get('memory_ids',g.get('episode_ids',[])))} for i,g in enumerate(groups,1)]
        return respond(f'Identifiquei {len(groups)} grupos de notas muito semelhantes para revisão, sem eliminar nada.',
                     action={'type':'open','panel':'memory'},data=rows)
    if key in ('mostra contradicoes','verifica contradicoes da memoria','mostra possiveis contradicoes'):
        candidates=engine.consolidation.review_candidates()
        rows=[{'id':str(i),'category':'review',
                'content':r['kind']+': '+r['subject']+' — '+r['note']+' '+
                    str(r.get('examples') or [v['value'] for v in r.get('values',[])])}
              for i,r in enumerate(candidates,1)]
        return respond(f'Encontrei {len(candidates)} situações para revisão. ' +
                     'Mudanças temporais não são automaticamente contradições.',
                     action={'type':'open','panel':'memory'},data=rows)
    return None
