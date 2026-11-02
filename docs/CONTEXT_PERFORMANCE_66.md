# EXPECTO 6.6 — Context Selection & Resource-Aware Inference

Evolução da 6.5, preservando o motor de voz e modelos FAST/STANDARD/DEEP.

## Seleção relevante de memórias

aura/context_selection.py reúne notas, episódios, documentos, relações, estado temporal, consolidações, continuidade, reflexões e hipóteses. Classifica por sobreposição lexical normalizada, importância e diversidade. Remove passagens duplicadas. O contexto global fica dentro do orçamento; instruções do sistema e identidade não são truncadas.

Passagens que não cabem integralmente são omitidas, protegendo referências de proveniência e URLs. O ranking é heurístico e exige avaliação de qualidade com perguntas reais. Modo AURA_PERFORMANCE_MODE=off mantém a recuperação completa como referência A/B.

## Gestor de recursos

AURA_OLLAMA_MAX_CONCURRENT=1 (padrão) limita o número de inferências Ollama simultâneas entre 1 e 4. Pode ajudar computadores com pouca RAM, mas pode aumentar a espera de pedidos concorrentes. Não controla Whisper/Piper.

## Monitorização

Diagnósticos mostram médias de passagens selecionadas e descartadas, e tamanho de contexto, nas últimas 64 inferências. Não guardam conteúdo das conversas.

## Testar

    python -m pytest -q tests/test_context_selection_v66.py
    python -m scripts.benchmark_adaptive_models --runs 20 --warmup 2 --output benchmark.json

O segundo teste requer modelos Ollama instalados. Não mede qualidade semântica nem desempenho de Whisper. Não afirmar melhorias de latência sem medição no PC.

## OpenJarvis

A arquitetura aproveita princípios gerais de ranking de contexto e gestão de recursos. A implementação deste empacotador é original, sem copiar código externo.
