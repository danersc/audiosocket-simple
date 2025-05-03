# Otimização do Reconhecimento de Voz Azure Speech

## Contexto e Problema

O sistema AudioSocket-Simple utiliza o Azure Speech SDK para reconhecimento de voz em chamadas VoIP. Embora o sistema detectasse corretamente quando o usuário começava e parava de falar (eventos `speech_start_detected` e `speech_end_detected`), o evento crucial `recognized` não estava sendo disparado, impedindo o processamento do texto transcrito.

## Diagnóstico

O áudio estava sendo capturado corretamente (comprovado pelos arquivos .slin gerados), mas o Azure Speech não estava retornando transcrições. Nossas hipóteses para o problema incluíam:

1. **Formato de áudio incompatível**: O formato SLIN (PCM 16-bit 8kHz) não estava sendo configurado corretamente para o Azure Speech SDK.
2. **Configurações inadequadas de segmentação**: Parâmetros como timeout de silêncio podem afetar quando o SDK considera uma frase completa.
3. **Problemas de conectividade**: Falhas na conexão com a API do Azure ou credenciais incorretas.
4. **Casos de NoMatch**: O Azure detectava fala mas não conseguia transcrevê-la, resultando em um evento `NoMatch` que não estava sendo monitorado.

## Otimizações Implementadas

### 1. Correção do Formato de Áudio

- Configuração explícita do formato como 8kHz 16-bit mono para garantir que o Azure Speech interpretasse corretamente o áudio SLIN:
  ```python
  audio_format = speechsdk.audio.AudioStreamFormat(
      samples_per_second=8000,  # Crucialmente importante: 8kHz para SLIN
      bits_per_sample=16,       # 16-bit PCM
      channels=1                # mono
  )
  ```

### 2. Tratamento Explícito de NoMatch e Cancelamentos

- Adicionado tratamento para o resultado `NoMatch` no callback `on_recognized`
- Implementado log detalhado no evento de cancelamento (`on_canceled`) para identificar erros específicos

### 3. Mecanismo de Timeout para Processamento de Áudio

- Implementado um fallback que processa o áudio mesmo sem transcrição:
  ```python
  async def check_recognition_timeout():
      await asyncio.sleep(3.0)  # Esperar 3 segundos
      
      # Se ainda temos o mesmo áudio no buffer, o evento on_recognized não foi disparado
      if self.collecting_audio == False and len(self.audio_buffer) > 0:
          logger.warning(f"[{self.call_id}] Timeout: on_recognized não foi disparado após 3s. Processando áudio diretamente.")
          # ... processamento do áudio ...
  ```

### 4. Aprimoramento da Coleta de Áudio

- Correção na lógica de `add_audio_chunk` para garantir que o áudio seja adicionado ao buffer sempre que fala for detectada
- Melhorada a limpeza do buffer para evitar mistura de áudios de diferentes eventos

### 5. Configurações Otimizadas de Reconhecimento

- Ajustados parâmetros de segmentação de silêncio para melhor desempenho com áudio VoIP
- Forçado o idioma de reconhecimento como Português Brasileiro (pt-BR)
- Desativado o pós-processamento de texto para resultados mais brutos e rápidos

### 6. Ferramentas de Diagnóstico

- Script `diagnose_azure_speech.py`: Testa a conectividade e funcionamento do SDK
- Script `improve_recognizer.py`: Aplica otimizações sem edição manual do código
- Ferramenta `play_slin.py`: Permite reproduzir e analisar os arquivos de áudio capturados

### 7. Logging Aprimorado

- Implementados logs detalhados para cada estágio do processo
- Salvamento automático de arquivos de áudio para diagnóstico
- Rastreamento da duração dos eventos de fala

## Resultados e Conclusões

O foco principal foi garantir que o sistema pudesse funcionar de forma confiável:

1. **Confiando no Azure quando possível**: Utilizando a detecção nativa de início/fim de fala
2. **Sendo resiliente a falhas**: Processando áudio mesmo quando o reconhecimento falha
3. **Mantendo diagnóstico detalhado**: Gerando logs e arquivos para análise posterior

Apesar de ainda haver desafios com o reconhecimento em ambientes ruidosos, as melhorias implementadas permitem que o sistema funcione de maneira mais robusta, superando falhas no reconhecimento de fala do Azure Speech sem sacrificar a qualidade geral do serviço.

## Próximos Passos

1. Monitorar logs de produção para identificar padrões nas falhas de reconhecimento
2. Considerar ajustes futuros nos parâmetros de timeout e segmentação com base em métricas reais
3. Explorar opções para pré-processamento de áudio (redução de ruído, normalização) antes do envio para o Azure

## Referências Técnicas

- [Documentação Azure Speech SDK](https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/speech-sdk)
- [Configurações de formato de áudio](https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/how-to-use-audio-input-streams)
- [Timeouts de silêncio e segmentação](https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/how-to-recognize-speech?pivots=programming-language-python)