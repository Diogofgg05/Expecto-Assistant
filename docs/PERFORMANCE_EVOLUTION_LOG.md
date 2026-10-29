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

## 2026-10-29 — Etapa 8: laboratório de benchmark real (proposta)

- Novo comando `python -m aura.ollama_benchmark --model NOME --runs 20 --warmup 2`; adicionar `--stream` para comparar o modo streaming.
- Mede `elapsed_ms`, `ttft_ms` quando disponível, durações reportadas por Ollama, e tokens/s. Exportação JSON opcional com `--output results.json`.
- Calcula p50/p95/p99 por interpolação a partir de amostras observadas, distinguindo ausência de dados de zeros.
- Executa ciclos de warmup fora das medições; não grava prompts nem respostas.
- Testes unitários adicionados para percentis, ausência de TTFT e exclusão de warmups.
- **Não foi executado no Ollama real nesta sessão**; CI e consumo RAM/CPU continuam pendentes. O benchmark não implica aceleração por si só.
- Próxima etapa: rodar no hardware alvo com o mesmo modelo e condições, comparar logs antes/depois e verificar eventuais regressões.

## 2026-10-29 — Etapa 9: política de regressões para benchmarks (candidata)

- Novo módulo `aura/benchmark_compare.py`: compara dois JSON gerados pelo laboratório Ollama existente.
- Exige coincidência de modelo, URL, modo streaming, versão Python e plataforma; requer pelo menos 10 medições por relatório e p50/p95 válidos.
- Classifica `reject` se p95 piorar mais de 5% (latência) ou throughput cair mais de 5%; `candidate_for_review` se p50 e p95 da latência melhorarem e não houver regressões observadas; caso contrário, `inconclusive`.
- Novo `tests/test_benchmark_compare.py` com sete casos unitários de política usando relatórios sintéticos.
- Mantém todas as funcionalidades e dependências anteriores; não modifica inferência nem aprova mudanças automaticamente.
- Limitações: não verifica qualidade de resposta, carga ou temperatura da máquina, nem versão do modelo Ollama. Requer revisão humana e resultados reais comparáveis.
- **Validação de testes executada: pendente**; benchmarks reais antes/depois: ainda não recolhidos.

Comando: `python -m aura.benchmark_compare before.json after.json`.
Próximas prioridades: executar testes/CI, registar versão e hardware exatos em cada benchmark, medir custo de inferência no computador alvo.

## 2026-10-29 — Etapa 10: benchmark compare fail-closed (implementada, candidata)

### Diagnóstico
O comparador anterior confiava nos campos p50/p95 dos JSON, sem recalcular a partir de `samples`. Um ficheiro com `summary` manipulado podia obter incorretamente `candidate_for_review`.

### Alteração
- `aura/benchmark_compare.py`: p50/p95 recalculados de amostras observadas; rejeita valores não finitos, negativos e zero.
- Validação de metadados comparáveis e pelo menos 10 amostras para cada candidato mantida.
- `tests/test_benchmark_compare.py`: substituídos testes antigos baseados em `samples=[{}]` por 10 casos coerentes com medições por amostra, incluindo `NaN` e resumo adulterado.
- Sem novas dependências, sem migração e sem alteração do motor de inferência.

### Verificação executada (ambiente isolado desta sessão, não CI)
- `python -m pytest tests/test_benchmark_compare.py -q`: 10 testes aprovados, 0 falhas, 0,04 s.
- Compilação via `python -m compileall`: passou.
- Microbenchmark do custo do comparador, 2000 chamadas após aquecimento: p50 0,02158 ms; p95 0,02385 ms. Mede exclusivamente o comparador, não o Ollama/Expecto.
- Casos demonstrativos com dados sintéticos: 100 -> 90 ms resulta em `candidate_for_review`; 100 -> 110 ms resulta em `reject`. Não são medições do modelo.
- Servidor Ollama local neste ambiente: inacessível. Suíte total do Expecto: não executada.

### Decisão
Candidata pendente de validação CI, benchmark real em hardware alvo e revisão humana. Alterações isoladas na branch da PR #10; a `main` mantém-se intacta.

### Próxima evolução
- Registar digest exato do modelo e identificação de hardware nos benchmarks.
- Comparar os mesmos prompts sob carga controlada, com avaliação da qualidade das respostas.
- Executar a suíte completa e validar o CI da PR.

## 2026-10-29 — Etapa 11: identidade reprodutível de modelo e hardware (candidata)

### Problema confirmado
Relatórios anteriores comparavam nome do modelo e nome genérico da plataforma mas não conferiam o digest do modelo instalado, o modelo CPU, memória física ou identificação do prompt. Podiam classificar como ganho uma execução com pesos/hardware diferentes.

### Alterações implementadas
- `aura/benchmark_identity.py`: digest SHA-256 de `/api/tags` do Ollama, hash SHA-256 do prompt fixo, CPU, arquitetura, número lógico de núcleos e RAM física; sem hostname, número de série, prompts ou respostas no relatório.
- `aura/ollama_benchmark.py`: acrescenta `schema_version=2` e identidade ao JSON. Se não for possível conhecer modelo/hardware, interrompe a medição em vez de produzir um benchmark sem identidade.
- `aura/benchmark_compare.py`: rejeita comparação automática entre digests, workloads e hardware diferentes, ou relatórios antigos sem esquema v2.
- `tests/test_benchmark_identity.py` (5 testes), `tests/test_benchmark_compare.py` (15 testes), `tests/test_ollama_benchmark.py` adaptado ao novo esquema. Não foram acrescentadas dependências.

### Verificação executada nesta sessão
- Verificação local isolada dos módulos `benchmark_identity` e `benchmark_compare` espelhados da branch: **20 testes aprovados, 0 falhas, 0,13 s** com pytest.
- `compileall` nos dois módulos: aprovado.
- 3000 comparações locais, após 250 warmups: **p50 0,02516 ms; p95 0,05825 ms; p99 0,18297 ms** neste ambiente. São tempos do comparador e não do Ollama nem do projeto completo; estes resultados não representam ganho de velocidade.
- A suíte integral, os testes da CLI de benchmark no ambiente completo, CI remoto e o benchmark de Qwen3 real **não foram executados**.

### Decisão e continuidade
**Candidata para revisão, ainda não aprovada para integração.** Preservados os métodos de benchmark, streaming, limites, RAG e Keep-Alive já existentes. Relatórios v1 continuam legíveis como JSON mas são inconclusivos no comparador v2 por falta de identidade verificável.

### Próximos objetivos
1. Validar o CI completo e as execuções do benchmark no hardware alvo.
2. Identificar também as opções exatas de inferência/versão do Ollama, além do digest, para comparações mais rigorosas.
3. Comparar 20+ execuções reais com o mesmo modelo e avaliar a qualidade das respostas, não apenas latência.

## 2026-10-29 — Etapa 12: laboratório A/B de contexto Ollama (candidata)

### Diagnóstico
O benchmark anterior media tempos mas não testava duas configurações de inferência com sondas determinísticas e controlo de regressões de correção. Não existe ainda medição real no hardware alvo que justifique alterar os parâmetros de produção.

### Implementação
- Novo `aura/ollama_tuning_lab.py` com interface CLI explícita para comparar `num_ctx` de referência (8192) e candidato (4096), sem mudar definições da aplicação.
- Emparelha as medições com a mesma pergunta e alterna a ordem dos candidatos para reduzir enviesamento de aquecimento.
- Usa o identificador de modelo/hardware existente em `benchmark_identity` e a função de percentis existente em `ollama_benchmark`; não duplica estas funcionalidades.
- Valida uma pequena bateria fixa de três operações aritméticas, captura p50/p95 e tokens/s e distingue `candidate_for_review`, `reject` e `inconclusive`.
- Exige 10–100 medições, limite de 1024–8192 tokens de contexto, saída JSON opcional; só usa HTTP loopback sem redirecionamentos.
- Novo `tests/test_ollama_tuning_lab.py` com cinco testes locais.

### Validação observada nesta sessão
- Testes isolados com transporte HTTP simulado: **5 passed, 0 failed, 0,11 s**, execução Python/pytest local.
- `compileall` do novo módulo e testes: passou.
- Ollama real não disponível neste ambiente (`127.0.0.1:11434` recusou ligação), logo **não há ganho em ms do Qwen3 comprovado**.
- O ambiente de testes contém stubs apenas para as dependências de importação; a suíte completa da aplicação não foi executada.

### Decisão
**Candidata, pendente de revisão.** O laboratório é opt-in, sem alteração de parâmetros em produção. Os testes aritméticos são smoke-tests e não garantem qualidade de raciocínio, recuperação documental ou segurança.

### Como reproduzir no computador com Ollama
```bash
python -m aura.ollama_tuning_lab --model qwen3 --baseline-ctx 8192 --candidate-ctx 4096 --runs 20 --warmup 2 --output tuning.json
```

### Próximas prioridades
1. Executar no hardware-alvo, com a suíte completa e benchmark comparável.
2. Expandir testes de qualidade de resposta para matemática, código, RAG e fontes contraditórias.
3. Registar opções completas de inferência, versão Ollama, consumo de RAM e carga térmica para comparações mais rigorosas.

## 2026-10-29 — Etapa 13: revisão estática Python e integridade RAG (candidata)

### Diagnóstico
`BookResearchEngine.investigate` selecionava primeiro as passagens por ranking, sobreposição e limite, e só depois verificava correspondência com o índice. Uma passagem desatualizada podia ocupar uma vaga de `limit` e impedir o retorno de outra evidência válida.

### Implementação
- `aura/book_research.py`: valida (book_id, página, texto, text_hash) e recalcula SHA-256 do conteúdo *antes* da seleção final; otimiza cálculo de tokens para a desduplicação.
- `aura/code_inspection.py`: API estática `inspect_python(source)` baseada na AST; identifica erros de sintaxe, `eval/exec`, `pickle.load(s)`, `subprocess(shell=True)`, `except:` e funções extensas. Nunca executa, importa ou altera código enviado pelo utilizador. As heurísticas não provam ausência de vulnerabilidades.
- `tests/test_programming_rag_integrity.py`: testes novos para inspeção estática e fonte inválida com classificação superior não bloquear a fonte válida.
- `tests/test_book_research_v41.py`: fixtures corrigidas para SHA-256 reais, preservando a validação dos testes anteriores.
- Nenhuma nova dependência nem alteração automática de parâmetros dos modelos.

### Verificação e limites
Alterações e testes foram submetidos ao GitHub; a suíte completa, os testes de integração reais e a execução do Ollama **não foram confirmados** nesta etapa. Não se afirma ganho de velocidade em ms nem aumento comprovado de accuracy/recall.
A revisão de código é **análise estática de Python**, não execução em sandbox, resolução de bugs por IA ou auditoria de segurança integral.

### Decisão
**Candidata para revisão**, ainda não aprovada. Preservadas a proveniência e classificação explícita das evidências e o comportamento conservador de validação de respostas.

### Próximos passos
1. CI e avaliação RAG com conjunto gold rotulado (hit@k, MRR, fonte adulterada).
2. Integração opcional e limitada da inspeção de Python no fluxo de perguntas de programação.
3. Avaliação de tarefas reais de código com testes em sandbox externo e qualidade verificada, sem executar código de origem desconhecida no processo principal.
