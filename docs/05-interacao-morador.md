# Interação com o Morador

Este documento detalha o fluxo específico de interação com o morador quando ele atende a chamada originada pelo sistema de portaria inteligente.

## Visão Geral

A interação com o morador é uma etapa crítica no fluxo da portaria inteligente. Após coletar e validar as informações do visitante, o sistema inicia uma chamada para o telefone do morador. Esta seção do fluxo foi cuidadosamente projetada para oferecer uma experiência natural e eficiente para o morador.

## Fluxo Detalhado de Interação

### 1. Estabelecimento da Chamada

1. **Conexão com o Morador**:
   - O sistema envia comando `clicktocall` via AMQP/RabbitMQ
   - O Asterisk inicia uma chamada telefônica para o número do morador
   - Quando atendida, a chamada é conectada ao servidor AudioSocket na porta 8081
   - O mesmo UUID (call_id) da sessão do visitante é utilizado para manter o contexto

2. **Detecção de Atendimento**:
   - O sistema detecta quando o morador atende a chamada
   - Estado da conversa muda para `ESPERANDO_MORADOR`
   - É enviada uma mensagem especial `AUDIO_CONNECTION_ESTABLISHED` internamente

### 2. Comunicação Inicial

1. **Saudação Personalizada**:
   ```
   Olá morador do apartamento {apt}! {visitor_name} está na portaria 
   solicitando {intent_desc}. Você autoriza a entrada? Responda SIM ou NÃO.
   ```

2. **Exemplos de Personalização**:
   - **Entrega**: "Olá morador do apartamento 501! Pedro da Silva está na portaria solicitando uma entrega. Você autoriza a entrada? Responda SIM ou NÃO."
   - **Visita**: "Olá morador do apartamento 501! Pedro da Silva está na portaria solicitando uma visita. Você autoriza a entrada? Responda SIM ou NÃO."
   - **Serviço**: "Olá morador do apartamento 501! Pedro da Silva está na portaria solicitando um serviço. Você autoriza a entrada? Responda SIM ou NÃO."

3. **Notificação ao Visitante**:
   - O sistema informa ao visitante: "O morador atendeu. Aguarde enquanto verificamos sua autorização..."

### 3. Processamento de Respostas do Morador

O sistema está preparado para lidar com diferentes tipos de resposta do morador:

#### a) Pedido de Mais Informações

Se o morador responde com uma pergunta (contendo "quem" ou "?"), o sistema fornece detalhes adicionais:

```python
if "quem" in lower_text or "?" in lower_text:
    additional_info = f"{visitor_name} está na portaria para {intent_type}. "
    if intent_type == "entrega":
        additional_info += "É uma entrega para seu apartamento."
    # ...
```

**Exemplo**:
- **Morador**: "Quem está aí?"
- **Sistema**: "Pedro da Silva está na portaria para entrega. É uma entrega para seu apartamento. Por favor, responda SIM para autorizar ou NÃO para negar."

#### b) Autorização

O sistema reconhece diversas expressões de autorização:

```python
elif "sim" in lower_text or "autorizo" in lower_text or "pode entrar" in lower_text or "autorizado" in lower_text or "deixa entrar" in lower_text or "libera" in lower_text or "ok" in lower_text or "claro" in lower_text or "positivo" in lower_text:
    # ...
```

**Exemplo**:
- **Morador**: "Sim, pode entrar"
- **Sistema**: "Obrigado! Pedro da Silva será informado que a entrega foi autorizada."
- **Para o Visitante**: "Ótima notícia! O morador autorizou sua entrega."

#### c) Negação

O sistema também reconhece expressões de negação:

```python
elif "não" in lower_text or "nao" in lower_text or "nego" in lower_text or "negativa" in lower_text or "negado" in lower_text or "bloqueado" in lower_text or "barrado" in lower_text:
    # ...
```

**Exemplo**:
- **Morador**: "Não, não autorizo"
- **Sistema**: "Entendido. Pedro da Silva será informado que a entrega não foi autorizada."
- **Para o Visitante**: "Infelizmente o morador não autorizou sua entrega neste momento."

#### d) Resposta Ambígua

Quando a resposta não é clara:

```python
else:
    # Resposta não reconhecida
    session_manager.enfileirar_resident(
        session_id, 
        "Desculpe, não consegui entender sua resposta. Por favor, responda SIM para autorizar a entrada ou NÃO para negar."
    )
```

### 4. Finalização da Interação

1. **Após Decisão do Morador**:
   - Sistema registra a decisão `authorization_result` (authorized/denied)
   - Envia mensagem de confirmação para o morador
   - Atualiza o estado para `FINALIZADO`

2. **Processo de Encerramento**:
   - Envia mensagem de despedida para o morador
   - Inicia processo de encerramento com `_finalizar()`
   - Agenda envio de KIND_HANGUP após delay para permitir ouvir a mensagem

## Detecção e Transcrição de Fala do Morador

A detecção de fala do morador usa configurações especiais para captar respostas curtas:

1. **Configuração Mais Sensível**:
   ```python
   vad = webrtcvad.Vad(3)  # Nível de agressividade maior (0-3)
   ```

2. **Processamento de Falas Curtas**:
   ```python
   # Mesmo com fala muito curta, processamos, pois pode ser um "Sim" rápido
   if len(frames) < 20:  # ~0.4 segundo de áudio (20 frames de 20ms)
       logger.info(f"Fala CURTA do morador detectada: {len(frames)} frames (~{len(frames)*20}ms) - Processando mesmo assim")
       # NÃO descartamos frames curtos para capturar "Sim" rápidos
   ```

## Diagrama de Sequência

```
┌─────────┐   ┌───────────┐   ┌───────────┐   ┌────────────────┐
│ Morador │   │AudioSocket│   │SessionMgr │   │ConversationFlow│
└────┬────┘   └─────┬─────┘   └─────┬─────┘   └───────┬────────┘
     │              │               │                 │
     │<─chamada─────│               │                 │
     │──atende─────>│               │                 │
     │              │──notifica────>│                 │
     │              │               │─────────────────>
     │              │               │                 │─┐
     │              │               │                 │ │ Muda para 
     │              │               │                 │<┘ ESPERANDO_MORADOR
     │<─saudação────│<──────────────│<────────────────│
     │──pergunta───>│               │                 │
     │              │──transcreve──>│                 │
     │              │               │───────────────>│
     │<─detalhes────│<──────────────│<────────────────│
     │──decisão────>│               │                 │
     │              │──transcreve──>│                 │
     │              │               │───────────────>│
     │              │               │                 │─┐
     │              │               │                 │ │ Muda para 
     │              │               │                 │<┘ FINALIZADO
     │<─confirmação─│<──────────────│<────────────────│
     │              │               │                 │─┐
     │              │               │                 │ │ Inicia
     │              │               │                 │ │ encerramento
     │              │               │<────────────────│<┘
     │<─despedida───│<──────────────│                 │
     │<─kind_hangup─│               │                 │
     │──fim────────>│               │                 │
```

## Tratamento de Timeout e Não-Atendimento

O sistema gerencia casos em que o morador não atende:

1. **Processo de Tentativas**:
   - Até 2 tentativas (configurável)
   - Timeout de 10 segundos por tentativa

2. **Quando Não Há Resposta**:
   ```python
   # Se todas as tentativas falharam, notifica o visitante
   logger.info(f"[Flow] Todas as {self.max_tentativas} tentativas de contato com o morador falharam")
   session_manager.enfileirar_visitor(
       session_id,
       "Não foi possível contatar o morador no momento. Por favor, tente novamente mais tarde."
   )
   ```

## Considerações Importantes

1. **Tempo de Silêncio**: Configuração especial para respostas típicas do morador (geralmente curtas)

2. **Flexibilidade nas Respostas**: Sistema reconhece múltiplas formas de dizer "sim" e "não"

3. **Contextualização**: Mensagens sempre são contextualizadas para o tipo de visita

4. **Resiliência**: Tratamento adequado de casos onde o morador desliga ou há problemas de conexão

---

*Próximo documento: [06-encerramento-chamadas.md](06-encerramento-chamadas.md)*