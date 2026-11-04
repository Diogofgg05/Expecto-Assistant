# EXPECTO 7.4 — Book Reasoning Components and Injectable Retrieval

## Motivation

The previous `aura/book_reasoning.py` (430 source lines) mixed five concerns:
model HTTP transport, pure evidence checks, SQL state and reporting, chapter
learning, and citation-grounded question/compare flows. Separating those
concerns makes it safer to extend capabilities without making the core heavier.

## Dependency diagram

```text
user command / book CLI
        |
        v
  aura.book_reasoning (legacy public facade)
        |
        +-> components/model.py       (BookModelPort, OllamaBookModel)
        +-> components/evidence.py    (pure, deterministic, no IO)
        +-> components/storage.py     (SQL + report; no model or RAG)
        +-> components/study.py       (chapter study + validation + map)
        +-> components/questions.py   (Q&A / compare + retrieval port)
        |
        v
    existing SQLite / SQLCipher data and optional Ollama
```

The public `BookReasoningEngine` inherits small domain-specific mixins to
preserve method names and signatures without rewriting sensitive database and
citation-validation behavior. The original `OllamaBookModel` and evidence
helpers are still importable from `aura.book_reasoning`.

## New extension seam

`BookReasoningEngine(db, semantic_index_factory=None)` defaults to the same
`BookSemanticIndex` previously instantiated inside `answer()`. For isolated
tests or alternative retrieval implementations, supply a factory accepting
`db` and providing async `search(question, **kwargs)`. The model adapter has
an explicit structural `BookModelPort.generate(task, payload)` interface.

This does **not** change the default retrieval algorithm, authorize automatic
network requests, or load HTTP dependencies until a model call is made.

## Compatibility and safety

- No API route changes, migrations, persisted data changes or memory deletions.
- No changes to citation length constraints, lexical evidence heuristics or
  claim-label semantics: lexical support is not independently proven truth.
- No changes to prompts, Ollama options, book study batching or model weights.
- No new mandatory dependency or new background worker.
- Existing `BookReasoningEngine.migrate`, `study_chapter`, `report`,
  `build_learning_map`, `answer`, and `compare_books` remain usable.
- Related 7.1/7.2 and 7.3 PRs modify other paths; keep them independently
  reviewable instead of merging branch contents automatically.

## Validation

```bash
python -m pytest -q tests/test_book_architecture_v74.py
python -m pytest -q tests/test_book_reasoning_v37.py tests/test_book_mastery_v39.py
python -m pytest -q tests
```

The new tests assert the preserved API, import direction, model port and an
injected deterministic search index without a running Ollama server. CI should
be green on this PR before merge to main. Refactoring alone does not prove
lower memory consumption, faster output or better answer accuracy.
