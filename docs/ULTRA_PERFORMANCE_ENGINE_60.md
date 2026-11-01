# EXPECTO 6.0 — Ultra Performance Engine

Esta versão é um PR **dependente da branch de voz 5.7**. Não altera a `main`
e não remove as proteções de segurança, a memória nem os comandos existentes.

## Perfis de inferência

`AURA_PERFORMANCE_MODE=balanced` (predefinição):

- **fast**: somente definições gerais curtas e autónomas, sem referências a
  projetos, histórico ou dados pessoais. Evita recuperação de memória,
  resumos, relações e conhecimento pessoal. Usa até 160 tokens de saída.
- **standard**: mantém pesquisa de memória habitual, usa contexto
  secundário limitado a 16.000 caracteres e saída de até 450 tokens.
- **deep**: matemática, código, demonstrações, arquitetura e auditoria.
  Mantém a recuperação contextual, admite até 24.000 caracteres de
  conteúdo secundário e saída de até 700 tokens.
- **conservative**: mantém todas as perguntas em perfil standard.
- **off**: regressa ao comportamento original sem limites novos de contexto
  e sem encaminhamento adaptativo.

O router usa regras conservadoras. Nunca autoriza comandos privilegiados,
executa ferramentas, nem decide se é permitido pesquisar ou modificar o
sistema. Essas responsabilidades continuam a pertencer ao motor de comandos.

## Monitorização privada

`GET /api/performance/status` expõe apenas estatísticas agregadas das últimas
64 inferências locais:

- tempo de preparação e tempo total: mediana e P95;
- tempo até primeiro token (TTFT) em modo streaming;
- perfis usados, tentativas falhadas e tamanho médio do contexto recuperado.

As métricas não contêm mensagens, respostas, URLs nem memórias e **não são
persistidas em disco**. Reiniciar a aplicação reinicia o monitor.

## Avaliação e limitações

```bash
python -m pytest -q tests/test_performance_engine_v60.py
python -m scripts.benchmark_ollama_streaming --runs 20 --warmup 2 --output benchmark_voz.json
```

O segundo comando mede um Ollama instalado localmente. Os testes automáticos
usam modelos falsos e **não** demonstram melhoria de tokens/s em hardware real.
Menos contexto pode melhorar o TTFT em alguns modelos, mas pode prejudicar
respostas complexas se os perfis forem mal escolhidos; por isso há os modos
`conservative` e `off` e testes de não acesso às memórias na rota fast.

A melhoria principal é evitar trabalho desnecessário nas perguntas
verdadeiramente simples, sem sacrificar o contexto nas perguntas difíceis.
