# Otimizações e Melhorias de Performance

Este documento detalha as otimizações implementadas no sistema AudioSocket-Simple para melhorar seu desempenho, reduzir latência e proporcionar uma experiência mais fluida aos usuários.

## Visão Geral das Otimizações

O sistema passou por várias otimizações para melhorar a performance em diferentes áreas:

1. **Processamento de Áudio**: Ajustes nos parâmetros de detecção de voz e transmissão
2. **Síntese de Voz**: Implementação de cache para mensagens comuns
3. **Inferência de IA**: Migração para serviços mais rápidos
4. **Gestão de Recursos**: Controle de concorrência e throttling adaptativo
5. **Gerenciamento de Memória**: Otimizações para evitar vazamentos de recursos

## Parâmetros Configuráveis

Os seguintes parâmetros foram ajustados e tornados configuráveis via `config.json`:

```json
{
    "system": {
        "silence_threshold_seconds": 1.5
    },
    "audio": {
        "transmission_delay_ms": 10,
        "post_audio_delay_seconds": 0.3,
        "discard_buffer_frames": 15
    }
}
```

### Valores Otimizados

| Parâmetro | Valor Anterior | Valor Atual | Impacto |
|-----------|----------------|-------------|---------|
| `silence_threshold_seconds` | 2.0s | 1.5s | Detecção mais rápida do fim da fala |
| `transmission_delay_ms` | 20ms | 10ms | Transmissão de áudio mais fluida |
| `post_audio_delay_seconds` | 0.5s | 0.3s | Retorno mais rápido ao modo de escuta |
| `discard_buffer_frames` | 25 | 15 | Menos frames descartados após IA falar |

## Sistema de Cache para Síntese de Voz

Uma das otimizações mais significativas foi a implementação de um sistema de cache para mensagens sintetizadas:

```python
# Verificar cache antes de sintetizar
hash_texto = hashlib.md5(texto.encode('utf-8')).hexdigest()
cache_path = os.path.join(CACHE_DIR, f"{hash_texto}.slin")

# Se já existe no cache, retornar o arquivo de áudio
if os.path.exists(cache_path):
    with open(cache_path, 'rb') as f:
        return f.read()
```

### Benefícios do Cache

- **Redução Drástica de Latência**: De 652-972ms por síntese para <1ms em frases cacheadas
- **Economia de Recursos**: Menor uso de API e CPU
- **Menor Carga em Azure**: Menos chamadas à API externa
- **Pré-carregamento Estratégico**: Frases comuns são pré-sintetizadas ao iniciar o sistema

## Migração para Modelos de IA Mais Rápidos (Groq)

A troca da API da OpenAI para Groq trouxe melhorias significativas:

| Etapa de processamento | Antes (OpenAI) | Depois (Groq) | Melhoria |
|------------------------|----------------|---------------|----------|
| Intent type | 3600ms | 889ms | 75% mais rápido |
| Nome do interlocutor | 4285ms | 773-1307ms | 81% mais rápido |
| Apartment/resident | 1788-2763ms | 1207-1318ms | 52% mais rápido |
| Total AI | 3974-7900ms | 1213-2636ms | 67% mais rápido |

## Gestão de Recursos e Throttling Adaptativo

O sistema implementa um `ResourceManager` que monitora a utilização de recursos e ajusta dinamicamente o comportamento:

```python
def should_throttle_audio(self):
    """
    Determina se a transmissão de áudio deve ser limitada com base na carga do sistema.
    Retorna True se o sistema estiver sobrecarregado.
    """
    system_load = self.get_system_load()
    cpu_percent = system_load.get('cpu_percent', 0)
    active_sessions = system_load.get('active_sessions', 0)
    
    # Se temos muitas sessões ativas E a CPU está alta, ativamos throttling
    return active_sessions > 3 and cpu_percent > 85
```

Quando o sistema está sobrecarregado, ajustes automáticos são aplicados:

```python
# Verificar se precisamos aplicar throttling baseado na carga do sistema
should_throttle = resource_manager.should_throttle_audio()
transmission_delay = TRANSMISSION_DELAY_MS * 1.5 if should_throttle else TRANSMISSION_DELAY_MS
```

## Semáforos para Limitar Processamento Concorrente

Para evitar sobrecarga em operações intensivas, o sistema usa semáforos:

```python
# Limite de simultaneidade
self.max_concurrent_transcriptions = int(os.getenv('MAX_CONCURRENT_TRANSCRIPTIONS', '3'))
self.max_concurrent_synthesis = int(os.getenv('MAX_CONCURRENT_SYNTHESIS', '3'))

# Semáforos para controle de acesso
self.transcription_semaphore = asyncio.Semaphore(self.max_concurrent_transcriptions)
self.synthesis_semaphore = asyncio.Semaphore(self.max_concurrent_synthesis)

async def acquire_transcription_lock(self, session_id: str):
    """Adquire um lock para transcrição"""
    await self.transcription_semaphore.acquire()
    self.set_transcribing(session_id, True)
    return True
```

## Otimizações de Socket

Os servidores de socket foram configurados para garantir melhor desempenho:

```python
# Servidor com parâmetros otimizados
server = await asyncio.start_server(
    handler,
    binding_ip,
    porta,
    limit=1024*1024,  # 1MB buffer
    start_serving=True
)
```

## Timeouts e Tratamento de Erros

Todos os timeouts são configuráveis e têm tratamento de erro adequado:

```python
try:
    # Timeout para evitar bloqueio indefinido
    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
except asyncio.TimeoutError:
    logger.info(f"[{call_id}] Timeout ao aguardar fechamento do socket")
```

## Resultados de Performance

Comparação detalhada entre a versão anterior e a nova versão otimizada:

### 1. Síntese de Voz (Caching)
- **Antes**: 652-972ms por síntese
- **Agora**: Maioria abaixo de 1ms, exceto por sínteses novas
- **Melhoria**: ~99% para frases comuns cacheadas

### 2. Transmissão de Áudio
- **Antes**: 3765-5144ms (média ~4260ms)
- **Agora**: 1535-2656ms (média ~2198ms)
- **Melhoria**: ~48% mais rápido

### 3. Tempo Total de Interação
- Tempo médio para processar cada entrada do usuário:
  - **Antes**: ~14-23 segundos
  - **Agora**: ~9-16 segundos
  - **Melhoria**: ~40% mais rápido

## Próximos Passos Recomendados

Para melhorias futuras de performance, recomendamos:

1. **Paralelização do processamento AI**:
   - Executar tarefas de extração de intenção simultaneamente usando `asyncio.gather()`
   - Atualmente são executadas sequencialmente (tipo, nome, apartamento)

2. **Otimização da transcrição**:
   - Implementar transcrição em streaming para processamento contínuo
   - Avaliar opções para usar modelo de transcrição mais leve quando possível

3. **Monitoramento contínuo**:
   - Adicionar dashboards para análise de desempenho em tempo real
   - Identificar e otimizar outros gargalos conforme uso aumenta

## Configuração Baseada em Hardware

O sistema pode se adaptar ao hardware disponível:

```python
def _configure_based_on_hardware(self):
    """Configura limites baseados nos recursos do hardware."""
    try:
        cpu_count = psutil.cpu_count(logical=False) or 2
        mem_gb = psutil.virtual_memory().total / (1024**3)
        
        # Ajustar limites com base em CPU e memória
        if cpu_count >= 4 and mem_gb >= 8:
            # Hardware robusto
            self.max_concurrent_transcriptions = max(3, min(cpu_count - 1, 6))
            self.max_concurrent_synthesis = max(3, min(cpu_count - 1, 6))
        elif cpu_count >= 2 and mem_gb >= 4:
            # Hardware médio
            self.max_concurrent_transcriptions = 2
            self.max_concurrent_synthesis = 2
        else:
            # Hardware limitado
            self.max_concurrent_transcriptions = 1
            self.max_concurrent_synthesis = 1
    except Exception as e:
        logger.warning(f"Erro ao configurar baseado no hardware: {e}. Usando valores padrão.")
```

## Conclusão

As otimizações implementadas reduziram significativamente o tempo de resposta do sistema, criando uma experiência conversacional mais natural e fluida. A combinação de cache de síntese, redução de atrasos e a troca para Groq proporcionou uma melhoria geral de aproximadamente 40% no tempo de interação.

---

*Próximo documento: [09-testes.md](09-testes.md)*