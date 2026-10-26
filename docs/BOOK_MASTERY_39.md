# Expecto 3.9 — Laboratório de compreensão e aprendizagem de livros

O sistema de estudo 3.7–3.8 extraía conceitos, criava sínteses com citações e recuperava passagens com FTS5/embeddings opcionais. **Não havia um teste externo para saber se a resposta a uma pergunta nova se aproximava da resposta esperada e citava as passagens necessárias.**

A versão 3.9 acrescenta `aura/book_mastery.py`:

1. **Avaliação de livro aberto:** o modelo recebe apenas a pergunta e passagens recuperadas do PDF que foi previamente importado com direitos confirmados.
2. **Conjunto de perguntas humanas separado:** um avaliador externo escolhe as perguntas, uma resposta de referência e os IDs de passagens esperados (`gold_passage_ids`). O gabarito não é enviado ao modelo.
3. **Métricas reproduzíveis:** sobreposição de tokens (F1), recuperação de evidência citada e taxa provisória de aprovação. Para contar como correspondência, exige um mínimo de F1 *e* todas as evidências esperadas citadas. Perguntas sem resposta exigem abstenção.
4. **Sinais de risco:** números inventados são rejeitados pelo motor de respostas existente; um teste adicional assinala mudanças de polaridade explícita, como `tem` versus `não tem`.
5. **Plano de revisão:** agrupa as falhas por livro, capítulo e páginas. Não injeta respostas corretas na memória ou no prompt do modelo.
6. **Histórico persistente e comparação:** compara apenas execuções do mesmo conjunto de avaliação, e deteta fontes que foram alteradas ou apagadas desde o teste.
7. **Privacidade:** sem transmissão para serviços externos pela avaliação; a base local guarda perguntas identificadas por ID, respostas produzidas, notas e páginas. SQLCipher só cifra a base se estiver instalado/configurado. O gabarito é mantido no ficheiro local JSON e não copiado para o relatório guardado.

## 1. Preparar os PDFs e estudar

A importação dos PDF continua a exigir autorização para uso local; consultar [BOOK_LEARNING_34.md](BOOK_LEARNING_34.md) e [BOOK_REASONING_37.md](BOOK_REASONING_37.md). Se estiver a usar SQLCipher, **não** execute o CLI com `--db`; deixe a configuração de encriptação no `.env` (o parâmetro `--db` é apenas para instalações locais de teste sem cifragem).

```bash
python -m aura.deep_book_cli chapters ID_LIVRO --pdf caminho/livro.pdf
python -m aura.deep_book_cli study-ai ID_CAPITULO
python -m aura.deep_book_cli learning-map ID_ESTUDO
```

## 2. Preparar o conjunto de avaliação

Crie um ficheiro JSON com perguntas **inéditas e verificadas manualmente**, como o esquema em `benchmarks/book_mastery_template.json`. Substitua os campos de exemplo pelos IDs reais dos livros, capítulos e passagens importados. Os IDs podem ser consultados na base de dados local ou nos relatórios anteriores de estudo. Cada pergunta deve ter:

- `id`: identificador único estável;
- `curation`: literalmente `human_reviewed`; o software valida a declaração, mas não consegue provar a revisão humana;
- `book_id`, `chapter_id` (facultativo), `question`;
- `expected_answer`: resposta criada/revista fora do modelo avaliado;
- `gold_passage_ids`: IDs das passagens que um leitor considera necessárias para responder;
- `unanswerable`: `true` se a pergunta não puder ser respondida pelo capítulo/livro; nesse caso, resposta e lista de evidências vazias.

**Não use perguntas, respostas ou exemplos já incluídos nos prompts de estudo**, pois isso introduz contaminação de avaliação. Crie dois conjuntos diferentes para avaliações posteriores.

## 3. Executar e consultar os resultados

```bash
python -m aura.deep_book_cli mastery-check benchmarks/meu_benchmark.json
python -m aura.deep_book_cli mastery-check benchmarks/meu_benchmark.json --semantic
python -m aura.deep_book_cli mastery-report ID_AVALIACAO
python -m aura.deep_book_cli mastery-plan ID_AVALIACAO
python -m aura.deep_book_cli mastery-history
python -m aura.deep_book_cli mastery-compare ID_ANTES ID_DEPOIS
```

`--semantic` exige que as passagens do livro tenham sido indexadas antes, com `AURA_EMBEDDING_MODEL` configurado e o Ollama local a funcionar.

O relatório contém: total, `passed`, `provisional_pass_rate`, `average_token_f1`, `evidence_recall`, diagnóstico por questão, e páginas a rever. **Nunca apresenta uma nota como verdade científica comprovada.** Uma avaliação em que as passagens tenham sido eliminadas ou alteradas é marcada `stale_sources`, e a taxa de aprovação deixa de ser apresentada.

## 4. O que isto não faz

- Não faz fine-tuning nem modifica os pesos de um LLM.
- A coincidência textual pode atribuir pontuações falsas a paráfrases equivalentes e a afirmações semanticamente diferentes. O bloqueio simples de negação **não substitui raciocínio lógico**.
- O facto de citar corretamente uma frase de um livro não significa que a frase é verdadeira.
- As perguntas sem resposta exigem que o modelo tenha a capacidade de se abster; não há detector universal de alucinações.
- Testes com modelos simulados validam o software, **não** a precisão ou inteligência real do Hermes/Ollama.
- Repetir exatamente o mesmo benchmark pode medir memorização dos itens, não generalização. A comparação do mesmo conjunto só é um indicador técnico; a melhoria genuína deve ser verificada num novo conjunto independente.

## 5. Verificação rápida local

```bash
python -m pytest -q tests/test_book_mastery_v39.py
python -m pytest -q
```

Os testes criam PDFs fictícios com PyMuPDF numa base temporária e validam persistência, isolamento do gabarito, referências falsas, adulteração de fontes, abstenção, diferenças entre conjuntos e planos de revisão.
