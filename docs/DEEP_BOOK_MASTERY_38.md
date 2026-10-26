# Expecto 3.8 — Aprendizagem profunda de livros com recuperação semântica

A versão 3.8 melhora o **Book Reasoning Engine** da 3.7. Não treina os pesos de nenhum LLM e não certifica que um modelo compreende um livro. A avaliação deve ser feita com perguntas novas anotadas por pessoas, não com uma nota produzida pelo próprio LLM.

## O que mudou

1. **Pesquisa híbrida**: FTS5/BM25 e, opcionalmente, embeddings locais Ollama com fusão de posições. Uma pergunta por paráfrase pode encontrar passagens mesmo que a palavra exata não exista no livro. O resultado mantém livro, página, passagem e texto original.
2. **Indexação persistente**: tabela `book_embeddings`, com hash do texto e modelo usado, reutilização entre reinícios e eliminação em cascata quando um livro é apagado. Nenhum ficheiro pessoal é enviado para a internet: a API de embeddings está limitada a um endereço Ollama local.
3. **Estudo conceptual de segunda passagem**: `learning-map RUN_ID` pede ao modelo relações entre conceitos, possíveis equívocos e exercícios de aplicação, apontando para passagens originais. Ligações entre conceitos exigem evidência de duas passagens distintas. Todos os resultados ficam com o estado `model_generated_requires_review`.
4. **Deteção de números introduzidos sem fonte**: a resposta não pode acrescentar números ausentes das citações. Isto reduz um tipo de alucinação, mas não constitui verificação de significado.
5. **Métrica reprodutível**: benchmark com perguntas e passagens de referência identificadas manualmente; apresenta Hit@k e MRR. São métricas de recuperação, não de compreensão profunda nem verdade.
6. **Relatórios de cobertura**: percentagem de páginas com alguma citação no estudo. `coverage_pages` descreve páginas percorridas, não páginas compreendidas.

## Passos na instalação local

No Windows, usa a instalação habitual; preserva os dados e a frase-passe SQLCipher da versão anterior. Para ativar embeddings, executa:

```bat
ollama pull qwen3-embedding:0.6b
```

No `.env`, define `AURA_EMBEDDING_MODEL=qwen3-embedding:0.6b` e mantém `AURA_OLLAMA_URL=http://127.0.0.1:11434`.

### Importar, estudar e criar o mapa

1. Importa apenas PDFs cujo uso local confirmaste, usando `python -m aura.book_cli import ...`; identifica o `book_id`.
2. Cria capítulos com `python -m aura.deep_book_cli chapters BOOK_ID --pdf livro.pdf` (substitui os IDs e caminhos, sem os símbolos `<>`).
3. Opcional: `python -m aura.deep_book_cli index-semantic BOOK_ID`. Sem esta etapa, a pesquisa continua textual.
4. `python -m aura.deep_book_cli study-ai CHAPTER_ID` devolve o ID da sessão.
5. `python -m aura.deep_book_cli learning-map RUN_ID` constrói relações, equívocos e exercícios com revisão necessária.
6. `python -m aura.deep_book_cli ask "Como se relacionam velocidade e aceleração?" --semantic` consulta as passagens indexadas. Usa `--book ID` ou `--chapter ID` para restringir.
7. `python -m aura.deep_book_cli report RUN_ID` mostra evidências, cobertura e limitações.

### Medir a recuperação com casos reais

Prepara um ficheiro JSON com perguntas e `gold_passage_ids` escolhidos **por alguém que leu o livro**:

```json
[
  {"question":"Como representamos o deslocamento de um objeto?", "book_id":"ID_DO_LIVRO", "gold_passage_ids":["ID_DA_PASSAGEM"]}
]
```

Depois executa:

```bat
python -m aura.deep_book_cli benchmark casos.json
python -m aura.deep_book_cli benchmark casos.json --semantic
```

Compara o Hit@5 / MRR dos dois comandos. Se não houver melhoria, não assumas que a indexação semântica ajudou.

## Limites atuais

- Embeddings exigem um modelo Ollama instalado e disponível. Não foram testados nesta máquina com Ollama real; foram testados com vetores controlados e PDFs reais criados para teste.
- Pesquisa vetorial realiza cálculo de similaridade em Python/SQLite e é adequada a pequenas bibliotecas locais, não a milhões de páginas. Não há índice ANN.
- Modelos podem criar ideias erradas com citações literais verdadeiras. A ligação a fontes não comprova causalidade, validade científica ou inferência.
- O resultado de exercícios de aplicação é uma proposta e **não é automaticamente avaliado como certo**.
- PDFs digitalizados precisam de OCR separado; imagens, equações e tabelas complexas não são analisadas integralmente.
- SQLCipher e DSPy reais continuam sujeitos a validação na tua instalação.
