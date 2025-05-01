# 11. Detecção de Voz Avançada com Azure Speech

Este documento descreve as melhorias avançadas implementadas no sistema de detecção de voz usando o Azure Speech SDK, com foco nas otimizações para reduzir falsos positivos e garantir processamento robusto em ambientes desafiadores.

## Visão Geral

O sistema AudioSocket-Simple utiliza o Azure Speech SDK como alternativa ao WebRTCVAD para detecção de voz. Embora a implementação básica do Azure Speech tenha melhorado a precisão da detecção, identificamos alguns desafios específicos:

1. **Falsos positivos** em detecção de fim de fala
2. **Processamento desnecessário** de ruídos e áudios curtos
3. **Loops de feedback** quando o sistema detecta sua própria saída de áudio

Este documento descreve as melhorias implementadas para resolver esses problemas e garantir uma detecção de voz mais robusta e confiável.

## Melhorias Implementadas

### 1. Filtragem Rigorosa de Eventos de Fim de Fala

Uma das principais causas de processamento desnecessário era a detecção de eventos de "fim de fala" sem um correspondente "início de fala". Para resolver isso, implementamos um sistema de filtragem em múltiplas camadas:

```python
# Filtragem rigorosa de eventos de fim de fala
if not self.collecting_audio:
    # Verificar se já tivemos alguma detecção de fala antes
    if not self.speech_detected:
        logger.warning(f"[{self.call_id}] IGNORANDO fim de fala por não haver início de fala detectado anteriormente")
        return
    
    # Verificar se temos algo no pre-buffer e se tem tamanho suficiente
    if not hasattr(self, 'pre_buffer') or not self.pre_buffer or len(self.pre_buffer) < 10:
        logger.warning(f"[{self.call_id}] IGNORANDO fim de fala - pre-buffer muito pequeno ou inexistente")
        return
```

Além disso, implementamos análise de energia do áudio para confirmar que o áudio contém voz real:

```python
# Verificar energia do áudio no pre-buffer para confirmar que é uma fala real
try:
    # Analisar apenas os últimos 10 frames para economia de processamento
    frames_to_analyze = self.pre_buffer[-10:]
    total_energy = 0
    
    for frame in frames_to_analyze:
        samples = struct.unpack('<' + 'h' * (len(frame) // 2), frame)
        frame_energy = sum(sample ** 2 for sample in samples) / len(samples)
        total_energy += frame_energy
    
    avg_energy = total_energy / len(frames_to_analyze)
    ENERGY_THRESHOLD = 800  # Threshold mais alto para confirmar que é fala real
    
    if avg_energy < ENERGY_THRESHOLD:
        logger.warning(f"[{self.call_id}] IGNORANDO fim de fala - energia muito baixa no pre-buffer ({avg_energy:.2f} < {ENERGY_THRESHOLD})")
        return
```

### 2. Verificação de Tamanho Mínimo e Energia do Áudio

Para evitar o processamento de áudio muito curto ou com pouca energia (que pode ser ruído ambiente), implementamos verificações adicionais:

1. **Verificação de Tamanho Mínimo do Buffer**:

```python
# Verificação final de tamanho mínimo do buffer
MINIMUM_VALID_FRAMES = 15  # Aproximadamente 300ms de áudio
if len(self.audio_buffer) < MINIMUM_VALID_FRAMES:
    logger.warning(f"[{self.call_id}] Buffer muito pequeno para processamento ({len(self.audio_buffer)} < {MINIMUM_VALID_FRAMES} frames) - descartando evento")
    # Limpar buffer e cancelar evento
    self.audio_buffer = []
    self.collecting_audio = False
    return
```

2. **Verificação de Energia do Áudio na Transcrição**:

```python
# Verificação para áudio muito curto - provável ruído
if audio_size < 4800:  # Menos de 300ms de áudio (~15 frames)
    print(f"[TRANSCRIÇÃO] Áudio muito curto detectado ({audio_size} bytes, ~{duracao_estimada:.2f}s) - considerando ruído ou resposta curta")
    return "ok"

# Verificar energia do áudio para descartar ruído
try:
    # Calcular energia média
    energy = sum(sample ** 2 for sample in samples) / len(samples)
    ENERGY_THRESHOLD = 600  # Threshold ajustável para considerar áudio válido
    
    if energy < ENERGY_THRESHOLD:
        print(f"[TRANSCRIÇÃO] Áudio com energia muito baixa ({energy:.2f} < {ENERGY_THRESHOLD}) - considerando ruído")
        # Para áudios com pouca energia, tratamos como confirmação
        return "ok"
```

### 3. Pré-Buffer Ampliado

Para garantir que o sistema não perca o início da fala mesmo quando o Azure Speech detecta apenas o final, aumentamos o tamanho do pré-buffer:

```python
# Tamanho do pre-buffer aumentado para 2 segundos de áudio para melhor captura
# Isto é importante para casos onde o sistema detecta o fim da fala sem ter detectado o início
pre_buffer_limit = 100  # 2 segundos (100 frames de 20ms)
```

Isto permite que, mesmo quando o Azure Speech falha em detectar o início da fala mas captura o fim, ainda tenhamos os dados de áudio necessários para processamento.

### 4. Proteção Anti-Loop e Anti-Eco

Para evitar que o sistema entre em loop ao detectar sua própria saída de áudio, implementamos várias camadas de proteção:

1. **Períodos de Guarda Após IA Falar**:

```python
# Se a detecção ocorrer menos de 1.5 segundos após o último reset, ignoramos
ANTI_ECHO_GUARD_PERIOD = 1.5  # segundos
if time_since_last_reset < ANTI_ECHO_GUARD_PERIOD:
    logger.warning(f"[{self.call_id}] IGNORANDO detecção de fala por estar muito próxima ao reset do sistema "
                 f"({time_since_last_reset:.2f}s < {ANTI_ECHO_GUARD_PERIOD}s)")
    return  # Simplesmente ignoramos esta detecção
```

2. **Limpeza de Buffer Após IA Falar**:

```python
# PROTEÇÃO ANTI-ECO ADICIONAL: Limpar quaisquer dados coletados durante o período
# em que a IA estava falando - isso evita processamento de eco
if 'speech_callbacks' in locals() or hasattr(session, 'speech_callbacks'):
    speech_callbacks_obj = speech_callbacks if 'speech_callbacks' in locals() else session.speech_callbacks
    
    if hasattr(speech_callbacks_obj, 'audio_buffer'):
        buffer_size = len(speech_callbacks_obj.audio_buffer)
        if buffer_size > 0:
            logger.info(f"[{call_id}] Limpando buffer de {buffer_size} frames coletados durante fala da IA")
            speech_callbacks_obj.audio_buffer = []
```

## Parâmetros Ajustáveis e Configuração

Vários parâmetros podem ser ajustados para otimizar a detecção de voz para diferentes ambientes:

1. **ANTI_ECHO_GUARD_PERIOD**: Tempo em segundos para ignorar eventos de fala após a IA falar (padrão: 1.5s)
2. **ENERGY_THRESHOLD**: Limite de energia para considerar um áudio como voz real (padrão: 600 para transcrição, 800 para validação do fim de fala)
3. **MINIMUM_VALID_FRAMES**: Número mínimo de frames para considerar uma fala válida (padrão: 15 frames ou ~300ms)
4. **pre_buffer_limit**: Tamanho do buffer de pré-captura para garantir que não perdemos o início da fala (padrão: 100 frames ou 2 segundos)

Estes parâmetros podem ser ajustados com base nas características do ambiente:

- Em ambientes mais silenciosos, os thresholds de energia podem ser reduzidos
- Em ambientes ruidosos, os thresholds de energia podem ser aumentados
- Em ambientes com eco significativo, o ANTI_ECHO_GUARD_PERIOD pode ser aumentado

## Resultados e Benefícios

As melhorias implementadas resultaram em:

1. **Redução drástica de falsos positivos** na detecção de fim de fala
2. **Eliminação de loops de processamento** causados por detecção de eco
3. **Melhor qualidade de transcrição** ao ignorar áudio com pouca energia ou muito curto
4. **Sistema mais robusto** em ambientes desafiadores com ruído ou eco

## Logs e Diagnóstico

O sistema agora gera logs detalhados que facilitam o diagnóstico de problemas:

```
INFO:[call_id] Atualizado timestamp de fim de fala: <timestamp>
WARNING:[call_id] IGNORANDO fim de fala - energia muito baixa no pre-buffer (<energy> < <threshold>)
INFO:[call_id] Fim de fala CONFIRMADO por energia do áudio (<energy> > <threshold>)
WARNING:[call_id] Buffer muito pequeno para processamento (<buffer_size> < <min_frames> frames) - descartando evento
```

Estes logs permitem identificar padrões e ajustar os parâmetros conforme necessário.

## Limitações e Trabalho Futuro

Embora as melhorias implementadas tenham resolvido os principais problemas, algumas limitações permanecem:

1. Os thresholds de energia são fixos e podem não ser ideais para todos os ambientes
2. O sistema ainda depende da precisão do Azure Speech SDK para detecção inicial
3. Áudios muito curtos (como "sim" ou "não") podem ser incorretamente classificados como ruído

Possíveis melhorias futuras incluem:

1. Implementação de aprendizado adaptativo para ajustar thresholds com base no ambiente
2. Combinação de múltiplos métodos de detecção para maior precisão
3. Otimização específica para reconhecimento de comandos curtos

## Conclusão

A implementação avançada de detecção de voz com Azure Speech permite um sistema muito mais robusto e confiável para o AudioSocket-Simple, especialmente em ambientes desafiadores. As múltiplas camadas de proteção contra falsos positivos e detecção de eco garantem uma experiência de conversação mais natural e fluida para os usuários.

---

*Próximo documento: [12-desenvolvimento-futuro.md](12-desenvolvimento-futuro.md)*