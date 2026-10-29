# Expecto Performance Engine 4.0 — perfil Legacy, métricas e diagnóstico

**Estado:** implementação experimental na branch `feat/expecto-v6.7-realtime-local-voice`; **não está na main** e não foi testada no hardware do utilizador. A base de dados, as memórias e a forma de verificar respostas continuam sob as regras atuais do Expecto.

## O que foi implementado

1. **Rota rápida conservadora para definições gerais**: em `legacy`, perguntas curtas como «O que é uma CPU?» podem dispensar a recuperação de memórias pessoais, resumos, relações, documentos e embeddings. Perguntas pessoais, temporais, com histórico ou ambíguas preservam o contexto completo. Não é uma classificação semântica perfeita; desativa este perfil se detetares perda de contexto.
2. **Cache em RAM de 60 segundos** dos nomes/tamanhos dos modelos instalados; sem pedidos de descoberta em perguntas normais quando não precisam de modelo rápido. Cache preenchida apenas após consulta bem-sucedida ao Ollama.
3. **Limites Ollama opcionais** para `legacy`: `num_ctx`, `num_batch` e `num_predict <= 220` apenas no caminho rápido, sem truncar respostas complexas. Diminuir contexto ou batch pode reduzir RAM mas também pode prejudicar qualidade e throughput.
4. **Métricas agregadas e privadas**: `GET /api/performance/status` e `GET /api/compute/status` mostram p50/p95 do tempo de preparação, pedido total e primeira emissão de token (só quando há streaming), contagens e erros. Janela limitada aos últimos 96 pedidos, sem armazenar texto, históricos nem tokens. As medições são **internas ao servidor**, não incluem renderização, fala ou rede do browser.
5. **Sem serviços adicionais**: o módulo utiliza a biblioteca padrão e não cria trabalhadores ou dependências de produção.

## Configuração sugerida para hardware antigo

Acrescentar ao `.env`, mantendo os outros valores e reiniciando o Expecto:

```dotenv
AURA_PERFORMANCE_PROFILE=legacy
AURA_PERFORMANCE_NUM_CTX=3072
AURA_PERFORMANCE_NUM_BATCH=64
AURA_COMPUTE_MAX_ACTIVE=1
AURA_COMPUTE_MAX_WAITING=2
```

O perfil predefinido é `balanced`, preservando o fluxo completo. Com `balanced`, as métricas continuam disponíveis; a rota rápida e os novos limites de contexto/batch não são ativados.

**Importante:** estas variáveis são próprias da versão 4.0. Não confundas com `AURA_RESOURCE_PROFILE=legacy`, que pertence aos patches autónomos Optimization 2.0 e pode conflituar com alterações ainda não integradas.

## Testes

```bat
py -3.12 -m pytest -q tests/test_performance_engine_v40.py
py -3.12 -m pytest -q tests
```

O CI usa modelos e transportes simulados. Para alegar ganhos, repetir a mesma tarefa no mesmo equipamento, com o mesmo modelo e a mesma resposta máxima, em `balanced` e `legacy`. Comparar **p50/p95**, primeiro token, RAM máxima, CPU e perda de recordações relevantes. Não há medições reais de 100×.

## Segurança e limitações

- Métricas são agregadas por processo e reiniciam ao reiniciar o servidor.
- O endpoint é apenas local e de leitura; herda as proteções existentes de origem única.
- Nenhum histórico pessoal é guardado no módulo de métricas.
- O perfil Legacy **não é ideal** para pesquisas autobiográficas sem linguagem pessoal explícita. Muda para `balanced` se uma pergunta depender da tua memória.
- O tempo até à primeira emissão de token requer `/api/command/stream`; no modo sem streaming aparecerá `null`.
- A pesquisa vetorial continua disponível no percurso completo; os embeddings não são apagados.
- Requer uma instalação baseada na branch experimental, não deve ser aplicado como ficheiros soltos sobre a main 5.2 sem validação de compatibilidade.
