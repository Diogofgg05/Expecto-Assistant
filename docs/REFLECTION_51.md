# Expecto 5.1 — Reflexão com feedback e continuidade de objetivos

## O que foi acrescentado

- **Feedback voluntário**, guardado em SQLCipher quando a base principal está cifrada, ou SQLite no modo de desenvolvimento.
- **Propostas determinísticas** de preferência de apresentação a partir de avaliações explícitas.
- **Aprovação/rejeição humana obrigatória** antes de qualquer alteração ao estilo de resposta.
- **Histórico e reversão** das adaptações, sem eliminar automaticamente as avaliações.
- **Registo explícito de avanços e bloqueios** associados a objetivos; sugestões adequam-se ao último estado declarado.
- **Classificação de sugestões** ligadas a objetivos existentes; apenas influencia a ordem, nunca inicia tarefas autonomamente.
- **Sem chamadas à internet, treino neuronal ou agentes adicionais** para gerar propostas. As avaliações ficam na base local existente.

## Comandos em português europeu

Diz/escreve, por exemplo:

```text
Feedback explicação curta: Preciso de mais exemplos.
Feedback explicação curta: Gostava de ver os cálculos.
Analisa feedback
Aprova melhoria <ID_DA_PROPOSTA>
Estado da reflexão
Reverte última melhoria
Apaga feedback <ID_DA_AVALIACAO>

Novo objetivo: Aprender Álgebra Linear
Meus objetivos
Bloqueio no objetivo <ID_DO_OBJETIVO>: Não consigo calcular uma inversa.
Avancei no objetivo <ID_DO_OBJETIVO>: Já consigo calcular determinantes.
Progresso do objetivo <ID_DO_OBJETIVO>
Apaga registo de progresso <ID_DO_REGISTO>
Expecto, tens sugestões?
Feedback sugestão útil <ID_DO_OBJETIVO>: Gostei desta ideia.
Feedback sugestão inútil <ID_DO_OBJETIVO>: Não ajuda no momento.
```

Também é possível dar feedback `explicação longa` ou `explicação boa`.

A proposta surge só depois de, pelo menos, duas avaliações **na mesma direção**, sem empate. A decisão só muda a dimensão `explanation_depth` (`balanced`, `concise` ou `detailed`). O modo científico/criativo/professor e a identidade estável não são modificados.

## Limitações importantes

Este módulo **não** lê emoções, não adivinha preferências, não treina pesos nem desenvolve vontade própria. É um mecanismo local, explicitamente controlado pelo utilizador, de adaptação da **apresentação** e de organização dos objetivos. Os testes usam SQLite temporário e modelos simulados. É necessário testar Ollama e SQLCipher reais na instalação de destino.

As notas de feedback nunca são concatenadas nas instruções do modelo. Apenas instruções aprovadas, construídas a partir de uma lista fechada, entram no contexto enviado ao Ollama.

O **modo privado** bloqueia o registo automático de conversas, mas estes comandos guardam intencionalmente o que o utilizador pedir. Não coloques dados confidenciais nas avaliações se não pretenderes guardá-los.

## Verificação

```bash
python -m pytest -q
```

A suíte v5.1 cobre persistência após reinício, feedback contraditório, propostas duplicadas, aprovação, rejeição, reversão, resistência a injeções, ordenação de sugestões, registos de objetivos e integração no router de comandos.

## Inspirações de design

Os padrões *human-in-the-loop* e de persistência de decisões do [LangGraph](https://github.com/langchain-ai/langgraph) foram estudados como referências, mas **não foi copiado nem instalado** código do projeto. Esta implementação é nativa e deliberadamente pequena para funcionar com o SQLite/SQLCipher da Expecto.
