# Expecto Performance Engine 4.1 — Pool HTTP e pesquisa semântica partilhada

**Estado:** implementação experimental na branch `feat/expecto-v6.7-realtime-local-voice`; ainda não integrada na `main`. Atualização incremental sobre Performance Engine 4.0.

## Melhorias implementadas

### 1. Um único embedding de pergunta para as duas pesquisas de memória

O caminho de respostas do Ollama podia pedir ao modelo de embeddings a mesma pergunta duas vezes:

- `MemoryEngine.recall(question)` para as notas pessoais;
- `MemoryEngine.recall_episodes(question)` para as conversas dos últimos meses.

O método **`MemoryEngine.recall_pair`** calcula o vetor da pergunta **uma só vez**, partilhando-o entre os dois algoritmos de recuperação (notas e conversas). Nenhum vetor de pergunta fica guardado permanentemente. Quando o embedding falha, ambas as pesquisas continuam por palavras, evitando uma segunda tentativa desnecessária. Os métodos públicos anteriores mantêm as suas assinaturas de chamada normais e continuam a funcionar isoladamente.

**Importante:** só ocorre quando `AURA_EMBEDDING_MODEL` está configurado e quando o percurso usa memória. A inicialização de embeddings continua opcional. Não implementa ANN, não limita o número de vetores existentes, e não substitui o índice de episódios.

### 2. Ligações HTTP Ollama persistentes e limitadas

`LocalInferencePool` cria um único `httpx.AsyncClient` **apenas quando necessário** e reutiliza as ligações keep-alive em pedidos de geração e revisão crítica. O máximo é 1–2 ligações, conforme as opções de concorrência. A API encerra o cliente no shutdown FastAPI; os endpoints de diagnóstico não inicializam este pool.

- Sem threads novas, serviços externos ou processos em segundo plano.
- `trust_env=False`: o Ollama local não utiliza proxies de ambiente do processo.
- Timeout da inferência principal: 65 segundos; revisão: 45 segundos.
- O fluxo de tokens SSE e o cancelamento preservam o transporte existente.
- O mecanismo mantém o circuit breaker e o limitador de pedidos já presentes.

As outras operações, como diagnóstico de saúde e indexação de embeddings, continuam com os clientes e limites anteriores.

### 3. Métricas sem conversas privadas

A resposta de `GET /api/compute/status` inclui o campo `ollama_http_pool` com apenas `created`, `active`, `max_connections` e `private_content_stored: false`. O endpoint `GET /api/performance/status` continua a mostrar p50/p95, primeiro token em streaming, contadores e perfil.

Nenhuma métrica contém mensagens, URLs privadas, texto gerado, conteúdos de memória, chaves ou texto dos prompts.

## Instalação e configuração

Esta versão foi desenvolvida sobre a branch experimental 6.7 e exige o código compatível dessa branch. O perfil continua `balanced` por defeito e **ambas** as melhorias da 4.1 se aplicam também ao modo equilibrado; não é preciso ativar `legacy`.

Para uma instalação com CPU antiga e poucos recursos:

```dotenv
AURA_PERFORMANCE_PROFILE=legacy
AURA_PERFORMANCE_NUM_CTX=3072
AURA_PERFORMANCE_NUM_BATCH=64
AURA_COMPUTE_MAX_ACTIVE=1
AURA_COMPUTE_MAX_WAITING=2
```

**Nota:** `legacy` reduz o contexto em algumas perguntas gerais; pode prejudicar respostas que dependam de memória. Para máxima fidelidade mantém `AURA_PERFORMANCE_PROFILE=balanced`.

## Validação

Executar, no ambiente do projeto:

```bash
python -m pytest -q tests/test_performance_engine_v40.py tests/test_performance_engine_v41.py
python -m pytest -q tests
```

CI em 29 de outubro de 2026: **406 testes Python aprovados, 2 ignorados, e 7 testes JavaScript aprovados**; sem falhas. Os testes do módulo 4.1 validam que o embedding é pedido uma vez, que o modo lexical funciona sem modelo, que o cliente HTTP é reutilizado e encerrado e que a configuração impõe limites.

**Ainda não foi medido o desempenho real com um modelo Ollama instalado**. Para atribuir ganhos é necessário comparar p50/p95, CPU, RAM, latência do primeiro token e qualidade de resposta num mesmo computador, com a mesma carga. O número de ligações diminui por reutilização, mas o tempo real depende do modelo, do hardware, do tamanho das memórias e do backend.

## Limitações

- O pool é local ao processo/loop de execução e reinicia com o backend.
- Não foi acrescentado cache persistente de perguntas pessoais; o vetor é apenas partilhado durante o pedido.
- Reutilizar um socket HTTP não reduz o custo computacional de carregar ou inferir um LLM grande.
- Os benefícios sobre a RAM do Ollama **não foram medidos**; o programa Python e o modelo são processos separados.
- A rota Legacy da 4.0 é conservadora mas não infalível. Perguntas pessoais devem usar o percurso completo.
