# Expecto 6.4 — Adaptive Compute (Apple × AMD × NVIDIA inspired)

**Status:** experimental branch. Independent software design inspired by public architectural principles; no vendor code, endorsement, proprietary API, CUDA, ROCm or NPU implementation.

## What actually works

- **Apple-inspired local-first:** Only the configured loopback Ollama service is used by the existing LLM adapter. Tasks and conversation history are not recorded in compute metrics. No new cloud dependency.
- **AMD-inspired explicit compute budgets:** Tunable concurrency, fast/primary model tiers and conservative memory-size gates. This is not hardware-level scheduling or Ryzen AI NPU support.
- **NVIDIA-inspired bounded inference admission:** Limit simultaneous requests, bound waiting requests, count timeouts and cancellations. This is not Triton dynamic batching, GPU allocation or CUDA stream scheduling.
- **Safe fast-model routing:** Only an explicitly configured, precisely installed secondary model can answer trivial one-turn greetings. Complex questions, longer conversations and ordinary prompts remain on the quality-oriented primary model.
- **Eco policy:** Optional `keep_alive=0s` hints Ollama to release idle model memory after replies; actual VRAM residency must be measured on the target machine. Optional CPU-only `num_gpu=0`.
- **Local diagnostics:** `GET /api/compute/status` shows policy, queue load and counters but no prompts, tokens, device identity or personal data.

## Configuration

Default configuration preserves the primary model and Ollama's accelerator decisions:

```dotenv
AURA_OLLAMA_MODEL=hermes3
AURA_COMPUTE_PROFILE=balanced
AURA_COMPUTE_FAST_MODEL=
AURA_COMPUTE_MEMORY_BUDGET_MB=0
AURA_COMPUTE_GPU_MODE=auto
AURA_COMPUTE_MAX_ACTIVE=2
AURA_COMPUTE_MAX_WAITING=4
```

Only if a fast model is intentionally installed, add e.g. `AURA_COMPUTE_FAST_MODEL=qwen2.5:1.5b`. A nonzero memory budget is an advisory comparison against model **disk size × 1.3**, not an actual RAM/VRAM guarantee. Under a strict budget, unknown or oversized secondary models are not selected.

Set `AURA_COMPUTE_PROFILE=eco` for short-lived model residency. Set `AURA_COMPUTE_GPU_MODE=cpu` only when intentionally disabling GPU use.

## Verify

```bash
python -m pytest -q tests/test_adaptive_compute_v64.py
python -m pytest -q tests
```

Real-world validation still needed: actual model quality, voice latency, GPU utilization, VRAM/RAM peak and energy consumption on the target hardware. No fabricated hardware results or claimed speedup.

## Reference concepts

- Apple Foundation Models framework (on-device task-specific inference): https://developer.apple.com/documentation/foundationmodels
- AMD ROCm optimization guidance: https://rocm.docs.amd.com/
- NVIDIA Triton inference server: https://docs.nvidia.com/deeplearning/triton-inference-server/

This 6.4 patch adds optional compute governance to the existing 6.3 work. It does not replace the application with another frontend, alter the holographic interface, train model weights or silently enable network tools.
