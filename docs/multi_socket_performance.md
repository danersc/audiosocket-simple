# Otimização de Performance para Múltiplos Sockets

Data: 29/04/2025

## Problema Identificado

Ao executar a aplicação em modo de ramais dinâmicos (`main_dynamic.py`) com múltiplos sockets ativos simultaneamente, foram observados problemas de qualidade de áudio:

- Áudio picotado ou com falhas
- Inconsistência na qualidade da transmissão
- Possível competição por recursos entre múltiplos sockets

Estes problemas não ocorriam quando a aplicação era executada no modo tradicional (`main.py`) com apenas um par de servidores socket.

## Solução Implementada

Foi desenvolvido um sistema de gerenciamento de recursos (`ResourceManager`) para controlar o acesso a recursos críticos e evitar sobrecarga quando múltiplas chamadas estão ativas simultaneamente. A solução inclui:

### 1. Limitação de Processamento Concorrente

- Limitação do número máximo de transcrições simultâneas
- Limitação do número máximo de sínteses de voz simultâneas
- Uso de semáforos assíncronos para controle de acesso a recursos

```python
# Controle de concorrência
self.transcription_semaphore = asyncio.Semaphore(self.max_concurrent_transcriptions)
self.synthesis_semaphore = asyncio.Semaphore(self.max_concurrent_synthesis)
```

### 2. Ajuste Dinâmico Baseado no Hardware

O sistema ajusta automaticamente seus limites com base nos recursos disponíveis:

```python
def _configure_based_on_hardware(self):
    cpu_count = psutil.cpu_count(logical=False) or 2
    mem_gb = psutil.virtual_memory().total / (1024**3)
    
    # Ajustar limites com base em CPU e memória
    if cpu_count >= 4 and mem_gb >= 8:
        # Hardware robusto
        self.max_concurrent_transcriptions = max(3, min(cpu_count - 1, 6))
        # ...
```

### 3. Throttling Adaptativo de Áudio

Implementação de controle adaptativo da taxa de transmissão de áudio:

```python
# Verificar se precisamos aplicar throttling baseado na carga do sistema
should_throttle = resource_manager.should_throttle_audio()
transmission_delay = TRANSMISSION_DELAY_MS * 1.5 if should_throttle else TRANSMISSION_DELAY_MS
```

### 4. Monitoramento e Métricas

Sistema de métricas para monitorar o desempenho de cada sessão:

```python
def record_transcription(self, session_id: str, duration_ms: float):
    """Registra métricas de uma transcrição."""
    if session_id in self.metrics:
        self.metrics[session_id]['transcription_count'] += 1
        self.metrics[session_id]['transcription_time_ms'] += duration_ms
```

### 5. Limpeza Apropriada de Recursos

Garantia que recursos são liberados corretamente ao final de cada chamada:

```python
def unregister_session(self, session_id: str):
    """Remove uma sessão terminada."""
    if session_id in self.active_sessions:
        self.active_sessions.remove(session_id)
    # ...
```

## Integração com Componentes Existentes

O `ResourceManager` foi integrado aos componentes existentes:

1. **speech_service.py**: Controle de concorrência em transcrições e sínteses
2. **audiosocket_handler.py**: Registro de sessões e ajuste dinâmico da taxa de envio de áudio
3. **session_manager.py**: Gerenciamento do ciclo de vida das sessões

## Benefícios

- **Melhor qualidade de áudio**: Evita competição por recursos que causava áudio picotado
- **Maior estabilidade**: Previne sobrecarga do sistema com muitas chamadas simultâneas
- **Escalabilidade**: Permite gerenciar efetivamente muitos sockets concorrentes
- **Utilização eficiente de recursos**: Adapta-se automaticamente ao hardware disponível

## Configuração

As configurações podem ser ajustadas através de variáveis de ambiente:

```
MAX_CONCURRENT_TRANSCRIPTIONS=3  # Número máximo de transcrições simultâneas
MAX_CONCURRENT_SYNTHESIS=3       # Número máximo de sínteses simultâneas
```

## Monitoramento

O sistema pode ser monitorado através dos logs, que agora incluem informações sobre:

- Carga do CPU e memória durante o processamento
- Número de sessões ativas e seus estados
- Tempo gasto em transcrições e sínteses
- Aplicação de throttling quando necessário

## Próximos Passos

- Implementar dashboard visual para monitoramento em tempo real
- Adicionar mais métricas para identificar outros possíveis gargalos
- Explorar mecanismos mais avançados de priorização de tráfego
- Considerar implementação de caching mais agressivo para respostas comuns