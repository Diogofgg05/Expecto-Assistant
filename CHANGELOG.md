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
