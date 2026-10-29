# Expecto Performance Engine 4.4 — Benchmark A/B e otimização comprovada

**Estado:** implementado na branch experimental `feat/expecto-v6.7-realtime-local-voice`; não foi integrado na `main` nem executado no Windows do utilizador. A versão Python mínima prevista para estas otimizações é **3.12**.

## Alterações reais face à 4.3

1. **Cálculo vetorial com `math.sumprod`** em `aura/memory.py`, substituindo laços Python de multiplicação/soma. Mantém a norma da consulta pré-calculada e valida equivalência numérica.
2. **Deteção antecipada de Ollama indisponível** em `aura/llm.py`: evita carregar memórias, embeddings e documentos quando o circuit breaker está aberto; liberta a tentativa exclusiva de recuperação se a preparação de contexto falhar.
3. **Sem despacho para thread quando só há pesquisa lexical**: `asyncio.to_thread` continua no percurso semântico, onde pode sobrepor consultas SQLite ao cálculo de embeddings, mas não é executado no percurso lexical.
4. **WAL SQLite inicializado uma vez**, em vez de emitir `PRAGMA journal_mode=WAL` em todas as ligações. O ganho medido desta alteração isolada é baixo e não constitui aceleração do modelo.

Nenhuma destas alterações reduz o tamanho do modelo, desativa memória pessoal ou altera o modo `AURA_REASONING_REVIEW_MODE`.

## Benchmark reprodutível, mesmo ambiente

`scripts/benchmark_processing_v44.py` obtém o código **4.3 anterior, fixo no Git `0ad21c90c79ceef069ef861abf35a10e3f9f1bc4`**, e compara as mesmas funções com a 4.4 do checkout atual na **mesma máquina**. O benchmark mede medianas e p95, aquece os percursos antes da medição, alterna a ordem dos testes e verifica equivalência.

**GitHub Actions, Python 3.12.15, Ubuntu runner, 29/10/2026**, [execução 40891869315](https://github.com/Diogofgg05/Expecto-Assistant/actions/runs/40891869315):

| Operação concreta | 4.3 p50 | 4.4 p50 | Rácio p50 | 4.3 p95 | 4.4 p95 |
|---|---:|---:|---:|---:|---:|
| 400 cossenos, 384 dimensões | 11.76655 ms | 3.53448 ms | **3.33×** | 11.86100 ms | 3.56000 ms |
| Contexto lexical, sem embeddings | 0.05073 ms | 0.00479 ms | 10.59× | 0.07393 ms | 0.00550 ms |
| Consulta SQLite (1000 registos) | 0.70327 ms | 0.69822 ms | 1.01× | 0.73515 ms | 0.72360 ms |
| Circuito aberto com espera sintética de 10 ms | 10.19864 ms | 0.00808 ms | **apenas cenário simulado** | 10.22242 ms | 0.00880 ms |

**Interpretação:** apenas as funções indicadas foram comparadas. O grande ganho em cossenos é genuinamente de processamento CPU num teste controlado; o ganho de 10.59× no contexto lexical corresponde a cerca de 0.046 ms poupados por pergunta. O cenário do circuito aberto injeta artificialmente 10 ms numa chamada de contexto antiga, por isso o grande rácio **não pode** ser apresentado como aceleração geral da aplicação. Os dados não constituem prova de tempo de inferência Ollama, energia ou FPS do holograma.

A artefacto de resultados `benchmark_results_v44.json` está anexado na execução GitHub Actions `40891869315`. Testes da mesma execução: **443 Python aprovados, 2 ignorados; 7 JavaScript aprovados**.

Para repetir o teste no checkout completo, com histórico Git:

```bash
python scripts/benchmark_processing_v44.py --iterations 220 --warmup 20 --output benchmark_results_v44.json
```

## Medir a latência real do teu Ollama (executar localmente)

`scripts/benchmark_expecto_local_v44.py` faz pedidos ao **backend Expecto que estiver efetivamente a correr no teu computador**, através da rota `/api/command/stream`. Mede:
- tempo até ao primeiro token de rascunho, incluindo HTTP;
- tempo até à resposta final (após eventuais revisões);
- mediana p50 e p95 para dois prompts sintéticos fixos;
- sem guardar prompts privados, texto de rascunho ou resposta final.

**Proteção de memória:** o script interrompe-se se `/api/memory/status` indicar gravação de conversas ativa e o modo privado não estiver ligado. Para testar sem poluir a memória pessoal, inicia o Expecto experimental com `AURA_EPISODIC_CAPTURE=false` ou modo privado confirmado; reinicia e verifica `http://127.0.0.1:8000/api/memory/status`. Também podes usar uma cópia isolada da base de dados, em vez da tua instalação de produção.

No terminal Windows, na raiz do repositório:

```bat
py -3.12 scripts\benchmark_expecto_local_v44.py --label antes --runs 8 --warmups 1 --output antes.json
```

Repete **com outra versão do código ou outra configuração**, mantendo o modelo Ollama, computador, carga, perguntas e parâmetros iguais:

```bat
py -3.12 scripts\benchmark_expecto_local_v44.py --label depois --runs 8 --warmups 1 --output depois.json
py -3.12 scripts\benchmark_expecto_local_v44.py --compare antes.json depois.json
```

A comparação é útil, por exemplo, entre 4.3 e 4.4 no mesmo PC. O script é uma **ferramenta pronta para executar**, não um benchmark do teu Ollama já executado. Se não receber streaming de tokens, recusa produzir um relatório de inferência bem-sucedida. Aceita apenas URL HTTP localhost explícito, sem ligações remotas.

## Limitações e próximos passos

- Algumas otimizações Python reduzem milissegundos ou microssegundos; o grosso da demora pode continuar a ser a geração de tokens pelo modelo. Comparar **tempo até primeiro token e tempo até resposta final** é indispensável.
- A inferência depende de modelo, quantização, CPU/GPU/VRAM, comprimento do contexto, tokens de saída, cache do Ollama e concorrência.
- `math.sumprod` exige Python 3.12+; o CI executa 3.12.
- A utilização de `AURA_REASONING_REVIEW_MODE=fast` reduz chamadas de revisão mas é uma troca qualidade/latência, distinta das melhorias 4.4. Não foi ativada automaticamente.
- Não foi executado um benchmark real de Ollama no hardware do utilizador.
