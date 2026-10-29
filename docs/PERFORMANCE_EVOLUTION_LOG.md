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
