# EXPECTO 7.0.2 — Lightweight Core

## Objetivo

Simplificar o código sem remover funcionalidades nem enfraquecer permissões.
**Menos linhas não demonstra, por si só, menor consumo de RAM ou CPU.**

## Antes e depois

- `aura/engine.py`: 588 → 172 linhas (~71% menos linhas no router principal).
- Comandos determinísticos isolados em `command_interface.py`,
  `command_memory.py` e `command_evidence.py`. Os módulos antigos
  `command_research.py` e `command_reflection.py` continuam intactos.
- Componentes opcionais como avaliação, investigação e histórico são
  inicializados sob pedido com `functools.cached_property`. Cada instância
  tem a sua própria cache, sem partilhar dados entre utilizadores/sessões.
- `Database.memory_count()` usa `SELECT COUNT(*)`, evitando carregar
  a lista completa quando só é necessária a quantidade de notas.
- Comandos do holograma usam uma única tabela de painéis e correspondência
  regex em vez de percorrer várias alternativas em Python por cada pedido.
- GitHub Actions dispara por padrões `aura/**` e `tests/**`
  e mantém a suite Python e os testes de voz JavaScript.
- Corrigida a lista de hosts autorizados para voltar a incluir
  `127.0.0.1`, o valor predefinido.

## Proteções preservadas

O encaminhador de comandos continua a executar apenas ações autorizadas
explicitamente pelo utilizador. Texto produzido pelo modelo, documentos
e pesquisa externa não autorizam comandos privilegiados.

As memórias pessoais existentes não são apagadas nem migradas; o motor
continua com pesquisa, reflexão, RAG, verificações de factos e voz.

## Validação e limites

```bash
python -m compileall -q aura tests scripts
python -m pytest -q tests
node --test tests/test_voice_browser_v54.cjs tests/test_voice_prefetch_v56.cjs tests/test_audio_pipeline_v62.cjs
```

Os testes de contratos e de criação lazy não são um benchmark de memória.
A diferença real de RSS, importação de módulos, TTFT e velocidade de
resposta deve ser medida no equipamento de destino, com a mesma versão
de Python/Ollama e os mesmos modelos em 7.0.1 e 7.0.2.
