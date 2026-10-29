# Expecto Performance Engine 4.6 — Reutilização controlada de conexões para embeddings

**Data:** 29/10/2026. **Estado:** experimental na branch
`feat/expecto-v6.7-realtime-local-voice`; ainda não integrado na `main`
nem medido no Windows do utilizador com um Ollama real.

## Problema identificado

A 4.5 já reutilizava HTTP na geração de texto, mas `MemoryEngine._embed`
criava e encerrava um `httpx.AsyncClient` em cada embedding da pergunta.
A indexação em lote das conversas também abria outra ligação HTTP para o
mesmo servidor. A criação e negociação das ligações pode introduzir latência.

## Mudanças da 4.6

- `MemoryEngine` usa um `LocalInferencePool` dedicado, criado apenas
  quando é necessário um embedding e limitado a **duas ligações locais**.
- Consultas individuais e indexação em lote reutilizam o transporte e
  continuam com os seus próprios timeouts (8 segundos e 30 segundos,
  respetivamente).
- O contexto e os vetores **não são guardados** pelo pool. Não existem
  serviços, threads permanentes ou pedidos em background adicionais.
- No encerramento do FastAPI, o serviço de memória fecha as ligações ativas.
- Falhas HTTP continuam a devolver `None` para embeddings individuais,
  mantendo o percurso lexical de recuperação.
- Há um interruptor de segurança para voltar ao método anterior caso um
  servidor de embeddings tenha comportamento pior com HTTP persistente.

**Configuração (predefinido):**

```dotenv
AURA_EMBEDDING_KEEPALIVE=true
```

**Se a medição local demonstrar uma regressão:**

```dotenv
AURA_EMBEDDING_KEEPALIVE=false
```

Reiniciar o Expecto depois de alterar o `.env`. Esta opção afeta
**apenas a comunicação HTTP da memória com os embeddings**, não a
inferência de chat nem a quantidade de contexto disponibilizado ao modelo.

## Benchmark A/B com ligações TCP reais, mas Ollama simulado

O script `scripts/benchmark_embedding_transport_v46.py` carrega a
implementação 4.5 fixada no Git em
`f70296847be02ad95d674e148faebbd2606b4d98` e compara-a com
o código 4.6 num único runner GitHub Actions, utilizando servidores
HTTP/1.1 reais em `127.0.0.1` com respostas artificiais de embeddings.
Ambos recebem 34 pedidos (30 medições + 4 aquecimentos) com vetores
idênticos.

**Execução de referência:**
[GitHub Actions 40897045873](https://github.com/Diogofgg05/Expecto-Assistant/actions/runs/40897045873).

| Servidor HTTP simulado | 4.5 TCP | 4.6 TCP | 4.5 p50 | 4.6 p50 | Resultado |
|---|---:|---:|---:|---:|---|
| HTTP/1.1 Python padrão | 34 | 1 | 14.1975 ms | 42.0481 ms | **4.6 mais lenta** |
| HTTP/1.1 com `TCP_NODELAY` | 34 | 1 | 13.3852 ms | 0.9421 ms | **4.6 ~14.21× mais rápida** |

Valores p95: servidor padrão 20.0933 → 42.3672 ms;
`TCP_NODELAY` 19.9087 → 1.0492 ms.

### Interpretação honesta

Reduzir 34 ligações TCP para uma é um facto medido, mas **não garante
menor latência**. Em HTTP/1.1 com respostas muito pequenas e pacotes
separados, o servidor Python padrão pode sofrer `delayed ACK`, e
manter a ligação aberta fica mais lento. Com `TCP_NODELAY` o efeito
deixa de ocorrer neste teste e a reutilização traz um ganho elevado.

**Isto não mede Ollama real**, nem a inferência em GPU/CPU, nem
a resposta final do utilizador. O Ollama real poderá apresentar outros
tempos, volumes de dados e configuração TCP. Não afirmar que o Expecto
ficou 14× mais rápido; o ganho corresponde exclusivamente a pedidos HTTP
contra um servidor simulado preparado de uma determinada forma.

A opção `AURA_EMBEDDING_KEEPALIVE=false` permite comparar rapidamente
e regressar ao método sem cache de ligações quando isso beneficiar
o equipamento.

## Reproduzir o A/B

No checkout Git com histórico completo e Python 3.12:

```bat
py -3.12 scripts\benchmark_embedding_transport_v46.py --runs 30 --warmup 4 --output benchmark_results_v46.json
```

O relatório JSON contém os tempos, contadores de conexões, SHA fixo
da versão anterior e limitações explícitas. É também publicado como
artefacto CI `performance-4-6-ab`.

Para medir **o Ollama instalado** e não o servidor simulado, utilizar o
benchmark local que já existia na 4.4:

```bat
py -3.12 scripts\benchmark_expecto_local_v44.py --runs 8 --output desempenho.json
```

O benchmark local exige ter a gravação automática de conversas desativada
ou o modo privado ativo; verifica esse estado antes de enviar perguntas.
Comparar versões ou configuração `AURA_EMBEDDING_KEEPALIVE` mantendo
o mesmo modelo, hardware, dados e carga. A ferramenta mede a primeira
emissão e a resposta final, não o volume de ligações TCP.

## Segurança e qualidade

- Não há armazenamento de prompts, embeddings ou texto gerado no pool.
- HTTP limitado à configuração do servidor Ollama local. O pool configura
  `trust_env=False` para evitar proxies de ambiente.
- Os testes verificam reutilização, indexação em lote, limite de
  ligações, encerramento, regressão configurável e fallback lexical.
- Não foram alterados os critérios de classificação de perguntas,
  os limiares de relevância, o motor matemático ou a interface holográfica.
