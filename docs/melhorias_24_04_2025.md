# Melhorias de Performance - 24/04/2025

## Resumo das Melhorias Implementadas

Foram realizadas diversas otimizações no sistema de portaria inteligente para reduzir a latência e melhorar a experiência do usuário. As principais alterações incluem:

### 1. Parâmetros Configuráveis no `config.json`

Os seguintes parâmetros foram adicionados e otimizados:

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

- **Redução do threshold de silêncio** de 2.0s para 1.5s
- **Redução do delay de transmissão** de 20ms para 10ms
- **Redução do delay pós-áudio** de 0.5s para 0.3s
- **Redução do buffer de frames** de 25 para 15 frames

### 2. Sistema de Cache para Síntese de Voz

Implementamos um sistema de cache para mensagens sintetizadas:

```python
# Verificar cache antes de sintetizar
hash_texto = hashlib.md5(texto.encode('utf-8')).hexdigest()
cache_path = os.path.join(CACHE_DIR, f"{hash_texto}.slin")

# Se já existe no cache, retornar o arquivo de áudio
if os.path.exists(cache_path):
    with open(cache_path, 'rb') as f:
        return f.read()
```

- **Cache usando hash MD5** para identificar mensagens
- **Pré-carregamento das frases comuns** ao iniciar o sistema
- **Armazenamento em `audio/cache/`** para reutilização rápida

### 3. Migração para Groq

A troca da API da OpenAI para Groq proporcionou:
- **Inferência mais rápida** para análise de intenções
- **Latência reduzida** no processamento de texto
- **Menores custos** por solicitação

## Resultados de Performance

Comparação detalhada entre a versão anterior e a nova versão otimizada:

### 1. Síntese de Voz (Caching)
- **Antes**: 652-972ms por síntese
- **Agora**: Maioria abaixo de 1ms, exceto por uma síntese (613ms)
- **Melhoria**: ~99% para frases comuns cacheadas (0.5ms vs 652ms)

### 2. Transmissão de Áudio
- **Antes**: 3765-5144ms (média ~4260ms)
- **Agora**: 1535-2656ms (média ~2198ms)
- **Melhoria**: ~48% mais rápido

### 3. Inferência AI (Groq)
- **Antes**: 
  - Intent type: 3600ms
  - Nome do interlocutor: 4285ms 
  - Apartment/resident: 1788-2763ms
  - Total AI: 3974-7900ms
- **Agora**:
  - Intent type: 889ms (75% mais rápido)
  - Nome do interlocutor: 773-1307ms (81% mais rápido)
  - Apartment/resident: 1207-1318ms (52% mais rápido)
  - Total AI: 1213-2636ms (67% mais rápido)

### 4. Detecção de Silêncio
- **Antes**: 2000ms padrão
- **Agora**: 1500ms (confirmado nos logs ~1505ms)
- **Melhoria**: 25% mais rápido

### 5. Tempo Total de Interação
- Tempo médio para processar cada entrada do usuário:
  - **Antes**: ~14-23 segundos
  - **Agora**: ~9-16 segundos
  - **Melhoria**: ~40% mais rápido

## Próximos Passos Recomendados

Para melhorias futuras, recomendamos:

1. **Paralelização do processamento AI**:
   - Executar tarefas de extração de intenção simultaneamente usando `asyncio.gather()`
   - Atualmente são executadas sequencialmente (tipo, nome, apartamento)

2. **Otimização da transcrição**:
   - Implementar transcrição em streaming para processamento contínuo
   - Avaliar opções para usar modelo de transcrição mais leve quando possível

3. **Monitoramento contínuo**:
   - Adicionar dashboards para análise de desempenho em tempo real
   - Identificar e otimizar outros gargalos conforme uso aumenta

## Conclusão

As otimizações implementadas reduziram significativamente o tempo de resposta do sistema, criando uma experiência conversacional mais natural e fluida. A combinação de cache de síntese, redução de atrasos e a troca para Groq proporcionou uma melhoria geral de aproximadamente 40% no tempo de interação.