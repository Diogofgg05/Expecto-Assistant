# AURA 3.2 — verificação da qualidade do conhecimento

A avaliação calcula níveis distintos: (1) arquivo local existe; (2) a sua
impressão digital permanece idêntica à registada no momento de extração;
(3) citações estão preservadas; (4) expressão matemática estrita verificada
com `fractions.Fraction`, quando aplicável; (5) possível cópia textual entre
fontes; (6) revisão temporal recomendada; (7) conflitos aritméticos literais.

Nunca confundir nenhum destes aspetos com prova de verdade no mundo real.

## Modelo de decisões

`withhold`: não enviar a hipótese aprendida para o contexto do Ollama por
rejeição, cálculo refutado, falta de evidência ou alteração de fonte.

`use_only_as_qualified_hypothesis`: pode ser apresentada com cautela, com
proveniência, nunca como facto estabelecido por este mecanismo.

Registos anteriores à AURA 3.2 mostram `legacy_unattested` porque não têm
uma impressão digital recolhida no instante original. A migração preserva
esta limitação em vez de a inventar.

O cálculo de qualidade não efetua rede, scraping nem escrita na base. A
captura das impressões digitais de evidências novas ocorre em transação
com a escrita da evidência. O utilizador pode consultar os relatórios por
comandos de voz ou API GET.
