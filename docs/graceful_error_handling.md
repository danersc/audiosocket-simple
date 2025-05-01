# Tratamento de Erros ao Encerrar Chamadas

Data: 01/05/2025

## Visão Geral

Este documento descreve as melhorias implementadas para tratar erros de conexão de forma adequada, especialmente os erros `ConnectionResetError` que ocorrem quando o cliente AudioSocket desconecta abruptamente após receber um comando KIND_HANGUP (0x00).

## Contexto do Problema

Quando enviamos o comando KIND_HANGUP para encerrar uma chamada, o cliente AudioSocket no Asterisk desconecta imediatamente, o que pode gerar mensagens de erro como:

```
ERROR:asyncio:Unhandled exception in client_connected_cb
transport: <_SelectorSocketTransport closed fd=10>
Traceback (most recent call last):
  File "/path/to/audiosocket_handler.py", line 631, in iniciar_servidor_audiosocket_visitante
    await writer.wait_closed()
  File "/usr/lib/python3.12/asyncio/streams.py", line 364, in wait_closed
    await self._protocol._get_close_waiter(self)
  File "/usr/lib/python3.12/asyncio/selector_events.py", line 1013, in _read_ready__data_received
    data = self._sock.recv(self.max_size)
ConnectionResetError: [Errno 104] Connection reset by peer
```

Estas mensagens não indicam um erro real no sistema, mas sim uma desconexão esperada. No entanto, elas podem dificultar a depuração e causar preocupação desnecessária.

## Solução Implementada

Implementamos tratamento adequado para estas exceções em vários pontos do código:

### 1. Tratamento ao Fechar Conexões no AudioSocket Handler

```python
try:
    writer.close()
    # Usar um timeout para wait_closed para evitar bloqueio indefinido
    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
except asyncio.TimeoutError:
    logger.info(f"[{call_id}] Timeout ao aguardar fechamento do socket - provavelmente já foi fechado pelo cliente")
except ConnectionResetError:
    # Isso é esperado se o cliente desconectar abruptamente após receber KIND_HANGUP
    logger.info(f"[{call_id}] Conexão resetada pelo cliente após KIND_HANGUP - comportamento normal")
except Exception as e:
    # Capturar qualquer outro erro durante o fechamento da conexão
    logger.warning(f"[{call_id}] Erro ao fechar conexão: {str(e)}")
```

### 2. Tratamento ao Enviar KIND_HANGUP no ConversationFlow

```python
try:
    logger.info(f"[Flow] Enviando KIND_HANGUP ativo para visitante na sessão {session_id}")
    visitor_conn['writer'].write(struct.pack('>B H', 0x00, 0))
    await visitor_conn['writer'].drain()
except ConnectionResetError:
    logger.info(f"[Flow] Conexão do visitante já foi resetada durante envio de KIND_HANGUP - comportamento normal")
except Exception as e:
    logger.warning(f"[Flow] Erro ao enviar KIND_HANGUP para visitante: {e}")
```

### 3. Tratamento ao Enviar KIND_HANGUP via API

```python
try:
    writer.write(struct.pack('>B H', 0x00, 0))
    await writer.drain()
except ConnectionResetError:
    logger.info(f"Conexão já foi resetada durante envio de KIND_HANGUP para {call_id} ({role}) - comportamento normal")
except Exception as e:
    logger.error(f"Erro ao enviar KIND_HANGUP para {call_id} ({role}): {e}")
    return web.json_response({
        "status": "error",
        "message": f"Erro ao enviar KIND_HANGUP: {str(e)}"
    }, status=500)
```

## Benefícios

1. **Melhor Observabilidade**: Logs mais claros e informativos sobre o encerramento de conexões
2. **Robustez**: O sistema não gera erros não tratados quando o cliente desconecta
3. **Cleanup Adequado**: Garantia de que os recursos são liberados mesmo quando há desconexões abruptas
4. **Preparação para Novas Chamadas**: O socket é adequadamente liberado para receber novas conexões

## Exemplos de Logs

Após as mudanças, veremos logs mais amigáveis como estes:

```
INFO:[99203132-1abf-4309-a05e-d7c6624c74af] Conexão resetada pelo cliente após KIND_HANGUP - comportamento normal
INFO:[99203132-1abf-4309-a05e-d7c6624c74af] Socket encerrado e liberado para novas conexões
```

Em vez de erros como:

```
ERROR:asyncio:Unhandled exception in client_connected_cb
...
ConnectionResetError: [Errno 104] Connection reset by peer
```

## Considerações Adicionais

1. **Timeout para wait_closed**: Adicionamos um timeout de 2 segundos para a operação `wait_closed()` para evitar bloqueios indefinidos.

2. **Logs Detalhados**: Adicionamos logs mais descritivos para facilitar o diagnóstico e monitoramento.

3. **Cleanup Garantido**: Mesmo em caso de erro, garantimos que a sessão será limpa e os recursos liberados.