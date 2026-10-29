# Expecto — Registo de evolução do Performance Engine

## 2026-10-29 — Etapa 2 (proposta, PR #10)

Base: branch `perf/parallel-searxng-latency-20261029`, derivada da `main`.

### Alterações
- Pesquisas externas SearXNG em paralelo, preservando a ordem dos lotes e deduplicação.
- Início da pesquisa web ao mesmo tempo que a investigação local de livros, em vez de após o RAG.
- Testes: concorrência entre pesquisas web, falha parcial, sobreposição RAG/web.

### Benchmark reprodutível de controlo (não end-to-end)
100 iterações, Python asyncio, 30 ms de espera simulada no RAG e 40 ms por pesquisa web. Medianas observadas:
- Pesquisa web paralela após RAG: 70,65 ms (p95 71,30 ms).
- Pesquisa web paralela sobreposta ao RAG: 40,56 ms (p95 40,99 ms).
- Ganho mediano 30,10 ms, aproximadamente 42,6%.

São medições isoladas com esperas artificiais, NÃO resultados do Ollama ou do serviço de produção. Os testes de regressão foram adicionados ao repositório, mas a suíte de testes da aplicação não foi executada/validada neste ambiente.

### Preservado
- Pesquisa externa opt-in no loopback, sem redirects.
- Limites de evidências, ordenação, verificação de referências e rejeição de propostas não sustentadas.
- Interfaces e entradas da CLI existentes.

### Riscos e pendências
- Validar CI e a suíte completa antes de merge.
- Medir com SearXNG e Ollama reais em hardware alvo: p50/p95/p99, tempo até primeiro token, RAM máxima e CPU.
- Avaliar um cliente HTTP persistente com controlo de ciclo de vida.
- Distinguir semântica verificada de indicadores heurísticos de evidência.

### Continuidade
Consultar primeiro a `main` atual e os PRs abertos, especialmente PR #10. Fazer alterações incrementais e registar benchmarks por commit e hardware. Não assumir que a PR foi integrada.

## 2026-10-29 — Etapa 3: Ollama HTTP connection reuse (proposta)

- `OllamaMultiLayerAdapter` oferece agora `async with` para reutilizar `httpx.AsyncClient` durante as chamadas sequenciais ao mesmo modelo.
- `reason-hybrid` abre um único cliente HTTP para planeamento e geração, e fecha-o mesmo após erro.
- Chamadas fora de contexto continuam a criar e fechar um cliente por chamada para compatibilidade.
- Adicionados testes isolados com cliente HTTP simulado: reutilização e limpeza após chamadas normais.
- **Benchmark de latência Ollama real: ainda não executado**. O benefício depende de manter ligação TCP e não altera a velocidade de inferência do modelo.
- Preservadas as otimizações de pesquisa concorrente das etapas anteriores.
- Pendente: executar testes completos/CI e medir TTFT, p50/p95 e RAM com Ollama local real, antes de afirmar ganhos em milissegundos.

## 2026-10-29 — Etapa 4: limite de geração separado para planeamento (proposta)

- O adaptador Ollama expõe `plan(prompt)` com `num_predict=192`; as restantes chamadas mantêm `num_predict=950`.
- O orquestrador usa `plan` quando disponível e preserva suporte para modelos que só implementam `__call__`.
- Adicionado teste unitário com HTTP simulado que verifica os dois orçamentos.
- Não há resultados end-to-end em milissegundos nem redução garantida: `num_predict` é teto de tokens, não quantidade obrigatoriamente gerada.
- Risco: planos grandes podem ser truncados; acompanhar taxa de JSON inválido e fallback à pergunta original em modelos reais.
- Preservados keep-alive, RAG/web concorrentes e verificações de fontes.

Pendente: executar suíte CI e benchmark com Ollama real antes de ajustar o limite de 192 tokens.

## 2026-10-29 — Etapa 5: Ollama inference telemetry (proposta)

- `OllamaMultiLayerAdapter.last_metrics` contém os dados da chamada mais recente: `elapsed_ms` (medido no cliente), `total_ms`, `load_ms`, `prompt_eval_ms`, `generation_ms`, `generated_tokens` e `tokens_per_second`.
- As durações da resposta Ollama são convertidas de nanossegundos para milissegundos; dados ausentes/inválidos aparecem como `None`. Não são guardados prompts ou respostas em telemetria.
- `ttft_ms=None` intencionalmente: o adaptador atual usa `stream=False`, portanto não mede o primeiro token.
- Teste adicionado com dados sintéticos para conferir conversões e throughput.
- **Não foi executado benchmark de inferência real nem a suíte de testes**. Instrumentação não implica melhoria de velocidade por si só.
- Preservados orçamentos distintos para planeamento e resposta, reutilização HTTP e sobreposição RAG/web.

### Próximo passo
Testar contra Ollama instalado e medir várias execuções após aquecimento (p50/p95/p99). Adicionar streaming instrumentado mantendo as respostas JSON verificadas.

## 2026-10-29 — Etapa 6: streaming JSON com TTFT (proposta)

- Criado `aura/ollama_stream_metrics.py` para reunir fragmentos NDJSON de `/api/chat` com `stream=True`, medir `ttft_ms` (primeiro conteúdo observado) e `elapsed_ms`.
- Adicionado método opcional `OllamaMultiLayerAdapter.stream_json(prompt)`; o método padrão `__call__` mantém `stream=False` e a lógica anterior.
- Valida JSON apenas após evento terminal, nunca devolve propostas parciais nem ignora os controlos de evidências.
- O leitor limita a 250000 caracteres, recusa eventos malformados e streams sem evento terminal; usa o HTTP client existente quando disponível.
- Testes com HTTP mock adicionados para fragmentação, JSON incompleto e falta de conclusão.
- Atenção: `ttft_ms` mede o primeiro fragmento de conteúdo recebido no cliente, não necessariamente o primeiro token gerado pelo modelo no servidor.
- Sem benchmark de latência com Ollama real e sem validação da suíte completa. A melhoria é observabilidade e suporte opcional a streaming, não ganho em ms confirmado.

### Próxima evolução
Integrar streaming final na interface sem publicar JSON parcial ou respostas sem verificação, e comparar p50/p95/p99 entre modos em hardware alvo.

## 2026-10-29 — Etapa 7: telemetria e tratamento de erros no streaming (proposta)

- O leitor `collect_json_stream` converte as durações do evento terminal de Ollama para ms, incluindo carregamento, processamento de prompt e geração; calcula tokens/s quando possível.
- Rejeita eventos com erro explícito e linhas de evento demasiado extensas.
- Mantém JSON completo e validado antes de entregar a proposta para verificação; não publica resultados parciais.
- Dois testes de regressão acrescentados para conversão de tempos e eventos de erro.
- Não foi executado benchmark real nem a suíte completa nesta sessão. Nenhuma redução de latência é alegada nesta etapa.
- Próximo passo: instrumentar a interface e executar comparação real de p50/p95/p99 em hardware alvo.
