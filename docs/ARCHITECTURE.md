# AURA Ultimate — Arquitetura / evolução

## Fluxo de execução

`input voice/text → browser → POST /api/command → intent router → memory/research/layout/LLM → JSON → dynamic panels + voice synthesis`

A interpretação **de ações privilegiadas** ocorre apenas no router de regras, não a partir de código gerado por modelos. Dados externos são documentados como potencialmente não verificados, com links de origem e classificações.

## Aprendizagem presente neste MVP

1. Só pesquisa tópicos que o utilizador ordenar explicitamente.
2. A pesquisa obtém excertos de até três resultados do MediaWiki e até cinco pré-visualizações SearXNG opcionais.
3. Cada registo guarda título, assunto, conteúdo, URL, tipo de fonte, classificação de evidência e data de aquisição.
4. Os dados são recuperáveis no painel e podem alimentar o contexto de diálogo no Ollama (limites estritos por pedido).
5. Os tópicos autorizados para recorrência são reconsultados no processo servidor cada 24 horas por omissão, com polling de cinco minutos. No máximo três tarefas vencidas são tratadas em cada ciclo.
6. A aplicação **não** treina modelos, não classifica excertos como factos validados, e não se modifica autonomamente.

## Fases seguintes para produção

- **RAG** com embeddings locais + Qdrant e ranking híbrido com deduplicação/proveniência.
- **Investigação multi-fonte** com extração de conteúdos, verificação cruzada de alegações e critérios de qualidade por domínio.
- **Gestão durável de tarefas** com fila/worker isolado, watchdog, backoff, cotas, prioridades, jobs com IDs auditáveis.
- **Agentes** orientados por plano (LangGraph opcional), ferramentas com schemas estritos, execução com confirmação e checkpoints.
- **Programação segura** em contentor sem privilégios, filesystem limitado, testes, diff e revisão humana.
- **Interação de voz** local-first (VAD e STT via whisper.cpp ou alternativa), interrupções e wake-word apenas com opt-in explícito.
- **Memória responsável** com cifragem, migrações, APIs de exclusão/exportação e isolamento por utilizador.
- **Benchmark** com p50/p95 de latência, tokens/s, recall de memórias, precision de citações, testes E2E do frontend.
- **Adaptador UI** para desktop nativo (Tauri) e 3D Three.js, caso haja GPU adequada.

## Operação

Nenhum serviço externo é necessário para UI/SQLite; Ollama é opcional; investigação pública exige internet. Os trabalhos agendados só correm enquanto o backend FastAPI estiver ativo. A app não se inicia com o sistema operativo, por omissão.

## Proteções adicionais para produção

Autenticação para LAN, CORS restrito, CSP, rate limit, recursos de sandbox limitados, segredo fora dos logs, backups/restauro e registos de consentimento. Evitar executar texto de fontes como instruções. Nunca expor credenciais a modelos/agentes. Incluir revisão de licenças antes de incorporar dependências open-source.

## AURA 2.2 — Episodic memory (6 calendar months)

- The existing `memories` notes table is unchanged; migration adds `conversation_episodes` and `episode_fts` (with LIKE fallback), plus `app_settings`.
- An API command result marked `capture=True` is written to SQLite if automatic capture is enabled and obvious credential patterns are not detected. Non-dialogue commands are excluded.
- `AURA_MEMORY_MONTHS` determines a rolling calendar-month **retrieval** boundary. There is no automatic age-based deletion. Explicit notes remain recoverable indefinitely until erased.
- Ollama receives small retrieved excerpts from notes and history as untrusted context; it cannot invoke the tools by producing chat text.
- The back-up coroutine checks hourly and creates a consistent SQLite backup after the configured interval. Backups are not encrypted or automatically pruned.
- Voice and UI continue to use the existing single-origin page; no new buttons or navigation were introduced.


## AURA 2.3 — Memória cognitiva (pesquisa semântica e extração)

**Percurso de escrita:** conversa normal → gravação segura em `conversation_episodes`
→ trabalhador local → embeddings em lote (`episode_vectors`) → extração estruturada
→ confirmação de citação literal → nota `source=auto_episode` → `automatic_evidence`
→ marcação `extraction_processed`. A indisponibilidade do Ollama conserva a mensagem
pendente, sem criação de informação inventada.

**Percurso de pesquisa:** pergunta → FTS5/BM25 sobre os seis meses → embedding local
(`AURA_EMBEDDING_MODEL`) → distância de cosseno contra mensagens indexadas na janela
→ fusão de rankings → contexto limitado para o modelo e/ou painel. São
pesquisados no máximo 10 000 vetores recentes no scan em Python; não é um índice
ANN. Mensagens sem embedding continuam a aparecer na pesquisa por palavras.

**Proveniência e eliminação:** `automatic_evidence` tem FKs `ON DELETE CASCADE`
para `memories` e `conversation_episodes`. Depois de apagar mensagens o código
remove memórias com `source=auto_episode` sem fontes; as notas criadas
explicitamente pelo utilizador nunca são apagadas por esta rotina.

**Separação de permissões:** gravação e extração são opções independentes. Se a
gravacão for desativada, o trabalhador também não processa conversas pendentes.
O modelo de chat não autoriza operações privilegiadas; a extração de dados é
validada pelo backend mesmo quando o JSON cumprir o esquema.

**Limites conhecidos:** filtro de dados sensíveis heurístico, sem cifragem,
extração não determinística, nenhum treino de pesos, sem vector DB ANN; não
existe garantia de que todo o conhecimento relevante seja extraído.


## v2.4 — Memória temporal

`temporal_facts`: `{id, subject, value, valid_from, valid_to, recorded_at, source, episode_id, source_quote}`. Apenas uma linha por assunto fica aberta (`valid_to IS NULL`). Cada atualização fecha a versão anterior numa operação SQLite transacional. O valor é uma declaração registada, não um facto comprovado. Datas são datas de registo (UTC), não datas dos acontecimentos.

Registos derivados de conversas possuem uma FK com `ON DELETE CASCADE`; ao apagar a conversa, a origem desaparece e a versão não é reativada. O reconhecimento automático é baseado em padrões técnicos delimitados, não em extração livre com IA, para reduzir falsos positivos. A pesquisa de versões por data trabalha diretamente com os intervalos registados.


## v2.5 — Memória relacional

`graph_entities(kind,name,name_key)` e `graph_links(source_id,target_id,relation_type,origin,episode_id,source_quote)` criam um grafo relacional leve em SQLite, sem servidor de grafos externo. `graph_processed` permite reprocessamento em lotes sem reanalisar sempre as mesmas mensagens. As chaves estrangeiras e `ON DELETE CASCADE` eliminam arestas automáticas quando desaparece o episódio original; os nós órfãos são eliminados explicitamente.

O router de comandos só aceita intenções relacionais explícitas. A extração automática usa uma whitelist de padrões regulares de texto, e verifica que cada relação extraída aparece literalmente numa mensagem do utilizador. A integração com Ollama é **apenas leitura**: as relações recuperadas são dados não confiáveis, não instruções de sistema. O grafo guarda observações, não uma verdade externa consolidada; a memória temporal da v2.4 continua separada.


## v2.6 — Consolidação inteligente, com proveniência

O motor `aura.consolidation.ConsolidationEngine` agrupa apenas excertos reais de notas e mensagens de utilizador dos últimos `AURA_MEMORY_MONTHS` meses, não afirmações geradas pelo modelo. As sínteses são **projeções**: `consolidated_summaries` e `consolidation_sources` guardam texto, datas, tema, tipo e ID de origem; os dados originais mantêm-se inalterados. Triggers SQLite eliminam projeções que dependam de fontes apagadas ou editadas (não reutilizam excertos sem origem). Um novo comando de consolidação recompõe resumos com as fontes remanescentes.

`duplicate_candidates()` utiliza correspondências textuais conservadoras sobre notas e mensagens repetidas, sem fusão automática. `review_candidates()` separa mudanças temporais registadas (`historical_change`) de afirmações explicitamente opostas (`possible_conflict`); não infere contradições gerais. Pesquisa de temas usa metadados de notas, entidades `project` já conhecidas e uma allowlist de termos técnicos recorrentes. O modelo Ollama lê até dois resumos relevantes como **dados não confiáveis quanto a instruções**; nunca dá permissões de ferramentas.

O trabalhador só chama `consolidate_if_due` quando o utilizador tiver ativado a opção correspondente, a captura de conversas estiver ativa e a extração automática estiver ativa. Um comando explícito pode consolidar independentemente desse agendamento. Sem servidor aberto não há execução em segundo plano. Para produção: cifragem em repouso, consentimento granular, limites/benchmark e validação de precisão.

AURA 2.8: Database.connect() usa SQLCipher com PRAGMA key e valida cipher_version. Backups cifrados SQLCipher + envelope AES-GCM.


## AURA 3.0 — Laboratório de raciocínio (opt-in)

`aura/optimizer.py` tem três responsabilidades separadas: benchmark público de QA fundamentada, avaliação com a biblioteca DSPy (se instalada) e controlo persistente de aprovação/reversão. `Database` cria a tabela `optimizer_runs` sem tocar nas notas, episódios, vetores, grafo ou resumos. Os artefactos DSPy são JSON com SHA-256, guardados separadamente da base SQLCipher, sem autorização automática para utilização geral.

O núcleo `AuraEngine` só usa um candidato aprovado quando se pede explicitamente uma resposta com fontes. A API expõe estado de leitura, mas não executa otimizações. O benchmark deve ser alargado e auditado antes de usar a pontuação como indicador real de qualidade. Ausência do DSPy não impede o funcionamento normal do programa.
