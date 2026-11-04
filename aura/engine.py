"""Constrained intent router; model output NEVER authorizes a privileged action."""
from __future__ import annotations
from .ollama_protocol import installed_models
import re
import unicodedata
from .database import Database
from .identity import Identity, IdentitySettings
from .config import Settings
from .command_reflection import handle_reflection_command
from .command_research import handle_research_command
from .command_interface import handle_interface_command
from .command_memory import handle_memory_command
from .command_evidence import handle_evidence_command
from .engine_services import EngineServicesMixin
from .core.services import CoreServices


def normalized(s: str) -> str:
    stripped = unicodedata.normalize('NFD', s.casefold())
    return re.sub(r'\s+', ' ', ''.join(c for c in stripped if unicodedata.category(c) != 'Mn')).strip()


def reply(text: str, *, action: dict | None = None, data=None, speak: bool = True) -> dict:
    return {'text': text, 'spoken': text[:380] if speak else '',
            'action': action, 'data': data, 'ok': True}


class AuraEngine(EngineServicesMixin):
    def __init__(self, settings: Settings, db: Database, *, services: CoreServices | None = None):
        self.settings, self.db = settings, db
        if services is not None and (services.settings is not settings or services.db is not db):
            raise ValueError("As dependências têm de usar as mesmas definições e base de dados.")
        self.services = services if services is not None else CoreServices(settings, db)
        # Keep legacy public attributes. Both are built by the same scoped
        # container; the model always receives the exact memory instance.
        self.memory = self.services.get("memory")
        self.llm = self.services.get("llm")

    async def command(self, original: str, history: list[dict] | None = None, *, on_token=None) -> dict:
        original = original.strip()
        original = re.sub(r'^(?:aura|expecto)[,\s:]+', '', original, flags=re.I).strip()
        key = normalized(original).rstrip('.!?')
        if not original:
            return reply('Estou a ouvir. Podes falar ou escrever um comando.')

        result = handle_reflection_command(self, original, key, reply)
        if result is not None:
            return result

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

        # 5.2: explicitly requested research/orchestration, never automatic web search.
        deep_request = re.match(r'^(?:investiga profundamente|raciocina com fontes|pesquisa aprofundada)\s*[:,-]?\s+(.+)$',original,re.I)
        if deep_request:
            import os
            import httpx
            from .reasoning_orchestrator import ReasoningOrchestrator,LocalSearxngSearch
            from .multilayer_reasoning import OllamaMultiLayerAdapter
            from .book_semantics import OllamaBookEncoder
            question=deep_request.group(1).strip()
            wants_web=bool(re.search(r'\b(?:na internet|na web|pesquisa externa)\b',normalized(question)))
            if wants_web and not self.settings.searxng_url:
                return reply('A pesquisa externa precisa de um SearXNG local configurado. '
                             'Sem ele posso investigar apenas os livros importados.')
            try:
                adapter=OllamaMultiLayerAdapter(self.settings.ollama_url,
                         self.settings.reasoning_research_model or os.getenv('AURA_REASONING_MODEL') or self.settings.ollama_model)
                external=LocalSearxngSearch(self.settings.searxng_url) if wants_web else None
                result=await ReasoningOrchestrator(self.db,adapter,external=external).run(question)
                if result['status'] == 'supported_proposal' and self.settings.reasoning_review_model:
                    import httpx
                    from .reasoning_engine72 import ReasoningEngine72, LocalReasoningModel
                    from scripts.benchmark_ollama_streaming import loopback_url
                    url = loopback_url(self.settings.ollama_url)
                    selected = self.settings.reasoning_research_model or os.getenv('AURA_REASONING_MODEL') or self.settings.ollama_model
                    reviewer = self.settings.reasoning_review_model
                    async def proposal(prompt):
                        return result['answer']  # Revisions cannot silently invent new sources.
                    async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
                        tags = await client.get(url + '/api/tags')
                        tags.raise_for_status()
                        installed = installed_models(tags.json())
                        if selected not in installed or reviewer not in installed:
                            return reply('Configura nomes exatos dos modelos de investigação e revisão já instalados.')
                        if installed.get(selected) and installed[selected] == installed.get(reviewer):
                            return reply('A revisão precisa de um modelo com pesos diferentes do gerador.')
                        checked = await ReasoningEngine72(proposal, model=selected,
                            review=LocalReasoningModel(client, url, reviewer, metrics=self.llm.metrics,
                                resource_probe=self.llm.loaded_models if self.settings.response_resource_sampling else None), review_model=reviewer, allow_revision=False).run(
                                question, domain='research', evidence=[{'id': e['id'], 'text': e['text']}
                                    for e in result.get('evidence', [])])
                    result['independent_review'] = checked
                    if checked['status'] != 'reviewed_proposal':
                        result['status'] = 'requires_revision'
                        result['answer'] = ''
                        result['limitations'].append('Revisão independente insuficiente; resposta retida')
                if result['status']=='supported_proposal':
                    message=result['answer'] + '\n\n(Resposta fundamentada em excertos; fontes não são provas.)'
                else:
                    message='Não consegui verificar suficientemente a resposta. '
                    message+=' '.join(result.get('limitations',[])[:2])
                return reply(message, data=result)
            except (ValueError, TypeError, KeyError, httpx.HTTPError) as ex:
                return reply('Não consegui completar a investigação: '+str(ex))

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

        result = await handle_interface_command(self, original, key, reply)
        if result is not None:
            return result

        result = await handle_memory_command(self, original, key, reply)
        if result is not None:
            return result

        result = await handle_evidence_command(self, original, key, reply)
        if result is not None:
            return result

        result = await handle_research_command(self, original, key, reply)
        if result is not None:
            return result

        if key in ('ajuda', 'o que podes fazer', 'comandos', 'como funcionas'):
            return reply('Podes pedir: abre a memória, lembra-te de algo, investiga sobre um tema, '
                         'investiga autonomamente sobre um tema, aprende profundamente sobre um tema, '
                         'ativa aprendizagem avançada, estado da aprendizagem, procura conversa sobre um assunto, '
                         'o que falámos há cinco meses, associa tecnologia SQLite ao projeto AURA, mostra relações do projeto AURA, atualiza o meu browser para Brave, consolida a memória, mostra memórias repetidas, desativa memória automática ou fecha tudo.')

        if key in ('olá', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'aura'):
            result = reply('Estou aqui. Em que posso ajudar?')
            result['capture'] = True
            return result

        from .command_reasoning import handle_reasoning_command
        checked = await handle_reasoning_command(self, original, reply)
        if checked is not None:
            return checked

        # Explicit user-invoked adaptive practice, with independent oracles.
        from .command_practice import handle_practice_command
        practice = handle_practice_command(self, original, key, reply)
        if practice is not None:
            return practice

        # Do not pass streaming-only arguments to the ordinary request path.
        # Preserves compatibility with local/third-party LLM adapters exposing
        # the historical reply(question, history) signature.
        if on_token is None:
            text = await self.llm.reply(original, history)
        else:
            text = await self.llm.reply(original, history, on_token=on_token)
        result = reply(text, speak=len(text) < 500 or on_token is not None)
        result['capture'] = True  # Save only actual conversations, never CRUD/control commands.
        return result

