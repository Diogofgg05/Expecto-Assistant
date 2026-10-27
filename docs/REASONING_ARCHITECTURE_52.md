# Expecto 5.2 — Research & Reasoning Architecture

## Princípio fundamental

**Pesquisar ≠ aprender ≠ comprovar.** Um excerto de um livro pode estar completo e ter uma citação correta e, mesmo assim, ser falso. O sistema deve qualificar o que encontra. Não deve treinar sobre respostas não verificadas.

## Pipeline implementado

1. **Modelo de linguagem local (Ollama)**: nome do modelo configurável por `AURA_REASONING_MODEL` (ou `AURA_OLLAMA_MODEL`); a aplicação não descarrega modelos automaticamente. O planner propõe até duas pesquisas auxiliares; o programa executa as pesquisas, nunca o modelo.
2. **RAG híbrido**: usa `BookResearchEngine` e `BookSemanticIndex` existentes (SQLite FTS5 e embeddings opcionais; rank fusion e diversidade). Passagens indexadas passam uma verificação de integridade por ID/texto/hash. `--semantic` exige ter previamente indexado os livros.
3. **Pesquisa externa, opcional**: SearXNG autoalojado em `http://127.0.0.1:PORTA`; não existe fallback para servidores públicos, DNS arbitrário, navegação automática nem seguimento de redirecionamentos. Os textos obtidos são **pré-visualizações não verificadas**. A pesquisa nunca envia memórias para motores externos; apenas a pergunta enviada voluntariamente.
4. **Orquestrador**: reúne no máximo 12 referências entre livros e web, impõe limites ao contexto, pede resposta em JSON, exige citações existentes e cria uma trilha de auditoria.
5. **Verificação**: `Evidence Critic` assinala números ausentes, negações suspeitas e fraca correspondência lexical; o `Reasoning Verifier` confirma ou refuta contas exatas com um verificador independente. Respostas com problemas ficam **retidas**. Mesmo respostas aceites continuam como `supported_proposal`.
6. **Avaliação**: reutiliza os benchmarks de recuperação (Hit@k, MRR) e de raciocínio 4.5, com perguntas rotuladas e teste reservado. Não há novo ganho de accuracy alegado sem uma avaliação real com Ollama.

### Comandos

```bash
# Pesquisa apenas nos PDFs, sem internet:
python -m aura.deep_book_cli reason-hybrid "O que é a independência linear?"
# Usar embeddings Ollama já indexados:
python -m aura.deep_book_cli reason-hybrid "O que é independência linear?" --semantic
# Pesquisa externa: exige AURA_SEARXNG_URL=http://127.0.0.1:8080 e SearXNG funcional
python -m aura.deep_book_cli reason-hybrid "O que é independência linear?" --external
# Usar modelo local de raciocínio diferente do modelo de conversação
python -m aura.deep_book_cli reason-hybrid "Problema complexo" --model MODELO_INSTALADO
```

Na conversa: «Expecto, investiga profundamente [assunto]». Para pesquisa externa explícita, acrescenta «na internet» à pergunta (com SearXNG configurado). Esta rota é uma operação solicitada, não uma tarefa autónoma silenciosa.

## Fine-tuning e preferência / RL

As mudanças em prompts com DSPy/GEPA e a adaptação dos pesos do modelo são **processos diferentes**. Foi implementado um exportador de exemplos curados por humanos, autorizados expressamente para *model training*, e com indicação de ausência de dados pessoais:

```bash
python -m aura.deep_book_cli prepare-tuning dados_revistos.json data/training_exports/minha_experiencia --format sft --i-authorize-export
# ou --format dpo (o JSON inclui chosen e rejected)
```

Exemplo de entrada SFT:

```json
[
 {"prompt":"O que é um determinante?", "chosen":"É um escalar associado a uma matriz quadrada...", "human_reviewed":true, "rights":"authorized_for_model_training", "contains_personal_data":false},
 {"prompt":"Quando existe uma inversa?", "chosen":"Uma matriz quadrada tem inversa se o determinante for não nulo.", "human_reviewed":true, "rights":"authorized_for_model_training", "contains_personal_data":false},
 {"prompt":"Qual a dimensão de R3?", "chosen":"A dimensão de R3 é três.", "human_reviewed":true, "rights":"authorized_for_model_training", "contains_personal_data":false}
]
```

Isto cria `train.jsonl`, `validation.jsonl`, `holdout.jsonl` e `manifest.json`, sem enviar dados a nenhuma nuvem e sem treinar nada. O formato DPO inclui `rejected`. Todos os ficheiros são colocados em pasta excluída do GitHub (`data/`). Os rótulos de revisão e autorização têm de ser **verdadeiros**, não são confirmados automaticamente pelo software.

**Experiência opcional de LoRA:** instala primeiro as dependências experimentais com `pip install -r requirements-training.txt`, num ambiente virtual específico e com drivers CUDA compatíveis.  o script `scripts/train_local_lora.py` usa TRL/PEFT, exige checkpoint HF local, GPU CUDA e aprovação `--approve-training`. Não é lançado pela Expecto, não publica o adapter nem o ativa sozinho. O seu funcionamento real e a compatibilidade com versões futuras do TRL não foram validados neste ambiente. Consulta licenças e custos do modelo base antes de treinar.

**Reforço/GRPO:** `aura.reward_lab.arithmetic_reward` é apenas um protótipo de função de recompensa para cálculos exatos. **Nenhum treino GRPO/PPO foi executado ou automatizado**. Para o futuro, Hugging Face TRL suporta GRPO, com experiências isoladas e recompensa verificável, sujeito a GPU, treino curado e avaliação independente. DPO é otimização por preferências, não uma demonstração de RL online.

## Projetos open-source avaliados

- [FastEmbed](https://github.com/qdrant/fastembed) (Apache-2.0): alternativa opcional aos embeddings Ollama; não integrado nesta versão.
- [DSPy/GEPA](https://github.com/stanfordnlp/dspy): otimização de prompts e programas com métricas, módulos existentes já preparados na Expecto; não é fine-tuning de pesos.
- [TRL](https://github.com/huggingface/trl) e [PEFT](https://github.com/huggingface/peft): LoRA, DPO, GRPO em treino experimental isolado. Usar versões compatíveis verificadas antes de treinar.
- [SearXNG](https://github.com/searxng/searxng) (AGPL-3.0): metapesquisa local opcional via API HTTP JSON, sem copiar o seu código para a Expecto.
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag): conceitos de grafos interessantes, mas projeto em manutenção e indexação potencialmente pesada; não integrado.

## Limites reais

Sem teste com modelos Ollama efetivos, não existe qualquer melhoria medida de raciocínio; as suites automatizadas validam os contratos e a segurança. Conteúdo web não é validado semanticamente nem comparado com a página original. Os verificadores determinísticos cobrem só subconjuntos estreitos de matemática. Não se deve promover um resultado apenas por parecer convincente. Confirmar direitos para cada PDF antes de usar os conteúdos em treino.
