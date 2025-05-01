# Detecção de Voz com Azure Speech

Este documento descreve a implementação de detecção de voz e silêncio usando o Azure Speech SDK como alternativa ao webrtcvad no AudioSocket-Simple.

## Visão Geral

O sistema AudioSocket-Simple requer detecção precisa de quando o usuário começa e termina de falar para funcionar corretamente. Originalmente, o sistema utilizava apenas a biblioteca `webrtcvad` para realizar esta detecção. Embora o webrtcvad seja eficaz em ambientes controlados, ele pode ter dificuldades em ambientes ruidosos, onde ruídos de fundo como carros passando, televisores ligados ou conversas ao fundo podem interferir na detecção correta do término da fala.

Para resolver este problema, implementamos um método alternativo de detecção de voz usando o Azure Speech SDK, que oferece algoritmos mais avançados para detecção de atividade de voz em ambientes ruidosos. O sistema agora permite escolher entre os dois métodos de detecção:

1. **WebRTCVAD** (implementação original) - Rápido e leve, ideal para ambientes silenciosos
2. **Azure Speech** (nova implementação) - Mais robusto contra ruídos, ideal para ambientes ruidosos

## Configuração

A escolha do método de detecção de voz é controlada no arquivo `config.json`:

```json
{
  "system": {
    "voice_detection_type": "azure_speech",  // opções: "webrtcvad" ou "azure_speech"
    "azure_speech_segment_timeout_ms": 800,  // timeout de silêncio em ms para segmentação (Azure)
    "silence_threshold_seconds": 1.5,        // timeout de silêncio para webrtcvad (em segundos)
    "resident_max_silence_seconds": 45.0     // timeout máximo para morador
  },
  // ... outras configurações
}
```

### Parâmetros de Configuração

- **voice_detection_type**: Determina qual método de detecção de voz será usado
  - `webrtcvad`: Usa a biblioteca webrtcvad para detecção (padrão)
  - `azure_speech`: Usa o Azure Speech SDK para detecção

- **azure_speech_segment_timeout_ms**: Define o tempo de silêncio (em milissegundos) que o Azure Speech aguarda após detectar silêncio para considerar que a fala terminou.
  - Valores menores (400-600ms) são mais reativos, mas podem cortar frases pausadas
  - Valores maiores (800-1000ms) permitem pausas mais longas na fala
  - Para o morador, o sistema usa um valor ligeiramente menor que este para detectar respostas curtas como "sim" de forma mais rápida

- **silence_threshold_seconds**: Define o tempo de silêncio (em segundos) para o método webrtcvad considerar que a fala terminou.

## Funcionamento

### Azure Speech SDK

Quando o método `azure_speech` está ativo, o sistema:

1. Inicia uma sessão de reconhecimento contínuo com o Azure Speech SDK
2. Monitora eventos do Azure Speech que indicam início e fim da fala
3. Coleta áudio durante períodos detectados como fala ativa
4. Processa o texto reconhecido pelo Azure ou, se necessário, envia o áudio coletado para transcrição

Benefícios específicos:

- **Melhor filtro de ruído**: O Azure Speech SDK usa modelos de IA para distinguir voz humana de ruídos de fundo
- **Detecção mais precisa de fim de fala**: Identifica melhor quando o usuário realmente terminou de falar mesmo em ambientes ruidosos
- **Detecção de fala mais rápida**: O sistema pode detectar o início da fala mais rapidamente

### Diferença entre Visitante e Morador

A implementação tem considerações especiais para cada papel:

- **Visitante**: Configurado para permitir frases mais longas, com maiores limiares de segmentação
- **Morador**: Otimizado para respostas curtas como "sim", "não" ou perguntas rápidas, com limiares de segmentação mais curtos e processamento especial para falas muito breves

## Testes e Verificação

Para testar o sistema com a detecção Azure Speech:

1. Configure `voice_detection_type` como `azure_speech` no `config.json`
2. Verifique se as variáveis de ambiente `AZURE_SPEECH_KEY` e `AZURE_SPEECH_REGION` estão definidas corretamente
3. Inicie o sistema e teste em diferentes ambientes:
   - Ambiente silencioso
   - Ambiente com ruído de fundo (TV, rádio, pessoas conversando)
   - Ambiente com sons intermitentes (portas batendo, telefones tocando)

Os logs da aplicação mostrarão informações detalhadas sobre a detecção de voz:

```
INFO:[call_id] Início de fala detectado pelo Azure Speech
INFO:[call_id] Fim de fala detectado pelo Azure Speech
INFO:[call_id] Azure Speech reconheceu texto: "Olá, gostaria de falar com o morador do 501"
```

## Considerações e Performance

- **Latência**: A detecção com Azure Speech pode adicionar uma pequena latência adicional, mas geralmente é imperceptível para o usuário final
- **Custo**: Esta implementação utiliza o serviço Azure Speech, que gera custos conforme o uso
- **Confiabilidade**: A detecção de voz com Azure Speech é mais confiável em ambientes ruidosos, reduzindo erros de cortes prematuros ou atrasos no processamento

## Recomendações

1. Para ambientes controlados e silenciosos, o método `webrtcvad` pode ser suficiente e mais econômico
2. Para ambientes com ruído de fundo significativo (halls de entrada, portarias com movimento, etc.), recomenda-se o uso do `azure_speech`
3. O parâmetro `azure_speech_segment_timeout_ms` pode ser ajustado conforme necessário:
   - Valores mais baixos (600-700ms) para interações rápidas
   - Valores mais altos (800-1000ms) para conversas mais naturais com pausas

## Solução de Problemas

- **Frases sendo cortadas**: Aumente o valor de `azure_speech_segment_timeout_ms`
- **Demora em processar após parar de falar**: Diminua o valor de `azure_speech_segment_timeout_ms`
- **Não detecta falas curtas do morador**: Verifique se o processamento de falas curtas está funcionando corretamente

## Mecanismo de Detecção de Deadlock

Para evitar situações em que o sistema pode ficar travado ao aguardar eventos do Azure Speech que nunca ocorrem, implementamos um mecanismo de detecção de deadlock com as seguintes características:

1. **Monitoramento periódico**: A cada ~5 segundos (250 frames de áudio), o sistema verifica o estado atual da detecção de voz
2. **Detecção de silêncio prolongado**: Se o sistema estiver coletando áudio por mais de 10 segundos sem que o Azure Speech tenha detectado o fim da fala, é considerado um possível deadlock
3. **Processamento forçado**: Quando um deadlock é detectado, o sistema força o processamento do áudio coletado até aquele momento, como se tivesse detectado o fim da fala naturalmente
4. **Registro de diagnóstico**: O sistema registra um aviso nos logs quando um deadlock é detectado e resolvido

Este mecanismo garante que mesmo se o Azure Speech SDK falhar em detectar corretamente o fim da fala (o que pode ocorrer em condições específicas de áudio), o sistema continuará funcionando e processando o áudio do usuário.

Exemplo de mensagem de log ao detectar um deadlock:
```
WARNING:[call_id] Detectado possível deadlock no Azure Speech! Forçando processamento manual após 10s de silêncio.
```

---

*Próximo documento: [11-versionamento.md](11-versionamento.md)*