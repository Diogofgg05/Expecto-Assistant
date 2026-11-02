## 7.0.3 — Lightweight runtime
- Lazily instantiate optional voice engines on first voice request.
- Reuse squared query norm when ranking memory and episode embedding vectors.
- Remove unreachable no-op wrapper in Ollama health.
- Regression tests verify lazy creation, scoring equivalence and API compatibility.
- No proven RAM/CPU speedup until benchmarks on target hardware.

## 7.0.2 — Lightweight Core & lazy optional services
- Router principal reduzido para cerca de 172 linhas; comandos de memória, interface e verificação separados sem alterar os contratos.
- Serviços secundários de auditoria, pesquisa e reflexão inicializados sob pedido, evitando objetos desnecessários no arranque.
- Número de memórias contabilizado via SELECT COUNT(*) sem materializar milhares de notas.
- Corrigido endereço loopback autorizado para a configuração 127.0.0.1.
- CI simplificada: gatilhos por diretório e suite Python completa.
- Os ganhos de latência/RAM reais não foram medidos em hardware de destino.

## 7.0.1 — API stability & modular engine
- Eliminada colisão da rota /api/memory/status: recursos passam para /api/resources/status.
- Verificação de rotas duplicadas HTTP/WebSocket na criação da app.
- Separados comandos de reflexão, investigação e serviços de fundo do motor principal.
- Testes completos e contratos de API na CI, com controlos de origem e payload.
- Nenhuma migração de dados ou alteração automática de modelos.

## 7.0.0 — NanoMemory Engine
- Política AUTO/ECO/BALANCED/MAX com leitura best-effort de RAM livre.
- Contexto Ollama num_ctx, num_predict e keep_alive regulados por perfil.
- Diagnóstico /api/memory/status: RAM livre e VRAM de modelos carregados (API Ollama /api/ps).
- Canvas do holograma reduz FPS, DPR e partículas sob pressão de RAM.
- Whisper persistente usa dois CPU threads em ECO durante carregamento.
- Mantém memória pessoal intacta, sem matar processos, sem quantizar pesos automaticamente.
- Testes isolados e documentação. Benchmark em hardware real pendente.

## 6.6.0 — Relevance-Aware Context and Concurrency
- Seleção determinística de passagens relevantes entre notas, episódios, relações, documentos e contexto temporal, com orçamento global de caracteres e deduplicação.
- O modo de desempenho off mantém a recuperação anterior sem novo corte de contexto.
- Fila de inferências Ollama limitada, para reduzir a sobrecarga de CPU e RAM. Definição opcional AURA_OLLAMA_MAX_CONCURRENT (1–4, padrão 1).
- Diagnósticos de passagens escolhidas e descartadas, sem guardar texto pessoal nas métricas.
- Validação por testes unitários; velocidade real em hardware ainda pendente.

## 6.5.0 — Ollama Adaptive Inference 2.0 (measurable optimization)
- Um único embedding por pergunta partilhado entre recuperação de notas e episódios: teste controlado **2 pedidos antes → 1 depois**; a cache é temporária e por consulta.
- Cliente HTTP persistente para embeddings, encerrado no shutdown.
- Modelos Ollama FAST e DEEP opcionais, seleção pelo perfil real e fallback para o modelo principal em 404.
- Em FAST, opção `think=false` para perguntas gerais simples; DEEP mantém o raciocínio original.
- Testes de regressão e benchmark real de dois modelos disponível em `scripts/benchmark_adaptive_models.py`.
- Ganhos de velocidade com modelos reais **não medidos** no hardware do utilizador. O teste de chamadas não equivale a melhoria de latência.

## 6.4.0 — Consolidated Voice & Ultra Performance (integration candidate)
- Consolida alterações de voz e desempenho das branches 5.3 a 6.3; não implica modelos de voz instalados ou validados em hardware real.
- HTTP Ollama assíncrono persistente com ligações limitadas e encerramento no lifespan.
- Métricas reais de tokens/s do Ollama (quando devolvidas), sem guardar prompts.
- Testes de regressão e atualização de versão da API.
- Otimização inspirada nos princípios de transporte de OpenJarvis; implementação original, sem copiar código fonte.
- Não há benchmark comparativo real nem prova de ganho absoluto de latência.

## 5.2 — Hybrid Research & Verified Reasoning
- Orquestrador limitado: planeamento de consultas + RAG híbrido e opcional pesquisa externa SearXNG local.
- Proveniência por livro/página/hash, web classificada como pré-visualização não verificada.
- Citações inventadas rejeitadas; crítica textual e cálculo aritmético independente podem reter respostas.
- `reason-hybrid` no CLI e comando natural explícito; modelo de raciocínio selecionável.
- Exportação consentida e curada de conjuntos SFT/DPO com holdout separado; treino nunca automático.
- Experiência LoRA com script isolado e recompensa aritmética experimental, não treino RL real.

## 5.1 — Adaptive Intelligence / Explicit Reflection (2026-10-27)
- Motor `aura/reflection.py` para avaliações voluntárias de respostas/sugestões e acompanhamento de objetivos.
- Propostas de profundidade das explicações baseadas em feedback convergente, sujeitas a aprovação explícita.
- Mudanças reversíveis com histórico; as notas de feedback nunca entram nas instruções do modelo.
- Sugestões dependentes de progresso ou bloqueios registados pelo utilizador; nenhuma execução automática.
- Novos comandos conversacionais, migração aditiva na base de dados e 12 testes de regressão.
- 227 testes aprovados e 2 integrações opcionais não executadas, sem treino neuronal demonstrado.

## 4.7 — Exact Linear Algebra Verifier
- Determinantes, inversas, produtos, sistemas lineares (Fractions).
- Limites de tamanho e entradas não executáveis; regressões testadas.
- CLI `verify-algebra` com JSON de entrada.
- 198 testes aprovados, 2 ignorados (integrações opcionais).

## 4.6 — Verified Reasoning
- Verificação independente de aritmética exata com AST restrita, limites de complexidade e sem execução de código.
- Segundo passo de crítica de respostas; citações limitadas às passagens recuperadas.
- Novo comando `reason-verify` com referências a livros e páginas.
- Testes de segurança, refutação e integração.
- Os resultados continuam a ser propostas; não é uma nova rede neuronal treinada.

## 4.5 — Independent Reasoning Benchmark
- Separação dev/test, avaliação de citações, respostas e abstenção; retenção do método inicial em caso de regressão.
- Avaliação independente das respostas esperadas; sem auto-treino de pesos.

## 4.4 — Evidence Critic
- Auditoria determinística de hipóteses por números, negações e suporte lexical.
- Todas as verificações são sinalizações, não comprovação semântica.
- Quatro testes adicionais de regressão.

## 4.3 — Multi-Layer Evidence Reasoning
- Motor de hipóteses contrastadas, críticas e proveniência; JSON seguro e limites explícitos.
- Exportador HTML 3D opcional com 3d-force-graph; sem alteração da interface principal.
- Testes de referências inventadas, falta de evidências e sanitização de HTML.
- Sem promessas de ganho neuronal; falta benchmark real Ollama.

## 3.9 — Book Mastery Lab (26-10-2026)

- Novo motor `aura/book_mastery.py` para avaliação de questões independentes, escolhidas/revistas por humanos, sobre passagens de PDFs autorizados.
- As respostas esperadas e IDs gold não entram no prompt do Ollama. Avaliação persistente por livro/capítulo, F1 lexical, evidências citadas e abstenção.
- Verificação conservadora de negação e de integridade/hash das fontes, com invalidação de avaliações depois de alterações.
- Comandos `mastery-check`, `mastery-report`, `mastery-plan`, `mastery-history` e `mastery-compare`; documentação e JSON de exemplo.
- Não há promoção automática a factos, nem aprendizagem real comprovada com Ollama sem testes nesse ambiente.

# Expecto Ultimate 3.8 — Deep Book Mastery (2026-10-26)

- Pesquisa híbrida com FTS5 e embeddings Ollama opcionais (`aura/book_semantics.py`).
- Cache cifrável de embeddings, hashes, isolamento por livro/capítulo, eliminação em cascata.
- Mapa de conceitos, equívocos e exercícios de aplicação ancorados em páginas (`learning-map`).
- Métricas de recuperação Hit@k / MRR com casos anotados, sem autocertificação do modelo.
- Respostas recusadas quando introduzem números não presentes nas evidências.
- Preservação de módulos anteriores; migrações aditivas.
- Testes offline com PDFs gerados e modelos simulados; Ollama real, SQLCipher e DSPy não validados aqui.

---

# Expecto Ultimate 3.7 — Book Reasoning Engine

- Novo motor de aprendizagem de livros `aura/book_reasoning.py`, separado da memória conversacional.
- Estudo por grupos de todas as passagens de um capítulo, com conceitos, questões e sínteses atribuídas a fontes.
- Ollama local em modo JSON; rejeição de citações, IDs e sínteses inconsistentes (sem fingir verificação semântica).
- Pesquisa de respostas limitada ao PDF e capítulo quando pedido, com abstinência sem evidência.
- Comparação de conceitos entre livros, guardada como avaliação não verificada.
- Tabelas novas aditivas com integridade referencial e eliminação em cascata.
- CLI estendida: `study-ai`, `ask`, `report` e `compare-ai`.
- Perguntas naturais “Expecto, segundo os livros, ...” respondidas a partir de PDFs importados.
- Preserva Patronum, holograma sem botões, memória de seis meses e requisitos de cifragem existentes.
- Testes determinísticos com PDFs gerados; modelo Ollama real não testado neste ambiente.

---

## 3.6 — Expecto / Patronum
- Novo nome público: Expecto.
- `Ativa Patronum`: diagnóstico combinado e visual holográfico especial.
- `Desativa Patronum`: regressa ao modo habitual.
- Mantida compatibilidade com dados e módulos AURA.

## 3.5
- Estudo de livros por capítulos ou blocos de páginas
- Resumos extrativos citados, conceitos e relações entre livros
- Comandos CLI e testes locais

# AURA Ultimate — Histórico

## 3.3.0 — Fact Verification (2026-10-25)

- Verificação factual externa controlada por comando, limitada à API oficial da Wikipédia portuguesa, com bloqueio de URLs arbitrários e redirecionamentos.
- Reconferência de excertos, diferenciando observação atual de certificação de verdade, sem promoção automática de hipóteses.
- Relatórios por evidência e histórico SQLCipher (`factcheck_runs`) com hashes de resposta, data e eliminação em cascata.
- Comparação de domínios arquivados sem afirmar independência editorial; impedimento de revalidação quando a proveniência já falhou.
- Comandos naturais, API somente de leitura para relatórios e apresentação no painel de investigação existente.
- Regressão e testes de rede simulada com allowlist. Integração HTTP real/SQLCipher real não validada nesta máquina.

---

# CHANGELOG — AURA Ultimate

## 3.2.0 — Evidence Intelligence (2026-10-25)

- Proveniência por SHA-256 de documentos, citações e URLs no momento de guardar cada nova ligação; esquema aditivo `evidence_snapshots`.
- Auditoria de alterações dos arquivos, evidências sem atestado legado e conteúdo possivelmente republicado entre sites.
- Alertas restritos de conflitos aritméticos e necessidade de revisão temporal, sem verificação ao vivo.
- Hipóteses com evidências alteradas, inexistentes, rejeitadas ou matematicamente refutadas deixam de alimentar o contexto de hipóteses do Ollama.
- Comandos por voz/texto e API apenas de consulta, mantendo o holograma e sem botões/sidebars.
- Suite de regressão atualizada para a API 3.2; cifragem real e DSPy real continuam opcionais/não verificados localmente.

---

# CHANGELOG — AURA Ultimate

## 3.0.0 — Reasoning Optimization Laboratory (2026-10-25)

- Camada `aura.optimizer` com DSPy opcional e Ollama local (`ollama_chat`).
- Métodos de otimização LabeledFewShot e BootstrapFewShot, acionados somente por CLI.
- Dataset público de perguntas fundamentadas, em divisões disjuntas treino/validação/teste.
- Avaliação exata de resposta + referência correta e comparação com baseline.
- Gate de desempenho e aprovação manual, sem alterações automáticas da estratégia em produção.
- Registo em SQLCipher, artefactos JSON com verificação SHA-256, rollback imediato.
- Comandos `Estado do raciocínio`, `Aprova otimização <ID>`, `Responde com fontes sobre ...`, `Reverte estratégia`.
- API read-only `/api/optimizer/status`, mantendo o holograma e interface da 2.9.
- Suite de testes de segurança e regressão; integração real DSPy/Ollama por validar na máquina de destino.
- Base de dados antiga preservada; atualização 2.9→3.0 sem mover backups nem dados automaticamente.

# Changelog

## 2.9.0 — Advanced Learning Engine (25-10-2026)

- Novo `aura/learning.py`: extração estruturada por Ollama, com limites de tamanho e citações literais.
- Novas tabelas idempotentes `learning_claims`, `learning_evidence`, `learning_runs` na base SQLCipher existente.
- Rastreabilidade por documentos persistidos; pesquisa multi-origem com estados `single_source`, `multiple_sources`, `approved_by_user` e `rejected`.
- Validação de URL HTTPS, bloqueio de IP privado e filtro lexical anti-alucinação conservador.
- Comandos naturais para investigar profundamente, ativar/desativar aprendizagem avançada, consultar hipóteses e revê-las.
- Integração com o motor de investigações periódicas apenas após ativação explícita e para temas autorizados.
- Contexto LLM distingue hipóteses de conhecimentos comprovados.
- API de consulta (`/api/learning/status` e `/api/learning/claims`) e apresentação dentro do espaço de pesquisa existente, sem novos controlos de navegação.
- Testes de regressão preservados; novos testes do motor sem dependências externas.
- Herda proteção SQLCipher e backup da 2.8; implementação e testes de cifragem real continuam dependentes do driver local.

> Esta versão NÃO inclui fine-tuning, autoedição de código, importação de framework DSPy/Deep Agents, nem alegações de aprendizagem comprovadamente correta.


## 3.4.0 — Book Learning
Motor local de ingestão PDF com FTS5, páginas/citações, verificações de integridade e propostas de conhecimento não verificadas.

## 4.0 — Independent Book Learning Cycle (2026-10-26)

- Novo `BookIterationLab`: ciclo de medição com **treino, validação e teste reservado** em conjuntos separados e preparados por humanos.
- Experimenta limites de recuperação 1–12 (máximo quatro configurações) com memória e pesquisas de livros existentes, sem reescrever o modelo nem instalar a alteração.
- A seleção usa apenas o treino; a validação e o teste reservado auditam melhorias. Um resultado inferior no teste reservado impede recomendação.
- Deteta questões iguais ou quase duplicadas entre divisões, integridade de passagens e divergências de fontes após a avaliação.
- Histórico persistente dos resultados e um plano de releitura com citações baseado **exclusivamente nas falhas de treino**, não nas respostas de validação e teste.
- Comandos CLI `learning-cycle`, `cycle-report`, `cycle-review`, `cycle-restudy` (opt-in) e `cycle-history`.
- Mantém livro/PDF, pesquisas locais e compatibilidade com bases 3.9; não envia dados para serviços externos por predefinição.
- **Limite:** o ciclo melhora escolhas de recuperação e avaliações; não é fine-tuning, aprendizagem de pesos ou prova de compreensão de livros.

## 4.1 — Cross-Book Research
- `aura/book_research.py`: agregação multi-pergunta por reciprocal rank fusion, diversidade de livros, deduplicação de excertos, cobertura e auditoria de integridade da evidência.
- CLI `research-books`: consulta documental por várias questões, opcionalmente com Ollama embeddings.
- Casos de teste para limites, cobertura, perguntas sem evidência e adulteração de resultados.
- Pesquisa de componentes GitHub: Docling (MIT), FastEmbed (Apache-2.0), GraphRAG (MIT, manutenção). Integração integral não efetuada para evitar dependências e custos não validados.

## 4.8 — Natural Algebra Reasoning
- Gramática PT-PT limitada para sistemas lineares e matrizes explícitas.
- Cálculo com frações exatas e apresentação de matriz reduzida.
- Rejeição de expressões não lineares e sintaxe desconhecida; sem execução de código.

## 4.9 — Identity Core
- Identidade de comunicação estável, modo persistente opt-in e proteção contra fontes não fidedignas.
- Integração com o prompt Ollama e comandos naturais.
- Testes de persistência, modo inválido e recuperação de ficheiro corrupto.

## 5.0 — Living Intelligence
- Memória autobiográfica apenas com consentimento explícito, objetivos persistentes e sugestões locais que exigem autorização para agir.
- Contexto de identidade adaptativo sem alterar os valores fundamentais.
- Migração idempotente dentro da base de dados existente e testes de controlo/retensão.
