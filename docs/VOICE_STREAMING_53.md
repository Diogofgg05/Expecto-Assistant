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