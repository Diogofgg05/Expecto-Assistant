"""Explicit, deterministic memory CRUD, privacy and relationship actions.

Only user commands reach this module. Model-generated output is never
allowed to invoke control commands or grant privileges.
"""
from __future__ import annotations
import re
import asyncio


async def handle_memory_command(engine, original: str, key: str, respond):
    if key in ('o que sabes sobre mim', 'o que te lembras', 'mostra as minhas memorias'):
        mems = engine.db.combined_memory_panel(engine.settings.episodic_lookback_months)
        return respond(f'Tenho {len(engine.db.memories(999999))} notas e {engine.db.episode_count(engine.settings.episodic_lookback_months)} mensagens na memória dos últimos {engine.settings.episodic_lookback_months} meses.',
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

    # Explicit temporal facts: preserve revisions rather than overwriting history.
    forget = re.match(r'^esquece (?:todas as versoes d[ao] |o meu |a minha )?(.+)$', key)
    if forget:
        from .temporal import canonical_subject
        subject=canonical_subject(forget.group(1))
        if subject:
            count=engine.db.erase_temporal_subject(subject)
            return respond(f'Eliminei {count} versões temporais desse assunto da base ativa. '
                         'Os backups anteriores não são alterados.')
    m = re.match(r'^(?:atualiza|muda|corrige) (?:o meu|a minha)?\s*(.+?) para (.+)$', original, re.I)
    if m:
        from .temporal import canonical_subject
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
        from .temporal import canonical_subject, DISPLAY
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
        from .temporal import canonical_subject
        rows=engine.db.temporal_current(m.group(1))
        if not rows:
            return respond('Ainda não tenho uma informação atual confirmada para esse assunto.')
        return respond('A última informação que me deste foi: '+rows[0]['value']+'. '
                     'Podes pedir o histórico para consultar versões anteriores.')
    m = re.match(r'^(?:como era|qual era) (?:o meu|a minha)?\s*(.+?) em (\d{4}-\d{2}-\d{2})$',key)
    if m:
        from .temporal import canonical_subject
        subject=canonical_subject(m.group(1))
        if subject:
            try:
                entry=engine.db.temporal_as_of(subject,m.group(2)+'T23:59:59+00:00')
            except ValueError:
                return respond('Data inválida. Usa AAAA-MM-DD.')
            return respond(('Nessa data eu tinha registado: '+entry['value']+'.' if entry else
                          'Não tenho registos suficientes para confirmar o estado nessa data.'))

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

    m = re.match(r'^(?:procura|pesquisa|encontra) (?:na )?memoria (?:sobre )?(.+)$', key)
    if m:
        query = original[original.casefold().find(m.group(1)):] if m.group(1) in original.casefold() else m.group(1)
        matches = await engine.memory.recall(query, 20)
        return respond(f'Encontrei {len(matches)} memórias relacionadas.' if matches else
                     'Não encontrei memórias relacionadas.',
                     action={'type':'open', 'panel':'memory'}, data=matches)

    m = re.match(r'^(?:corrige|atualiza) (?:a )?(?:memoria|nota) ([a-f0-9]{12}) (?:para|com) (.+)$', key)
    if m:
        original_match = re.match(r'^(?:corrige|atualiza) (?:a )?(?:mem[oó]ria|nota) [a-f0-9]{12} (?:para|com) (.+)$', original, re.I)
        new_content = original_match.group(1) if original_match else m.group(2)
        updated = await engine.memory.correct(m.group(1), new_content)
        return respond('Atualizei a memória e preservei o histórico da correção.' if updated else
                     'Não encontrei essa memória.',
                     action={'type':'open', 'panel':'memory'}, data=engine.db.memories())

    if key in ('indexa as memorias', 'atualiza o indice da memoria'):
        result = await engine.memory.index_pending()
        return respond(f"Indexei {result['indexed']} memórias. Por indexar: {result['pending']}. {result['reason']}")

    if key in ('faz backup da memoria', 'cria copia de seguranca da memoria'):
        try:
            target = engine.secure_backups.create_backup()
            return respond('Criei uma cópia de segurança CIFRADA em '+str(target)+
                         '. Guarda a frase-passe separadamente: sem ela não é possível restaurar.')
        except (VaultError, OSError) as exc:
            return respond('Não criei backup. '+str(exc))

    if key in ('exporta a memoria', 'exporta as minhas memorias'):
        try:
            target = engine.secure_backups.export_memory(engine.settings.episodic_lookback_months)
            return respond('Exportei a memória CIFRADA em '+str(target))
        except (VaultError, OSError) as exc:
            return respond('Não exportei a memória. '+str(exc))

    m = re.match(r'^(?:lembra[ -]te de|guarda na memoria|memoriza)\s+(.+)$', key)
    if m:
        # Use original case/accents of note, not normalized version.
        prefix = re.match(r'^(?:lembra[ -]te de|guarda na mem[oó]ria|memoriza)\s+', original, re.I)
        note = (original[prefix.end():] if prefix else m.group(1)).strip()
        if len(note) < 3:
            return respond('A nota é demasiado curta para guardar.')
        item = await engine.memory.remember(note)
        return respond('Guardei essa informação na tua memória local.',
                     action={'type': 'open', 'panel': 'memory'},
                     data=engine.db.memories())

    m = re.match(r'^(?:esquece a (?:nota|memoria)|apaga a nota)\s+([a-f0-9]{12})$', key)
    if m:
        deleted = engine.db.delete_memory(m.group(1))
        return respond('Nota eliminada.' if deleted else 'Não encontrei essa nota.',
                     action={'type': 'open', 'panel': 'memory'}, data=engine.db.memories())

    return None
