# Melhorias na Conexão AMQP

Este documento detalha as melhorias implementadas no sistema de conexão AMQP para garantir o correto funcionamento das chamadas aos moradores e o tratamento adequado de erros conforme os requisitos do projeto.

## Requisitos Implementados

1. **Falha Explícita do Sistema**: De acordo com os requisitos, "se o AMQP não funcionar, deve quebrar a aplicação". Isso foi implementado com propagação adequada de exceções.

2. **Gestão Detalhada de Erros**: Implementação de tratamento específico para cada tipo de erro AMQP possível.

3. **Logging Detalhado**: Cada etapa do processo AMQP é registrada em log para facilitar o diagnóstico de problemas.

4. **Tratamento de Recursos**: Implementação de gerenciamento de conexões e canais com padrões de `try/finally` para garantir que recursos sejam liberados.

5. **Configuração de Timeouts**: Parâmetros de timeout e tentativas configurados para uma detecção mais rápida de falhas.

## Principais Melhorias

### 1. `enviar_clicktocall` (conversation_flow.py)

- **Propagação de Exceções**: Em vez de retornar `False` em caso de erro, o método agora lança exceções específicas.
- **Gestão de Recursos**: Implementação de `try/finally` para garantir o fechamento de conexões e canais.
- **Tratamento Específico de Erros**:
  - `AMQPConnectionError`: Erro de conexão ao servidor RabbitMQ
  - `ChannelError`: Erro no canal AMQP
  - `AMQPChannelError`: Erro específico de canal AMQP
  - `socket.gaierror`: Erro de resolução DNS
  - `socket.timeout`: Timeout da conexão
  - Erros TCP/IP: `ConnectionError`, `ConnectionRefusedError`, `ConnectionResetError`

### 2. `iniciar_processo_chamada` (conversation_flow.py)

- **Tratamento de Exceções**: Captura exceções do método `enviar_clicktocall` e propaga erros fatais.
- **Notificação ao Usuário**: Antes de quebrar a aplicação, notifica o visitante sobre o problema.
- **Logging Detalhado**: Registra cada tentativa e erro de conexão AMQP.

### 3. `on_visitor_message` (conversation_flow.py)

- **Task Supervisionada**: Implementação da tarefa de chamada como uma task supervisionada para captura e tratamento de exceções.
- **Propagação de Erros**: Garante que erros fatais sejam propagados para cima, quebrando a aplicação conforme requerido.

## Parâmetros de Conexão Melhorados

```python
parameters = pika.ConnectionParameters(
    host=rabbit_host,
    virtual_host=rabbit_vhost,
    credentials=credentials,
    connection_attempts=3,     # Aumentado para 3 tentativas
    retry_delay=2,             # 2 segundos entre tentativas
    socket_timeout=10,         # 10 segundos de timeout
    blocked_connection_timeout=5  # Timeout para conexões bloqueadas
)
```

## Próximos Passos

1. **Monitoramento**: Implementar monitoramento da conexão AMQP em produção.
2. **Recuperação Automática**: No futuro, pode-se considerar uma estratégia de recuperação automática com limite de tentativas.
3. **Teste de Carga**: Realizar testes de carga para verificar a estabilidade da conexão sob demanda.

## Observações

Esta implementação atende ao requisito específico de quebrar a aplicação quando o AMQP não funcionar, em vez de degradar graciosamente ou usar mocks. Para ambientes de produção, pode ser necessário revisar essa estratégia com base nos requisitos de disponibilidade e resiliência do sistema.