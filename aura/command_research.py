"""User-triggered research, knowledge and evidence-learning commands.

All network access remains gated by the same explicit normalized phrases;
research and model output never grant additional application privileges.
"""
from __future__ import annotations
import re


async def handle_research_command(engine, original: str, key: str, respond):
    # v2.9: source-bound learning, explicit intent and reversible user review.
    if key in ('ativa aprendizagem avancada', 'ativa o motor de aprendizagem'):
        engine.db.set_option('advanced_learning_enabled','true')
        return respond('Motor avançado ligado para os temas de investigação que autorizaste. '
                     'Guardo hipóteses com fontes; não modifico os meus modelos nem o código.')
    if key in ('desativa aprendizagem avancada', 'desliga o motor de aprendizagem'):
        engine.db.set_option('advanced_learning_enabled','false')
        return respond('Motor avançado desligado. As fontes e hipóteses existentes continuam guardadas.')
    if key in ('estado da aprendizagem','como esta a tua aprendizagem','mostra estado da aprendizagem'):
        stats=engine.learning.stats()
        return respond(f"Registei {stats['runs']} ciclos de aprendizagem e "
                     f"{stats['evidence_links']} ligações a fontes. As hipóteses não são factos comprovados.",
                     action={'type':'open','panel':'research'}, data={'topic':'',
                     'documents':engine.db.documents(limit=12),'claims':engine.learning.claims(limit=12),
                     'learning':stats})
    m = re.match(r'^(?:mostra descobertas sobre|mostra hipoteses sobre|que aprendeste sobre)\s+(.+)$',key)
    if m:
        topic=m.group(1)
        claims=engine.learning.claims(topic,20)
        return respond(f'Encontrei {len(claims)} hipóteses documentadas relacionadas com {topic}. '
                     'Verifica sempre as fontes.',action={'type':'open','panel':'research'},
                     data={'topic':topic,'documents':engine.db.documents(topic,12),
                           'claims':claims})
    m = re.match(r'^(?:aprova|rejeita) (?:a )?(?:hipotese|descoberta)\s+([a-f0-9]{12})$',key)
    if m:
        result=engine.learning.review(m.group(2), 'approve' if m.group(1)=='aprova' else 'reject')
        return respond('Registei a tua revisão; isto não equivale a comprovação independente.'
                     if result else 'Não encontrei essa hipótese.')
    m = re.match(r'^(?:aprende profundamente sobre|investiga a fundo|faz investigacao aprofundada sobre)\s+(.+)$',key)
    if m:
        topic=m.group(1).strip().rstrip('.!?')[:160]
        outcome=await engine.research.learn(topic)
        result=await engine.learning.learn_from(topic,outcome.documents,outcome.warning)
        return respond(f'Investiguei {topic}: {result.documents} fontes, {result.stored} novas ligações de evidência e '
                     f'{result.rejected} propostas rejeitadas. Os dados requerem revisão. '
                     f'{result.warning}',action={'type':'open','panel':'research'},
                     data={'topic':topic,'documents':outcome.documents,
                           'claims':engine.learning.claims(topic,20), 'warning':result.warning})

    m = re.match(r'^(?:para|desativa|cancela) (?:a )?(?:investigacao|pesquisa) (?:autonoma )?(?:sobre )?(.+)$', key)
    if m:
        removed = engine.db.disable_job(m.group(1))
        return respond('Investigação periódica desativada.' if removed else
                     'Não encontrei uma investigação ativa com esse tema.',
                     action={'type': 'open', 'panel': 'jobs'}, data=engine.db.jobs())

    m = re.match(r'^(?:investiga autonomamente sobre|pesquisa diariamente sobre|aprende autonomamente sobre|pesquisa periodicamente sobre)\s+(.+)$', key)
    if m:
        topic = engine._topic_from(original)
        job = engine.db.create_job(topic, engine.settings.research_interval_hours)
        # Do the first pass now; subsequent passes occur in scheduler while server runs.
        outcome = await engine.research.learn(topic)
        engine.db.job_result(topic, outcome.warning if not outcome.documents else '')
        count = len(outcome.documents)
        result = (f'Ativei pesquisa periódica sobre {topic}. Encontrei {count} fontes ou pré-visualizações. '
                  f'Os conteúdos não estão verificados independentemente. {outcome.warning}'.strip())
        return respond(result, action={'type': 'open', 'panel': 'research'},
                     data={'topic': topic, 'documents': outcome.documents,
                           'warning': outcome.warning})

    m = re.match(r'^(?:investiga|pesquisa|aprende)(?: sobre)?\s+(.+)$', key)
    if m:
        topic = engine._topic_from(original)
        outcome = await engine.research.learn(topic)
        if outcome.documents:
            result = (f'Investiguei {topic} e guardei {len(outcome.documents)} referências. '
                      'São fontes e excertos, não conclusões verificadas independentemente.')
        else:
            result = f'Não consegui reunir fontes sobre {topic}. {outcome.warning}'
        return respond(result, action={'type': 'open', 'panel': 'research'},
                     data={'topic': topic, 'documents': outcome.documents,
                           'warning': outcome.warning})

    m = re.match(r'^(?:o que aprendeste sobre|resume o que sabes sobre|mostra conhecimento sobre)\s+(.+)$', key)
    if m:
        topic = engine._topic_from(original)
        documents = engine.db.documents(topic, 15)
        if not documents:
            return respond(f'Ainda não tenho fontes guardadas sobre {topic}. Podes pedir-me para investigar.')
        return respond(f'Tenho {len(documents)} registos relacionados com {topic}. Vou mostrá-los com as fontes.',
                     action={'type': 'open', 'panel': 'research'},
                     data={'topic': topic, 'documents': documents, 'warning': ''})


    return None
