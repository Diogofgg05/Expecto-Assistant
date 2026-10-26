# Expecto 4.1 — Pesquisa documental entre livros

Este módulo melhora **recuperação documental**. Não comprova aprendizagem autónoma, consenso ou factos científicos.

## Comandos

```bash
python -m aura.deep_book_cli research-books 'O que é uma matriz inversa?' 'Quando existe a inversa?' --limit 10
python -m aura.deep_book_cli research-books 'transformações invertíveis' --semantic --book ID_DO_LIVRO
```

A primeira consulta usa o índice textual. `--semantic` exige embeddings Ollama pré-indexados e acessíveis localmente.

## Comportamento

1. Recupera evidências para até seis perguntas diferentes.
2. Combina rankings (RRF) sem inventar pontuações de verdade.
3. Evita passagens quase duplicadas e limita concentração num único livro.
4. Confere o ID, a página, o texto e o hash guardados antes de citar.
5. Mostra livros, páginas, perguntas cobertas e perguntas ainda sem evidência.

**Limites:** fontes erradas continuam erradas; resultados relevantes não representam confirmação independente. A deduplicação por palavras também pode colapsar excertos distintos e deve ser avaliada com benchmarks humanos.

## Projetos avaliados

- [Docling](https://github.com/docling-project/docling) — MIT, parser de documentos complexos, alternativa futura ao extrator PDF existente; instalação opcional por ser pesada.
- [FastEmbed](https://github.com/qdrant/fastembed) — Apache-2.0, embeddings ONNX, potencial alternativa local ao Ollama; requer benchmark PT-PT antes de adoção.
- [GraphRAG](https://github.com/microsoft/graphrag) — MIT; indexação cara e projeto em modo de manutenção; não integrado.

Nenhum destes motores foi copiado ou instalado nesta atualização; a melhoria publicada é nativa e tem testes locais próprios.
