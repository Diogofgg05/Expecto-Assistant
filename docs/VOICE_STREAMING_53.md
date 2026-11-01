# EXPECTO 5.3 — Conversa incremental e reprodução de voz por frases

## Alterações

- `POST /api/command/stream`: NDJSON com `token`, `final` e `error`.
- Mantém `POST /api/command` e todas as intenções existentes (abrir painéis, memória, pesquisa).
- `aura/llm.py`: usa `stream: true` apenas na nova rota; recebe os fragmentos em `aiter_lines()` do Ollama e encaminha-os logo ao cliente.
- `web/voice.js`: fila de frases PT-PT com `SpeechSynthesisUtterance`, cancelamento e interrupção por voz. Os primeiros segmentos podem ser reproduzidos antes do fim da geração.
- `web/app.js`: leitura progressiva com `ReadableStream`, fallback para a rota antiga quando a nova devolve HTTP 404, e estados de fala do avatar ligados à síntese.
- Uma conversa interrompida **não** é guardada na memória como resposta completa.
- Métricas por comando no evento `final.metrics`: `ttft_ms` (tempo até primeiro token observado pelo servidor) e `total_ms`.

## Controlos

- `V`: falar / interromper a resposta atual e começar a ouvir (onde o browser suportar).
- Duplo clique/toque no avatar: iniciar voz sem botão.
- `/`: escrever.
- `ESC`: interromper voz, cancelar geração e regressar ao modo principal.

## Dependências e limitações

A saída vocal continua a usar a síntese Web Speech do browser; **não** é TTS neural local e a qualidade depende das vozes disponíveis. O reconhecimento continua a usar `SpeechRecognition` do browser, que pode usar serviços externos dependendo do navegador e pode falhar em alguns sistemas. O programa não pede acesso ao microfone até um gesto explícito do utilizador.

A API usa uma fila limitada a 128 eventos. A nova versão usa `stream: true` no Ollama, mas não acelera o próprio cálculo dos tokens no modelo. Melhora sobretudo a **latência percebida**. A qualidade do modelo, o número de tokens/s, VAD local, STT neural, TTS neural e o áudio realmente sincronizado com o movimento 3D exigem trabalho adicional.

Os modos de conversa automática são de turno a turno; interrompê-los com `ESC` ou `V` não reativa o microfone silenciosamente. A reativação automática pode depender da política de permissões do browser.

## Testes e medição

```bash
python -m pytest tests/test_voice_streaming_v53.py -q
node --check web/app.js
node --check web/voice.js
```

O teste automatizado usa um modelo falso e **não** mede os tempos reais do Ollama. Para obter métricas de hardware, usa a aplicação local com Ollama e observa o evento NDJSON `final.metrics` no painel Network. Faz 20 pedidos iguais, com aquecimento prévio, e compara a mediana e p95 do TTFT, bem como o tempo total.

Não anunciar ganhos quantitativos sem medir em hardware real.

## 5.4 — Melhorias adicionais

- Reprodução vocal por frases com divisão antecipada de texto longo sem pontuação, orçamento máximo de 2700 caracteres e eventos `expecto:voice` (`ready`, `start`, `boundary`, `segment_end`, `done`, `cancel`) para animação futura do avatar.
- `aura/llm.py`: leitura de notas e de episódios em paralelo com `asyncio.gather`. Com embeddings ativos, podem ocorrer dois pedidos de embedding simultâneos; medir consumo e latência antes de alargar a solução.
- Erros do Ollama depois de começar a emitir tokens deixam de ser tratados como conclusão válida; o cliente recebe `error` e a troca incompleta não é guardada.
- Fila HTTP em backpressure drena todos os eventos na conclusão normal e cancela o produtor quando o cliente desconecta.
- `AURA_OLLAMA_KEEP_ALIVE`: tempo de permanência do modelo na memória do Ollama, por defeito `10m`; valores válidos de `0m` a `99m`. Usar `0m` em computadores com pouca RAM (pode aumentar a latência do arranque do modelo).
- Benchmark real sem alterar a memória: `python -m scripts.benchmark_ollama_streaming --runs 20 --warmup 2 --output benchmark_voz.json`. Executar com Ollama iniciado e modelo instalado.

```bash
python -m pytest -q tests/test_voice_streaming_v53.py tests/test_api.py tests/test_engine.py
node --test tests/test_voice_browser_v54.cjs
python -m scripts.benchmark_ollama_streaming --runs 20 --warmup 2 --output benchmark_voz.json
```

O benchmark calcula p50 e p95 para TTFT, tempo total e tokens/s. Não deve ser usado para afirmar uma melhoria absoluta na inferência; quantifica a diferença de latência *percebida* por streaming num determinado computador. A qualidade do ASR/TTS e os atrasos físicos da reprodução por voz continuam dependentes do navegador.

A branch de desenvolvimento não altera `main` até revisão e merge explícitos.
