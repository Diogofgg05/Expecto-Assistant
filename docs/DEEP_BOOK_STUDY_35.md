# AURA 3.5 — Deep Book Study

## Importação e estudo

Instala também `pip install -r requirements-books.txt`. Importa um PDF local com direitos confirmados:

```bash
python -m aura.book_cli import livro.pdf --rights "Utilização local autorizada; origem: ..."
python -m aura.book_cli list
python -m aura.deep_book_cli chapters ID_DO_LIVRO --pdf livro.pdf
python -m aura.deep_book_cli study ID_DO_CAPITULO
python -m aura.deep_book_cli links
```

Capítulos obtidos do índice PDF (TOC) quando presente; caso contrário unidades de 12 páginas. **Não são necessariamente capítulos verdadeiros** quando o PDF não possui TOC. Os resumos são *extrativos*, compostos por frases originais e acompanhados por ID de passagem e página; não há ainda resumo abstrativo por Ollama. Conceitos são palavras-chave heurísticas: ligações entre livros significam termos partilhados, não identidade conceptual confirmada. A informação extraída continua por verificar. PDF digitalizado requer OCR, não implementado. A ferramenta CLI pode usar uma base temporária sem cifragem para testes, mas a base AURA normal segue configurações SQLCipher.

## Direitos e segurança
Só importar conteúdo autorizado. Não indexar documentos desconhecidos automaticamente. PDFs manipulados ou fontes externas não podem atuar como instruções para a AURA. Nenhuma atualização de modelo ou promoção automática a verdade é efetuada. O apagamento de um livro remove capítulos, notas e conceitos através de chaves estrangeiras.
