# Suporte a Múltiplas Chamadas Simultâneas

Este documento explica como o sistema AudioSocket Simple gerencia múltiplas chamadas simultâneas em diferentes portas e sockets.

## Arquitetura para Chamadas Simultâneas

O sistema foi projetado para suportar múltiplas chamadas simultâneas, com cada chamada sendo gerenciada de forma isolada através de portas dedicadas e identificadores de sessão únicos.

### Componentes Principais

1. **ServerManager**: Gerencia múltiplos servidores socket em diferentes portas
2. **SessionManager**: Controla o isolamento entre diferentes chamadas
3. **ExtensionManager**: Coordena a configuração de múltiplos ramais
4. **Handlers Assíncronos**: Processam conexões de forma não-bloqueante

## Capacidade de Múltiplas Conexões

O sistema suporta múltiplas chamadas simultâneas através de:

### 1. Servidores Socket Dinâmicos

```python
# Em server_manager.py
async def start_all_servers(self, configs: List[Dict[str, Any]]) -> int:
    success_count = 0
    
    for config in configs:
        try:
            await self.start_server(config)
            success_count += 1
        except Exception as e:
            logger.error(f"Falha ao iniciar servidor para ramal {config['ramal_ia']}: {e}")
    
    return success_count
```

Cada ramal configura dois servidores socket:
- Um servidor para visitantes na `porta_ia`
- Um servidor para moradores na `porta_retorno` 

### 2. Isolamento de Sessões

```python
# Em session_manager.py
def create_session(self, session_id: Optional[str] = None) -> SessionData:
    if not session_id:
        # Gerar UUID para identificação da sessão
        session_id = str(uuid4())
        
    if session_id not in self.sessions:
        self.sessions[session_id] = SessionData(session_id, self.extension_manager)
    return self.sessions[session_id]
```

Cada chamada recebe:
- Um UUID único para identificação da sessão
- Filas de mensagens dedicadas
- Um objeto `ConversationFlow` próprio
- Sinais de controle de terminação independentes

### 3. Rastreamento de Portas e Ramais

```python
# Em server_manager.py
# Mapeamento de porta para extension_id para identificação rápida
self.port_to_extension: Dict[int, int] = {}

# Mapeamento de ramal para extension_id
self.extension_to_id: Dict[str, int] = {}
```

Esses mapeamentos permitem:
- Identificar rapidamente qual ramal está associado a qual porta
- Rotear mensagens corretamente entre os componentes do sistema
- Manter o isolamento entre diferentes chamadas

## Fluxo de Múltiplas Chamadas

Quando múltiplas chamadas são recebidas:

1. **Identificação de Porta**:
   - Quando uma conexão chega, o sistema identifica a porta e determina qual ramal está sendo acessado
   - O `ServerManager` mantém mapeamentos para associar portas a ramais específicos

2. **Criação/Recuperação de Sessão**:
   - Cada conexão recebe um UUID de sessão único
   - O `SessionManager` cria estruturas de dados isoladas para cada sessão

3. **Processamento Paralelo**:
   - Tarefas assíncronas (`asyncio.Task`) são criadas para processar cada conexão
   - Múltiplas conexões são gerenciadas concorrentemente sem bloqueio

4. **Enfileiramento de Mensagens**:
   - As mensagens são enfileiradas em filas específicas para cada sessão
   - Não há vazamento de dados entre diferentes sessões

5. **Terminação Independente**:
   - Cada sessão tem controles independentes de terminação
   - Uma chamada pode ser encerrada sem afetar outras chamadas ativas

## Gerenciamento de Recursos

O sistema gerencia recursos para múltiplas chamadas através de:

### 1. Alocação Dinâmica de Portas

```python
# Em server_manager.py
if not self.is_port_available(binding_ip, porta_ia):
    logger.warning(f"Porta {porta_ia} não está disponível para ramal IA {ramal_ia}")
    # Tenta encontrar uma porta alternativa
    for alt_port in range(porta_ia + 1, porta_ia + 100, 2):
        if self.is_port_available(binding_ip, alt_port):
            logger.info(f"Usando porta alternativa {alt_port} para ramal IA {ramal_ia}")
            porta_ia = alt_port
            config['porta_ia'] = alt_port
            break
```

Se uma porta estiver ocupada, o sistema tenta automaticamente usar uma porta alternativa.

### 2. Limpeza de Recursos

```python
# Em server_manager.py
async def stop_server(self, extension_id: int) -> bool:
    # ...
    # Remover mapeamentos
    porta_ia = config['porta_ia']
    porta_retorno = config['porta_retorno']
    ramal_ia = config['ramal_ia']
    
    if porta_ia in self.port_to_extension:
        del self.port_to_extension[porta_ia]
    # ...
```

Quando uma chamada termina, todos os recursos associados são liberados adequadamente.

### 3. Terminação Graciona

```python
# Em session_manager.py
def _complete_session_termination(self, session_id: str):
    if session_id in self.sessions:
        del self.sessions[session_id]
        logger.info(f"[SessionManager] Sessão {session_id} finalizada e completamente removida.")
```

O sistema assegura que todas as conexões sejam encerradas corretamente antes de liberar recursos.

## Limites e Considerações

O sistema pode gerenciar múltiplas chamadas simultâneas, mas existem alguns limites a considerar:

1. **Recursos do Sistema**: O número máximo de chamadas simultâneas é limitado pelos recursos disponíveis (CPU, memória, descritores de arquivo).

2. **Portas Disponíveis**: O sistema precisa de duas portas por ramal. Se muitas portas já estiverem em uso, pode haver limitação.

3. **Carga de Processamento**: Cada chamada consome recursos de CPU para processamento de áudio e IA. Muitas chamadas simultâneas podem degradar a qualidade do serviço.

4. **Degradação Graciona**: O sistema foi projetado para degradar graciosamente sob carga, priorizando a manutenção de chamadas existentes em vez de aceitar novas chamadas quando os recursos estão esgotados.

## Conclusão

O sistema AudioSocket Simple está preparado para lidar com múltiplas chamadas simultâneas em diferentes portas, fornecendo:

- **Isolamento**: Cada sessão é completamente isolada das demais
- **Escalabilidade**: Configurações dinâmicas de ramais permitem adicionar capacidade
- **Resiliência**: Falhas em uma chamada não afetam outras chamadas em andamento
- **Gerenciamento de Recursos**: Alocação e liberação adequada de recursos para cada chamada

Para testar múltiplas chamadas simultâneas, execute `test_dual_client.py` em diferentes terminais, especificando diferentes portas para cada instância de teste.