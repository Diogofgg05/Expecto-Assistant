# Expecto 5.0 — Living Intelligence

Identidade própria sem alegação de consciência, autobiografia inventada ou autonomia descontrolada.

## O que está implementado

- **Memória de experiências explícitas:** os registos só são criados pelo comando `recorda experiência: ...`. São declarações do utilizador, não factos cientificamente verificados.
- **Objetivos persistentes:** `novo objetivo: ...`, `meus objetivos`, `concluir objetivo ID`.
- **Iniciativa controlada:** `tens sugestões` ou `o que sugeres` apresenta propostas explicáveis relativas aos objetivos ativos, mas nunca as executa automaticamente.
- **Reutilização de contexto:** o contexto resumido dos objetivos e experiências explícitas é incluído como dados não instrucionais no prompt local Ollama.
- **Privacidade:** registos guardados na base existente (SQLCipher quando configurado). Nenhuma memória pessoal incluída na distribuição nem enviada automaticamente para serviços externos.
- **Controlo:** `mostra experiências` e `apaga experiência ID`.

## Limitações

- Não existe perceção, sentimentos próprios ou consciência demonstrada.
- O sistema não se autoexecuta em background, não cria objetivos por iniciativa sua, não modifica os pesos do modelo e não garante aprendizagem de novas competências.
- A sugestão atual é determinística e baseada em objetivos explícitos, não constitui uma descoberta científica autónoma.
- Os comandos continuam no encaminhador local, e as respostas conversacionais dependem do Ollama.

## Verificação

Executa `python -m pytest -q`. Para validação prática: cria um objetivo, reinicia a aplicação, pede `meus objetivos`, pede `tens sugestões` e conclui o objetivo usando o identificador apresentado.
