"""Explicit command routing for local skill practice; no model-generated actions."""
from __future__ import annotations
import re


def handle_practice_command(engine, original: str, key: str, respond):
    if key in ("estado das competencias", "progresso das competencias",
               "mostra competencias", "diagnostico de competencias"):
        report = engine.competency.report()
        rows = report["domains"]
        details = "; ".join(
            f"{r['area']}: {r['correct']}/{r['answered']} corretos"
            for r in rows)
        suggested = report["suggested_domain"]
        tip = f" Recomendo praticar {suggested}." if suggested else (
            " Começa por praticar para recolher resultados.")
        return respond("Progresso local: " + details + "." + tip +
                       " Isto mede exercícios concretos, não o conhecimento total do modelo.",
                       data=report)

    if key in ("salta exercicio", "ignora exercicio"):
        skipped = engine.competency.skip()
        return respond("Exercício ignorado; não contou como erro." if skipped else
                       "Não tens exercícios pendentes.")

    match = re.fullmatch(
        r"(?:responde (?:ao )?(?:exercicio|treino))\s+([a-f0-9]{12})\s*"
        r"(?::|=|com)\s*(.+)", key)
    if match:
        try:
            result = engine.competency.submit(match.group(1), match.group(2))
        except ValueError as exc:
            return respond(str(exc))
        message = ("Resposta correta! " if result["correct"] else
                   "Resposta incorreta. ") + result["explanation"]
        return respond(message + " Podes pedir outro exercício.", data=result)

    match = re.fullmatch(
        r"(?:treina|treinar|pratica|praticar)\s+(?:as\s+)?"
        r"(competencias|matematica|programacao|fisica)", key)
    if match or key in ("proximo exercicio", "exercicio adaptativo"):
        domain = match.group(1) if match else None
        domain = None if domain == "competencias" else domain
        challenge = engine.competency.next(domain)
        return respond(
            f"Treino de {challenge['area']} (nível {challenge['level']}): "
            f"{challenge['question']} "
            f"Para responder escreve: responde treino {challenge['id']}: <resposta>.",
            data=challenge)
    return None
