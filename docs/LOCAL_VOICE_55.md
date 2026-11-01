# EXPECTO 5.5 — Voz local opcional + modo de conversação

A versão 5.5 acrescenta **reconhecimento de fala local** com Whisper.cpp e
**síntese de voz local** com Piper, em modo opt-in, mantendo o navegador como
fallback para computadores onde não estejam instalados.

## Instalação

1. Instala e compila o [whisper.cpp](https://github.com/ggml-org/whisper.cpp);
   indica o caminho completo do `whisper-cli` e de um modelo multilíngue
   `ggml-*.bin` no teu `.env`. O modelo `.en` não é adequado a PT-PT.
2. Para saída de voz opcional, instala o executável
   [Piper](https://github.com/rhasspy/piper) e descarrega um modelo de voz em
   português `.onnx` com o respetivo ficheiro `.onnx.json`.
3. Acrescenta estas variáveis ao `.env`, usando os teus caminhos reais:

```ini
AURA_VOICE_WHISPER_BINARY=C:/tools/whisper/whisper-cli.exe
AURA_VOICE_WHISPER_MODEL=C:/tools/whisper/models/ggml-base.bin
AURA_VOICE_PIPER_BINARY=C:/tools/piper/piper.exe
AURA_VOICE_PIPER_MODEL=C:/tools/piper/voices/<modelo_pt>.onnx
```

Apenas o componente configurado fica ativo. Sem Whisper, o projeto mantém
`SpeechRecognition` do navegador. Sem Piper, mantém
`SpeechSynthesisUtterance`. Estes componentes do navegador podem utilizar
serviços de reconhecimento externos, consoante o sistema e o navegador.

## Funcionamento

- `GET /api/voice/capabilities` comunica disponibilidade sem expor caminhos.
- `POST /api/voice/transcribe` aceita apenas áudio WAV PCM16/16 kHz/mono.
- `POST /api/voice/synthesize` aceita texto até 240 caracteres e devolve WAV.
- A entrada local utiliza `getUserMedia`, deteta voz por energia RMS, termina
  após silêncio ou ao atingir o limite de 15 segundos e envia áudio apenas ao
  servidor Expecto em localhost.
- Os ficheiros temporários são criados em pasta temporária e apagados. Não há
  uploads automáticos de áudio ou chamadas a servidores externos de fala.
- O backend limita gravações a 512 KiB, duração 0,25–15 s, síntese a 240
  caracteres por segmento e tempos máximos de 40 s (STT) e 30 s (TTS).
- O sistema pode iniciar/reproduzir fala por frases, sem esperar pelo fim da
  geração textual do modelo.
- `V` começa a escutar, `Esc` interrompe, `/` permite escrever; duplo
  clique no avatar inicia a voz.

## Segurança e desempenho

A transcrição local **não é instantânea**: o Whisper CLI tem custos de
inicialização a cada gravação. Para diminuir latência futura, integrar um
processo persistente com buffers e isolamento, em vez de lançar um processo
por frase. O Piper também inicia um processo por segmento, pelo que em
hardware antigo o TTS do navegador pode ser mais rápido.

O reconhecimento RMS usa limiares fixos e pode precisar de calibração para
microfones ruidosos. O gravador utiliza `ScriptProcessorNode` por compatibilidade
e deverá evoluir para `AudioWorklet` após testes CSP e de navegadores.

## Testes

```bash
python -m pytest -q tests/test_voice_streaming_v53.py tests/test_local_voice_v55.py
node --test tests/test_voice_browser_v54.cjs
node --check web/local-voice.js
```

Os testes simulam os binários locais; não provam a qualidade do
reconhecimento/síntese nem os tempos de latência numa máquina real.
