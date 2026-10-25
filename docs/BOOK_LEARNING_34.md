# AURA 3.4 — Autonomous Book Learning Engine (fase documental)

## O que funciona
- Importar PDFs locais com texto extraível e declaração explícita de direitos de utilização.
- Segmentação por página com sobreposição, SHA-256 do PDF e de cada excerto.
- Indexação FTS5 com fallback textual e recuperação com título, página e excerto.
- Guardar propostas com passagem literal existente (estado `unverified_proposal`).
- Remover um livro e todos os excertos/propostas associados; nunca altera memórias conversacionais.
- Funciona com a base SQLite ou SQLCipher existente (desde que a dependência SQLCipher esteja instalada e a chave correta seja dada).

## O que não faz ainda
- OCR de PDFs digitalizados; análise de figuras e tabelas complexas.
- Não descarrega livros da internet, não executa código de documentos e não envia PDFs para servidores.
- Não executa um ciclo autónomo com o Ollama; o CLI testa extração, recuperação e propostas manualmente.
- Verificação de citação NÃO é verificação científica da afirmação, e não existe atualização dos pesos dos modelos.
- Embeddings e respostas generativas baseadas em fontes devem ser integrados e avaliados em versão posterior.

## Instalação
`pip install -r requirements-books.txt`

Em Windows, após instalar a AURA, executar dentro da pasta da aplicação:

```
.venv\Scripts\python.exe -m aura.book_cli import "livro.pdf" --rights "Tenho licença/autorização para indexação local; fonte: ..."
.venv\Scripts\python.exe -m aura.book_cli search "o que são vetores?"
.venv\Scripts\python.exe -m aura.book_cli list
.venv\Scripts\python.exe -m aura.book_cli delete ID_DO_LIVRO
```

Faz backup cifrado antes de qualquer migração. Os ficheiros PDF não são copiados para a base; a AURA guarda excertos indexados, potencialmente sensíveis, na base ativa. Não partilhes bases contendo obras com restrições de distribuição. Só importar materiais autorizados.
