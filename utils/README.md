# Sistema de Logs para Análise de Desempenho

Este sistema de logs foi projetado para monitorar e analisar o desempenho das chamadas no projeto AudioSocket-Simple. O sistema registra detalhadamente cada etapa do processamento de chamadas, permitindo identificar gargalos e problemas de performance.

## Estrutura

O sistema consiste em:

1. **CallLogger**: Classe que registra eventos específicos de uma chamada em um arquivo log único (um arquivo por chamada).
2. **CallLoggerManager**: Gerenciador singleton que mantém instâncias de loggers para cada chamada ativa.
3. **log_analyzer.py**: Script para analisar os arquivos de log e gerar relatórios.

## Funcionamento

Cada chamada telefônica gera um arquivo de log no formato `{uuid_chamada}.log` contendo entradas JSON estruturadas com:

- Timestamp preciso de cada evento
- Tempo decorrido desde o início da chamada
- Tipo de evento (ex: SPEECH_DETECTED, TRANSCRIPTION_COMPLETE, etc.)
- Dados específicos do evento (duração, texto transcrito, etc.)

## Tipos de Eventos Registrados

O sistema registra eventos em todas as fases de uma chamada:

### Processamento de Áudio
- Detecção de fala (`SPEECH_DETECTED`)
- Término de fala (`SPEECH_ENDED`) 
- Detecção de silêncio (`SILENCE_DETECTED`)

### Transcrição
- Início da transcrição (`TRANSCRIPTION_START`)
- Conclusão da transcrição (`TRANSCRIPTION_COMPLETE`)

### Processamento de IA
- Início do processamento (`AI_PROCESSING_START`)
- Extração de intenções (`INTENT_EXTRACTION_START`, `INTENT_EXTRACTION_COMPLETE`)
- Validação fuzzy (`FUZZY_VALIDATION_START`, `FUZZY_VALIDATION_COMPLETE`)
- Conclusão do processamento (`AI_PROCESSING_COMPLETE`)

### Síntese de Fala
- Início da síntese (`SYNTHESIS_START`)
- Conclusão da síntese (`SYNTHESIS_COMPLETE`)

### Eventos de Chamada
- Configuração da chamada (`CALL_SETUP`)
- Saudação (`GREETING`)
- Mudança de estado (`STATE_CHANGE`)
- Comunicação com morador (`CALL_MORADOR`, `MORADOR_CONNECTED`)
- Término da chamada (`CALL_ENDED`)

### Erros
- Erros ocorridos durante a chamada (`ERROR`)

## Análise de Logs

O script `log_analyzer.py` oferece:

1. **Análise de uma única chamada**: 
   ```
   python utils/log_analyzer.py --call_id UUID_DA_CHAMADA
   ```

2. **Análise de todas as chamadas**: 
   ```
   python utils/log_analyzer.py --all
   ```

3. **Resumo agregado**:
   ```
   python utils/log_analyzer.py --all --summary
   ```

4. **Exportação para JSON**:
   ```
   python utils/log_analyzer.py --all --output relatorio.json
   ```

## Identificando Gargalos

Os relatórios produzidos pelo analisador ajudam a identificar diversos problemas:

1. **Tempos de Transcrição**: Valores altos podem indicar problemas com o serviço de transcrição ou qualidade do áudio.

2. **Tempos de Processamento da IA**: Valores elevados em etapas específicas (ex: extração de intenção) podem apontar necessidade de otimização dos modelos.

3. **Tempos de Síntese**: Atrasos na geração de áudio sintético que podem degradar a experiência.

4. **Detecção de VAD**: Problemas no reconhecimento de início e fim de falas.

5. **Erros**: Registro completo de falhas ocorridas durante as chamadas.

## Exemplo de Uso

Para usar este sistema em seu código, simplesmente obtenha um logger para a chamada atual:

```python
from utils.call_logger import CallLoggerManager

# No início de uma chamada
call_id = "uuid_da_chamada"
call_logger = CallLoggerManager.get_logger(call_id)

# Durante a chamada, registre eventos
call_logger.log_speech_detected()
call_logger.log_transcription_start(audio_data_size)
call_logger.log_transcription_complete(transcribed_text, transcription_time)
call_logger.log_ai_processing_start(transcribed_text)
call_logger.log_ai_processing_complete(response, processing_time)
call_logger.log_synthesis_start(response_text)
call_logger.log_synthesis_complete(audio_size, synthesis_time)

# Registrar eventos personalizados
call_logger.log_event("MY_CUSTOM_EVENT", {
    "some_key": "some_value",
    "another_key": 123
})

# No final da chamada
call_logger.log_call_ended("normal_disconnection")
CallLoggerManager.remove_logger(call_id)  # Liberar recursos
```