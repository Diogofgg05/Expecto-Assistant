"""Explicit, deterministic verification and quality actions.

Only user commands reach this module. Model-generated output is never
allowed to invoke control commands or grant privileges.
"""
from __future__ import annotations
import re
import asyncio


async def handle_evidence_command(engine, original: str, key: str, respond):
    # v3.0: human-gated evaluation lab. No autonomous optimization or
    # automatic promotion of experiments. All actions originate from this
    # exact user command, never from the language model or a web document.
    if key in ('estado do raciocinio', 'mostra estado do raciocinio',
               'estado do otimizador', 'mostra experiencias de raciocinio'):
        state=engine.optimizer.status()
        return respond(f"Encontrei {len(state['experiments'])} experiências de raciocínio. "
                     + ('Existe uma estratégia aprovada.' if state['active'] else
                        'Não existe uma estratégia ativa. Para realizar testes DSPy, usa o terminal.'),
                     action={'type':'open','panel':'diagnostics'},
                     data={'optimizer':state})
    m=re.fullmatch(r'(?:aprova otimizacao|aprova estrategia) ([a-f0-9]{12})',key)
    if m:
        ok=engine.optimizer.approve(m.group(1))
        return respond('Estratégia aprovada para respostas fundamentadas, sujeitas a verificação de referências.'
                     if ok else 'Não aprovada. É necessário superar o benchmark, manter o mesmo modelo e ter um artefacto íntegro.')
    if key in ('desativa otimizacao', 'reverte estrategia', 'volta ao raciocinio original'):
        rolled=engine.optimizer.rollback()
        return respond('Reverti para o comportamento original.' if rolled else
                     'Já não há nenhuma estratégia otimizada ativa.')
    m=re.match(r'^responde com fontes sobre (.+)$',key)
    if m:
        query=engine._topic_from(original)
        docs=engine.db.documents(query=query,limit=4)
        try:
            output=await asyncio.to_thread(engine.optimizer.answer,query,docs)
        except (RuntimeError,ValueError,OSError):
            return respond('O motor otimizado está indisponível. Confirma o Ollama e o DSPy; não vou inventar fontes.')
        return respond(output['text'], action={'type':'open','panel':'research'} if output['ok'] else None,
                     data={'topic':query,'documents':docs,'sources':output.get('sources',[])} if output['ok'] else None)

    # v3.3: explicit external source re-check. No continuous arbitrary browsing.
    if key in ('estado da verificacao factual','mostra verificacoes factuais',
               'historico de verificacoes factuais'):
        runs=engine.factcheck.latest(30)
        return respond(f'Encontrei {len(runs)} verificações externas registadas. '
                     'Estas verificações não certificam a verdade das afirmações.',
                     action={'type':'open','panel':'research'},
                     data={'factcheck_history':runs})
    m=re.fullmatch(r'(?:verifica factos|verifica factualmente|verifica fontes externas) ([a-f0-9]{12})',key)
    if m:
        report=await engine.factcheck.verify_live(m.group(1))
        if report is None:return respond('Não encontrei essa hipótese.')
        return respond('Verificação externa: '+report['grade']+'. '
                     'Continua sem existir prova definitiva de verdade.',
                     action={'type':'open','panel':'research'},data={'factcheck_report':report})
    m=re.fullmatch(r'(?:analisa evidencias externas|mostra verificacao factual) ([a-f0-9]{12})',key)
    if m:
        report=engine.factcheck.offline(m.group(1))
        if report is None:return respond('Não encontrei essa hipótese.')
        return respond('Estado dos relatos arquivados: '+report['grade']+'. '
                     'Não foram consultadas páginas ao vivo.',
                     action={'type':'open','panel':'research'},data={'factcheck_report':report})

    # v3.2: user-requested offline knowledge quality checks.
    if key in ('verifica qualidade da aprendizagem', 'mostra qualidade da aprendizagem',
               'audita a fiabilidade', 'mostra fiabilidade das fontes'):
        report=engine.quality.overview(50)
        return respond(f"Analisei {report['checked']} hipóteses. "
                     f"{report['decisions'].get('withhold',0)} devem ser retidas "
                     f"e {report['repeated_text_warnings']} apresentam texto repetido "
                     'entre domínios. Isto não é prova de verdade.',
                     action={'type':'open','panel':'research'},data={'quality_report':report})
    m=re.fullmatch(r'(?:avalia fiabilidade|verifica proveniencia|analisa qualidade) ([a-f0-9]{12})',key)
    if m:
        result=engine.quality.inspect(m.group(1))
        if result is None:return respond('Não encontrei essa hipótese para avaliar.')
        return respond('Estado da proveniência: '+result['snapshot_status']+
                     '. Decisão: '+result['decision']+'.',
                     action={'type':'open','panel':'research'},data={'quality_report':result})

    # v3.1: sources ≠ learning ≠ independently reproducible truth.
    # No remote code execution; only offline source integrity + exact arithmetic.
    if key in ('audita conhecimentos','audita a aprendizagem',
               'verifica evidencias','verifica as evidencias'):
        report=engine.epistemics.audit_all(50)
        return respond(f"Auditei {report['audited']} hipóteses. "
                     f"{report['grades'].get('reproduced_calculation',0)} cálculos reproduzidos; "
                     f"{report['grades'].get('unsubstantiated',0)} hipóteses sem evidência íntegra. "
                     'Fontes concordantes não comprovam automaticamente a verdade.',
                     action={'type':'open','panel':'research'},data={'epistemic_audit':report})
    m=re.fullmatch(r'(?:audita descoberta|audita hipotese|verifica descoberta) ([a-f0-9]{12})',key)
    if m:
        report=engine.epistemics.audit(m.group(1))
        if not report:return respond('Não encontrei essa hipótese para auditar.')
        labels={
            'reproduced_calculation':'cálculo reproduzido com aritmética exata',
            'falsified_calculation':'cálculo refutado',
            'multiple_reports_unverified':'relatada por várias origens, sem prova independente',
            'quoted_unverified':'citação íntegra, sem comprovação independente',
            'unsubstantiated':'evidência original ausente ou alterada',
            'rejected':'hipótese rejeitada pelo utilizador',
        }
        return respond('Auditoria: '+labels.get(report['grade'],report['grade'])+'.',
                     action={'type':'open','panel':'research'},data={'epistemic_audit':report})

    return None
