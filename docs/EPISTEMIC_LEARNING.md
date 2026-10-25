# AURA 3.1 — Motor epistémico de investigação e verificação

## Princípio fundamental

**Pesquisar não significa aprender; aprender não significa provar que uma afirmação é verdadeira.**

A AURA distingue:

1. **Documento encontrado**: texto e URL arquivados. Pode estar errado, ser antigo ou tentar manipular o modelo.
2. **Hipótese extraída**: uma proposição curta associada a excerto literal; mesmo citada, ainda pode ser falsa.
3. **Auditoria de evidência**: consulta **a cópia local guardada** e verifica se o excerto existe, se o documento ainda existe, se o URL coincide e se o domínio é permitido. Isto **não verifica** o site online em tempo real e não garante autoria legítima.
4. **Comprovação reproduzível restrita**: expressões aritméticas autossuficientes com `+ - * / ( ) =` são calculadas com `fractions.Fraction` e interpretação limitada da árvore sintática Python. Não há `eval`, `exec`, scripts externos nem execução de código das fontes.
5. **Revisão pelo utilizador**: aprovação/rejeição é armazenada separadamente da integridade documental e da correção aritmética; a aprovação **não é prova científica**.

### Estados

| Estado | Interpretação |
|---|---|
| `quoted_unverified` | Citação e referência local intactas. Afirmação não comprovada. |
| `multiple_reports_unverified` | Duas ou mais origens (`host`) reportam a afirmação; não é verificação de independência editorial. |
| `reproduced_calculation` | Uma igualdade aritmética estrita, presente literalmente na citação, foi reproduzida com precisão racional e está correta. **Só prova essa igualdade**, não qualquer conclusão alargada. |
| `falsified_calculation` | Uma igualdade aritmética foi refutada pela reprodução matemática. |
| `unsubstantiated` | A evidência original falta ou já não corresponde à cópia arquivada. Não promover. |
| `rejected` | O utilizador rejeitou esta hipótese. Não equivale a validação de uma hipótese alternativa. |

## Comandos naturais

- **"AURA, audita conhecimentos"**: audita até 50 hipóteses recentes e mostra um resumo no espaço de investigação.
- **"AURA, verifica as evidências"**: equivalente.
- **"AURA, audita descoberta `<ID>`"**: audita um registo concreto, preservando o relatório e a sua proveniência.
- **"AURA, mostra descobertas sobre Python"**: mostra as hipóteses, sem as declarar factos comprovados.

Não foram adicionados botões, rotas de páginas ou barras laterais: os resultados são dados de um espaço holográfico já existente.

## API local apenas de consulta

`GET /api/epistemics/claims/{claim_id}` — consulta uma hipótese com análise atual; não grava relatório.

`GET /api/epistemics/audits?limit=20` — lista auditorias previamente solicitadas.

As ações que gravam auditorias passam pelo router de intenções explícitas. O texto de fontes externas **não** pode dar comandos ao router.

## Persistência e migração

Ao iniciar, a versão 3.1 acrescenta a tabela `epistemic_audits` à base SQLCipher, sem apagar tabelas anteriores. As auditorias são uma fotografia do momento. A leitura atual recalcula a integridade da cópia local, mas não visita sites remotos nem substitui os arquivos por textos da internet.

**Atualização da 3.0:** encerra a AURA, faz uma cópia do ficheiro cifrado e dos backups, transfere `data/aura.sqlite3` da 3.0 para a pasta `data/` da 3.1 e arranca com a mesma frase-passe SQLCipher. Não substituas o ficheiro enquanto a base estiver aberta. Os backups continuam a ter a frase-passe própria.

## Segurança

- Entrada matemática limitada a 120 caracteres, operações binárias simples, AST limitada em profundidade e 1024 bits de numerador/denominador.
- Erros, divisão por zero, funções e potências são rejeitados, sem código executável.
- A integridade documental é apenas relativa à cópia guardada pela AURA; um atacante com acesso à base de dados pode alterar tanto o documento como as citações. Para prova forte de integridade externa são necessários assinaturas ou registos de confiança.
- Sites replicados e canais do mesmo grupo podem aparentar consenso. O número de domínios **não** equivale a fontes independentes.
- Factos empíricos requerem métodos e experiências adequadas, amostras, data, contexto, revisão crítica e, muitas vezes, especialistas. O motor não classifica automaticamente factos empíricos como comprovados.
- Sem execução autónoma de testes de programação nem alteração automática de estratégias, código ou pesos dos modelos.
- A memória das conversas de 6 meses permanece como anteriormente; este motor não altera a retenção.

## Motores GitHub avaliados (não instalados na 3.1)

- [DSPy GEPA / MIPROv2](https://github.com/stanfordnlp/dspy): evolução de instruções baseada em métricas e treino/validação; o laboratório DSPy da 3.0 foi mantido, mas estes otimizadores avançados não são executados automaticamente.
- [DeepEval](https://github.com/confident-ai/deepeval): métricas de fidelidade, resposta e avaliação de agentes.
- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai): avaliação estruturada de modelos e agentes.
- [Ragas](https://github.com/explodinggradients/ragas): qualidade de sistemas de pesquisa e resposta com fontes.

Futura investigação: avaliação factual externa com proveniência, fontes independentes, versões temporais, isolamento de benchmarks treino/dev/test e execução de **testes de software em sandbox, sujeitos a permissões**. Nenhuma destas capacidades adicionais está implementada nesta versão.
