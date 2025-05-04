# Solução para Problemas de Asyncio em Múltiplas Threads

## Problema Identificado

O sistema apresentava erro ao tentar iniciar o processo de chamada para o morador:

**Erro inicial:**
```
ERROR:conversation_flow:[Flow] Erro no processamento: There is no current event loop in thread 'Dummy-1'.
```

**Erro seguinte após a primeira tentativa de correção:**
```
RuntimeWarning: coroutine 'ConversationFlow.iniciar_processo_chamada' was never awaited
```

Estes erros ocorrem quando tentamos usar funcionalidades assíncronas em um ambiente multi-thread. O processo de chamada ao morador não estava sendo iniciado, parando o fluxo logo após mostrar a mensagem:

```
INFO:call.XXXX:SYNTHESIS_START | {"target": "visitor", "text": "Aguarde enquanto entramos em contato com o morador...", "timestamp": "2025-05-03T21:48:38.094921", "elapsed_seconds": 41.274}
```

## Causa Raiz

1. **Event Loop em Threads**: O erro `There is no current event loop in thread 'Dummy-1'` ocorre porque o asyncio tenta obter um event loop em uma thread onde não existe um.

2. **Coroutine Não Executada**: O erro `coroutine was never awaited` ocorre quando uma coroutine é criada mas não é executada com `await` ou adicionada a um event loop.

3. **Conflito de Ambientes**: O problema fundamental é tentar misturar código assíncrono (asyncio) com código síncrono ou em threads diferentes sem o tratamento adequado.

## Solução Implementada

Para resolver esses problemas, implementamos uma abordagem completamente nova usando threads dedicadas com sua própria execução assíncrona:

### 1. Abordagem com Threads Dedicadas

```python
# Usar uma estratégia diferente: executar a coroutine em uma thread separada
import threading

def run_async_call():
    """Função auxiliar para executar a coroutine em uma thread separada"""
    try:
        logger.info(f"[Flow] Iniciando thread para executar iniciar_processo_chamada")
        # asyncio.run() vai criar um novo event loop e executar a coroutine nele
        asyncio.run(self.iniciar_processo_chamada(session_id, session_manager))
        logger.info(f"[Flow] Thread de chamada concluída com sucesso")
    except Exception as e:
        logger.error(f"[Flow] Erro em thread de chamada: {e}", exc_info=True)

# Iniciar a thread
logger.info(f"[Flow] Criando thread para iniciar_processo_chamada com session_id={session_id}")
call_thread = threading.Thread(target=run_async_call)
call_thread.daemon = True  # Thread em segundo plano
call_thread.start()

# Armazenar referência
self.calling_task = call_thread
```

Essa abordagem tem várias vantagens:

1. **Isolamento de Contexto**: Cada thread cria seu próprio event loop usando `asyncio.run()`, evitando conflitos.
2. **Simplicidade**: Não é necessário gerenciar event loops manualmente.
3. **Robustez**: Funciona independentemente de como o restante da aplicação está estruturado.

### 2. Mesma Abordagem para Hangup

Aplicamos a mesma estratégia ao método `_schedule_active_hangup`:

```python
def run_async_hangup():
    """Função auxiliar para executar o hangup em uma thread separada"""
    try:
        logger.info(f"[Flow] Iniciando thread para executar hangup para session_id={session_id}")
        # asyncio.run() vai criar um novo event loop e executar a coroutine nele
        asyncio.run(send_hangup_after_delay())
        logger.info(f"[Flow] Thread de hangup concluída com sucesso")
    except Exception as e:
        logger.error(f"[Flow] Erro em thread de hangup: {e}", exc_info=True)

# Iniciar a thread
logger.info(f"[Flow] Criando thread para hangup com session_id={session_id}")
hangup_thread = threading.Thread(target=run_async_hangup)
hangup_thread.daemon = True  # Thread em segundo plano
hangup_thread.start()
```

### 3. Logging Detalhado

Adicionamos logs detalhados em todas as etapas críticas para facilitar a identificação de problemas:

- Antes de iniciar a thread
- Dentro da thread quando inicia
- Dentro da thread após concluir
- Em caso de erro

## Por Que Esta Solução Funciona

1. **Encapsulamento Completo**: Cada operação assíncrona é encapsulada em sua própria thread com seu próprio event loop.

2. **Uso de `asyncio.run()`**: Esta função cria um novo event loop, executa a coroutine e fecha o loop automaticamente.

3. **Threads em Segundo Plano**: As threads daemon garantem que o programa principal não será bloqueado.

4. **Tratamento de Erros Isolado**: Erros em uma thread não afetam as demais partes do sistema.

## Benefícios da Solução

1. **Funciona em Qualquer Ambiente**: Funciona tanto em aplicações síncronas quanto assíncronas.

2. **Manutenibilidade**: O código é mais fácil de entender e manter.

3. **Isolamento de Falhas**: Falhas em uma operação assíncrona não comprometem toda a aplicação.

4. **Melhor Logging**: Com logs detalhados, é mais fácil identificar problemas.

## Próximos Passos Recomendados

1. **Monitoramento de Threads**: Considerar adicionar monitoramento para garantir que threads não fiquem "órfãs".

2. **Timeout Global**: Implementar um mecanismo de timeout global para operações assíncronas.

3. **Testes de Carga**: Verificar o comportamento com múltiplas chamadas simultâneas.

4. **Padronização**: Aplicar a mesma abordagem a todos os outros pontos da aplicação que usam asyncio.