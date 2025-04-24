# Mecanismo de Encerramento de Chamadas

Este documento descreve o mecanismo implementado para encerrar chamadas de forma controlada e graciosamente no sistema de portaria inteligente.

## Visão Geral

Quando uma sessão de conversa precisa ser encerrada (por autorização/negação do morador, timeout, ou outro motivo), o sistema deve:

1. Notificar os participantes (visitante e/ou morador) com mensagens de despedida apropriadas
2. Permitir que essas mensagens sejam ouvidas antes de encerrar a conexão
3. Liberar os recursos associados à sessão de forma controlada
4. Registrar adequadamente o encerramento nos logs

## Fluxo de Encerramento

### 1. Inicialização do Encerramento

O encerramento é iniciado no método `_finalizar` do `ConversationFlow`:

```python
def _finalizar(self, session_id: str, session_manager):
    # Mensagens de despedida adequadas ao contexto
    session_manager.enfileirar_resident(session_id, "A conversa foi finalizada...")
    session_manager.enfileirar_visitor(session_id, "Sua entrada foi autorizada...")
    
    # Sinaliza que deve encerrar a sessão
    session_manager.end_session(session_id)
```

### 2. Sinalização para Encerramento

O `SessionManager` sinaliza que as conexões devem ser encerradas:

```python
def end_session(self, session_id: str):
    session = self.get_session(session_id)
    if not session:
        return
        
    # Sinaliza para as tarefas que devem encerrar
    session.terminate_visitor_event.set()
    session.terminate_resident_event.set()
```

### 3. Detecção do Sinal nas Tasks

As tarefas de recebimento e envio de áudio verificam periodicamente por sinais de terminação:

```python
while True:
    # Verificar sinal de terminação
    if session.terminate_visitor_event.is_set():
        logger.info(f"[{call_id}] Detectado sinal para encerrar...")
        break
    
    try:
        # Timeout permite verificar terminação periodicamente
        header = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
    except asyncio.TimeoutError:
        continue
```

### 4. Despedida e Encerramento Gracioso

As tarefas de envio de mensagens detectam o sinal e enviam mensagens de despedida:

```python
if session.terminate_visitor_event.is_set() and not final_message_sent:
    # Enviar mensagem de despedida e encerrar
    await send_goodbye_and_terminate(writer, session, call_id, "visitante", call_logger)
    
    # Completar encerramento
    session_manager._complete_session_termination(call_id)
    break
```

### 5. Limpeza Final

Após as despedidas, o `SessionManager` completa a limpeza:

```python
def _complete_session_termination(self, session_id: str):
    if session_id in self.sessions:
        del self.sessions[session_id]
        logger.info(f"[SessionManager] Sessão {session_id} finalizada...")
```

## Mensagens de Despedida

Configuráveis via `config.json`:

```json
"call_termination": {
    "enabled": true,
    "goodbye_messages": {
        "visitor": {
            "authorized": "Sua entrada foi autorizada. Obrigado...",
            "denied": "Sua entrada não foi autorizada. Obrigado...",
            "default": "Obrigado por utilizar nossa portaria..."
        },
        "resident": {
            "default": "Obrigado pela sua resposta. Encerrando..."
        }
    }
}
```

## Prazos e Timeouts

O sistema permite ajustar:

- `goodbye_delay_seconds`: Tempo de espera após a mensagem de despedida (default: 3.0s)
- `TERMINATE_CHECK_INTERVAL`: Intervalo para verificar sinais de terminação (default: 0.5s)

## Implementação Técnica

Principais componentes:

1. **Flags de terminação**: `terminate_visitor_event` e `terminate_resident_event` na classe `SessionData`

2. **Funções auxiliares**:
   - `check_terminate_flag()`: Monitora sinais de terminação
   - `send_goodbye_and_terminate()`: Envia mensagem de despedida e encerra conexão

3. **Modificações nos loops de processamento**:
   - Verificação periódica de sinais de terminação
   - Timeout em operações de leitura para permitir verificação
   - Flags para controlar envio de mensagens de despedida apenas uma vez

## Benefícios

- Encerramento mais natural para os usuários (sem cortes abruptos)
- Liberação controlada de recursos do sistema
- Maior robustez contra desconexões inesperadas
- Logs mais detalhados sobre o processo de encerramento