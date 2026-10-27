# Expecto 4.4 — Evidence Critic

Audit deterministicamente as hipóteses produzidas pelo raciocínio em camadas.

- Confere se os números que surgem na afirmação também existem nos excertos citados.
- Assinala fraca sobreposição lexical (não é um modelo semântico).
- Assinala a presença de uma negação na afirmação quando não é detetada nas fontes.
- Cada hipótese recebe `audit.flags`, `audit.lexical_coverage` e `audit.semantic_entailment_verified=false`.
- Um alerta implica revisão, nunca a promoção automática a uma verdade provada.
- **Limites:** as verificações são superficiais, podem apresentar falsos positivos e falsos negativos, e não detetam contradições semânticas em geral.

## Verificar

`python -m pytest -q tests/test_evidence_critic_v44.py`

O Ollama real, respostas científicas inéditas e precisão semântica não foram avaliados nestes testes.
