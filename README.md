# AudioSocket Simple

Aplicação simplificada para atendimento por IA em condomínios utilizando o protocolo AudioSocket do Asterisk.

## Descrição

Esta aplicação é responsável por gerenciar chamadas VoIP através do protocolo AudioSocket, realizando:

1. Detecção de voz usando VAD (Voice Activity Detection)
2. Transcrição do áudio usando Azure Speech Services
3. Processamento de intenções via API de IA
4. Síntese de voz para respostas
5. Gerenciamento de turnos de conversa entre usuário e IA

## Funcionalidades principais

- Socket TCP para comunicação com o Asterisk via protocolo AudioSocket
- Máquina de estados simplificada com 4 estados (STANDBY, USER_TURN, WAITING, IA_TURN)
- Gerenciamento de IDs de conversa para manter o contexto entre mensagens
- Mensagem de saudação automática configurável
- Detecção de voz e silêncio usando webrtcvad
- Transcrição de áudio através do Azure Speech Services
- Comunicação com API de IA para processar mensagens do usuário
- Síntese de voz usando Azure Speech Services
- Interface web simples para debug e monitoramento

## Requisitos

- Python 3.8+
- Biblioteca webrtcvad para detecção de voz
- Azure Speech Services para transcrição e síntese de voz
- API de IA para processamento de mensagens

## Configuração

1. Crie um arquivo `.env` com as seguintes variáveis de ambiente:
   ```
   AZURE_SPEECH_KEY=sua_chave_do_azure
   AZURE_SPEECH_REGION=sua_regiao_do_azure
   SILENCE_THRESHOLD_SECONDS=2.0
   AI_API_URL=http://localhost:8000/messages
   ```

2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

3. Personalize a mensagem de saudação no arquivo `config.json`:
   ```json
   {
     "greeting": {
       "message": "Condomínio Apoena, em que posso ajudar?",
       "voice": "pt-BR-AntonioNeural",
       "delay_seconds": 2
     },
     ...
   }
   ```

## Execução

### Servidor principal
Inicie o servidor principal que lida com a chamada e inclui a interface web de debug:
```
python main.py
```

O servidor AudioSocket irá escutar em 127.0.0.1:8080 e a interface web de debug estará disponível em http://127.0.0.1:8081.

### Cliente de teste com microfone
Para testar o sistema com seu microfone local:
```
python microfone_client.py
```

Este cliente captura áudio do microfone do seu computador e o envia para o servidor AudioSocket, permitindo testar toda a funcionalidade sem precisar do Asterisk.

Opções disponíveis:
```
python microfone_client.py --host 127.0.0.1 --port 8080
```

## Fluxo de conversação

1. **Estado STANDBY**: 
   - Sistema aguarda uma conexão
   - Ao receber uma conexão, registra o ID da chamada
   - Após um breve delay, envia a mensagem de saudação
   
2. **Estado USER_TURN**:
   - Sistema ativa após a saudação
   - Detecta quando o usuário começa a falar
   - Captura o áudio até identificar silêncio
   - Transcreve o áudio usando Azure Speech
   
3. **Estado WAITING**:
   - Processa o texto transcrito
   - Envia para a API de IA
   
4. **Estado IA_TURN**:
   - Recebe a resposta da IA
   - Sintetiza a fala usando Azure Speech
   - Envia o áudio de resposta
   - Retorna para USER_TURN ou STANDBY dependendo da resposta da IA

## Interface de Debug

A interface web de debug mostra:
- Estado atual da chamada
- ID da conversa ativa
- Histórico de transcrições (usuário, IA e sistema)

A página atualiza automaticamente a cada 2 segundos para mostrar o estado atual.

## API de IA

A aplicação se comunica com uma API de IA pela URL `http://localhost:8000/messages` que deve retornar uma resposta no formato:

```json
{
    "content": {
        "mensagem": "Texto da resposta da IA",
        "dados": {
            "intent_type": "tipo_intencao",
            "outros_dados": "valores_relevantes"
        },
        "valid_for_action": false
    },
    "timestamp": "2025-04-15T19:17:59.052067",
    "set_call_status": "USER_TURN"
}
```

O campo `set_call_status` pode ter os valores: "USER_TURN", "WAITING", "IA_TURN" ou "STANDBY" para controlar o fluxo da conversa.