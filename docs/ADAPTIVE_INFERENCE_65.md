# EXPECTO 6.5 — Ollama Adaptive Inference 2.0

Esta versão responde a um problema real: versões anteriores tinham nomes
FAST/DEEP mas continuavam a usar o mesmo modelo; e, com embeddings ativados,
a recuperação simultânea de notas e episódios podia enviar o mesmo texto duas
vezes ao endpoint `/api/embed`.

## Melhorias concretas

1. **Embedding single-flight por pergunta.** `MemoryEngine.query_scope()`
   partilha a mesma `asyncio.Task` entre pesquisas de notas e episódios.
   Pedido de texto idêntico: **2 chamadas sem otimização → 1 chamada com
   otimização** no teste controlado. É uma redução de 50% nas chamadas de
   embedding duplicadas — **não** uma medição de 50% menos latência total.
   A cache é apagada ao terminar a consulta e não conserva dados pessoais
   entre pedidos.
2. **Ligações persistentes para embeddings.** `MemoryEngine` reutiliza um
   cliente HTTP limitado, encerrado com o backend no shutdown. Evita abrir um
   socket novo em cada embedding.
3. **Escolha REAL de modelos opcionais.** FAST e DEEP podem chamar modelos
   diferentes já instalados no Ollama. O modelo original continua a ser o
   padrão para STANDARD. FAST só é escolhido para definições curtas sem
   histórico nem referências a dados pessoais. O modo FAST pode pedir
   `think=false` para evitar tokens de raciocínio desnecessários.
4. **Fallback.** Se um modelo FAST/DEEP devolver HTTP 404, a aplicação usa o
   modelo principal e evita voltar a tentar o modelo em falta durante a
   execução atual. Uma resposta interrompida não é guardada como concluída.
5. **Observabilidade.** A telemetria mantém contagem dos modelos efetivamente
   usados, sem guardar perguntas ou respostas.

## Configuração no `.env`

```ini
AURA_OLLAMA_MODEL=hermes3
AURA_PERFORMANCE_MODE=balanced
# Ativar apenas quando os modelos estiverem instalados localmente:
AURA_OLLAMA_FAST_MODEL=qwen3:0.6b
AURA_OLLAMA_DEEP_MODEL=qwen3:8b
```

Os modelos FAST/DEEP são opcionais. Defini-los pode aumentar a RAM ocupada
porque o Ollama pode manter múltiplos modelos em memória. Em hardware
antigo, medir primeiro e manter apenas um modelo se for mais eficiente.

## Prova automática vs. desempenho real

```bash
python -m pytest -q tests/test_adaptive_inference_v65.py
```

O teste mostra numericamente a redução de chamadas de embedding
duplicadas (2 → 1). **Não é um benchmark real de CPU/GPU.**

Para medir dois modelos Ollama realmente instalados no computador,
faz uma comparação alternada de prompts, com aquecimento e métricas
TTFT, tempo total, tokens/s (mediana e P95):

```bash
python -m scripts.benchmark_adaptive_models --fast qwen3:0.6b --runs 20 --warmup 2 --output adaptive_benchmark.json
```

Compara `primary` e `fast` no ficheiro JSON. Um `median_ttft_change_pct`
negativo indica redução da latência até ao primeiro token no modelo candidato.
Não considera precisão, correção de respostas, nem tarefas complexas; não
selecionar outro modelo apenas porque é mais rápido. Os modelos devem
existir no Ollama local antes do benchmark.

**Não há métricas reais do PC do utilizador disponíveis nesta sessão.**
A implementação é real, a aceleração no seu hardware é uma hipótese a medir.
