# Expecto 4.2 — extração documental estruturada (opcional)

A importação habitual continua a usar PyMuPDF. Para experimentar o [Docling](https://github.com/docling-project/docling) (MIT) em tabelas, fórmulas e documentos difíceis, instala opcionalmente `pip install -r requirements-docling.txt` e executa:

```bash
python -m aura.book_cli import livro.pdf --rights 'Tenho autorização de leitura e indexação local' --parser docling
```

Ou utiliza `--parser auto` para recuar a PyMuPDF se Docling não estiver disponível ou se não conseguir conservar referências à página. O modo `docling` falha explicitamente quando não consegue estabelecer a página; a Expecto não deve inventar citações. O Docling pode instalar e descarregar modelos na primeira execução, precisa de recursos adicionais e **ainda não foi validado num equipamento com o Docling real**.

A integração usa o `DocumentConverter`, `iterate_items()`, `prov.page_no`, `text` e `table.export_to_markdown()`. Apenas os itens com proveniência da página válida são indexados; os não identificados são contabilizados. Isto não prova que todas as tabelas e fórmulas sejam lidas corretamente; confirma apenas o contrato e permite medições controladas. Uma tabela longa com proveniência em várias páginas é atribuída à primeira página por prudência.

Para comparar leitores, usa **dois PDFs com o mesmo conteúdo** (pois a verificação SHA-256 recusa importar duas vezes o mesmo ficheiro) numa base de dados de testes separada e mede respostas/citações manualmente. O benchmark de compreensão continua separado da extração.
