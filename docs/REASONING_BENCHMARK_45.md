# Expecto 4.5 — Independent Reasoning Benchmark

Crie dois conjuntos `dev` e `test` com perguntas não repetidas, respostas de referência revistas por pessoas, `gold_evidence_ids` e `answerable`. Nunca forneça ao modelo as respostas de referência. O módulo `compare_methods` recebe duas funções async que devolvem `answer`, `evidence_ids` e `abstained`.

Uma recomendação é apenas para revisão humana; o modelo não recebe novos pesos. Métricas de sobreposição lexical não detetam todas as contradições ou raciocínios incorretos. Não reutilize repetidamente o teste reservado para ajustar parâmetros.
