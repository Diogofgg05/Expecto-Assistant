# EXPECTO 6.1 — Whisper persistente e contexto Ollama

## Ativação opcional
Instala `faster-whisper` e `numpy` no ambiente Python do Expecto.
Coloca um modelo CTranslate2 **já descarregado** numa pasta com `model.bin`:

```ini
AURA_VOICE_WHISPER_PERSISTENT_MODEL=C:/models/faster-whisper-small
AURA_PERFORMANCE_MODE=balanced
```

Este modo é independente do Whisper.cpp anterior (ficheiros ggml não são intercambiáveis).
Sem o modelo CTranslate2, continua disponível o Whisper CLI configurado anteriormente ou a voz do navegador. Nenhuma voz ou modelo é descarregado automaticamente pelo backend.

## Áudio contínuo
O navegador usa o microfone após um gesto do utilizador e envia PCM16 mono
16 kHz para `ws://localhost:8000/api/voice/continuous`.
O servidor mantém a ligação ativa, calcula transcrições provisórias de janelas
recentes e uma transcrição final quando ocorre silêncio ou o utilizador termina.
Cada turno está limitado a 15 segundos e o processamento parcial é limitado a
uma atualização a cada 2 segundos, com no máximo 5 segundos de áudio.

O reconhecimento não é verdadeiramente palavra-a-palavra e pode repetir
conteúdo na versão parcial; a final é a que segue para o motor conversacional.
A entrada continua a usar VAD RMS simplificado; melhoria posterior: AudioWorklet
e Silero VAD, com calibragem de ruído e cancelamento de eco.

## Otimização Ollama
O histórico é enviado ao modelo do turno mais recente para o mais antigo,
com orçamento limitado (FAST 1800, STANDARD 3600, DEEP 5200 caracteres).
O sistema nunca trunca o prompt de segurança, e os modos conservador e off
continuam disponíveis. O objetivo é evitar contextos longos que atrasem o
TTFT, não reduzir arbitrariamente a qualidade.

## Medições e limitações
```bash
python -m pytest -q tests/test_whisper_continuous_v61.py
python -m pytest -q tests/test_performance_engine_v60.py
python -m scripts.benchmark_ollama_streaming --runs 20 --warmup 2 --output benchmark_voz.json
```

Os testes utilizam um Whisper simulado. Não medem precisão de transcrição
PT-PT nem latência num computador real. O modelo fica carregado na RAM;
o primeiro pedido pode ser lento e o modo persistente consome memória.
Não há transcrição de áudio 24/7 nem captação sem ativação explícita.
