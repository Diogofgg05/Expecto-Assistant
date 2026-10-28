# Expecto: design principles inspired by Apple (independent implementation)

These are general design ideas, not Apple code, branding, or a claim of feature parity.

1. **On-device first**: keep speech, memory and reasoning local unless the user enables an external service. A future cloud adapter must expose its destination and data categories.
2. **Intent before action**: tools declare capabilities; sensitive reads, writes, execution and deletion require explicit confirmation. Unknown capabilities fail closed. See `aura/intent_privacy.py`.
3. **Responsive interaction**: voice turn generation tokens invalidate stale work; use bounded queues, barge-in and adaptive compute budgets.
4. **Continuity without surveillance**: user-visible memory retention, deletion and per-source consent. Never infer consent from a conversational command.
5. **Accessibility**: Portuguese speech, captions, reduced motion and keyboard access must coexist with the hologram-first visual design.
6. **Energy-aware operation**: lazy-load expensive models, measure CPU/RAM/VRAM and latency, and stop idle work. No performance claims without end-to-end benchmarks.
7. **Quality gates**: use offline unit tests, integration tests with real Ollama and voice backends, and adversarial permission tests before shipping.

The intent gate is a foundation only: it must be called from the actual tool dispatcher and confirmation must be bound to a specific action and parameters before it can enforce end-to-end authorization.
