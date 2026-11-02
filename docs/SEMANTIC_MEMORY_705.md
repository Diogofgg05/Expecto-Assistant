# EXPECTO 7.0.5 — Semantic Memory Streaming

## O que mudou

A memória híbrida continua a usar SQLite/SQLCipher, FTS5, os embeddings
Ollama locais e a mesma função de similaridade cosseno, com limites e
limiares anteriores (notas 0,39; episódios 0,56).

Antes, `MemoryEngine.recall()` carregava até 2.500 registos completos com
vetores JSON numa lista, e `recall_episodes()` carregava até 10.000.
Agora os novos iteradores de `Database` utilizam `fetchmany(128)`, enviando
apenas identificador e JSON do vetor para um heap de candidatos. Os registos
completos são consultados **apenas para os vencedores**.

- `aura/db_notes.py`: `iter_memory_vectors`, `has_memory_vectors`
  e `memory_rows_by_ids`, com índice SQLite por modelo.
- `aura/db_episodes.py`: `iter_episode_vectors`, `has_episode_vectors`,
  `episode_rows_by_ids`, preservando o filtro de seis meses.
- `aura/memory.py`: `top_semantic` faz top-k exato, com ordenação estável
  e a mesma fusão lexical/semântica. Mantém os métodos de pesquisa anteriores.

## Memória e precisão

Os vetores continuam **todos a ser avaliados** dentro dos limites históricos,
para não perder resultados semanticamente relevantes sem palavras idênticas.
O heap mantém apenas os melhores 20/50 identificadores e pontuações;
mesmo com muitos candidatos, o consumo de RAM de Python durante a pesquisa
deixa de depender linearmente do número de vetores carregados de uma só vez.

Esta solução não é um índice vetorial ANN: um futuro índice como sqlite-vec
poderá ser opcional, depois de uma comparação de recall e verificação de
compatibilidade SQLCipher. Não foi adicionado nenhum plugin binário.

**Nenhuma memória é comprimida, removida, reindexada ou enviada para fora.**
A base atual abre normalmente; há apenas um índice SQLite não destrutivo
sobre `memory_vectors(model)`. A API pública `Database`, o formato dos
vetores e os limiares permanecem.

## Benchmark reprodutível

```bash
python -m scripts.benchmark_semantic_memory --rows 1200 --dims 64 --runs 3 --output semantic_comparison.json
python -m pytest -q tests
```

O script gera uma base **temporária com dados sintéticos**, mede o tempo de
leitura e ranking e o pico de alocações Python via `tracemalloc`, e confirma
igualdade dos 12 vencedores. **Não** mede RAM total do processo, VRAM, consumo
energético, geração de embeddings ou qualidade das respostas. Ganhos de
tempo dependem do sistema, disco, tamanho dos vetores e instalações.

## Compromissos

- A varredura cosseno continua O(N) em CPU; para milhões de registos, um
  índice ANN poderá ser mais rápido, mas pode perder recall.
- Existe uma nova consulta `has_*_vectors` e leitura dos vencedores por ID;
  estas operações adicionais podem tornar pesquisas pequenas ligeiramente
  mais lentas. O benefício esperado é sobretudo a memória transitória.
- A pesquisa continua a filtrar a janela temporal e a não executar
  embeddings se não houver índice do modelo instalado.
