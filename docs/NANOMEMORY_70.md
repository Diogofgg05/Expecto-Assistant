# EXPECTO 7.0 — NanoMemory Engine

The NanoMemory Engine is an adaptive resource policy, not lossless compression
of model weights. It minimizes unnecessary RAM/VRAM residency and rendering.
Ollama remains responsible for weight quantization and actual KV-cache layout.

## Modes

Set AURA_NANOMEMORY_MODE=auto in the Expecto .env.

- auto: ECO with <=8 GiB RAM or pressure, MAX with >=24 GiB total and
  >=8 GiB free, BALANCED otherwise.
- eco: 0m Ollama keep_alive, 2048–4096 token context windows, 12 FPS
  canvas, two Whisper CPU threads on initial model load.
- balanced: 2m keep_alive, 4096–12288 context, 24 FPS canvas.
- max: configured keep_alive (default 10m), 8192–24576 context,
  40 FPS canvas and full particles.

In critical memory pressure (available RAM below 1.25 GiB or 13% total),
ECO overrides all profiles including MAX. An unknown RAM snapshot defaults
AUTO to BALANCED. Decisions are reevaluated before each new LLM request.

CAUTION: ECO can be slower on successive queries because Ollama reloads
weights for every request. ECO may also truncate long conversation context,
which can reduce answer quality. Choose BALANCED or MAX when appropriate.

## Monitoring

GET /api/memory/status reports only system RAM available, active policy
and Ollama loaded model count/size_vram from /api/ps (if reachable).
Ollama size_vram is *usage*, not VRAM capacity or total GPU memory.
GET /api/performance/status includes anonymous aggregate inference metrics.

No private prompts or memory text are persisted by this policy. The
saved personal memory database is not compressed, truncated or deleted.
No process is forcibly killed; no weights are silently modified.

## Quantization and server settings (optional)

An appropriate pre-quantized Q4_K_M / Q8_0 model can save model RAM.
EXPECTO does NOT convert weights automatically, because automatic
conversions can silently harm quality. Compare a small and full model
on the same accuracy tasks before opting in.

Ollama SERVER configuration (outside Expecto .env):

    OLLAMA_MAX_LOADED_MODELS=1
    OLLAMA_NUM_PARALLEL=1
    OLLAMA_FLASH_ATTENTION=1
    OLLAMA_KV_CACHE_TYPE=q8_0

KV cache q8_0 or q4_0 depends on the Ollama version, accelerator and
Flash Attention support. It compresses the KV cache, not all program
RAM. Test answer quality and restart the Ollama process for settings
to take effect.

## Validation

    python -m pytest -q tests/test_nanomemory_v70.py
    python -m scripts.benchmark_adaptive_models --help

Automated tests run with fake Ollama hardware and do not prove faster
latency, lower battery use or memory savings on your actual computer.
