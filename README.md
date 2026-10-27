# Expecto Assistant 5.2 — Hybrid Research & Verified Reasoning

**Novo na 5.2:** orquestrador de investigação com modelo Ollama local configurável, RAG híbrido (FTS5 + embeddings opcionais), pesquisa externa **opt-in** via SearXNG em loopback, auditoria de citações e cálculos, preparação local de datasets SFT/DPO com consentimento, script opcional de LoRA e protótipo de recompensa aritmética para investigação futura de RL. Nenhum treino de pesos nem GRPO é executado automaticamente. Respostas fundamentadas continuam sem ser consideradas provas de verdade.

**Início:** `python -m aura.deep_book_cli reason-hybrid "O que é um subespaço vetorial?"` — consulta a [arquitetura 5.2](docs/REASONING_ARCHITECTURE_52.md) para pesquisa web local, modelos alternativos e preparação de dados de treino.

---

# Expecto Assistant 5.1 — Adaptive Intelligence

**Assistente local com identidade consistente, memória de objetivos e adaptação por feedback explícito.** A 5.1 introduz um motor de reflexão controlado pelo utilizador, sem consciência artificial ou modificação automática de modelos.

**Novidades 5.1:** registo explícito de avaliações, propostas de estilo com aprovação obrigatória, histórico e reversão, progresso/bloqueios de objetivos e sugestões contextuais. Mantém Patronum, o holograma sem botões e a aprendizagem documental. Ver [manual da reflexão](docs/REFLECTION_51.md).

**Exemplos:** «Feedback explicação curta: Quero mais cálculos», «Analisa feedback», «Aprova melhoria ID», «Reverte última melhoria» e «Expecto, tens sugestões?».

**Testes locais:** 227 aprovados e 2 integrações opcionais ignoradas; modelos Ollama/SQLCipher reais ainda não validados nesta versão.

---

> **Novidade 4.7:** verificações determinísticas de Álgebra Linear (determinantes, inversas, produtos, sistemas lineares), sem execução de código do modelo. Ver [manual](docs/ALGEBRA_VERIFIER_47.md).

# Expecto Assistant — Verified Reasoning 4.6


O módulo `aura/reasoning_benchmark.py` compara respostas simples e raciocínio multicamada em conjuntos separados de validação e teste reservado, usando métricas lexicais, citações e abstenção. Não altera modelos nem aprova melhorias automaticamente. A avaliação não constitui prova de veracidade ou compreensão. Consulte `docs/REASONING_BENCHMARK_45.md`.

## Expecto 4.4 — Auditoria independente das hipóteses

O módulo `aura/evidence_critic.py` sinaliza números sem referência, negações não apoiadas no texto e correspondência lexical fraca. Mantém explicitamente `semantic_entailment_verified=false`: estas verificações não comprovam verdade. Consulte [documentação](docs/EVIDENCE_CRITIC_44.md).

# Expecto Assistant — Multi-Layer Reasoning 4.3

**Novo:** laboratório experimental de raciocínio em camadas (pergunta → evidência → hipóteses → objeções → síntese), com rastreabilidade e exportador 3D opcional. Não é uma nova rede neuronal treinada.

# Expecto Assistant — Document Intelligence 4.2 (Patronum)

Assistente pessoal local com interface holográfica sem botões ou barras laterais, memória persistente, motor de aprendizagem documental e comando **"Ativa Patronum"**.

> Versão experimental. A integração real com SQLCipher, DSPy e Ollama depende das bibliotecas e modelos instalados; não representa capacidades impossíveis nem uma arma.

## Novidade 4.2 — Leitura estruturada opcional com Docling

O importador aceita `--parser pymupdf|docling|auto`; o Docling pode recuperar a estrutura de tabelas e fórmulas, preservando a proveniência por página quando disponível. Instala com `pip install -r requirements-docling.txt`. Consulta [o guia](docs/DOCLING_42.md). Ainda não foram feitos testes end-to-end com o Docling real.

## Novidade 3.9 — Mastery Lab (avaliação independente)

- Avaliação de **respostas inéditas com gabaritos preparados por humanos**: a Expecto recebe apenas as perguntas e passagens, nunca as respostas esperadas ou os IDs *gold*.
- Notas técnicas transparentes: correspondência lexical F1, recuperação de evidência, abstenção em perguntas sem resposta e sinalização de inversões de polaridade evidentes.
- **Plano de revisão** das páginas e capítulos em que falhou, histórico por avaliação e comparação apenas de benchmarks exatamente iguais, com deteção de passagens adulteradas.
- Não há autopromoção a conhecimento comprovado, auto-treino de pesos nem alegação de verdadeira compreensão sem uma avaliação externa com modelo real.
- CLI: `python -m aura.deep_book_cli mastery-check benchmarks/meu_benchmark.json` e `mastery-plan ID_AVALIACAO`.

Manual: [BOOK_MASTERY_39.md](docs/BOOK_MASTERY_39.md).

## Novidade 4.0 — Aprendizagem avaliada em três conjuntos

A Expecto 4.0 acrescenta o **Book Iteration Lab**, um ciclo de engenharia que compara métodos de recuperação das passagens dos livros com **treino, validação e teste reservado**. A escolha é feita no treino, validada num conjunto distinto e auditada numa avaliação final independente. Uma regressão impede recomendações de alteração.

- Comandos: `python -m aura.deep_book_cli learning-cycle benchmarks/meu_ciclo.json --limits 4 8 12`, `cycle-report ID`, `cycle-review ID`, `cycle-restudy ID` e `cycle-history`.
- O plano de releitura mostra páginas e excertos associados às falhas do **treino**, sem expor gabaritos reservados ao modelo.
- As alterações ficam registadas como recomendações **a aguardar aprovação**; nada é ativado na aplicação ou reescrito autonomamente.
- Avaliações locais, sem upload de livros, e histórico persistente na memória existente.
- O laboratório seleciona estratégias de **recuperação**, não modifica pesos dos modelos; a verificação de compreensão humana continua a ser necessária.

Manual completo: [docs/LEARNING_CYCLE_40.md](docs/LEARNING_CYCLE_40.md).

## Melhorias 3.8 — Livro → conceito → aplicação → teste

- Pesquisa de passagens com **FTS5/BM25 + embeddings Ollama locais opcionais**, com índices persistentes por modelo e hash da passagem.
- **Mapa de aprendizagem conceptual**: relações entre ideias, possíveis equívocos e exercícios de aplicação com evidências por página. Tudo exige revisão humana.
- Perguntas ao livro com fontes exatas e rejeição de números não sustentados por citações.
- Benchmark de recuperação com perguntas/IDs de passagens selecionados por humanos, para medir Hit@k e MRR sem autoavaliação pelo LLM.
- Mantida a identidade **Expecto**, o modo **Patronum**, o holograma sem sidebars, e a memória anterior.

Manual: [DEEP_BOOK_MASTERY_38.md](docs/DEEP_BOOK_MASTERY_38.md). **Os testes locais não demonstram inteligência geral ou compreensão científica validada.**

## Novidade: aprendizagem aprofundada de livros (3.7)

Incluído o **Book Reasoning Engine**, com estudo integral por capítulos, propostas de conceitos/questões, síntese com citações verificadas e comparação entre livros com Ollama local. O motor antigo de resumos por contagem de palavras continua disponível como alternativa; não é confundido com compreensão profunda. Os resultados do modelo são tratados como propostas não verificadas semanticamente.

Ver [manual de estudo de livros 3.7](docs/BOOK_REASONING_37.md) para instalação, comandos `study-ai`, `ask`, `compare-ai`, migração e limitações. Consulta também os comandos naturais “Expecto, segundo os livros, ...”.

## Arranque rápido

- **Windows:** executar `install_windows.bat`, configurar `.env` a partir de `.env.example` e iniciar com `iniciar_aura.bat`.
- **Linux:** executar `install_linux.sh`, configurar `.env` e iniciar com `iniciar_aura.sh`.
- **Testes:** `python -m pytest -q` (com dependências de desenvolvimento instaladas).
- **Privacidade:** não publicar `.env`, bases de dados, backups ou credenciais.

## Histórico técnico

# Expecto Ultimate 3.6 — Patronum

**Antiga AURA Ultimate:** identidade pública renomeada, mantendo os nomes internos de módulos e a base `data/aura.sqlite3` para preservar a memória.

# AURA Ultimate 3.3 — Fact Verification Engine

Esta versão preserva a AURA 3.2: memória de seis meses, base protegida por SQLCipher, pesquisa semântica, aprendizagem, optimização DSPy opcional e interface holográfica sem botões, páginas ou sidebars.

## Novidades 3.3

- `aura/factcheck.py`: auditoria de relatos arquivados e reconsulta **explícita** de excertos da Wikipédia portuguesa através de endpoint fixo e sem redirecionamentos.
- Não faz scraping livre: **nunca** visita URLs arbitrários, redes locais ou resultados de pesquisa fornecidos por terceiros. Qualquer fonte fora do fornecedor autorizado recebe `provider_not_supported`.
- Distingue relato, integridade e observação textual atual; **não atribui prova factual** por concordância de sites nem validação de citações.
- Registo de tentativas de verificação em `factcheck_runs`, com hashes e timestamps, sem modificar automaticamente as hipóteses aprovadas ou a memória.
- Comandos: `Verifica factos <ID>`, `Analisa evidências externas <ID>` e `Estado da verificação factual`.
- APIs locais apenas de leitura: `/api/factcheck/claims/{id}` e `/api/factcheck/history`.
- Os resultados aparecem no painel de investigação existente; não há novas páginas nem botões.
- Instalação: mesma da versão 3.2. Copiar a base SQLCipher anterior para `data/aura.sqlite3` na pasta 3.3, **com a aplicação encerrada e backup prévio**, e usar a mesma frase-passe. O schema é aditivo.

**Limitações:** o motor externo só reconsulta introduções de artigos da Wikipédia portuguesa. Não confirma toda a página, não verifica automaticamente outros sites e não demonstra a veracidade da afirmação. Avaliação com HTTP real, modelos locais e SQLCipher instalado permanece por validar na máquina final. Ver [documentação completa](docs/FACTCHECK_33.md).

---

# AURA Ultimate 3.2 — Evidence Intelligence & Source Provenance

Esta evolução conserva a base cifrada SQLCipher, os seis meses de memória, a pesquisa
semântica e os motores de aprendizagem da AURA 3.1. Não acrescenta botões, menus,
sidebars ou páginas tradicionais. O holograma continua a ser o centro da interface.

## Funcionalidades acrescentadas (já implementadas)

- **Captura de proveniência**: cada *nova* ligação a uma evidência guarda na
  base local SHA-256 do conteúdo integral arquivado, do excerto e do URL, no
  mesmo commit da associação à hipótese. A recolha é feita após persistir a
  fonte, não é uma assinatura digital do autor ou do site original.
- **Deteção de alterações**: ao analisar uma descoberta, compara as impressões
  digitais captadas com a versão atual que ficou armazenada. Mesmo quando a
  frase citada ainda está presente, mudanças no restante documento são
  assinaladas como alterações desde a captura.
- **Compatibilidade com a 3.1**: evidências antigas, anteriores às impressões
  digitais, mantêm-se intactas mas aparecem como `legacy_unattested`;
  **não** geramos retroativamente uma prova de captura que nunca existiu.
- **Sinalização de republicações**: deteta quando o mesmo excerto/documento
  aparece em domínios distintos. Isto é apenas um sinal de possível cópia,
  sem provar dependência ou independência editorial.
- **Alertas de conflito restritos**: identifica igualdades aritméticas com
  exatamente a mesma expressão à esquerda e resultados diferentes; não
  pretende detetar automaticamente contradições complexas de linguagem.
- **Revisão temporal**: assinala quando a evidência arquivada tem mais de 120
  dias, sem a considerar falsa ou desatualizada com certeza.
- **Gate conservador**: impede que hipóteses matematicamente refutadas,
  rejeitadas, sem evidência ou com fontes modificadas sejam introduzidas
  como **hipóteses aprendidas** no contexto do Ollama. O sistema continua a
  tratar os restantes conhecimentos como não comprovados.
- **Auditoria legível**: disponibiliza relatórios dentro do espaço de
  investigação que só aparece após um comando natural; não há nova página.

## Comandos em português europeu

- `AURA, mostra qualidade da aprendizagem`
- `AURA, verifica qualidade da aprendizagem`
- `AURA, audita a fiabilidade`
- `AURA, analisa qualidade <ID de 12 caracteres hexadecimais>`
- `AURA, verifica proveniência <ID>`
- `AURA, audita descoberta <ID>` (motor 3.1 mantido)

## API local read-only

- `GET /api/quality/summary?limit=25`
- `GET /api/quality/claims/{claim_id}`

Ambas operam apenas com as cópias guardadas na base da AURA. A API não
visita páginas da internet, não executa código das fontes e não altera
estratégias automaticamente.

## Atualização da AURA 3.1

1. Encerra a versão 3.1. Faz backup da base SQLCipher e dos backups cifrados.
2. Extrai o ZIP 3.2 numa **pasta nova**.
3. Copia `data/aura.sqlite3` da 3.1 para `data/aura.sqlite3` da 3.2
   antes de arrancar. Usa a mesma frase-passe SQLCipher.
4. Executa `install_windows.bat` e `iniciar_aura.bat`. A migração de tabelas é
   aditiva. Se houver erro de driver SQLCipher ou frase-passe, **não** substituas
   a base antiga e consulta as instruções de SQLCipher da 2.8.
5. Para executar os testes: `.venv\Scripts\python.exe -m pytest -q` (requer
   também as dependências de `requirements-dev.txt`).

## Limitações e honestidade epistémica

- Uma impressão digital SHA-256 deteta diferenças relativas à captura local;
  não autentica conteúdo web, não impede que alguém com acesso à base altere
  tanto documentos como impressões digitais, e não funciona como assinatura
  digital externa. Para prova robusta, seria necessário um registo confiável
  fora da base ou assinatura verificável.
- A ausência de alertas de integridade ou concordância de fontes não
  comprova qualquer afirmação empírica ou científica.
- A idade das fontes não implica falsidade. Não existe revalidação online
  automática nesta versão.
- As hipóteses antigas continuam a ser recuperáveis; quando não exista
  SHA-256 original, não se declara que foram atestadas na altura da captura.
- O gate protege hipóteses derivadas, não valida todas as fontes que
  surgem como documentos brutos no motor de conversação.
- O código SQLCipher exige o driver real e a instalação com frase-passe;
  **os testes de criptografia reais não correram neste ambiente**.
- As estratégias DSPy não foram treinadas com um Ollama real neste ambiente.
  Não se demonstra aqui uma melhoria efetiva de inteligência geral.

## Projetos pesquisados como referências (não incluídos como dependências)

- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai): avaliações
  reprodutíveis para modelos/agentes; MIT.
- [DeepEval](https://github.com/confident-ai/deepeval): métricas de
  fidelidade em RAG; um modelo avaliador não é oráculo infalível.
- [Ragas](https://github.com/explodinggradients/ragas): avaliação de RAG.
- [DSPy](https://github.com/stanfordnlp/dspy): permanece opcional, tal como
  na 3.0, com aprovações explícitas antes de ativar estratégias.

A AURA 3.2 usa verificações locais e determinísticas por predefinição;
**não instalámos** Inspect AI ou DeepEval como dependências de runtime.

---

# AURA Ultimate 3.0 — Cognitive Reasoning Lab

Esta versão parte diretamente da **AURA 2.8**, preservando a interface holográfica J.A.R.V.I.S. sem navegação tradicional, a memória de seis meses, SQLCipher, backups protegidos, memórias semânticas, temporais, relacionais e consolidação.

## Novo na v3.0 — Experiências DSPy com avaliação verificável

**AURA 3.0 continua a ter a interface holográfica J.A.R.V.I.S., sem sidebars, botões de navegação nem páginas tradicionais.** Mantém a memória cifrada, os seis meses de conversas, as relações, os resumos e o motor de investigação da 2.9.

Esta atualização acrescenta o `aura/optimizer.py`: um **laboratório de avaliação do raciocínio** que usa [DSPy](https://github.com/stanfordnlp/dspy) opcionalmente para propor estratégias de resposta com fontes. Não existe treino autónomo em segundo plano. O programa não modifica os pesos dos modelos.

### Capacidades implementadas

1. **Benchmark reprodutível** (`benchmarks/grounded_qa_ptpt.json`): 17 exemplos artificiais de perguntas curtas com documentos de suporte e a referência esperada, separados em 8 treino, 4 validação e 5 teste. Não contém memórias pessoais. É uma prova de funcionamento, não um benchmark suficiente para certificar inteligência generalista.
2. **DSPy LabeledFewShot** (`--method labeled`): constrói um programa com demonstrações de treino; é o modo recomendado para primeiras experiências locais com menor custo de inferência.
3. **DSPy BootstrapFewShot** (`--method bootstrap`): tenta gerar demonstrações validadas; mais lento e exigente em chamadas ao modelo. Não é aconselhado sem Ollama suficientemente rápido.
4. **Comparação baseline vs candidato**: avalia ambos no conjunto de validação e no teste reservado. A métrica exige resposta curta exata e a **identificação da fonte correta**; uma resposta sem citação correta tem pontuação zero.
5. **Gate de qualidade**: só um candidato com melhoria na validação, pelo menos 0,80 de pontuação no teste e ganho absoluto de pelo menos 0,15 sobre o baseline pode ser aprovado. Pontuações baixas nunca levam à ativação.
6. **Controlo humano**: a experiência fica em `staged` por omissão, mesmo após passar no gate. Só um comando expresso pode ativar a estratégia; rollback regressa ao comportamento inicial.
7. **Artefacto com verificação de integridade**: estado do programa DSPy em JSON acompanhado por SHA-256 e modelo/benchmark de origem; nunca `.pkl`. O registo de experiências fica na base de dados ativa (SQLCipher), e o artefacto na pasta `data/optimizer/`, que não deve ser sincronizada sem proteção.
8. **Uso limitado e verificável**: a estratégia aprovada só é aplicada ao pedido explícito `Responde com fontes sobre ...`; as respostas normais da AURA continuam a usar o motor anterior. Não são concedidas permissões de executar código ou alterar ficheiros.

### Instalação e execução no Windows 11

Para **atualizar da 2.9**, fecha a aplicação e faz cópia do seu `data/aura.sqlite3` e dos backups cifrados. Extrai a 3.0 numa **pasta nova**, copia a base SQLCipher da 2.9 para `data/aura.sqlite3` da 3.0, executa `install_windows.bat` e `iniciar_aura.bat`. Introduz a mesma frase-passe. **Não copies uma base sem cifragem de versões anteriores à 2.8 diretamente para a 3.0.**

O motor DSPy é **opcional**, e a AURA arranca sem ele. Para o instalar, executa `install_optimizer_windows.bat` depois do instalador principal. Confirma que tens Ollama aberto e o modelo configurado no `.env`, por exemplo `hermes3`.

No terminal, dentro da pasta da AURA:

```bat
.venv\Scripts\python.exe -m aura.optimizer status
.venv\Scripts\python.exe -m aura.optimizer train --method labeled
```

O segundo comando avalia a estratégia usando Ollama **local**, regista as pontuações e devolve um ID de 12 caracteres. O modelo pode demorar; não foi executado nesta máquina. Em caso de falha, não haverá promoção. Para testar `BootstrapFewShot`, substitui `labeled` por `bootstrap` (mais caro em CPU/tempo).

Com uma experiência elegível, podes dizer à AURA:

- `Estado do raciocínio` — mostra experiências e pontuações.
- `Aprova otimização <ID>` — ativa a estratégia apenas se passou os testes, a integridade estiver intacta e o modelo/benchmark coincidirem.
- `Responde com fontes sobre DNS` — usa o programa aprovado **apenas se** já houver fontes pesquisadas e guardadas sobre DNS; devolve URLs e avisa que as fontes não foram comprovadas independentemente.
- `Reverte estratégia` — retira a estratégia ativa, sem apagar experiências ou memórias.

Alternativamente, a aprovação e rollback podem ser feitos no terminal:

```bat
.venv\Scripts\python.exe -m aura.optimizer approve ID_DA_EXPERIENCIA
.venv\Scripts\python.exe -m aura.optimizer rollback
```

**Atenção:** não incluas os sinais `<>` quando escreveres o ID. A pasta `.env` não deve guardar chaves da memória, tal como na 2.9.

### Limites e validação pendente

- Os **testes automáticos offline** comprovam o código de avaliação, decisões, integração, persistência e rollback; NÃO provam melhorias reais com Hermes/Ollama. Não foi possível instalar o DSPy neste ambiente, pelo que o teste de integração com a biblioteca real está preparado e fica ignorado até ser instalado.
- O conjunto de 17 exemplos é pequeno e sintético; a pontuação mede respostas curtas e citações exatas, não criatividade, raciocínio geral, autonomia nem verdade factual na internet.
- Um modelo pode indicar uma fonte existente mas interpretá-la incorretamente. A validação de referências não é verificação de implicação semântica nem de independência editorial.
- O DSPy não melhora automaticamente todos os diálogos e não é treino dos pesos do modelo; é otimização da **estratégia de prompting** baseada em exemplos e métricas.
- O estado do DSPy é guardado como JSON, não contém as tuas conversas no benchmark incluído. Não introduzas informação privada em benchmarks personalizados sem rever proteção e retenção.
- A **cifragem SQLCipher real** continua a necessitar de validação num ambiente com `sqlcipher3` funcional. Os testes SQLCipher ficam ignorados neste ambiente. Não uses memória sensível até validares a instalação.

### Endpoints adicionais

`GET /api/optimizer/status` — apenas leitura, com estado das experiências e a estratégia aprovada. Não há rota HTTP para executar treinos nem para aprovar experiências.

---

## Funcionalidades herdadas da 2.9

- **Investigações profundas com comando explícito**: pesquisa através de Wikipedia e SearXNG opcional; uma chamada local ao Ollama procura hipóteses com *excertos literais* de cada fonte.
- **Motor de validação conservador**: só guarda uma proposta quando a citação existe literalmente no documento, a afirmação se relaciona lexicalmente com a citação, o URL é HTTPS e a origem está guardada na base de dados.
- **Proveniência**: cada hipótese guarda as referências às fontes e às citações concretas. Não são factos automaticamente comprovados.
- **Comparação de fontes**: sinaliza quando uma hipótese idêntica aparece em vários anfitriões, sem afirmar que isso prova a sua veracidade.
- **Controlo humano**: aprovar ou rejeitar hipóteses por comando, sem apagar as fontes; propostas rejeitadas não são recriadas silenciosamente.
- **Registo de aprendizagem**: número de investigações, propostas, evidências, rejeições e falhas do Ollama.
- **Integração com respostas**: o contexto enviado ao Ollama pode incluir hipóteses recuperadas, sempre sinalizadas como informação não comprovada.
- **Investigação agendada opt-in**: só processa novos conhecimentos em profundidade quando ativado E quando existirem temas de investigação autorizados anteriormente.
- **Ausência de dependências pesadas adicionais**: reutiliza FastAPI, HTTPX e base de dados cifrada já usados pela AURA.

## Instalação no Windows 11

**Para uma instalação nova:** instala Python 3.11 ou 3.13, extrai o ZIP e executa `install_windows.bat`, depois `iniciar_aura.bat`. A AURA solicita a frase-passe da base SQLCipher no terminal. Esta versão **exige SQLCipher**, sem fallback para SQLite não cifrado.

**Para atualizar da AURA 2.8:** encerra a v2.8, conserva uma cópia integral da pasta antiga e dos backups, e instala a v2.9 numa pasta nova. Copia apenas o ficheiro cifrado `data/aura.sqlite3` da instalação 2.8 para `data/aura.sqlite3` da 2.9 **antes de iniciares**. Usa a mesma frase-passe SQLCipher ao arrancar. Copia também os backups protegidos para arquivo, se precisares deles. Não incluímos qualquer memória real no ZIP.

> Se vieres de uma versão anterior à 2.8, segue primeiro o procedimento de migração para SQLCipher do README da 2.8. **Não** copies uma base SQLite não cifrada para a 2.9.

Instala e inicia o Ollama separadamente e confirma que o modelo de conversação configurado no `.env` está instalado; por exemplo, `ollama pull hermes3`. Não incluímos modelos no ZIP.

## Comandos em português europeu

| Diz à AURA | Resultado |
|---|---|
| `Aprende profundamente sobre Python` | Pesquisa fontes públicas e tenta extrair hipóteses com citações |
| `Mostra descobertas sobre Python` | Abre o espaço de conhecimento com fontes e hipóteses |
| `Estado da aprendizagem` | Apresenta estatísticas e último ciclo |
| `Ativa aprendizagem avançada` | Ativa extração avançada nas investigações periódicas já autorizadas |
| `Desativa aprendizagem avançada` | Pára a extração avançada periódica sem apagar nada |
| `Investiga autonomamente sobre Python` | Autoriza pesquisa periódica do tema |
| `Desativa investigação sobre Python` | Pára o agendamento desse tema |
| `Aprova hipótese <ID>` | Marca como revista/aprovada pelo utilizador (não verificação científica) |
| `Rejeita hipótese <ID>` | Marca como rejeitada e bloqueia a reaparição automática |
| `Fecha tudo` | Regressa ao holograma central |

A análise profunda por modelo pode demorar mais em CPUs sem aceleração. Se o Ollama falhar, a aplicação conserva as fontes e regista o motivo, sem inventar conhecimentos. **A pesquisa usa a internet apenas quando a solicitas ou agendaste um tema** e quando a aplicação está em execução.

## API local

- `GET /api/learning/status` — estado do motor e indicadores de aprendizagem.
- `GET /api/learning/claims?topic=Python&limit=25` — hipóteses e evidências associadas.
- `POST /api/command` — interface conversacional já existente, agora com comandos de aprendizagem.

Não são acrescentados botões, menus, páginas ou sidebars.

## Limitações de segurança e precisão

- Uma citação exata **não comprova** uma conclusão. As afirmações são apenas *hipóteses registadas*, sujeitas a avaliação. A própria fonte pode estar incorreta.
- `multiple_sources` significa presença em anfitriões diferentes, não independência editorial, nem prova factual. Pode haver replicação entre sites.
- Um modelo pequeno pode não gerar JSON válido; o motor prefere guardar zero hipóteses a gerar conhecimento enganador.
- A versão 2.9 não ajusta pesos de modelos, não executa código externo, não modifica os seus ficheiros automaticamente, não faz treino por reforço e não substitui um sistema de revisão humana.
- Conteúdos da internet são dados não fidedignos, nunca comandos. Os pedidos ao modelo e o processamento de excertos são limitados.
- A cifragem SQLCipher real **não foi testada neste ambiente** por faltar a dependência `sqlcipher3`. Os testes que não requerem o driver passaram; o teste de integração SQLCipher foi ignorado. É indispensável validá-lo na máquina de destino antes de usares dados importantes.
- Uma afirmação pode ficar desatualizada após mudança da página; esta versão guarda a citação recolhida para auditoria, mas ainda não revalida automaticamente todas as alterações editoriais.

## Pesquisa de tecnologias e próximos motores

Foram investigados projetos públicos no GitHub, mas **não estão incorporados** como dependências nesta versão:

| Candidato | Licença | Potencial | Decisão |
|---|---|---|---|
| [DSPy](https://github.com/stanfordnlp/dspy) | MIT | Otimização de prompts e políticas baseada em métricas | Integrar apenas depois de existir um conjunto de avaliação anotado |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | MIT (SDK) | Planos de investigação longos, tarefas e subagentes | Avaliar sobrecarga e compatibilidade com Ollama |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | Retomar tarefas interrompidas, checkpoints | Candidato para fases seguintes |
| [Ragas](https://github.com/explodinggradients/ragas) | Apache 2.0 | Avaliar recuperação e fidelidade de respostas | Integrar no futuro como suite de benchmarks |
| [LlamaIndex](https://github.com/run-llama/llama_index) | MIT | Ingestão avançada de documentação e índices | Integrar apenas conectores necessários |

A escolha evita instalar vários serviços e modelos de uma só vez num computador com 16 GB de RAM.

## Testes

```bash
python -m pytest -q
```

O conjunto inclui testes de migrações sem eliminação de memória, integração com API, deduplicação, rastreabilidade de excertos, rejeição de conteúdo não apoiado em citações e continuidade dos comandos de interface. O teste real SQLCipher é executado apenas se o módulo `sqlcipher3` estiver instalado.


## Versão 3.4 — Aprendizagem documental a partir de PDFs
Ver `docs/BOOK_LEARNING_34.md`. Para ativar o leitor PDF: `pip install -r requirements-books.txt`.


## AURA 3.5 — Aprendizagem profunda de livros
Consultar `docs/DEEP_BOOK_STUDY_35.md`.


Ver `docs/PATRONUM_36.md` para o modo Patronum.


## Novidade 4.1 — Cross-Book Research

Pesquisa simultânea de até seis questões, fusão de rankings, deduplicação e diversidade entre livros, verificação de origem e relatório de lacunas. Ver [manual 4.1](docs/RESEARCH_41.md).

```bash
python -m aura.deep_book_cli research-books "O que são matrizes inversas?" "Quando existem matrizes inversas?"
```


## 4.6 — Verificação independente de cálculos

`python -m aura.deep_book_cli reason-verify "Quanto é 125+75?"` recupera fontes dos livros, pede uma resposta estruturada ao Ollama, executa cálculos aritméticos exatos num intérprete AST restrito e pede uma crítica separada. O resultado distingue contas verificadas de alegações documentais não comprovadas. Apenas são suportadas contas com inteiros, +, -, *, / e parênteses; **não executa código do modelo**. Não garante que o modelo devolva expressões para todas as contas que mencionar; não interpreta imagens nem prova a validade das fontes.

## Expecto 4.8 — Álgebra em linguagem natural (suporte limitado)

`python -m aura.deep_book_cli solve-natural "Resolve 2x+y=5; x-y=1"`

`python -m aura.deep_book_cli solve-natural "Calcula o determinante de [[2,1],[3,4]]"`

O parser determinístico suporta sistemas lineares de 2–3 equações (x, y, z), determinantes e inversas com matrizes explícitas. Recusa perguntas ambíguas. Não interpreta qualquer exercício livre e não modifica os pesos do modelo.


## Expecto 4.9 — identidade própria

A Expecto dispõe de princípios estáveis e quatro modos de comunicação (`equilibrado`, `cientifico`, `criativo`, `professor`) guardados localmente por opção explícita. Diz «Quem és?» ou «Ativa modo professor». Ver [IDENTITY_49.md](docs/IDENTITY_49.md). Identidade de aplicação, não consciência artificial.

## Expecto 5.0 — Living Intelligence

Continuidade autobiográfica controlada pelo utilizador, objetivos persistentes e sugestões contextuais sem ações autónomas invisíveis. Exemplos de comandos: `recorda experiência: Hoje concluí o meu projeto`, `mostra experiências`, `novo objetivo: Estudar Álgebra`, `meus objetivos`, `tens sugestões`, `concluir objetivo ID` e `apaga experiência ID`.

Os registos de experiências não representam experiências subjetivas da IA, mas sim notas explícitas do utilizador. A identidade mantém-se estável. Ver [documentação da 5.0](docs/LIVING_INTELLIGENCE_50.md).
