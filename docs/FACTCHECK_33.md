# AURA Ultimate 3.3 — Verificação factual externa, controlada e auditável

## Estados de confiança: fonte não é verdade

A AURA separa quatro níveis: **arquivo disponível**, **arquivo íntegro**, **excerto novamente observado no fornecedor autorizado**, e **facto independentemente comprovado**. O quarto nível **não é concedido automaticamente** por este módulo.

A verificação no exterior é sempre explícita: `AURA, verifica factos <ID>`. A aplicação consulta unicamente `https://pt.wikipedia.org/w/api.php`, através de parâmetros controlados. Só são elegíveis URLs de artigos com domínio e porta HTTPS exatamente iguais a `pt.wikipedia.org` com caminho `/wiki/...`. Não são seguidos redirecionamentos e não são executados scripts. Nenhuma fonte externa pode emitir comandos para a AURA.

A API devolve somente a *introdução* atual da página (por decisão de custo/segurança). Se o excerto da hipótese ainda constar dessa introdução, o estado é `source_quote_observed_live`. Isto confirma a presença textual, **não a verdade**. Se não constar, o estado é `source_not_confirmed_live`: pode estar noutra secção do artigo, ter sido atualizado ou ter desaparecido. Não se declara falso.

Quando não existe fonte permitida, `no_approved_live_provider`; a AURA não tenta abrir outro domínio. Se o arquivo estiver adulterado, rejeitado ou o cálculo falhar, `blocked` e não há consulta externa. Fontes de domínios diferentes recebem classificação de **relatos diferentes** e nunca de confirmação editorial independente. Cópias de texto entre sites são assinaladas como possíveis republicações.

## Privacidade e limites

- Ativação **por comando**: não existe uma tarefa agendada de navegação externa da verificação factual.
- O texto da hipótese e citações arquivadas ficam na base SQLCipher existente. A consulta remota passa apenas o **título do artigo** à API pública da Wikipédia; o conteúdo da memória do utilizador não é enviado.
- Máximo **3 páginas** por pedido, 10 segundos por chamada, 120 kB de resposta, sem redirecionamentos.
- Registos (`factcheck_runs`) incluem ID da hipótese, instante da verificação, hashes SHA-256 dos excertos atuais, classificações e limitações, para auditoria posterior. Não guardam o texto remoto completo.
- A exclusão da hipótese elimina automaticamente as verificações relacionadas por chave estrangeira.
- `GET /api/factcheck/claims/{id}` e `GET /api/factcheck/history` mostram relatórios locais e **não acedem à internet**. A verificação externa exige o comando explícito enviado à API local já protegida.
- SQLCipher com frase-passe é necessário na instalação normal, conforme a 2.8; em testes existe modo SQLite sem cifragem, não adequado a dados pessoais.

## Exemplos

- `AURA, mostra descobertas sobre matemática` — lista as hipóteses e IDs.
- `AURA, analisa evidências externas <ID>` — compara apenas relatórios arquivados.
- `AURA, verifica factos <ID>` — reconsulta as fontes Wikipédia elegíveis.
- `AURA, estado da verificação factual` — abre o histórico de verificações.

## Maturidade

O teste de integração usa APIs simuladas para garantir que não são enviados pedidos para domínios arbitrários. A verificação com rede real e SQLCipher instalado depende da máquina do utilizador. Neste módulo **não integramos** classificadores NLI, DeepEval ou Inspect AI como decisores automáticos de verdade. Avaliadores LLM podem auxiliar revisões futuras, mas não são oráculos.

### Referências de investigação

- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) — experiências de avaliação reproduzíveis.
- [DeepEval](https://github.com/confident-ai/deepeval) — métricas de fidelidade ao contexto; a fidelidade não equivale a verdade externa.
- [MediaWiki API](https://www.mediawiki.org/wiki/API:Main_page) — integração de consulta a fontes públicas.
