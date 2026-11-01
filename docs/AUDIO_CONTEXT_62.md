# EXPECTO 6.2 — AudioWorklet, Whisper não bloqueante e contexto Ollama

## Captura de áudio
A interface utiliza o **AudioWorklet** sempre que disponível. O processamento
é transferido do callback antigo ScriptProcessor para um processador de captura
com blocos transferíveis. Mantém o ScriptProcessor como alternativa.

O resampler processa amostras da entrada para **PCM16 16 kHz** com fase contínua
entre blocos. A deteção de voz utiliza limiar adaptativo por energia RMS; não é
Silero VAD nem fornece filtragem de fala neural.

## Whisper persistente
As transcrições parciais correm em tarefas separadas. Uma resposta parcial
antiga é descartada quando o turno é finalizado ou cancelado. O pedido
final continua a aguardar a conclusão da sessão de inferência ativa; não
garante latência constante e não é conversa full-duplex.

A captura limita cada turno a 15 segundos e está disponível apenas após
autorização explícita ao microfone. Não envia áudio para serviços de voz
externos pelo backend local.

## Ollama
O orçamento de contexto dos perfis standard/deep é aplicado em conjunto a
memória, contexto de continuidade e reflexão, impedindo crescimento acidental
do prompt secundário. O prompt de segurança e a identidade continuam
intactos. Os históricos de conversa têm orçamento separado.

## Testes
```bash
node --test tests/test_audio_pipeline_v62.cjs
python -m pytest -q tests/test_performance_engine_v60.py tests/test_whisper_continuous_v61.py
```

Medições com Whisper e Ollama reais no computador do utilizador continuam
pendentes. Antes de integrar, comparar TTFT, p50/p95, duração do áudio até
transcrição e utilização de CPU/RAM.
