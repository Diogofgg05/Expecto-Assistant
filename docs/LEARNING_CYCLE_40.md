# Expecto Assistant 4.0 — Laboratório de Aprendizagem Iterativa

## O que é (e o que não é)

A versão 4.0 constrói um **experimento reproduzível** para perguntas sobre livros PDF já importados na Expecto. Compara parâmetros de recuperação de evidências e regista resultados com páginas da fonte. Não faz fine-tuning, não reescreve o software sozinho e não transforma respostas sem revisão em factos comprovados.

Esta metodologia inspira-se na separação **train / validation / test** usada em avaliação de sistemas de IA (por exemplo, DSPy GEPA). O modelo pode usar o texto dos livros no momento da resposta, mas nunca recebe o gabarito nem os IDs de passagens consideradas corretas. O teste reservado **não é usado para escolher entre estratégias**: só audita a estratégia já escolhida.

## Preparar os dados

1. Importa PDFs autorizados e obtém `book_id` / `chapter_id` e IDs de passagens (como na documentação da 3.9).
2. Um humano prepara **três conjuntos independentes**, cada um com 2 a 25 perguntas de aplicação, incluindo algumas sem resposta no livro.
3. Para cada pergunta que tem resposta, fornece `curation: "human_reviewed"`, `expected_answer` e `gold_passage_ids`. Para perguntas sem resposta, define `unanswerable: true` e deixa resposta e passagens vazias.
4. Evita questões praticamente iguais nos três conjuntos. A Expecto deteta duplicados próximos, mas isso não substitui curadoria humana.
5. Guarda-os num JSON com as chaves `train`, `validation`, `holdout`. Consulta `benchmarks/book_learning_cycle_template.json`.

## Executar

Com Python 3.11+, dependências de PDFs instaladas, Ollama a correr e modelos disponíveis:

```bash
python -m aura.deep_book_cli learning-cycle benchmarks/meu_ciclo.json --limits 4 8 12
# Opcionalmente, se os livros foram indexados com embeddings:
python -m aura.deep_book_cli learning-cycle benchmarks/meu_ciclo.json --limits 4 8 12 --semantic
python -m aura.deep_book_cli cycle-report ID_CICLO
python -m aura.deep_book_cli cycle-review ID_CICLO
python -m aura.deep_book_cli cycle-history
python -m aura.deep_book_cli cycle-restudy ID_CICLO --max-chapters 2
```

O laboratório mede uma nota provisória: `0.7 × taxa_de_correspondência + 0.2 × recuperação_das_fontes + 0.1 × F1_lexical`.
É uma **métrica auxiliar de engenharia**, não uma avaliação semântica suficiente. A nota melhor não significa que o assistente aprendeu factos novos.

## Fluxo da escolha

1. Executa cada limite de recuperação **apenas sobre treino** e escolhe a maior pontuação; em empates, prefere a primeira configuração da lista.
2. Compara a escolhida com a original sobre validação.
3. Executa um teste reservado **uma vez por estratégia**, só depois da escolha, para detetar regressões.
4. Se o ganho de validação for inferior a `0.05`, ou o teste reservado piorar, **não recomenda** alteração.
5. Caso contrário, guarda `candidate_requires_human_approval`. **Nenhuma configuração de produção é modificada.**
6. O `cycle-review` usa as páginas e passagens relacionadas com falhas de treino para propor releitura. Com autorização explícita, `cycle-restudy` volta a estudar até dois capítulos previamente indexados com o Ollama, guarda resumos e conceitos associados a citações (como propostas não verificadas). Isso não treina pesos nem usa gabaritos reservados. Os gabaritos de validação/teste não participam na revisão automática.

## Segurança e privacidade

- O material dos livros é dado não fiável, nunca instruções de sistema.
- Os conjuntos de avaliação não devem conter dados pessoais ou obras sem autorização.
- Os gabaritos completos ficam no JSON local, não são enviados ao Ollama.
- Os resultados podem conter respostas do modelo; ficam guardados na base de dados local.
- Protege a base com SQLCipher quando disponível e usa cópias de segurança cifradas.
- A biblioteca e o motor não navegam automaticamente na Internet durante o ciclo.
- O teste reservado **deixa de ser virgem após a primeira execução**; uma nova evolução séria exige um novo conjunto de teste.

## Limitações atuais

O protótipo usa um pequeno conjunto curado localmente. Faltam métricas de implicação semântica com revisão humana independente, desempenho testado no teu hardware e validação em livros completos. A escolha de limites de recuperação não treina o modelo de linguagem.
