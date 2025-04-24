# Melhorias no Sistema de Chamadas com Moradores

## Problemas Identificados

Durante os testes de chamadas, identificamos dois problemas críticos:

1. **Timeout prematuro**: As ligações com moradores estavam sendo encerradas prematuramente. Logo após o morador atender, se ele não falasse dentro de um período curto de tempo, a chamada era encerrada automaticamente.

2. **Perda de contexto entre sessões**: A chamada para o morador não estava mantendo o mesmo contexto da chamada do visitante, resultando em perda da conversa e quedas de ligação.

## Soluções Implementadas

### 1. Correção de Timeouts

#### 1.1 Novos parâmetros de configuração

Adicionamos novos parâmetros de configuração específicos para lidar com o tempo máximo de silêncio permitido nas interações com moradores:

```json
"system": {
    "default_state": "STANDBY",
    "silence_threshold_seconds": 1.5,
    "max_transaction_time_seconds": 60,
    "resident_max_silence_seconds": 45,
    "goodbye_delay_seconds": 3.0
},
```

O parâmetro `resident_max_silence_seconds` permite que o morador tenha até 45 segundos para responder após atender a chamada, sem que a conexão seja encerrada.

#### 1.2 Processamento diferenciado para moradores

Modificamos o handler de áudio do morador para usar este novo parâmetro:

```python
# Usar um tempo de silêncio maior para o morador
if silence_duration > RESIDENT_MAX_SILENCE_SECONDS:
    is_speaking = False
    # ...resto do código...
```

#### 1.3 Aumentado tempo máximo de transação

Aumentamos o `max_transaction_time_seconds` de 30 para 60 segundos, fornecendo mais tempo para toda a interação.

### 2. Preservação de Contexto entre Sessões

#### 2.1 Reutilização de sessões existentes

Modificamos o `iniciar_servidor_audiosocket_morador` para verificar e utilizar a sessão existente do visitante:

```python
# Verificar se sessão já existe (deve existir se o fluxo estiver correto)
existing_session = session_manager.get_session(call_id)
if not existing_session:
    logger.warning(f"[MORADOR] Call ID {call_id} não encontrado como sessão existente. Criando nova sessão.")
    session_manager.create_session(call_id)
    # ...
else:
    logger.info(f"[MORADOR] Sessão existente encontrada para Call ID: {call_id}. Conectando morador ao fluxo existente.")
    # Não enviar saudação, a conversa já deve estar em andamento no fluxo
```

#### 2.2 Garantia de preservação do GUID na chamada AMQP

Melhoramos a função `enviar_clicktocall` para garantir que o mesmo GUID da sessão do visitante seja usado na chamada para o morador:

```python
# IMPORTANTE: Garantir que o mesmo GUID da sessão seja usado
# na chamada para o morador, para que os contextos se conectem
payload = {
    "data": {
        "destiny": "IA",
        "guid": guid,  # GUID da sessão original
        "license": "123456789012",
        "origin": morador_voip_number
    },
    # ...
}
```

#### 2.3 Melhor tratamento de erros e validações

Adicionamos verificações de segurança para garantir que os GUIDs e números de telefone sejam válidos:

```python
# Verificação de segurança - GUID não pode estar vazio
if not guid or len(guid) < 8:
    logger.error(f"[Flow] GUID inválido para clicktocall: '{guid}'")
    return False

# Verificação de segurança - número do morador não pode estar vazio
if not morador_voip_number:
    logger.error(f"[Flow] Número do morador inválido: '{morador_voip_number}'")
    return False
```

## Benefícios

1. **Continuidade da conversa**: Agora o morador é incluído no mesmo contexto da chamada do visitante, permitindo uma conversa contínua e coerente.

2. **Maior tempo de reflexão para moradores**: Os moradores têm mais tempo para pensar e responder, sem que a chamada seja encerrada.

3. **Redução de chamadas perdidas**: Evita a frustração tanto do visitante quanto do morador quando a chamada cai prematuramente.

4. **Logging aprimorado**: Mais informações de diagnóstico são registradas nos logs, facilitando a identificação de problemas.

## Próximos Passos

- Monitorar se o novo tempo de timeout de 45 segundos é adequado ou se precisa de ajustes
- Considerar implementar um aviso automático quando o morador ficar muito tempo sem responder (ex: "Você ainda está aí?")
- Avaliar a possibilidade de detecção automática de ruído de fundo vs. silêncio real
- Implementar um mecanismo de recuperação para lidar com situações onde o GUID não é preservado corretamente

Data da implementação: 25/04/2025