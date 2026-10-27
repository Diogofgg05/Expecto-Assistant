# Expecto 4.7 — Verificador independente de Álgebra Linear

A versão 4.7 acrescenta um motor determinístico de Álgebra Linear, sem executar código gerado pelo modelo e sem depender do Ollama para confirmar contas.

Funcionalidades: determinantes exatos, matriz inversa, produto de matrizes, resolução de sistemas lineares com solução única, inexistente ou infinitas soluções. Limites: matrizes até 8x8, entradas inteiras ou frações como texto, rejeição de `float` e expressões não numéricas.

Comando de exemplo:

```sh
python -m aura.deep_book_cli verify-algebra problema.json
```

Exemplo de `problema.json`:

```json
{"type":"solve","matrix":[[2,1],[1,-1]],"rhs":[5,1],"claimed":{"status":"unique","solution":[2,1]}}
```

O resultado `verified_algebra` comprova **apenas** o cálculo submetido, não a pertinência do modelo matemático ou a veracidade de afirmações gerais. Ainda não existe extração autónoma fiável de sistemas a partir de texto livre e PDFs.
