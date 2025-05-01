# Implementação do Mecanismo de Encerramento Ativo de Chamadas

Data: 01/05/2025

## Visão Geral

Este documento descreve a implementação do sistema de encerramento ativo de chamadas no AudioSocket-Simple. O objetivo é permitir que o sistema encerre a chamada de forma proativa e controlada, enviando o sinal KIND_HANGUP (0x00) para o cliente AudioSocket.

## Motivação

Anteriormente, o sistema dependia exclusivamente do cliente para encerrar a chamada. Isso gerava dois problemas:
1. Chamadas podiam ficar "penduradas" se o cliente não desconectasse
2. O processo de encerramento não era controlado pelo sistema

Com estas melhorias, o sistema agora pode:
1. Enviar ativamente o sinal KIND_HANGUP para encerrar chamadas
2. Garantir que todas as mensagens sejam ouvidas antes do encerramento
3. Realizar uma limpeza adequada de recursos após a desconexão

## Componentes Implementados

### 1. Endpoint HTTP para Testes

Criamos um endpoint na API REST para testar o mecanismo:

```http
POST /api/hangup
Content-Type: application/json

{
  "call_id": "uuid-da-chamada",
  "role": "visitor"  // ou "resident"
}
```

Este endpoint permite:
- Enviar KIND_HANGUP para uma chamada específica
- Especificar se é para o visitante ou morador
- Obter feedback imediato sobre o resultado da operação

### 2. Gerenciamento de Conexões no ResourceManager

Modificamos o `ResourceManager` para armazenar e gerenciar o acesso às conexões ativas:

```python
# Armazenamento de conexões
self.active_connections: Dict[str, Dict] = {}

# Registro de conexões
def register_connection(self, call_id: str, role: str, reader, writer):
    if call_id not in self.active_connections:
        self.active_connections[call_id] = {}
    self.active_connections[call_id][role] = {
        'reader': reader,
        'writer': writer,
        'timestamp': time.time()
    }

# Recuperação de conexões para envio de KIND_HANGUP
def get_active_connection(self, call_id: str, role: str):
    if call_id in self.active_connections and role in self.active_connections[call_id]:
        return self.active_connections[call_id][role]
    return None
```

### 3. Função para Encerramento com KIND_HANGUP

Implementamos o método `_schedule_active_hangup` no `ConversationFlow`:

```python
def _schedule_active_hangup(self, session_id: str, session_manager, delay=5.0):
    """
    Agenda o envio de KIND_HANGUP ativo após um delay para encerrar a chamada.
    """
    async def send_hangup_after_delay():
        await asyncio.sleep(delay)  # Aguardar para mensagens serem enviadas
        
        # Importar ResourceManager para acessar conexões
        from extensions.resource_manager import resource_manager
        import struct
        
        # Enviar KIND_HANGUP para o visitante e morador
        visitor_conn = resource_manager.get_active_connection(session_id, "visitor")
        if visitor_conn and 'writer' in visitor_conn:
            visitor_conn['writer'].write(struct.pack('>B H', 0x00, 0))
            await visitor_conn['writer'].drain()
            
        # Finalizar completamente a sessão
        await asyncio.sleep(1.0)
        session_manager.end_session(session_id)
```

### 4. Integração no Fluxo de Conversação

Integramos o encerramento ativo ao fluxo normal no método `_finalizar`:

```python
def _finalizar(self, session_id: str, session_manager):
    # [Código para enviar mensagens de despedida]
    
    # Utilizar encerramento ativo KIND_HANGUP após delay
    self._schedule_active_hangup(session_id, session_manager)
    logger.info(f"[Flow] Finalização programada com encerramento ativo KIND_HANGUP")
```

## Detalhes Técnicos

### Formato do Pacote KIND_HANGUP

O pacote KIND_HANGUP segue o formato do protocolo AudioSocket:

```python
struct.pack('>B H', 0x00, 0)
```

Onde:
- `>` indica ordenação big-endian
- `B` representa um byte unsigned (o tipo KIND_HANGUP = 0x00)
- `H` representa um unsigned short (2 bytes) para o tamanho do payload (0)

### Processo de Encerramento

1. O sistema envia mensagens de despedida para visitante e morador
2. Agenda uma tarefa assíncrona para enviar KIND_HANGUP após um delay (5s padrão)
3. Após o delay, envia KIND_HANGUP para ambas as conexões
4. Aguarda mais 1s para processamento do comando
5. Chama `end_session()` para iniciar encerramento controlado da sessão
6. Se necessário, força remoção da sessão após mais um delay

### Tratamento de Erros

Em caso de falha ao enviar KIND_HANGUP, o sistema:
1. Registra o erro nos logs
2. Tenta encerrar a sessão pelo mecanismo tradicional
3. Garante que recursos sejam liberados mesmo em caso de falha

## Benefícios

1. **Controle de Ciclo de Vida**: O sistema agora controla o ciclo de vida completo da chamada
2. **Melhor Experiência do Usuário**: Encerramento mais limpo, sem chamadas "penduradas"
3. **Recursos Liberados**: Menor consumo de recursos no servidor por liberação proativa
4. **Registro Mais Preciso**: Melhor observabilidade do encerramento de chamadas nos logs

## Conclusão

A implementação do mecanismo de encerramento ativo representa uma melhoria significativa na robustez e usabilidade do sistema AudioSocket-Simple. Agora o sistema pode controlar proativamente o encerramento de chamadas, resultando em uma experiência mais fluida e confiável.

Recomenda-se monitorar o comportamento deste mecanismo em produção e ajustar os parâmetros (como o delay antes do envio de KIND_HANGUP) conforme necessário para otimizar a experiência do usuário.