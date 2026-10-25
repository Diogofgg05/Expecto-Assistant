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
