# Fluxos de Comunicação

Este documento descreve em detalhes os fluxos de comunicação entre os diversos componentes do sistema AudioSocket-Simple, desde o atendimento do visitante até o encerramento das chamadas.

## Fluxo Completo de Uma Chamada

### 1. Início da Chamada

1. **Inicialização do Sistema**:
   - Sistema inicia dois servidores AudioSocket (visitante e morador)
   - Servidores aguardam conexões nas portas 8080 e 8081

2. **Chegada de Visitante**:
   - Visitante liga para o ramal da portaria
   - Asterisk encaminha chamada para o AudioSocket na porta 8080
   - Sistema recebe conexão e cria uma nova sessão com ID único
   - Mensagem de saudação é enviada ao visitante

### 2. Coleta de Dados do Visitante

1. **Detecção de Fala**:
   - Sistema usa VAD para detectar quando o visitante começa a falar
   - Após silêncio de 1,5 segundos, considera que a fala terminou

2. **Processamento da Fala**:
   - Áudio do visitante é transcrito pelo Azure Speech
   - Texto transcrito é enviado para processamento

3. **Extração de Intenções**:
   - Sistema extrai progressivamente:
     - Tipo de intenção (entrega, visita, serviço)
     - Nome do visitante
     - Número do apartamento e nome do morador

4. **Validação de Dados**:
   - Sistema valida os dados usando fuzzy matching
   - Verifica se apartamento e morador existem no banco de dados

### 3. Contato com o Morador

1. **Estabelecimento de Chamada**:
   - Sistema envia comando clicktocall via AMQP
   - Morador recebe chamada telefônica
   - Sistema aguarda até 2 tentativas se não houver resposta

2. **Quando Morador Atende**:
   - Conexão estabelecida com o servidor na porta 8081 (mesmo ID da sessão)
   - Sistema envia mensagem informando sobre o visitante
   - Estado muda para ESPERANDO_MORADOR

### 4. Interação com o Morador

1. **Apresentação do Contexto**:
   ```
   Olá morador do apartamento 501! Pedro da Silva está na portaria solicitando uma entrega. 
   Você autoriza a entrada? Responda SIM ou NÃO.
   ```

2. **Processamento da Resposta**:
   - Sistema reconhece três tipos de respostas:
     - Pedido de mais informações ("Quem é?" ou "?")
     - Autorização ("sim", "autorizo", "pode entrar")
     - Negação ("não", "nego", "não autorizo")

3. **Tratamento de Respostas Ambíguas**:
   - Sistema pede confirmação quando não entende a resposta
   ```
   Desculpe, não consegui entender sua resposta. Por favor, responda SIM para 
   autorizar a entrada ou NÃO para negar.
   ```

### 5. Comunicação com o Visitante

1. **Informação da Decisão**:
   - Sistema informa o visitante sobre a decisão do morador
   ```
   Boa notícia! O morador autorizou sua entrega.
   ```
   ou
   ```
   Infelizmente o morador não autorizou sua entrada neste momento.
   ```

2. **Mensagem de Despedida**:
   - Sistema envia mensagem de despedida personalizada

### 6. Encerramento das Chamadas

1. **Encerramento Ordenado**:
   - Sistema envia mensagens finais a ambos participantes
   - Após um delay para que as mensagens sejam ouvidas (3-5 segundos)
   - Envia comando KIND_HANGUP (0x00) para encerrar as conexões
   - Libera recursos associados à sessão

## Diagrama de Estados

```
┌─────────────────┐           ┌───────────────┐           ┌────────────────────┐
│  COLETANDO      │           │               │           │                    │
│  DADOS          ├──────────►│   VALIDADO    ├──────────►│  CHAMANDO_MORADOR  │
└─────────────────┘           └───────────────┘           └──────────┬─────────┘
                                                                      │
                                                                      ▼
┌─────────────────┐           ┌───────────────┐           ┌────────────────────┐
│                 │           │               │           │                    │
│   FINALIZADO    │◄──────────┤ ESPERANDO     │◄──────────┤ CALLING_IN_PROGRESS│
│                 │           │ MORADOR       │           │                    │
└─────────────────┘           └───────────────┘           └────────────────────┘
```

## Detalhes por Tipo de Chamada

### Visitante → IA (Porto 8080)

1. **Inicialização**: 
   - `iniciar_servidor_audiosocket_visitante()`
   - Saudação inicial e criação de sessão

2. **Loop Principal**:
   - `receber_audio_visitante()`: Captura áudio, detecta fim da fala, transcreve
   - `enviar_mensagens_visitante()`: Monitora fila de mensagens, sintetiza e envia resposta

3. **Processamento**:
   - `session_manager.process_visitor_text()`: Gerencia o texto do visitante
   - `conversation_flow.on_visitor_message()`: Processa a mensagem com IA

### Morador → IA (Porto 8081)

1. **Inicialização**:
   - `iniciar_servidor_audiosocket_morador()`
   - Recupera contexto da sessão existente

2. **Loop Principal**:
   - `receber_audio_morador()`: Captura áudio, com configuração mais sensível para respostas curtas
   - `enviar_mensagens_morador()`: Monitora fila de mensagens, sintetiza e envia ao morador

3. **Processamento**:
   - `session_manager.process_resident_text()`: Gerencia o texto do morador
   - `conversation_flow.on_resident_message()`: Interpreta decisão do morador

## Tratamento de Encerramento de Chamadas

### Encerramento Programático

O sistema pode encerrar chamadas de forma programática usando o sinal KIND_HANGUP:

1. **Via ConversationFlow**:
   - `_schedule_active_hangup()`: Agenda o encerramento após delay
   - Envia KIND_HANGUP (0x00) para o cliente AudioSocket
   - Trata exceções de ConnectionResetError adequadamente

2. **Via API HTTP**:
   - Endpoint `/api/hangup`
   - Parâmetros: `call_id` e `role` (visitor/resident)
   - Notifica o cliente correto com KIND_HANGUP

### Mecanismo de Encerramento

```python
# 1. Enviar KIND_HANGUP
writer.write(struct.pack('>B H', 0x00, 0))
await writer.drain()

# 2. Sinalizar que a sessão deve terminar
session_manager.end_session(call_id)

# 3. Limpar completamente após delay
session_manager._complete_session_termination(call_id)
```

### Tratamento de Erros

- System trata graciosamente erros de `ConnectionResetError` quando o cliente desconecta
- Implementa timeouts para evitar bloqueios em operações de I/O
- Mantém logs detalhados para diagnóstico e monitoramento

## Comunicação entre Estados

A progressão entre estados é controlada pelo ConversationFlow e comunica-se com o sessão via:

1. `session_manager.enfileirar_visitor()`: Envia mensagem para o visitante
2. `session_manager.enfileirar_resident()`: Envia mensagem para o morador
3. `session_manager.end_session()`: Sinaliza encerramento das conexões

## Diagrama de Sequência Detalhado

```
┌─────────┐   ┌──────────┐   ┌───────────┐   ┌────────────┐   ┌──────────┐   ┌─────────┐
│Visitante│   │AudioSocket│   │SessionMgr │   │  Flow      │   │  IA      │   │ Morador │
└────┬────┘   └─────┬────┘   └─────┬─────┘   └─────┬──────┘   └────┬─────┘   └────┬────┘
     │              │              │               │                │             │
     │──chamada────>│              │               │                │             │
     │              │──cria sessão>│               │                │             │
     │              │<─confirma────│               │                │             │
     │<─saudação────│              │               │                │             │
     │──fala───────>│              │               │                │             │
     │              │──transcreve─>│               │                │             │
     │              │<─texto───────│               │                │             │
     │              │              │──processa────>│                │             │
     │              │              │               │──extrai intent>│             │
     │              │              │               │<─intent────────│             │
     │              │              │<─resposta─────│                │             │
     │<─pergunta────│              │               │                │             │
     │──resposta───>│              │               │                │             │
     │              │              │──processa────>│                │             │
     │              │              │               │──dados validos>│             │
     │              │              │               │<─confirmação───│             │
     │              │              │               │────────────────────clicktocal>│
     │<─aguarde─────│              │               │                │             │
     │              │              │               │                │<─atendimento│
     │              │              │               │<────────────────────────────│
     │              │              │               │────────────────────────────>│
     │              │              │               │<────────────────────decisão│
     │<─autorizado──│              │               │                │             │
     │              │              │<─encerrar─────│                │             │
     │<─kind_hangup─│              │               │                │             │
     │──fim────────>│              │               │                │             │
     │              │<─fim─────────│               │                │<─kind_hangup│
     │              │              │<─limpar───────│                │             │
     
```

---

*Próximo documento: [05-interacao-morador.md](05-interacao-morador.md)*