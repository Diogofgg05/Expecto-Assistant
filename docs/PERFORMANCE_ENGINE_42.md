# Expecto Performance Engine 4.2 — RAM adaptativa e segura

**Estado:** experimental, implementado na branch `feat/expecto-v6.7-realtime-local-voice`; não está na `main`, não está instalado no computador do utilizador e não foi medido com Ollama real.

## Melhoria

O módulo `aura/resource_budget.py` consulta sob pedido a quantidade aproximada de memória RAM física disponível no sistema e limita o custo de inferência **apenas para definições gerais curtas**, sem histórico ou contexto pessoal, no perfil `legacy`. Usa uma cache em memória de 10 segundos para não consultar o sistema a cada pedido. Não inicia processo, thread ou tarefa em segundo plano.

A adaptação precisa de consentimento explícito. A configuração predefinida mantém o comportamento anterior:

```dotenv
AURA_PERFORMANCE_PROFILE=legacy
AURA_PERFORMANCE_ADAPTIVE_MEMORY=true
AURA_PERFORMANCE_NUM_CTX=3072
AURA_PERFORMANCE_NUM_BATCH=64
AURA_COMPUTE_MAX_ACTIVE=1
AURA_COMPUTE_MAX_WAITING=2
```

Sem a variável `AURA_PERFORMANCE_ADAPTIVE_MEMORY=true`, a funcionalidade mantém-se desligada. Para desligar volta a `false`. Reiniciar o Expecto para carregar o `.env`.

| RAM livre observada | Estado | Limites máximos opcionais (apenas pergunta simples) |
|---|---|---|
| > 1 GB e > 10% da RAM física | normal | mantêm-se opções originais |
| <= 1 GB ou <= 10% (acima do nível crítico) | constrained | num_ctx 2048, num_batch 32, num_predict 160 |
| <= 512 MB ou <= 5% | critical | num_ctx 1536, num_batch 16, num_predict 112 |
| Desconhecida/erro de leitura | unknown | mantêm-se opções originais |

Os limites são tetos, não valores forçados para cima. Nunca são aplicados a perguntas pessoais, com histórico, complexas ou matemáticas pelo novo recurso. **O perfil legacy já limita o contexto para essas perguntas**, independentemente desta funcionalidade. Para máxima fidelidade usa `balanced`, que não ativa este adaptador.

## Diagnóstico

`GET http://127.0.0.1:8000/api/performance/status` e `GET http://127.0.0.1:8000/api/compute/status` apresentam `resource_guard` com modo, pressão observada, número de leituras e quantas perguntas simples foram ajustadas. O endpoint não inicia leituras da RAM, não carrega modelos e não grava prompts, históricos ou mensagens.

Windows: `GlobalMemoryStatusEx`. Linux: `/proc/meminfo` (pode refletir RAM do anfitrião em contentores). Estas medições não representam VRAM, RSS do Ollama nem memória livre efetiva para carregar um modelo. A memória disponível pode mudar depois da leitura.

## Testes

```bat
py -3.12 -m pytest -q tests/test_performance_engine_v40.py tests/test_performance_engine_v41.py tests/test_performance_engine_v42.py
py -3.12 -m pytest -q tests
```

GitHub Actions de 29/10/2026: 422 testes Python aprovados, 2 ignorados, e 7 testes JavaScript aprovados na execução 40874919051. Foram usados simuladores e testes automatizados; não se pode inferir ganho percentual, autonomia energética ou menor consumo real de RAM antes de benchmarking com hardware e modelos reais.

A 4.2 preserva as melhorias da 4.1: cliente HTTP partilhado com Ollama, um único embedding de pergunta para notas e conversas, circuit breaker e streaming SSE. Não apaga a memória, não atualiza modelos e não altera a identidade do assistente.
