# Expecto 4.3 — Multi-Layer Evidence Reasoning

Camadas 0–4: pergunta, evidências, hipóteses, objeções, síntese. Cada hipótese exige referências a passagens existentes. O grafo 3D é uma **representação visual**, não uma rede neuronal treinada nem uma prova da verdade.

O módulo `aura.multilayer_reasoning.MultiLayerReasoner` utiliza um adaptador de modelo assíncrono que devolve JSON estruturado. As passagens provêm de `BookResearchEngine`. Os prompts não são executáveis. Testes com simulações não demonstram melhoria no raciocínio de Ollama real. A visualização depende de `3d-force-graph` via CDN; não foi integrado no ecrã holográfico padrão.

Para testar a exportação, usar `export_graph_html(resultado["graph"])`. Antes de distribuir comercialmente a biblioteca de visualização verificar avisos de licença e empacotar a dependência localmente.

Para medir melhoria real: datasets inéditos de problemas matemáticos, programação e livros com gabarito humano, comparando 4.2 vs 4.3 em exatidão, citações, latência e memória. Só ativar estratégia mais custosa quando demonstrar melhoria.

Projetos estudados: DSPy/GEPA, Microsoft GraphRAG e `vasturiano/3d-force-graph`. Apenas um adaptador para grafos 3D foi criado; os motores GEPA/GraphRAG não foram integrados nesta versão.

## Execução

Com um livro importado, Ollama instalado e uma base SQLCipher acessível:

```bash
python -m aura.deep_book_cli reason-3d "Como se relacionam estes conceitos?" --html conhecimento.html
```

A visualização é opcional e depende de recursos de CDN: sem internet, o HTML apresenta uma mensagem de indisponibilidade. As cinco camadas representam estrutura de inferência sobre evidência e **não** ativam uma rede neuronal 3D treinada. O modo 3D é opt-in e não introduz botões ou sidebars na interface principal.
