# Configuração de Sockets para Múltiplas Portas

Data: 29/04/2025

## Configuração Otimizada de Servidores Socket

Para garantir a mesma qualidade de áudio entre a versão principal (`main.py`) e a versão de ramais dinâmicos (`main_dynamic.py`), foram feitas modificações na inicialização dos servidores socket. Estas mudanças visam padronizar o comportamento em todas as portas do sistema.

### Parâmetros Fundamentais para Qualidade de Áudio

Os seguintes parâmetros foram identificados como críticos para a qualidade da transmissão de áudio:

```python
# Parâmetros otimizados para servidores socket
ia_server = await asyncio.start_server(
    iniciar_servidor_audiosocket_visitante,
    binding_ip,
    porta_ia,
    # Parâmetros adicionais para melhorar performance e estabilidade
    limit=1024*1024,    # 1MB de buffer para evitar perdas de dados
    backlog=100,        # Fila de conexões pendentes mais ampla
    reuse_address=True, # Permite reutilização da porta imediatamente
    start_serving=True  # Começa a servir imediatamente
)
```

### Explicação dos Parâmetros

1. **`limit=1024*1024` (1MB)**: 
   - Define o tamanho do buffer de leitura do socket
   - Um buffer maior evita perda de dados em situações de alta carga
   - Especialmente importante para áudio que requer transmissão contínua
   - O valor padrão (64KB) é muito pequeno para transmissão de áudio

2. **`backlog=100`**:
   - Aumenta a fila de conexões pendentes 
   - Permite que mais chamadas sejam enfileiradas
   - Essencial durante picos de demanda

3. **`reuse_address=True`**:
   - Permite reutilização imediata da porta após fechamento
   - Evita erros de "Address already in use" durante reinicializações
   - Melhora a resiliência do sistema

4. **`start_serving=True`**:
   - Inicia o servidor imediatamente sem aguardar um loop explícito
   - Garante que o servidor comece a aceitar conexões assim que for criado

### Inicialização Paralela

Além da configuração dos sockets individuais, o método de inicialização de múltiplos servidores foi otimizado para inicialização paralela:

```python
async def start_all_servers(self, configs: List[Dict[str, Any]]) -> int:
    success_count = 0
    tasks = []
    
    # Iniciar todos os servidores em paralelo para melhorar performance
    for config in configs:
        task = asyncio.create_task(self._safe_start_server(config))
        tasks.append(task)
    
    # Esperar que todos os servidores sejam iniciados
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Contar os servidores iniciados com sucesso
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Erro ao iniciar servidor: {result}")
        elif result:
            success_count += 1
    
    return success_count
```

Esta abordagem:
- Inicia todos os servidores ao mesmo tempo usando `asyncio.create_task`
- Usa `asyncio.gather` para aguardar a conclusão de todas as tarefas
- Trata exceções individualmente para cada servidor
- Mantém o sistema funcionando mesmo que um socket falhe ao iniciar

### Monitoramento Periódico

Um sistema de monitoramento periódico foi adicionado para verificar a saúde dos servidores:

```python
# Verificar status dos sockets a cada hora
try:
    active_servers = len(extension_manager.server_manager.servers)
    logger.info(f"Status periódico: {active_servers} servidores ativos")
    
    # Exibir informações sobre cada servidor
    for ext_id, server_data in extension_manager.server_manager.servers.items():
        config = server_data.get('config', {})
        ramal = config.get('ramal_ia', 'desconhecido')
        porta = config.get('porta_ia', 0)
        logger.info(f"Servidor {ext_id} (ramal {ramal}): porta {porta} ativo")
        
except Exception as e:
    logger.error(f"Erro ao verificar status dos servidores: {e}")
```

Este monitoramento:
- Verifica o número de servidores ativos a cada hora
- Registra informações detalhadas sobre cada servidor
- Facilita a detecção de problemas de estabilidade a longo prazo

## Implicações e Benefícios

Estas modificações são críticas para:

1. **Consistência de qualidade**: Garante que todos os ramais, independentemente da porta, ofereçam a mesma qualidade de áudio
2. **Robustez**: Melhora a estabilidade do sistema com múltiplos sockets ativos
3. **Observabilidade**: Facilita o monitoramento e detecção de problemas
4. **Escalabilidade**: Permite adicionar mais ramais sem degradação da qualidade

## Próximos Passos

1. Monitorar o desempenho com os novos parâmetros para verificar se o problema de áudio picotado foi resolvido
2. Considerar ajustes adicionais específicos para ambientes com alta carga
3. Implementar alertas baseados no monitoramento de status dos servidores