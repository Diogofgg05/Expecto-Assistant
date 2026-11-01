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


## EXPECTO 5.6 — Frases em pipeline e menor custo do microfone

A fila Piper passou a preparar **no máximo uma frase seguinte**, enquanto a
primeira é reproduzida. Um segmento preparado é reutilizado quando chega a
sua vez, sem repetir a chamada HTTP de síntese. O cancelamento aborta a
reprodução atual e o pré-carregamento; respostas interrompidas não são
reproduzidas de novo.

O separador passa a processar **a primeira frase completa** por vez, em vez
de agrupar um parágrafo inteiro num só pedido de síntese. Quando não há
pontuação, divide em segmentos limitados de texto. A voz emitirá eventos
`expecto:voice` com `engine='piper'`, `preloaded`, `synthesisMs`
e `gapMs` (diferença local entre terminar uma frase e começar a seguinte).
Estes eventos são medições locais da interface, não medições end-to-end
dos motores de IA.

A gravação do microfone usa fragmentos `Float32Array` compactos e limitados
em vez de adicionar cada amostra a uma lista de números JavaScript. Isto
reduz alocações e picos de memória, sobretudo em gravações longas e
dispositivos com elevada frequência de amostragem.

```bash
node --test tests/test_voice_prefetch_v56.cjs tests/test_voice_browser_v54.cjs
```

Os testes de prefetch verificam reutilização, ordem, interrupção, fallback
para síntese Web Speech e libertação dos URLs temporários.

**Limites:** não existe ainda serviço persistente Piper/Whisper em memória;
continuar a lançar binários por segmento pode limitar o tempo de resposta,
sobretudo em hardware antigo. A melhoria reduz a pausa percebida quando a
síntese da próxima frase termina antes de acabar a anterior. Os ganhos reais
dependem do CPU, modelo e tamanho dos segmentos e não foram medidos no PC
do utilizador.


## EXPECTO 5.7 — Piper persistente em memória

Agora é possível reutilizar a **mesma sessão ONNX do Piper** para gerar várias
frases, evitando carregar o modelo e iniciar um processo em cada síntese.

### Ativação (opcional)

Instala o pacote Piper Python no ambiente que executa o backend:

```powershell
python -m pip install piper-tts
```

Mantém o modelo `.onnx` e a configuração `.onnx.json` no mesmo diretório.
Configura, no `.env`:

```ini
AURA_VOICE_PIPER_MODEL=C:/tools/piper/voices/<modelo_portugues>.onnx
AURA_VOICE_PIPER_INPROCESS=true
```

Este modo **não exige o binário Piper CLI**. Quando é ativado, a importação da
biblioteca é opcional: se o Python não tiver o pacote ou o ficheiro JSON
estiver em falta, o sistema pode usar o binário Piper CLI (quando também
configurado). Caso contrário, a saída vocal do navegador continua disponível.

### Proteções e observabilidade

- A voz é carregada **na primeira síntese**, não no arranque do Expecto.
- Um `threading.Lock` protege o modelo partilhado mesmo quando o utilizador
  interrompe o pedido HTTP. Cancelar uma coroutine não interrompe uma
  inferência já iniciada numa thread Python; a próxima fica serializada.
- O WAV sintetizado tem limite de 4 MiB, texto máximo de 240 caracteres, e
  não é guardado em disco pelo modo Python.
- `GET /api/voice/capabilities` indica `tts_mode` (`persistent`, `cli`
  ou `disabled`) e `tts_model_loaded`. Não expõe caminhos privados.
- Com `AURA_VOICE_PIPER_INPROCESS=false` (valor predefinido), o modo CLI da
  versão anterior é mantido sem alteração.
- Uma falha ao carregar o modelo só é tentada uma vez por instância do
  servidor. Reiniciar a aplicação permite voltar a tentar.
- Este modo pode aumentar significativamente a RAM ocupada e não garante menor
  latência em todas as máquinas; fazer medições locais antes de o escolher
  como predefinição.

### Verificação

```bash
python -m pytest -q tests/test_piper_persistent_v57.py
python -m pytest -q tests/test_local_voice_v55.py
```

Os testes verificam carregamento único, reutilização em pedidos concorrentes,
WAVs, fallbacks e falta do pacote. Utilizam um **Piper falso**; não incluem
benchmark de ONNX real nem medições da tua máquina. O Whisper.cpp continua
como CLI por gravação e ainda não é mantido em memória.
