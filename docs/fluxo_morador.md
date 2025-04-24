# Fluxo de Interação com o Morador

Este documento descreve o fluxo de interação com o morador quando ele atende a chamada originada pelo sistema de portaria inteligente.

## Visão Geral

Quando o sistema identifica um visitante e valida seus dados (apartamento e morador), ele inicia uma chamada para o telefone do morador. Ao atender a chamada, o morador participa de uma conversa automatizada que permite autorizar ou negar a entrada do visitante.

## Fluxo Detalhado

### 1. Início da Interação
Quando o morador atende a ligação, ele recebe uma mensagem personalizada contendo:
- Saudação identificando o apartamento
- Nome do visitante
- Tipo de visita (entrega, visita pessoal, serviço)
- Solicitação de autorização

Exemplo:
```
"Olá morador do apartamento 501! Pedro da Silva está na portaria solicitando uma entrega. Você autoriza a entrada? Responda SIM ou NÃO."
```

### 2. Possíveis Respostas do Morador

#### a) Pergunta ou Pedido de Detalhes
Se o morador responde com uma pergunta (contendo "quem" ou "?"), o sistema fornece informações adicionais:
```
"Pedro da Silva está na portaria para entrega. É uma entrega para seu apartamento. Por favor, responda SIM para autorizar ou NÃO para negar."
```

#### b) Autorização
Se o morador responde afirmativamente (palavras como "sim", "autorizo", "pode entrar"):
- Confirma ao morador que sua resposta foi registrada
- Informa ao visitante que sua entrada foi autorizada
- Finaliza a sessão

#### c) Negação
Se o morador responde negativamente (palavras como "não", "nao", "nego"):
- Confirma ao morador que sua resposta foi registrada
- Informa ao visitante que sua entrada não foi autorizada
- Finaliza a sessão

#### d) Resposta Ambígua
Se o morador responde de forma que o sistema não consegue interpretar como sim ou não:
```
"Desculpe, não consegui entender sua resposta. Por favor, responda SIM para autorizar a entrada ou NÃO para negar."
```

## Diagramas de Sequência

### Fluxo Principal
```
Visitante          Sistema          Morador
    |                 |                |
    |---- Dados ----->|                |
    |                 |---- Liga ----->|
    |                 |<--- Atende ----|
    |                 |--- Explica --->|
    |<-- Aguarde -----|                |
    |                 |<--- Decide ----|
    |<-- Resultado ---|--- Confirma -->|
    |                 |                |
```

### Fluxo com Dúvidas do Morador
```
Visitante          Sistema          Morador
    |                 |                |
    |                 |<--- Pergunta --|
    |                 |-- Mais Info -->|
    |                 |<--- Decide ----|
    |<-- Resultado ---|--- Confirma -->|
    |                 |                |
```

## Considerações Técnicas

1. A detecção do atendimento do morador é automática através da primeira mensagem recebida durante os estados `CHAMANDO_MORADOR` ou `CALLING_IN_PROGRESS`

2. A transição de estados segue o fluxo:
   ```
   CHAMANDO_MORADOR/CALLING_IN_PROGRESS -> ESPERANDO_MORADOR -> FINALIZADO
   ```

3. O sistema aceita variações nas respostas de autorização/negação:
   - Autorização: "sim", "autorizo", "pode entrar"
   - Negação: "não", "nao", "nego"

4. O sistema oferece suporte a solicitações de informações adicionais antes da decisão