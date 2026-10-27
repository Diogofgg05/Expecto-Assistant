"""Constrained intent router; model output NEVER authorizes a privileged action."""
from __future__ import annotations
import asyncio
import re
import unicodedata
from .database import Database
from .research import Researcher
from .llm import Ollama
from .identity import Identity, IdentitySettings, MODES
from .living_intelligence import ContinuityEngine
from .memory import MemoryEngine
from .cognition import KnowledgeExtractor
from .config import Settings
from .relations import RelationMemory, DISPLAY as RELATION_DISPLAY
from .consolidation import ConsolidationEngine
from .learning import LearningEngine
from .optimizer import OptimizationLab
from .epistemics import EpistemicEngine
from .quality import KnowledgeQuality
from .factcheck import FactChecker
from .security import SecureBackupManager, VaultError


def normalized(s: str) -> str:
    stripped = unicodedata.normalize('NFD', s.casefold())
    return re.sub(r'\s+', ' ', ''.join(c for c in stripped if unicodedata.category(c) != 'Mn')).strip()


def reply(text: str, *, action: dict | None = None, data=None, speak: bool = True) -> dict:
    return {'text': text, 'spoken': text[:380] if speak else '',
            'action': action, 'data': data, 'ok': True}


class AuraEngine:
    def __init__(self, settings: Settings, db: Database):
        self.settings, self.db = settings, db
        self.research = Researcher(db, settings.searxng_url)
        self.memory = MemoryEngine(settings, db)
        self.extractor = KnowledgeExtractor(settings, db)
        self.relations = RelationMemory(db)
        self.consolidation = ConsolidationEngine(db)
        self.learning = LearningEngine(settings, db)
        self.optimizer = OptimizationLab(settings, db)
        self.epistemics = EpistemicEngine(db)
        self.quality = KnowledgeQuality(db)
        self.factcheck = FactChecker(db)
        self.secure_backups = SecureBackupManager(db, settings.data_dir / 'secure_backups', settings.backup_passphrase)
        self.continuity = ContinuityEngine(db)
        self.llm = Ollama(settings, db, self.memory)

    async def command(self, original: str, history: list[dict] | None = None) -> dict:
        original = original.strip()
        original = re.sub(r'^(?:aura|expecto)[,\s:]+', '', original, flags=re.I).strip()
        key = normalized(original).rstrip('.!?')
        if not original:
            return reply('Estou a ouvir. Podes falar ou escrever um comando.')

        if key.startswith('recorda experiencia: '):
            item = self.continuity.remember(original.split(':', 1)[1])
            return reply('Registei esta experiência como declaração tua, não como facto verificado.', data={'experience': item})
        if key in ('mostra experiencias', 'minhas experiencias'):
            return reply('Estas são as experiências que pediste para registar.', data={'experiences': self.continuity.experiences()})
        if key.startswith('apaga experiencia '):
            ident = key.removeprefix('apaga experiencia ').strip()
            return reply('Experiência apagada.' if self.continuity.forget(ident) else 'Não encontrei essa experiência.')
        if key.startswith('novo objetivo: '):
            item = self.continuity.add_goal(original.split(':', 1)[1])
            return reply('Objetivo guardado. Não farei ações por iniciativa própria sem autorização.', data={'goal': item})
        if key in ('meus objetivos', 'mostra objetivos'):
            return reply('Estes são os objetivos registados.', data={'goals': self.continuity.goals()})
        if key.startswith('concluir objetivo '):
            ident = key.removeprefix('concluir objetivo ').strip()
            return reply('Objetivo concluído.' if self.continuity.goal_status(ident, 'done') else 'Não encontrei esse objetivo.')
        if key in ('expecto, tens sugestoes', 'tens sugestoes', 'sugere proximo passo', 'sugere um proximo passo', 'o que sugeres'):
            suggestions = self.continuity.suggestions()
            return reply('Tenho estas sugestões. Só atuo depois de me dares autorização.' if suggestions else
                         'Ainda não registei objetivos ativos. Podes dizer: novo objetivo: ...', data={'suggestions': suggestions})

        if key in ('quem es', 'quem es tu', 'qual e a tua identidade', 'identidade da expecto'):
            ident = Identity()
            mode = IdentitySettings(self.settings.data_dir).mode()
            return reply(f'Sou a {ident.name}, um assistente local com uma identidade de comunicação estável. '
                         f'A minha missão é: {ident.mission} Modo: {mode}. '
                         'Não sou uma pessoa nem tenho consciência demonstrada.')
        match_mode = re.fullmatch(r'(?:ativa |muda para |usa )?modo (equilibrado|cientifico|criativo|professor)', key)
        if match_mode:
            new_mode = IdentitySettings(self.settings.data_dir).set_mode(match_mode.group(1))
            return reply(f'Modo {new_mode} ativado e guardado. A minha identidade e as regras de segurança permanecem iguais.')

        # Book-grounded natural questions: only imported/authorized PDF passages.
        m=re.match(r'^(?:segundo os livros|pesquisa nos livros|consulta os livros)\s*[:,-]?\s+(.+)$',original,re.I)
        if m:
            from .book_reasoning import BookReasoningEngine,OllamaBookModel
            from .books import BookLearningEngine
            if not BookLearningEngine(self.db).books():
                return reply('Ainda não tenho livros PDF autorizados importados para consultar.')
            q=m.group(1).strip()
            if not q:
                return reply('Indica a pergunta que queres investigar nos livros.')
            try:
                core=BookReasoningEngine(self.db)
                model=OllamaBookModel(self.settings.ollama_url,self.settings.ollama_model)
                encoder=None
                if self.settings.embedding_model:
                    from .book_semantics import OllamaBookEncoder
                    encoder=OllamaBookEncoder(self.settings.embedding_model,self.settings.ollama_url)
                result=await core.answer(q,model,encoder=encoder)
            except Exception:
                return reply('Não consegui consultar o modelo local. Verifica a ligação ao Ollama. Nenhuma memória foi alterada.')
            if result['abstained']:
                return reply('Não encontrei evidências suficientes nos livros para responder com segurança. '+
                             result.get('reason',''))
            bibliography=[{'id':c['passage_id'],'category':'book',
              'content':f"{c['title']} · página {c['page']}: {c['quote']}"} for c in result['citations']]
            return reply(result['answer']+' As passagens estão assinaladas por livro e página. '
                         'A presença de uma citação não prova por si só que a afirmação seja verdadeira.',
                         action={'type':'open','panel':'research'},data=bibliography)

        # Patronum: user-invoked, bounded orchestration; never executes unsafe tools.
        if key in ('ativa patronum', 'ativar patronum', 'expecto patronum', 'patronum'):
            status = await self.panel_data('diagnostics')
            online = bool(status.get('ollama', {}).get('available')) if isinstance(status.get('ollama'), dict) else False
            report = {
                'mode':'PATRONUM', 'ollama_available': online,
                'memories':status['memory_count'], 'documents':status['knowledge_count'],
                'conversations_6months':status['episodes_6months'],
                'verified_math_scope':'aritmética restrita; não prova factos externos',
                'recommendations':[
                    'Verificar a disponibilidade do Ollama antes de uma investigação profunda',
                    'Comparar passagens de livros com citações e páginas',
                    'Assinalar hipóteses ainda não validadas',
                    'Não executar ações externas nem alterar produção sem aprovação'
                ]
            }
            return reply('Patronum ativado. Diagnóstico e análise combinados. '
                         'Consigo investigar, relacionar evidências e identificar lacunas, '
                         'mas não tenho capacidades ilimitadas nem declaro verdades sem prova.',
                         action={'type':'patronum', 'panel':'patronum'}, data=report)
        if key in ('desativa patronum', 'desativar patronum', 'encerra patronum'):
            return reply('Modo Patronum desativado.', action={'type':'patronum_off'})

        # Explicit user-intent actions, never LLM-inferred actions.
        if key in ('fecha tudo', 'fechar tudo', 'volta ao normal', 'limpa o ecra', 'volta ao inicio'):
            return reply('Regressei ao modo central.', action={'type': 'close_all'})
        # Voice-driven layout changes, without buttons.
        m = re.match(r'^(aumenta|expande|reduz|encolhe) (?:a|o|os)?\s*(memoria|pesquisa|browser|diagnosticos|projetos)$', key)
        if m:
            panel = {'memoria':'memory','pesquisa':'research','browser':'browser',
                     'diagnosticos':'diagnostics','projetos':'projects'}[m.group(2)]
            size = 'large' if m.group(1) in ('aumenta','expande') else 'normal'
            return reply('Ajustei o espaço do ecrã.', action={'type':'resize', 'panel':panel, 'size':size})
        m = re.match(r'^coloca (?:a|o|os)?\s*(memoria|pesquisa|browser|diagnosticos|projetos) (?:a|ao) direita$', key)
        if m:
            panel = {'memoria':'memory','pesquisa':'research','browser':'browser',
                     'diagnosticos':'diagnostics','projetos':'projects'}[m.group(1)]
            return reply('Reorganizei os espaços.', action={'type':'move', 'panel':panel})

        for term, panel in [('memoria','memory'), ('pesquisa','research'),
                            ('investigacoes','jobs'), ('diagnosticos','diagnostics'),
                            ('estado','diagnostics'), ('projetos','projects'),
                            ('browser','browser'), ('navegador','browser')]:
            if key in (f'abre a {term}', f'abre o {term}', f'mostra a {term}',
                       f'mostra o {term}', f'mostra os {term}', f'abre os {term}',
                       f'abrir {term}', f'abre {term}'):
                return reply(f'Abri {term}.', action={'type': 'open', 'panel': panel},
                             data=await self.panel_data(panel))
            if key in (f'fecha a {term}', f'fecha o {term}', f'fecha os {term}',
                       f'fechar {term}'):
                return reply(f'Fechei {term}.', action={'type': 'close', 'panel': panel})

        if key in ('o que sabes sobre mim', 'o que te lembras', 'mostra as minhas memorias'):
            mems = self.db.combined_memory_panel(self.settings.episodic_lookback_months)
            return reply(f'Tenho {len(self.db.memories(999999))} notas e {self.db.episode_count(self.settings.episodic_lookback_months)} mensagens na memória dos últimos {self.settings.episodic_lookback_months} meses.',
                         action={'type': 'open', 'panel': 'memory'}, data=mems)

        # v2.7: private mode stops automatic capture/index/extraction, preserving old notes.
        if key in ('ativa modo privado','ativa o modo privado','modo privado'):
            self.db.set_option('private_mode', 'true')
            return reply('Modo privado ligado: novas conversas deixam de ser registadas automaticamente. ' 
                         'As memórias existentes permanecem até pedires para as apagar.')
        if key in ('desativa modo privado','desativa o modo privado','sai do modo privado'):
            self.db.set_option('private_mode', 'false')
            return reply('Modo privado desligado. A gravação obedece à configuração de memória automática.')
        if key in ('estado da privacidade','estado da seguranca da memoria'):
            private = self.db.get_option('private_mode','false') == 'true'
            return reply(('Modo privado ativo. ' if private else 'Modo privado inativo. ')+
                         ('Backup cifrado disponível.' if self.secure_backups.enabled else
                          'Backup cifrado indisponível até definires uma frase-passe no arranque.')+
                         ' A base SQLite ativa continua sem cifragem de disco.')

        # v2.6: evidence-linked, non-destructive consolidation.
        if key in ('ativa consolidacao automatica','ativa a consolidacao automatica'):
            self.db.set_option('auto_consolidate_memory','true')
            return reply('Ativei a consolidação automática local, sem apagar ou fundir memórias.')
        if key in ('desativa consolidacao automatica','desativa a consolidacao automatica'):
            self.db.set_option('auto_consolidate_memory','false')
            return reply('Desativei a consolidação automática. Os resumos já criados continuam disponíveis.')
        if key in ('consolida a memoria','organiza a memoria','cria resumos da memoria'):
            output=self.consolidation.consolidate(self.settings.episodic_lookback_months)
            rows=self._summary_rows(self.consolidation.summaries())
            return reply(f"Criei {output['summaries']} sínteses por temas com fontes associadas. "
                         'Não fundi nem apaguei memórias.',action={'type':'open','panel':'memory'},data=rows)
        if key in ('mostra resumos da memoria','mostra as sinteses da memoria'):
            rows=self._summary_rows(self.consolidation.summaries())
            return reply(f'Encontrei {len(rows)} sínteses guardadas com referências às origens.',
                         action={'type':'open','panel':'memory'},data=rows)
        m=re.match(r'^(?:resume|resumo de|mostra resumo de) (?:a minha |a )?memoria sobre (.+)$',key)
        if m:
            rows=self._summary_rows(self.consolidation.summaries(m.group(1)))
            return reply(f'Encontrei {len(rows)} sínteses sobre {m.group(1)}. ' +
                         ('Pede «consolida a memória» para atualizar os resumos.' if not rows else
                          'Cada excerto inclui a origem.'),
                         action={'type':'open','panel':'memory'},data=rows)
        if key in ('mostra memorias repetidas','mostra duplicados da memoria'):
            groups=self.consolidation.duplicate_candidates()
            rows=[{'id':str(i),'category':'duplicate','content':
                    'Possível duplicado (não apagado): '+ ' / '.join(g['examples']) +
                    ' | IDs: '+', '.join(g.get('memory_ids',g.get('episode_ids',[])))} for i,g in enumerate(groups,1)]
            return reply(f'Identifiquei {len(groups)} grupos de notas muito semelhantes para revisão, sem eliminar nada.',
                         action={'type':'open','panel':'memory'},data=rows)
        if key in ('mostra contradicoes','verifica contradicoes da memoria','mostra possiveis contradicoes'):
            candidates=self.consolidation.review_candidates()
            rows=[{'id':str(i),'category':'review',
                    'content':r['kind']+': '+r['subject']+' — '+r['note']+' '+
                        str(r.get('examples') or [v['value'] for v in r.get('values',[])])}
                  for i,r in enumerate(candidates,1)]
            return reply(f'Encontrei {len(candidates)} situações para revisão. ' +
                         'Mudanças temporais não são automaticamente contradições.',
                         action={'type':'open','panel':'memory'},data=rows)

        # v2.5 relational memory: deterministic, user-authorized graph operations.
        if key in ('ativa relacoes automaticas','ativa a memoria relacional'):
            self.db.set_option('auto_link_memory','true')
            return reply('Ativei a identificação conservadora de relações nas novas conversas gravadas.')
        if key in ('desativa relacoes automaticas','desativa a memoria relacional'):
            self.db.set_option('auto_link_memory','false')
            return reply('Desativei a criação automática de relações. As existentes permanecem guardadas.')
        if key in ('organiza relacoes das conversas','relaciona conversas antigas'):
            allowed=(self.db.capture_enabled(self.settings.episodic_capture) and
                self.db.get_option('auto_extract_memory',str(self.settings.auto_extract_memory).lower())=='true' and
                self.db.get_option('auto_link_memory',str(self.settings.auto_link_memory).lower())=='true')
            if not allowed:
                return reply('Ativa a gravação, a extração e as relações automáticas para analisar conversas antigas.')
            result=self.relations.backfill(self.settings.episodic_lookback_months,50)
            return reply(f"Analisei {result['examined']} mensagens anteriores e identifiquei "
                         f"{result['linked']} novas relações verificáveis pela mensagem original.",
                         action={'type':'open','panel':'memory'},
                         data=self.db.combined_memory_panel(self.settings.episodic_lookback_months))
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
                    record=self.relations.add_link(fk,fn,rel,tk,tn)
                except ValueError as ex:
                    return reply('Não guardei essa ligação: '+str(ex))
                return reply('Relação guardada com proveniência explícita.' if record['created']
                             else 'Essa relação já estava guardada.',
                             action={'type':'open','panel':'memory'},
                             data=self.db.combined_memory_panel(self.settings.episodic_lookback_months))
        m=re.match(r'^(?:esquece|apaga) (?:a )?rela[cç][aã]o ([a-f0-9]{12})$',key)
        if m:
            removed=self.relations.remove_link(m.group(1),include_auto=True)
            return reply('Relação eliminada da base ativa.' if removed else
                         'Não encontrei essa relação. Os backups não foram alterados.',
                         action={'type':'open','panel':'memory'},
                         data=self.db.combined_memory_panel(self.settings.episodic_lookback_months))
        m=re.match(r'^(?:mostra|consulta|abre) (?:as )?rela[cç][oõ]es (?:do|da|de) (?:projeto|problema|tecnologia|solu[cç][aã]o|decis[aã]o) (.+)$',original,flags=re.I)
        if not m:
            m=re.match(r'^(?:que tecnologias usa|quais os problemas do|quais as decis[oõ]es do) projeto (.+)$',original,flags=re.I)
        if m:
            name=m.group(1).strip().rstrip('.!?')
            linked=self.relations.list_links(name=name,months=self.settings.episodic_lookback_months)
            if not linked:
                return reply('Não encontrei ligações registadas para '+name+'.')
            panel=[self._relational_row(x) for x in linked]
            return reply(f'Encontrei {len(panel)} relações associadas a {name}. '
                         'São declarações guardadas, não factos confirmados.',
                         action={'type':'open','panel':'memory'},data=panel)

        # Explicit temporal facts: preserve revisions rather than overwriting history.
        forget = re.match(r'^esquece (?:todas as versoes d[ao] |o meu |a minha )?(.+)$', key)
        if forget:
            from .temporal import canonical_subject
            subject=canonical_subject(forget.group(1))
            if subject:
                count=self.db.erase_temporal_subject(subject)
                return reply(f'Eliminei {count} versões temporais desse assunto da base ativa. '
                             'Os backups anteriores não são alterados.')
        m = re.match(r'^(?:atualiza|muda|corrige) (?:o meu|a minha)?\s*(.+?) para (.+)$', original, re.I)
        if m:
            from .temporal import canonical_subject
            subject=canonical_subject(m.group(1))
            if subject:
                try:
                    result=self.db.set_temporal_fact(subject,m.group(2))
                    return reply('Atualizei a informação atual e preservei a versão anterior no histórico.',
                                 action={'type':'open','panel':'memory'},
                                 data=self.db.combined_memory_panel(self.settings.episodic_lookback_months))
                except ValueError:
                    return reply('Não consegui guardar esse valor. Verifica o assunto e evita informações sensíveis.')
        m = re.match(r'^(?:(?:mostra|consulta|abre)\s+)?(?:o\s+)?historico\s+(?:do meu\s+|da minha\s+|de\s+|do\s+|da\s+)?(.+)$', key)
        if m:
            from .temporal import canonical_subject, DISPLAY
            subj=canonical_subject(m.group(1))
            if subj:
                hist=self.db.temporal_history(subj,self.settings.episodic_lookback_months)
                entries=[{**x,'category':'temporal',
                          'content':DISPLAY.get(subj,subj)+': '+x['value']+
                                    (' (ATUAL)' if x['valid_to'] is None else ' (ANTERIOR)'),
                          'created_at':x['valid_from'], 'updated_at':x['valid_from']} for x in hist]
                return reply(f'Encontrei {len(hist)} versões registadas para {DISPLAY.get(subj,subj)}. '
                             'As datas indicam quando tomei conhecimento da alteração.',
                             action={'type':'open','panel':'memory'},data=entries)
        m = re.match(r'^(?:qual e|qual era|o que e) (?:o meu|a minha)?\s*(browser|navegador|sistema operativo|distribuicao linux|editor|editor de codigo|ide|modelo ollama)(?: atual)?$',key)
        if m:
            from .temporal import canonical_subject
            rows=self.db.temporal_current(m.group(1))
            if not rows:
                return reply('Ainda não tenho uma informação atual confirmada para esse assunto.')
            return reply('A última informação que me deste foi: '+rows[0]['value']+'. '
                         'Podes pedir o histórico para consultar versões anteriores.')
        m = re.match(r'^(?:como era|qual era) (?:o meu|a minha)?\s*(.+?) em (\d{4}-\d{2}-\d{2})$',key)
        if m:
            from .temporal import canonical_subject
            subject=canonical_subject(m.group(1))
            if subject:
                try:
                    entry=self.db.temporal_as_of(subject,m.group(2)+'T23:59:59+00:00')
                except ValueError:
                    return reply('Data inválida. Usa AAAA-MM-DD.')
                return reply(('Nessa data eu tinha registado: '+entry['value']+'.' if entry else
                              'Não tenho registos suficientes para confirmar o estado nessa data.'))

        if key in ('ativa memoria automatica','ativa a memoria automatica','liga a memoria automatica'):
            self.db.set_option('episodic_capture','true')
            return reply('Ativei a gravação local de conversas. Podes desativá-la quando quiseres.')
        if key in ('desativa memoria automatica','desativa a memoria automatica','para de guardar conversas'):
            self.db.set_option('episodic_capture','false')
            return reply('Desativei a gravação automática. As memórias antigas continuam guardadas até pedires para apagar.')
        if key in ('ativa extracao automatica', 'ativa aprendizagem da memoria', 'ativa memoria inteligente'):
            self.db.set_option('auto_extract_memory','true')
            return reply('Ativei a extração automática local de conhecimentos a partir das conversas gravadas.')
        if key in ('desativa extracao automatica', 'desativa aprendizagem da memoria', 'desativa memoria inteligente'):
            self.db.set_option('auto_extract_memory','false')
            return reply('Desativei a extração automática. As memórias já guardadas não são apagadas.')
        if key in ('analisa conversas pendentes','extrai conhecimento das conversas'):
            result = await self.extractor.extract_one()
            return reply(f"Analisei {result['processed']} conversa e guardei {result['added']} novos conhecimentos. {result['reason']}")
        if key in ('indexa as conversas','indexa conversas antigas'):
            result = await self.memory.index_episode_pending(self.settings.episodic_lookback_months, 20)
            return reply(f"Indexei {result['indexed']} mensagens. Pendentes nesta amostra: {result['pending']}. {result['reason']}")
        if key in ('apaga historico de conversas', 'esquece todas as conversas'):
            removed = self.db.erase_episodes()
            return reply(f'Apaguei {removed} mensagens da memória ativa. Backups e exportações antigos não são apagados.')
        m = re.match(r'^(?:esquece|apaga) (?:a )?conversa ([a-f0-9]{12})$', key)
        if m:
            ok = self.db.delete_episode(m.group(1))
            return reply('Mensagem removida da memória de conversas.' if ok else 'Não encontrei essa mensagem.')
        m = re.match(r'^(?:procura|pesquisa|encontra) (?:uma )?conversa (?:sobre )?(.+)$', key)
        if m:
            found = await self.memory.recall_episodes(m.group(1), self.settings.episodic_lookback_months, 20)
            rows = [{**e,'category':'conversation',
                     'content':('TU: ' if e['role']=='user' else 'AURA: ')+e['content']} for e in found]
            return reply(f'Encontrei {len(rows)} mensagens relacionadas nos últimos {self.settings.episodic_lookback_months} meses.',
                         action={'type':'open','panel':'memory'},data=rows)
        m = re.match(r'^(?:o que (?:falamos|conversamos)|mostra (?:as )?conversas)(?: de)? ha (um|dois|tres|quatro|cinco|seis|[1-9][0-9]?) mes(?:es)?$', key)
        if m:
            number = {'um':1,'dois':2,'tres':3,'quatro':4,'cinco':5,'seis':6}.get(m.group(1))
            number = number or int(m.group(1))
            if number > self.settings.episodic_lookback_months:
                return reply('A pesquisa está configurada para os últimos '
                             f'{self.settings.episodic_lookback_months} meses. O conteúdo antigo não é apagado.')
            items = self.db.episodes_months_ago(number)
            rows = [{**e,'category':'conversation',
                     'content':('TU: ' if e['role']=='user' else 'AURA: ')+e['content']} for e in items]
            return reply(f'Encontrei {len(rows)} mensagens de há cerca de {number} meses.',
                         action={'type':'open','panel':'memory'},data=rows)
        if key in ('mostra as conversas antigas','mostra o historico de conversas'):
            rows = self.db.combined_memory_panel(self.settings.episodic_lookback_months)
            return reply(f'Tenho {self.db.episode_count(self.settings.episodic_lookback_months)} mensagens recuperáveis dos últimos {self.settings.episodic_lookback_months} meses.',
                         action={'type':'open','panel':'memory'},data=rows)

        m = re.match(r'^(?:procura|pesquisa|encontra) (?:na )?memoria (?:sobre )?(.+)$', key)
        if m:
            query = original[original.casefold().find(m.group(1)):] if m.group(1) in original.casefold() else m.group(1)
            matches = await self.memory.recall(query, 20)
            return reply(f'Encontrei {len(matches)} memórias relacionadas.' if matches else
                         'Não encontrei memórias relacionadas.',
                         action={'type':'open', 'panel':'memory'}, data=matches)

        m = re.match(r'^(?:corrige|atualiza) (?:a )?(?:memoria|nota) ([a-f0-9]{12}) (?:para|com) (.+)$', key)
        if m:
            original_match = re.match(r'^(?:corrige|atualiza) (?:a )?(?:mem[oó]ria|nota) [a-f0-9]{12} (?:para|com) (.+)$', original, re.I)
            new_content = original_match.group(1) if original_match else m.group(2)
            updated = await self.memory.correct(m.group(1), new_content)
            return reply('Atualizei a memória e preservei o histórico da correção.' if updated else
                         'Não encontrei essa memória.',
                         action={'type':'open', 'panel':'memory'}, data=self.db.memories())

        if key in ('indexa as memorias', 'atualiza o indice da memoria'):
            result = await self.memory.index_pending()
            return reply(f"Indexei {result['indexed']} memórias. Por indexar: {result['pending']}. {result['reason']}")

        if key in ('faz backup da memoria', 'cria copia de seguranca da memoria'):
            try:
                target = self.secure_backups.create_backup()
                return reply('Criei uma cópia de segurança CIFRADA em '+str(target)+
                             '. Guarda a frase-passe separadamente: sem ela não é possível restaurar.')
            except (VaultError, OSError) as exc:
                return reply('Não criei backup. '+str(exc))

        if key in ('exporta a memoria', 'exporta as minhas memorias'):
            try:
                target = self.secure_backups.export_memory(self.settings.episodic_lookback_months)
                return reply('Exportei a memória CIFRADA em '+str(target))
            except (VaultError, OSError) as exc:
                return reply('Não exportei a memória. '+str(exc))

        m = re.match(r'^(?:lembra[ -]te de|guarda na memoria|memoriza)\s+(.+)$', key)
        if m:
            # Use original case/accents of note, not normalized version.
            prefix = re.match(r'^(?:lembra[ -]te de|guarda na mem[oó]ria|memoriza)\s+', original, re.I)
            note = (original[prefix.end():] if prefix else m.group(1)).strip()
            if len(note) < 3:
                return reply('A nota é demasiado curta para guardar.')
            item = await self.memory.remember(note)
            return reply('Guardei essa informação na tua memória local.',
                         action={'type': 'open', 'panel': 'memory'},
                         data=self.db.memories())

        m = re.match(r'^(?:esquece a (?:nota|memoria)|apaga a nota)\s+([a-f0-9]{12})$', key)
        if m:
            deleted = self.db.delete_memory(m.group(1))
            return reply('Nota eliminada.' if deleted else 'Não encontrei essa nota.',
                         action={'type': 'open', 'panel': 'memory'}, data=self.db.memories())

        # v3.0: human-gated evaluation lab. No autonomous optimization or
        # automatic promotion of experiments. All actions originate from this
        # exact user command, never from the language model or a web document.
        if key in ('estado do raciocinio', 'mostra estado do raciocinio',
                   'estado do otimizador', 'mostra experiencias de raciocinio'):
            state=self.optimizer.status()
            return reply(f"Encontrei {len(state['experiments'])} experiências de raciocínio. "
                         + ('Existe uma estratégia aprovada.' if state['active'] else
                            'Não existe uma estratégia ativa. Para realizar testes DSPy, usa o terminal.'),
                         action={'type':'open','panel':'diagnostics'},
                         data={'optimizer':state})
        m=re.fullmatch(r'(?:aprova otimizacao|aprova estrategia) ([a-f0-9]{12})',key)
        if m:
            ok=self.optimizer.approve(m.group(1))
            return reply('Estratégia aprovada para respostas fundamentadas, sujeitas a verificação de referências.'
                         if ok else 'Não aprovada. É necessário superar o benchmark, manter o mesmo modelo e ter um artefacto íntegro.')
        if key in ('desativa otimizacao', 'reverte estrategia', 'volta ao raciocinio original'):
            rolled=self.optimizer.rollback()
            return reply('Reverti para o comportamento original.' if rolled else
                         'Já não há nenhuma estratégia otimizada ativa.')
        m=re.match(r'^responde com fontes sobre (.+)$',key)
        if m:
            query=self._topic_from(original)
            docs=self.db.documents(query=query,limit=4)
            try:
                output=await asyncio.to_thread(self.optimizer.answer,query,docs)
            except (RuntimeError,ValueError,OSError):
                return reply('O motor otimizado está indisponível. Confirma o Ollama e o DSPy; não vou inventar fontes.')
            return reply(output['text'], action={'type':'open','panel':'research'} if output['ok'] else None,
                         data={'topic':query,'documents':docs,'sources':output.get('sources',[])} if output['ok'] else None)

        # v3.3: explicit external source re-check. No continuous arbitrary browsing.
        if key in ('estado da verificacao factual','mostra verificacoes factuais',
                   'historico de verificacoes factuais'):
            runs=self.factcheck.latest(30)
            return reply(f'Encontrei {len(runs)} verificações externas registadas. '
                         'Estas verificações não certificam a verdade das afirmações.',
                         action={'type':'open','panel':'research'},
                         data={'factcheck_history':runs})
        m=re.fullmatch(r'(?:verifica factos|verifica factualmente|verifica fontes externas) ([a-f0-9]{12})',key)
        if m:
            report=await self.factcheck.verify_live(m.group(1))
            if report is None:return reply('Não encontrei essa hipótese.')
            return reply('Verificação externa: '+report['grade']+'. '
                         'Continua sem existir prova definitiva de verdade.',
                         action={'type':'open','panel':'research'},data={'factcheck_report':report})
        m=re.fullmatch(r'(?:analisa evidencias externas|mostra verificacao factual) ([a-f0-9]{12})',key)
        if m:
            report=self.factcheck.offline(m.group(1))
            if report is None:return reply('Não encontrei essa hipótese.')
            return reply('Estado dos relatos arquivados: '+report['grade']+'. '
                         'Não foram consultadas páginas ao vivo.',
                         action={'type':'open','panel':'research'},data={'factcheck_report':report})

        # v3.2: user-requested offline knowledge quality checks.
        if key in ('verifica qualidade da aprendizagem', 'mostra qualidade da aprendizagem',
                   'audita a fiabilidade', 'mostra fiabilidade das fontes'):
            report=self.quality.overview(50)
            return reply(f"Analisei {report['checked']} hipóteses. "
                         f"{report['decisions'].get('withhold',0)} devem ser retidas "
                         f"e {report['repeated_text_warnings']} apresentam texto repetido "
                         'entre domínios. Isto não é prova de verdade.',
                         action={'type':'open','panel':'research'},data={'quality_report':report})
        m=re.fullmatch(r'(?:avalia fiabilidade|verifica proveniencia|analisa qualidade) ([a-f0-9]{12})',key)
        if m:
            result=self.quality.inspect(m.group(1))
            if result is None:return reply('Não encontrei essa hipótese para avaliar.')
            return reply('Estado da proveniência: '+result['snapshot_status']+
                         '. Decisão: '+result['decision']+'.',
                         action={'type':'open','panel':'research'},data={'quality_report':result})

        # v3.1: sources ≠ learning ≠ independently reproducible truth.
        # No remote code execution; only offline source integrity + exact arithmetic.
        if key in ('audita conhecimentos','audita a aprendizagem',
                   'verifica evidencias','verifica as evidencias'):
            report=self.epistemics.audit_all(50)
            return reply(f"Auditei {report['audited']} hipóteses. "
                         f"{report['grades'].get('reproduced_calculation',0)} cálculos reproduzidos; "
                         f"{report['grades'].get('unsubstantiated',0)} hipóteses sem evidência íntegra. "
                         'Fontes concordantes não comprovam automaticamente a verdade.',
                         action={'type':'open','panel':'research'},data={'epistemic_audit':report})
        m=re.fullmatch(r'(?:audita descoberta|audita hipotese|verifica descoberta) ([a-f0-9]{12})',key)
        if m:
            report=self.epistemics.audit(m.group(1))
            if not report:return reply('Não encontrei essa hipótese para auditar.')
            labels={
                'reproduced_calculation':'cálculo reproduzido com aritmética exata',
                'falsified_calculation':'cálculo refutado',
                'multiple_reports_unverified':'relatada por várias origens, sem prova independente',
                'quoted_unverified':'citação íntegra, sem comprovação independente',
                'unsubstantiated':'evidência original ausente ou alterada',
                'rejected':'hipótese rejeitada pelo utilizador',
            }
            return reply('Auditoria: '+labels.get(report['grade'],report['grade'])+'.',
                         action={'type':'open','panel':'research'},data={'epistemic_audit':report})

        # v2.9: source-bound learning, explicit intent and reversible user review.
        if key in ('ativa aprendizagem avancada', 'ativa o motor de aprendizagem'):
            self.db.set_option('advanced_learning_enabled','true')
            return reply('Motor avançado ligado para os temas de investigação que autorizaste. '
                         'Guardo hipóteses com fontes; não modifico os meus modelos nem o código.')
        if key in ('desativa aprendizagem avancada', 'desliga o motor de aprendizagem'):
            self.db.set_option('advanced_learning_enabled','false')
            return reply('Motor avançado desligado. As fontes e hipóteses existentes continuam guardadas.')
        if key in ('estado da aprendizagem','como esta a tua aprendizagem','mostra estado da aprendizagem'):
            stats=self.learning.stats()
            return reply(f"Registei {stats['runs']} ciclos de aprendizagem e "
                         f"{stats['evidence_links']} ligações a fontes. As hipóteses não são factos comprovados.",
                         action={'type':'open','panel':'research'}, data={'topic':'',
                         'documents':self.db.documents(limit=12),'claims':self.learning.claims(limit=12),
                         'learning':stats})
        m = re.match(r'^(?:mostra descobertas sobre|mostra hipoteses sobre|que aprendeste sobre)\s+(.+)$',key)
        if m:
            topic=m.group(1)
            claims=self.learning.claims(topic,20)
            return reply(f'Encontrei {len(claims)} hipóteses documentadas relacionadas com {topic}. '
                         'Verifica sempre as fontes.',action={'type':'open','panel':'research'},
                         data={'topic':topic,'documents':self.db.documents(topic,12),
                               'claims':claims})
        m = re.match(r'^(?:aprova|rejeita) (?:a )?(?:hipotese|descoberta)\s+([a-f0-9]{12})$',key)
        if m:
            result=self.learning.review(m.group(2), 'approve' if m.group(1)=='aprova' else 'reject')
            return reply('Registei a tua revisão; isto não equivale a comprovação independente.'
                         if result else 'Não encontrei essa hipótese.')
        m = re.match(r'^(?:aprende profundamente sobre|investiga a fundo|faz investigacao aprofundada sobre)\s+(.+)$',key)
        if m:
            topic=m.group(1).strip().rstrip('.!?')[:160]
            outcome=await self.research.learn(topic)
            result=await self.learning.learn_from(topic,outcome.documents,outcome.warning)
            return reply(f'Investiguei {topic}: {result.documents} fontes, {result.stored} novas ligações de evidência e '
                         f'{result.rejected} propostas rejeitadas. Os dados requerem revisão. '
                         f'{result.warning}',action={'type':'open','panel':'research'},
                         data={'topic':topic,'documents':outcome.documents,
                               'claims':self.learning.claims(topic,20), 'warning':result.warning})

        m = re.match(r'^(?:para|desativa|cancela) (?:a )?(?:investigacao|pesquisa) (?:autonoma )?(?:sobre )?(.+)$', key)
        if m:
            removed = self.db.disable_job(m.group(1))
            return reply('Investigação periódica desativada.' if removed else
                         'Não encontrei uma investigação ativa com esse tema.',
                         action={'type': 'open', 'panel': 'jobs'}, data=self.db.jobs())

        m = re.match(r'^(?:investiga autonomamente sobre|pesquisa diariamente sobre|aprende autonomamente sobre|pesquisa periodicamente sobre)\s+(.+)$', key)
        if m:
            topic = self._topic_from(original)
            job = self.db.create_job(topic, self.settings.research_interval_hours)
            # Do the first pass now; subsequent passes occur in scheduler while server runs.
            outcome = await self.research.learn(topic)
            self.db.job_result(topic, outcome.warning if not outcome.documents else '')
            count = len(outcome.documents)
            result = (f'Ativei pesquisa periódica sobre {topic}. Encontrei {count} fontes ou pré-visualizações. '
                      f'Os conteúdos não estão verificados independentemente. {outcome.warning}'.strip())
            return reply(result, action={'type': 'open', 'panel': 'research'},
                         data={'topic': topic, 'documents': outcome.documents,
                               'warning': outcome.warning})

        m = re.match(r'^(?:investiga|pesquisa|aprende)(?: sobre)?\s+(.+)$', key)
        if m:
            topic = self._topic_from(original)
            outcome = await self.research.learn(topic)
            if outcome.documents:
                result = (f'Investiguei {topic} e guardei {len(outcome.documents)} referências. '
                          'São fontes e excertos, não conclusões verificadas independentemente.')
            else:
                result = f'Não consegui reunir fontes sobre {topic}. {outcome.warning}'
            return reply(result, action={'type': 'open', 'panel': 'research'},
                         data={'topic': topic, 'documents': outcome.documents,
                               'warning': outcome.warning})

        m = re.match(r'^(?:o que aprendeste sobre|resume o que sabes sobre|mostra conhecimento sobre)\s+(.+)$', key)
        if m:
            topic = self._topic_from(original)
            documents = self.db.documents(topic, 15)
            if not documents:
                return reply(f'Ainda não tenho fontes guardadas sobre {topic}. Podes pedir-me para investigar.')
            return reply(f'Tenho {len(documents)} registos relacionados com {topic}. Vou mostrá-los com as fontes.',
                         action={'type': 'open', 'panel': 'research'},
                         data={'topic': topic, 'documents': documents, 'warning': ''})

        if key in ('ajuda', 'o que podes fazer', 'comandos', 'como funcionas'):
            return reply('Podes pedir: abre a memória, lembra-te de algo, investiga sobre um tema, '
                         'investiga autonomamente sobre um tema, aprende profundamente sobre um tema, '
                         'ativa aprendizagem avançada, estado da aprendizagem, procura conversa sobre um assunto, '
                         'o que falámos há cinco meses, associa tecnologia SQLite ao projeto AURA, mostra relações do projeto AURA, atualiza o meu browser para Brave, consolida a memória, mostra memórias repetidas, desativa memória automática ou fecha tudo.')

        if key in ('olá', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'aura'):
            result = reply('Estou aqui. Em que posso ajudar?')
            result['capture'] = True
            return result

        text = await self.llm.reply(original, history)
        result = reply(text, speak=len(text) < 500)
        result['capture'] = True  # Save only actual conversations, never CRUD/control commands.
        return result

    @staticmethod
    def _summary_rows(summaries: list[dict]) -> list[dict]:
        return [{**x, 'category':'summary', 'updated_at':x['created_at']} for x in summaries]

    @staticmethod
    def _relational_row(edge: dict) -> dict:
        label=(f"{RELATION_DISPLAY.get(edge['source_kind'],edge['source_kind'])} "
               f"{edge['source_name']} {RELATION_DISPLAY.get(edge['relation_type'],edge['relation_type'])} "
               f"{RELATION_DISPLAY.get(edge['target_kind'],edge['target_kind'])} {edge['target_name']}")
        return {**edge,'category':'relation','content':label,
                'created_at':edge['created_at'],'updated_at':edge['created_at']}

    @staticmethod
    def _topic_from(original: str) -> str:
        # Capture after the final literal 'sobre', if any; otherwise after first verb.
        m = re.search(r'\bsobre\s+(.+)$', original, flags=re.I)
        topic = m.group(1) if m else re.sub(r'^\S+\s+', '', original)
        return topic.strip().rstrip('.!?')[:160]

    async def panel_data(self, panel: str):
        if panel == 'memory':
            return self.db.combined_memory_panel(self.settings.episodic_lookback_months)
        if panel == 'research' or panel == 'browser':
            return {'topic': '', 'documents': self.db.documents(limit=25),
                    'claims':self.learning.claims(limit=18), 'warning': ''}
        if panel == 'jobs':
            return self.db.jobs()
        if panel == 'diagnostics':
            return {'ollama': await self.llm.health(), 'memory_count': len(self.db.memories(100)),
                    'knowledge_count': len(self.db.documents(limit=200)),
                    'episodes_6months': self.db.episode_count(self.settings.episodic_lookback_months),
                    'episodic_capture': self.db.capture_enabled(self.settings.episodic_capture),
                    'memory_months': self.settings.episodic_lookback_months,
                    'semantic_indexed':self.db.episode_vector_count(self.settings.embedding_model,self.settings.episodic_lookback_months) if self.settings.embedding_model else 0,
                    'extracted_knowledge':self.db.extracted_count(),
                    'temporal_facts':self.db.temporal_count(),
                    'relation_links':self.relations.stats()['links'],
                    'consolidation': self.consolidation.stats(),
                    'advanced_learning':self.learning.stats(),
                    'optimization_lab':self.optimizer.status(),
                    'epistemic_audits':self.epistemics.latest(10),
                    'learning_quality':self.quality.overview(12),
                    'extraction_active':self.db.get_option('auto_extract_memory','true' if self.settings.auto_extract_memory else 'false')=='true',
                    'private_mode': self.db.get_option('private_mode','false')=='true',
                    'encrypted_backups_enabled': self.secure_backups.enabled,
                    'active_database_encrypted': self.db.encrypted,
                    'research_jobs': len(self.db.jobs(True)), 'research_provider':
                    'Wikipedia + SearXNG' if self.settings.searxng_url else 'Wikipedia'}
        if panel == 'projects':
            return {'message': 'Painel de projetos demonstrativo. A leitura de repositórios locais ainda não está implementada.',
                    'projects': ['Expecto Ultimate']}
        return None

    async def memory_daemon(self, stop: asyncio.Event):
        """Bounded indexing/extraction. Never starts if recording was switched off."""
        while not stop.is_set():
            if (self.db.capture_enabled(self.settings.episodic_capture) and
                self.db.get_option('private_mode','false') != 'true'):
                if self.settings.embedding_model:
                    await self.memory.index_episode_pending(self.settings.episodic_lookback_months, 12)
                enabled = self.db.get_option('auto_extract_memory',
                    'true' if self.settings.auto_extract_memory else 'false')=='true'
                if enabled:
                    await self.extractor.extract_one()
                auto = self.db.get_option('auto_consolidate_memory',
                    'true' if self.settings.auto_consolidate_memory else 'false')=='true'
                if auto and enabled:
                    await asyncio.to_thread(self.consolidation.if_due,
                        self.settings.episodic_lookback_months)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.memory_worker_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def research_daemon(self, stop: asyncio.Event):
        """No silent system modification: only opt-in public-topic research."""
        while not stop.is_set():
            for job in self.db.due_jobs():
                if stop.is_set():
                    break
                try:
                    result = await self.research.learn(job['topic'])
                    if (self.db.get_option('advanced_learning_enabled','false')=='true'
                        and self.db.get_option('private_mode','false')!='true'):
                        advanced = await self.learning.learn_from(job['topic'],result.documents,result.warning)
                        self.db.job_result(job['topic'],advanced.warning)
                    else:
                        self.db.job_result(job['topic'], result.warning)
                except Exception as exc:
                    # Do not write sensitive exception internals to persistent storage.
                    self.db.job_result(job['topic'], type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass
