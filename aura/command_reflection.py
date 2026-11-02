"""Explicit, user-authorized reflection, goal and feedback commands.

LLM-generated text never invokes these functions; the router only calls them
for a direct normalized user command. None of the operations is implicit.
"""
from __future__ import annotations
import re


def handle_reflection_command(engine, original: str, key: str, respond):
    # v5.1: Reflection is opt-in; feedback notes are never treated as instructions.
    m=re.match(r'^feedback explicacao (curta|longa|boa)\s*:\s*(.*)$',key)
    if m:
        rating={'curta':'too_short','longa':'too_long','boa':'helpful'}[m.group(1)]
        note=original.split(':',1)[1].strip()
        item=engine.reflection.feedback('explanation',rating,note)
        return respond('Feedback explícito registado. Só adapto o estilo após a tua aprovação.',
                     data={'feedback':item})
    m=re.match(r'^feedback sugestao (util|inutil) ([a-f0-9]{32})(?:\s*:\s*(.*))?$',key)
    if m:
        note=original.split(':',1)[1].strip() if ':' in original else ''
        try:
            item=engine.reflection.feedback('suggestion',
                'helpful' if m.group(1)=='util' else 'unhelpful',note,m.group(2))
        except ValueError as ex:
            return respond('Não guardei a avaliação: '+str(ex))
        return respond('Avaliação guardada. Vou ter em conta esta preferência quando pedires sugestões.',
                     data={'feedback':item})
    if key in ('analisa feedback', 'reflete sobre o feedback', 'avalia a tua evolucao'):
        outcome=engine.reflection.proposal()
        if outcome['status']=='pending':
            return respond('Tenho uma proposta de ajuste ao detalhe das explicações. '
                         'Precisa da tua aprovação explícita.',data=outcome)
        if outcome['status']=='already_suitable':
            return respond('O estilo aprovado já corresponde ao feedback recente.',data=outcome)
        return respond('Ainda não há feedback consistente suficiente para sugerir uma alteração.',data=outcome)
    if key in ('estado da reflexao', 'mostra o feedback', 'que aprendeste com o feedback'):
        return respond('Aqui estão as avaliações explícitas e as adaptações aprovadas. '
                     'Isto não é treino dos pesos do modelo.',
                     data={'setting':engine.reflection.setting(),
                           'feedback':engine.reflection.feedback_history(),
                           'proposals':engine.reflection.proposals()})
    m=re.fullmatch(r'(aprova|rejeita) (?:a )?(?:melhoria|adaptacao) ([a-f0-9]{32})',key)
    if m:
        try:
            outcome=engine.reflection.decide(m.group(2),'approve' if m.group(1)=='aprova' else 'reject')
        except ValueError as ex:
            return respond('Não foi possível rever a proposta: '+str(ex))
        return respond('Preferência aplicada com aprovação explícita.' if outcome['applied'] else
                     'Proposta rejeitada; o estilo permanece igual.',data=outcome)
    if key in ('reverte ultima melhoria','desfaz ultima adaptacao','reverte a ultima adaptacao'):
        outcome=engine.reflection.rollback()
        return respond('Reverti a última adaptação de comunicação.' if outcome['reverted'] else
                     'Não existem adaptações ativas para reverter.',data=outcome)
    m=re.fullmatch(r'apaga feedback ([a-f0-9]{32})',key)
    if m:
        removed=engine.reflection.delete_feedback(m.group(1))
        return respond('Feedback eliminado.' if removed else 'Não encontrei essa avaliação.')

    m=re.match(r'^(avancei|bloqueio) no objetivo ([a-f0-9]{32})\s*:\s*(.+)$',key)
    if m:
        state='progress' if m.group(1)=='avancei' else 'blocked'
        try:
            item=engine.reflection.checkin(m.group(2),state,original.split(':',1)[1])
        except ValueError as ex:
            return respond('Não guardei o progresso: '+str(ex))
        return respond('Registo guardado como declaração tua; não executei nenhuma ação.',data={'checkin':item})
    m=re.fullmatch(r'(?:historico|progresso) do objetivo ([a-f0-9]{32})',key)
    if m:
        return respond('Aqui estão os registos explícitos deste objetivo.',
                     data={'checkins':engine.reflection.checkins(m.group(1))})
    m=re.fullmatch(r'apaga registo de progresso ([a-f0-9]{32})',key)
    if m:
        return respond('Registo de progresso apagado.' if engine.reflection.delete_checkin(m.group(1)) else
                     'Não encontrei esse registo.')

    if key.startswith('recorda experiencia: '):
        item = engine.continuity.remember(original.split(':', 1)[1])
        return respond('Registei esta experiência como declaração tua, não como facto verificado.', data={'experience': item})
    if key in ('mostra experiencias', 'minhas experiencias'):
        return respond('Estas são as experiências que pediste para registar.', data={'experiences': engine.continuity.experiences()})
    if key.startswith('apaga experiencia '):
        ident = key.removeprefix('apaga experiencia ').strip()
        return respond('Experiência apagada.' if engine.continuity.forget(ident) else 'Não encontrei essa experiência.')
    if key.startswith('novo objetivo: '):
        item = engine.continuity.add_goal(original.split(':', 1)[1])
        return respond('Objetivo guardado. Não farei ações por iniciativa própria sem autorização.', data={'goal': item})
    if key in ('meus objetivos', 'mostra objetivos'):
        return respond('Estes são os objetivos registados.', data={'goals': engine.continuity.goals()})
    if key.startswith('concluir objetivo '):
        ident = key.removeprefix('concluir objetivo ').strip()
        return respond('Objetivo concluído.' if engine.continuity.goal_status(ident, 'done') else 'Não encontrei esse objetivo.')
    if key in ('expecto, tens sugestoes', 'tens sugestoes', 'sugere proximo passo', 'sugere um proximo passo', 'o que sugeres'):
        suggestions = engine.continuity.suggestions()
        return respond('Tenho estas sugestões. Só atuo depois de me dares autorização.' if suggestions else
                     'Ainda não registei objetivos ativos. Podes dizer: novo objetivo: ...', data={'suggestions': suggestions})


    return None
