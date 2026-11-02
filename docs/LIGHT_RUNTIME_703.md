# EXPECTO 7.0.3 — Lightweight Runtime

## Goal

Retain all voice, memory, security, streaming and command behavior of 7.0.2,
while avoiding unnecessary work during text-only usage.

The 7.0.2 release already reduced the main command router from 588 to about
172 lines and delayed the construction of secondary engine services.
This release builds on that work rather than introducing duplicate routers.

## Changes

1. **Lazy voice services:** `aura/app.py` caches a LocalVoice and a
   PersistentWhisper service per application instance, constructing them only
   on the first voice endpoint request. Creating an app, asking text-only
   questions or reading configuration does not import optional speech model
   runtimes through these constructors. Text and speech endpoints preserve
   their existing response schema. Instances are reused on later calls.
2. **Memory retrieval CPU:** `aura/memory.py` computes the squared norm of
   the query vector once for each lexical+semantic retrieval. Cosine scores
   continue to use the **same formula** and retain identical numerical
   ordering, except unavoidable floating point properties.
3. **Remove dead branches:** the Ollama health check no longer wraps its
   request in `if True`; error handling and health responses are unchanged.

## Safety and limitations

A shorter source file does not guarantee lower overall process RAM.
The effect of delayed imports depends on installed optional voice packages;
once speech is used, its memory footprint is still required.
Query-norm reuse can reduce Python CPU work over thousands of embeddings,
but may have little effect when Ollama model inference dominates.
No automatic user memory deletion, model compression, or change to permissions.

### Validation

```bash
python -m pytest -q tests
node --test tests/test_voice_browser_v54.cjs tests/test_voice_prefetch_v56.cjs tests/test_audio_pipeline_v62.cjs
```

New tests check that a text-only API session creates **zero** voice engines,
that the first voice capabilities request constructs each **once**, and that
precomputed cosine scores are numerically identical to the original formula.
No live Whisper/Piper/Ollama or RAM/RSS benchmark on the target PC is claimed.
