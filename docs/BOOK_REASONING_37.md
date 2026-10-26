# Expecto 3.7 — Aprendizagem aprofundada de livros

## O que mudou face à 3.6

Anteriormente, a funcionalidade `deep_books.study()` selecionava frases com base na frequência de palavras. Era um resumo **extrativo**, não uma análise conceptual. A versão 3.7 mantém essa função como fallback, mas acrescenta um motor distinto (`aura/book_reasoning.py`) para estudo por capítulos com Ollama local.

### Processo real

1. Importa **apenas PDFs locais com autorização confirmada**, usando `aura.book_cli`.
2. Cria capítulos a partir do índice (TOC) ou, caso não exista, grupos de páginas (não verdadeiros capítulos identificados).
3. Percorre **todas as passagens indexadas** de cada capítulo em grupos controlados (até 4 600 caracteres por pedido).
4. Pede ao Ollama propostas de afirmações, conceitos, definições e perguntas conceptuais. Cada item inclui um ID de passagem e uma citação literal.
5. Valida que a passagem realmente pertence ao livro/capítulo e que a citação aparece no texto. Rejeita IDs inventados e citações inexistentes. Aplica um filtro lexical mínimo que reduz erros mas **não demonstra implicação lógica**.
6. Elabora sínteses a partir **apenas** de propostas ancoradas, referenciando os seus IDs de evidência. A síntese é guardada com origem e estado `model_synthesis_needs_review`.
7. Guarda questões e conceitos para estudo, sempre com referências, sem os promover automaticamente a factos.
8. Responde a perguntas de utilizador recuperando passagens do(s) livro(s), aceitando respostas apenas quando as citações são verificadas. Sem evidência, abstém-se.
9. Pode comparar conceitos entre dois livros usando passagens de ambos. A relação continua com estado `model_assessed_unverified`.

O relatório contém `coverage_pages` (páginas **percorridas**) e `cited_pages` (páginas **com referências geradas**). Uma cobertura total da entrada não significa que o modelo aproveitou todas as ideias.

## Como usar

```bash
pip install -r requirements-books.txt
ollama pull hermes3
# Com o Ollama a funcionar em localhost:
python -m aura.book_cli import "livro.pdf" --rights "Uso local autorizado, origem e licença: ..."
python -m aura.book_cli list
python -m aura.deep_book_cli chapters ID_LIVRO --pdf "livro.pdf"
python -m aura.deep_book_cli study-ai ID_CAPITULO
python -m aura.deep_book_cli ask "Qual é a diferença entre escalares e vetores?" --book ID_LIVRO
python -m aura.deep_book_cli report ID_SESSAO
python -m aura.deep_book_cli compare-ai ID_LIVRO_A ID_LIVRO_B
```

No assistente também se pode dizer:

> **Expecto, segundo os livros, como se define um vetor?**

A pergunta vai ao Ollama **local configurado**, e as passagens usadas no contexto são as que já estavam importadas. A análise integral de capítulos é iniciada pela CLI porque pode demorar e não deve bloquear uma interação por voz.

Em produção, usa-se a base SQLCipher configurada, não `--db` (que foi criado para testes/desenvolvimento e desativa a exigência de cifragem). **Não copiar bases de dados pessoais para o GitHub.**

## Proteções e limitações

- Os PDFs não são executados, interpretados como comandos nem enviados automaticamente para a internet; o texto de cada grupo é transmitido ao **endpoint Ollama configurado** (se apontar para fora da máquina, os excertos saem da máquina).
- Citações verificadas literalmente **não** significam conhecimento verdadeiro ou inferência correta. Resumos e comparações do modelo são **não verificados semanticamente**.
- Não é treino de pesos neuronais. A aprendizagem consiste em artefactos recuperáveis e em aplicação contextual do conhecimento.
- A pesquisa de respostas usa sobreposição lexical local; paráfrases sem palavras comuns podem não ser encontradas. Embeddings e reordenação semântica continuam uma melhoria futura.
- PDFs digitalizados sem texto requerem OCR; não existe OCR nesta versão.
- A geração sobre capítulos longos pode consumir bastante tempo e recursos; o limite de grupos é explícito, nunca se eliminam silenciosamente páginas para caber no contexto.
- Sem Ollama real neste ambiente de teste, só foram executados testes controlados com respostas JSON simuladas. Há que medir compreensão com exercícios novos e avaliador humano/independente.
- Uma alteração para 3.7 não altera dados pessoais existentes; tabelas novas são aditivas e os registos são removidos ao apagar um livro, por integridade referencial.

## Referências de engenharia

- Ollama JSON structured outputs: https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx
- Ragas Faithfulness: https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/faithfulness.md
- LlamaIndex Citation Query Engine: https://developers.llamaindex.ai/python/framework-api-reference/query_engine/citation/

Inspiração de design. Estes frameworks **não** foram instalados como dependências de runtime.
