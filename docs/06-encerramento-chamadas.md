# Encerramento de Chamadas

Este documento detalha o mecanismo de encerramento ativo de chamadas implementado no sistema AudioSocket-Simple, incluindo o uso do comando KIND_HANGUP e o tratamento de erros relacionados.

## Visão Geral

O encerramento adequado das chamadas é um aspecto crítico do sistema. Ele envolve:

1. A notificação aos participantes da conversa
2. O envio controlado do comando KIND_HANGUP para encerrar o protocolo AudioSocket
3. A liberação eficiente de recursos do sistema
4. O tratamento adequado de desconexões abruptas

## Protocolo AudioSocket e KIND_HANGUP

O protocolo AudioSocket do Asterisk define diferentes tipos de pacotes, incluindo:

- **KIND_ID (0x01)**: Identificação da chamada
- **KIND_SLIN (0x10)**: Dados de áudio no formato SLIN
- **KIND_HANGUP (0x00)**: Sinalização de encerramento da chamada

O pacote KIND_HANGUP tem esta estrutura:
```
┌────────┬──────────┬────────┐
│ 0x00   │ 00 00    │        │
├────────┼──────────┼────────┤
│ 1 byte │ 2 bytes  │ 0 bytes│
│ Tipo   │ Tamanho  │ Dados  │
└────────┴──────────┴────────┘
```

## Mecanismos de Encerramento Implementados

### 1. Encerramento via ConversationFlow

O método `_schedule_active_hangup()` no `ConversationFlow` implementa o encerramento ativo:

```python
def _schedule_active_hangup(self, session_id: str, session_manager, delay=5.0):
    """
    Agenda o envio de KIND_HANGUP ativo após um delay para encerrar a chamada.
    O delay permite que todas as mensagens de áudio sejam reproduzidas primeiro.
    """
    async def send_hangup_after_delay():
        # Aguardar o delay para permitir que as mensagens sejam enviadas
        await asyncio.sleep(delay)
        
        # Verificar se a sessão ainda existe
        session = session_manager.get_session(session_id)
        if not session:
            return
            
        try:
            # Importar ResourceManager para acessar conexões ativas
            from extensions.resource_manager import resource_manager
            import struct
            
            # Enviar KIND_HANGUP para o visitante e morador
            visitor_conn = resource_manager.get_active_connection(session_id, "visitor")
            if visitor_conn and 'writer' in visitor_conn:
                visitor_conn['writer'].write(struct.pack('>B H', 0x00, 0))
                await visitor_conn['writer'].drain()
            
            # Após enviar os KIND_HANGUP, aguardar e finalizar a sessão
            await asyncio.sleep(1.0)
            session_manager.end_session(session_id)
        except Exception as e:
            logger.error(f"[Flow] Erro ao enviar KIND_HANGUP ativo: {e}")
```

### 2. Encerramento via API HTTP

O endpoint `/api/hangup` permite encerrar chamadas através da API REST:

```python
async def hangup_call(self, request: web.Request) -> web.Response:
    """
    Envia sinal de hangup (KIND_HANGUP, 0x00) para uma chamada ativa.
    
    URL: POST /api/hangup
    Body: {"call_id": "uuid-da-chamada", "role": "visitor|resident"}
    """
    # Obter conexão ativa da sessão
    connection = resource_manager.get_active_connection(call_id, role)
    
    # Enviar KIND_HANGUP (0x00)
    writer.write(struct.pack('>B H', 0x00, 0))
    await writer.drain()
    
    # Agendar limpeza completa da sessão após delay
    asyncio.create_task(self._cleanup_session_after_delay(call_id, session_manager))
```

## Tratamento de Erros de Conexão

Uma característica importante é o tratamento adequado de erros de conexão, especialmente `ConnectionResetError` que ocorre quando o cliente desconecta abruptamente:

```python
# Tratar fechamento do socket com robustez
try:
    writer.close()
    # Usar um timeout para wait_closed
    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
except asyncio.TimeoutError:
    logger.info(f"[{call_id}] Timeout ao aguardar fechamento do socket")
except ConnectionResetError:
    # Isso é esperado se o cliente desconectar abruptamente
    logger.info(f"[{call_id}] Conexão resetada pelo cliente - comportamento normal")
except Exception as e:
    # Capturar qualquer outro erro
    logger.warning(f"[{call_id}] Erro ao fechar conexão: {str(e)}")
```

## Fluxo de Encerramento Completo

O encerramento completo de uma chamada segue esta sequência:

1. **Preparação para Encerramento**:
   - O sistema decide encerrar a conversa (por autorização, negação ou timeout)
   - O método `_finalizar()` é chamado no `ConversationFlow`

2. **Envio de Mensagens de Despedida**:
   - Mensagens de despedida são enfileiradas para visitante e morador
   - As mensagens são enviadas, sintetizadas e reproduzidas

3. **Agendamento de KIND_HANGUP**:
   - Um delay é aplicado (5s padrão) para permitir que as mensagens sejam ouvidas
   - Após o delay, o sistema envia KIND_HANGUP para as conexões ativas

4. **Tratamento de Desconexão**:
   - O sistema trata adequadamente desconexões abruptas
   - Registra o ocorrido em logs informativos (não como erros)

5. **Liberação de Recursos**:
   - A sessão é removida do `SessionManager`
   - Conexões são removidas do `ResourceManager`
   - Logs são limpos e recursos liberados

## Testes e Verificação

### Via API

O endpoint de API permite testar facilmente o encerramento:

```bash
# Obter a lista de sessões ativas para identificar o call_id
curl http://localhost:8082/api/status

# Encerrar uma chamada específica
curl -X POST -H "Content-Type: application/json" \
  -d '{"call_id":"UUID-DA-CHAMADA", "role":"visitor"}' \
  http://localhost:8082/api/hangup
```

### Via Conversa

Durante o desenvolvimento, você pode testar usando um comando especial:

```
Visitante: test hangup
IA: Teste de KIND_HANGUP ativado. Ao finalizar, o sistema enviará ativamente o comando de desconexão.
```

## Logs e Monitoramento

Os logs de encerramento fornecem informações detalhadas sobre o processo:

```
INFO:[99203132-1abf-4309-a05e-d7c6624c74af] Enviando KIND_HANGUP ativo para visitante na sessão
INFO:[99203132-1abf-4309-a05e-d7c6624c74af] Conexão resetada pelo cliente após KIND_HANGUP - comportamento normal
INFO:[99203132-1abf-4309-a05e-d7c6624c74af] Socket encerrado e liberado para novas conexões
```

## Benefícios da Implementação

1. **Controle do Ciclo de Vida**: O sistema controla o encerramento, não dependendo do cliente
2. **Experiência Melhorada**: As mensagens de despedida são ouvidas antes do encerramento
3. **Robustez**: Tratamento adequado de erros de conexão
4. **Eficiência**: Liberação adequada de recursos
5. **Observabilidade**: Logs informativos para diagnóstico e monitoramento

## Considerações para o Futuro

1. **Timeout Automático**: Implementar encerramento automático após inatividade prolongada
2. **Detecção de Problemas**: Encerrar chamadas automaticamente em caso de problemas persistentes
3. **Métricas de Duração**: Coletar estatísticas sobre a duração média das chamadas

---

*Próximo documento: [07-processamento-ai.md](07-processamento-ai.md)*