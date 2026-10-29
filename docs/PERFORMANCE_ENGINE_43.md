# Expecto Performance Engine 4.3 — Processing Fast Path

**Estado:** implementação experimental em `feat/expecto-v6.7-realtime-local-voice`. Não foi integrada na `main` nem medida no computador do utilizador com Ollama real.

## Objetivo

Reduzir a latência de processamento entre a pergunta e a resposta, mantendo memória pessoal e verificações aritméticas. Esta atualização foca o **número de chamadas ao modelo** e **o custo de recuperar contexto**, não apenas os limites de RAM.

### 1. Raciocínio rápido com menos chamadas Ollama (opt-in)

Configurar:

```dotenv
AURA_REASONING_REVIEW_MODE=fast
```

O modo anterior **`balanced` permanece predefinido**. Com `fast`, uma resposta que passe a auditoria aritmética determinística não gera uma segunda chamada ao mesmo modelo apenas para revisão semântica. Isto evita uma inferência adicional especialmente em perguntas complexas. **Compromisso de qualidade:** não existe a segunda opinião do modelo; pode ser mais rápido, mas a precisão factual não aumenta automaticamente.

- Cálculos que o verificador determina estarem errados continuam a exigir uma correção bounded e nova auditoria.
- Respostas com expressões aritméticas reconhecíveis mas fora da gramática suportada são recusadas no modo rápido quando não é possível verificar.
- Verificação exata de matrizes, sistemas e aritmética já integrada continua prioritária e não depende do Ollama.
- `off` desativa a auditoria de raciocínio, pelo que não é recomendado para uso geral.
- `deep` mantém revisões reforçadas quando a qualidade é mais importante do que o tempo.

Para trabalhar com código, decisões importantes ou investigação de fontes, considera manter `balanced`, porque a revisão pelo modelo também pode detetar problemas que não são contas exatas.

### 2. Pesquisa de memória mais rápida, sem perda de resultados

Os percursos `MemoryEngine.recall_pair` agora **iniciam consultas lexicais SQLite enquanto o embedding da pergunta é calculado**. O vetor continua a ser partilhado entre memória e histórico, sem ficar numa cache persistente.

A pesquisa semântica de episódios usa:
- norma do vetor de pergunta calculada uma vez;
- seleção top-50 em heap, em vez de ordenar todos os candidatos;
- ranking estável em empates, conservando o resultado e as pontuações do método anterior;
- preservação do limite e do limiar de similaridade existentes.

Os métodos antigos de pesquisa direta continuam disponíveis.

### 3. Preparação do contexto em paralelo

O caminho de resposta inicia as consultas locais de documentos, hipóteses, estado temporal, relações, resumos e reflexões enquanto recupera as memórias e episódios. Usa `asyncio.to_thread` e conexões SQLite independentes; não cria um novo serviço e não guarda textos em métricas.

A utilização de workers pode adicionar algum overhead em máquinas com poucas cores, pelo que a melhoria real depende do equipamento e da quantidade de informação na base de dados.

### Perfis recomendados

**Equilíbrio entre rapidez e memória pessoal:**
```dotenv
AURA_PERFORMANCE_PROFILE=balanced
AURA_REASONING_REVIEW_MODE=fast
```

**Prioridade à verificação adicional pelo modelo:**
```dotenv
AURA_PERFORMANCE_PROFILE=balanced
AURA_REASONING_REVIEW_MODE=balanced
```

O perfil `legacy` do Performance 4.0 é independente: só evita contexto pessoal em algumas perguntas reconhecidas como definições gerais. Não é preciso ativar `legacy` para obter as optimizações 4.3 da pesquisa.

## Como medir no computador real

1. Utilizar **o mesmo modelo Ollama**, configuração, pergunta, histórico e tamanho máximo de saída nos dois modos, com o mesmo hardware.
2. Executar várias repetições (pelo menos 20) em `balanced` e `fast`.
3. Observar `GET /api/performance/status` para preparação, p50/p95 e primeiro token quando há streaming, e `reasoning_runtime.status()` para contagem de revisões.
4. Comparar também **tempo até à resposta final validada**, que pode incluir chamadas adicionais não medidas pelo tempo interno do `Ollama.reply`.
5. Auditar qualidade da resposta e fiabilidade da memória; não medir apenas milissegundos.

**Não existem medições verificadas de melhoria percentual de latência, CPU ou energia no computador do utilizador.** Os testes CI validam contratos de código, não benchmarks de produção.

## Testes

```bat
py -3.12 -m pytest -q tests/test_performance_engine_v43.py tests/test_performance_memory_v43.py tests/test_performance_context_v43.py
py -3.12 -m pytest -q tests
```

A branch deve manter a suite de testes Python e JavaScript aprovada antes de integrar na `main`. O modo rápido é experimental e opcional, por isso deve ser ativado conscientemente.
