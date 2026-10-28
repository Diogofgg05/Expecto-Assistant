# Expecto Assistant — galeria de previews PNG e clips MP4

Imagens criadas para documentação visual do projeto, versão de referência **5.2**. Todas em formato **PNG 1280 × 720**.

**01–10:** capturas do frontend HTML/CSS/JS existente, com exemplos de dados fictícios. Os números e estados apresentados não correspondem a uma sessão real de Ollama, à base de dados do utilizador ou ao funcionamento da internet.

**11–20:** mockups ilustrativos construídos sobre o mesmo estilo visual; representam funcionalidades, laboratórios ou propostas em fases diferentes de desenvolvimento. **Não são capturas da implementação atual desses ecrãs.**

### 01 — Ecrã inicial

**Tipo:** Frontend real com dados de demonstração.

![Ecrã inicial](./01-01-inicio-holografico.png)

### 02 — Memória autobiográfica

**Tipo:** Frontend real com dados de demonstração.

![Memória autobiográfica](./02-02-memoria-autobiografica.png)

### 03 — Patronum ativado

**Tipo:** Frontend real com dados de demonstração.

![Patronum ativado](./03-03-patronum-ativado.png)

### 04 — Investigação documental

**Tipo:** Frontend real com dados de demonstração.

![Investigação documental](./04-04-investigacao-documental.png)

### 05 — Fontes e pesquisa

**Tipo:** Frontend real com dados de demonstração.

![Fontes e pesquisa](./05-05-pesquisa-de-fontes.png)

### 06 — Diagnósticos

**Tipo:** Frontend real com dados de demonstração.

![Diagnósticos](./06-06-diagnosticos-sistema.png)

### 07 — Projetos e objetivos

**Tipo:** Frontend real com dados de demonstração.

![Projetos e objetivos](./07-07-projetos-e-objetivos.png)

### 08 — Investigações agendadas

**Tipo:** Frontend real com dados de demonstração.

![Investigações agendadas](./08-08-investigacao-agendada.png)

### 09 — Memória + investigação

**Tipo:** Frontend real com dados de demonstração.

![Memória + investigação](./09-09-memoria-e-pesquisa.png)

### 10 — Patronum + diagnósticos

**Tipo:** Frontend real com dados de demonstração.

![Patronum + diagnósticos](./10-10-patronum-com-diagnosticos.png)

### 11 — Pesquisa RAG híbrida

**Tipo:** Mockup ilustrativo / conceito.

![Pesquisa RAG híbrida](./11-11-pesquisa-rag-hibrido.png)

### 12 — Leitura de PDF

**Tipo:** Mockup ilustrativo / conceito.

![Leitura de PDF](./12-12-leitura-de-pdf.png)

### 13 — Tabelas e fórmulas

**Tipo:** Mockup ilustrativo / conceito.

![Tabelas e fórmulas](./13-13-extracao-de-tabelas.png)

### 14 — Raciocínio multicamada

**Tipo:** Mockup ilustrativo / conceito.

![Raciocínio multicamada](./14-14-raciocinio-multicamadas.png)

### 15 — Crítica de evidências

**Tipo:** Mockup ilustrativo / conceito.

![Crítica de evidências](./15-15-critica-de-evidencias.png)

### 16 — Verificação matemática

**Tipo:** Mockup ilustrativo / conceito.

![Verificação matemática](./16-16-verificacao-de-matematica.png)

### 17 — Álgebra passo a passo

**Tipo:** Mockup ilustrativo / conceito.

![Álgebra passo a passo](./17-17-estudo-de-algebra.png)

### 18 — Avaliação independente

**Tipo:** Mockup ilustrativo / conceito.

![Avaliação independente](./18-18-laboratorio-de-avaliacao.png)

### 19 — Adaptação e feedback

**Tipo:** Mockup ilustrativo / conceito.

![Adaptação e feedback](./19-19-aprendizagem-e-feedback.png)

### 20 — Grafo 3D — conceito

**Tipo:** Mockup ilustrativo / conceito.

![Grafo 3D — conceito](./20-20-grafo-de-conhecimento-3d.png)


---

## Atualização de 2026 — interface real demonstrativa (21–28)

As imagens 21–26 e os clips 27–28 são gerados com **Chromium a executar os ficheiros HTML/CSS/JS da branch main**. Os exemplos de memória, fontes e diagnósticos são **dados inventados especificamente para demonstração**; os clips são gravados do frontend em funcionamento, **sem áudio, reconhecimento vocal, Ollama, acesso real à Internet ou memória privada**.

| Preview | Tipo | Descrição |
| --- | --- | --- |
| [21 · Início](21-interface-inicial-2026.png) | PNG real do frontend | Holograma em repouso |
| [22 · Memória](22-memoria-demonstracao-2026.png) | PNG real do frontend + demo | Painel de memória ativado por comando simulado |
| [23 · Patronum](23-patronum-demonstracao-2026.png) | PNG real do frontend + demo | Estado visual especial |
| [24 · Diagnósticos](24-diagnosticos-demonstracao-2026.png) | PNG real do frontend + demo | Diagnósticos ilustrativos |
| [25 · Pesquisa](25-pesquisa-demonstracao-2026.png) | PNG real do frontend + demo | Resultados fictícios, sem pesquisa online |
| [26 · Voz](26-voz-estado-demonstracao-2026.png) | PNG real do frontend + demo | Estado a ouvir simulado, sem gravação |
| [27 · Holograma](27-holograma-em-movimento.mp4) | MP4 do frontend | Animação real do canvas |
| [28 · Painéis](28-paineis-dinamicos.mp4) | MP4 do frontend | Transições visuais entre componentes com dados fictícios |

![Novo ecrã inicial](./21-interface-inicial-2026.png)

![Nova memória demonstrativa](./22-memoria-demonstracao-2026.png)

[▶ Clip: holograma em movimento](./27-holograma-em-movimento.mp4) · [▶ Clip: painéis dinâmicos](./28-paineis-dinamicos.mp4)

### Reprodução

```bash
python -m pip install playwright
python -m playwright install chromium
python scripts/render_app_previews.py
```

Para vídeos MP4 é necessário `ffmpeg` disponível no PATH. O script só acede ao servidor local temporário e à interface estática existente; não inicia o backend privado nem cria mensagens de utilizador. O workflow de previews publica automaticamente os ficheiros gerados na branch documental, antes de serem revistos para integração.
