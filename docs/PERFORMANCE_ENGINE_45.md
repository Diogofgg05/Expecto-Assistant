# Expecto Performance Engine 4.5 — Pesquisa semântica antecipada

**Data:** 29/10/2026 · **Estado:** implementado e testado na branch experimental
`feat/expecto-v6.7-realtime-local-voice`. Não integrado na `main`; não testado
com o Ollama instalado no PC do utilizador.

## Problema da 4.4

A 4.4 já iniciava em paralelo o embedding da pergunta e as pesquisas lexicais SQLite.
No entanto, carregava os vetores semânticos das notas e conversas **só depois de
terminar o embedding**, prolongando a preparação do contexto.

## Melhoria da 4.5

`aura/memory.py` faz pré-leitura **por pedido** de quatro conjuntos:

- notas por FTS5/lexical;
- episódios por FTS5/lexical;
- vetores das notas;
- vetores dos episódios do intervalo solicitado.

Esta leitura trabalha numa thread local ao mesmo tempo que o Ollama calcula o
vetor da pergunta. O resultado continua a seguir para `recall` e
`recall_episodes`, que mantêm as regras de ranking, os limites, os limiares e
a recuperação de contexto anteriores. A leitura antecipada não retém resultados
entre perguntas e não introduz cache persistente; na pergunta seguinte os vetores
são novamente lidos, pelo que alterações recentes não ficam ocultas.

Ollama e SQLite podem continuar a competir pelo processador em hardware limitado.
Não se deve assumir um ganho universal: quando não há latência de embeddings
significativa, o benefício pode ser nulo ou a thread pode aumentar a latência.

## Benchmark 4.4 vs 4.5 — GitHub Actions

Comparação realizada na **mesma máquina CI** com o código 4.4 fixo em
`f46d190790289ccf321cbe85093d270f5238febb` e o código da branch mais
recente. `scripts/benchmark_processing_v45.py` utiliza perguntas e vetores
totalmente artificiais, verifica equivalência de resultados, aquece as rotinas
e alterna a ordem dos pedidos.

**Execução:** [GitHub Actions 40895010936](https://github.com/Diogofgg05/Expecto-Assistant/actions/runs/40895010936)

| Cenário de teste | 4.4 p50 | 4.5 p50 | Rácio | 4.4 p95 | 4.5 p95 |
|---|---:|---:|---:|---:|---:|
| Embedding sintético de 15 ms + leitura DB de 2 ms por etapa | 20.446 ms | 16.494 ms | **1.24×** | 20.626 ms | 16.583 ms |
| Embedding imediato + leituras DB sem atraso | 1.235 ms | 1.220 ms | 1.01× | 1.269 ms | 1.287 ms |

Os tempos do segundo cenário diferem menos do que o ruído provável do runner;
não constituem melhoria material. **No p95 do segundo cenário, a 4.5 é
ligeiramente pior.** Este é um resultado legítimo e documentado.

**Limitação essencial:** as durações de embedding e acesso a BD são
injetadas/simuladas. Embora o temporizador meça a execução de Python e
concorrência reais, estes números não são a latência medida do Ollama,
nem a velocidade total de resposta no Windows. Os testes não medem VRAM,
tokens por segundo ou tempo de síntese de voz.

### Validação

Execução `40895010936`:
- 460 testes Python aprovados, 2 ignorados;
- 7 testes JavaScript aprovados;
- benchmark A/B concluído sem falhas;
- comparação de resultados exatos das duas versões;
- testes de leitura simultânea de vetores e ausência de cache desatualizada.

A evidência estruturada está no artefacto `performance-4-5-ab` da execução CI.

Para repetir num checkout com histórico Git:

```bat
py -3.12 scripts\benchmark_processing_v45.py --runs 24 --warmup 4 --output benchmark_results_v45.json
```

### Benchmark do Ollama real

A ferramenta da 4.4 continua disponível:
`scripts/benchmark_expecto_local_v44.py`, que mede o primeiro token
e a resposta final sobre a API SSE do Expecto. Corre-a antes e depois,
com o mesmo modelo e hardware, e sem gravação de conversas de benchmark.

**Próximo passo:** utilizar esse relatório de primeira palavra e resposta final
no PC real para determinar se o limite principal é embedding, preparação de
contexto, inferência/tokenização ou revisão do modelo. Só depois de medir
convém decidir entre quantização, batching, concorrência e cache de prefixo.
