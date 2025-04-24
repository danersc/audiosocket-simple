# Melhorias no Timeout de Chamadas com Moradores

## Problema Identificado

Durante os testes de chamadas, foi detectado que as ligações com moradores estavam sendo encerradas prematuramente. Logo após o morador atender, se ele não falasse dentro de um período curto de tempo, a chamada era encerrada automaticamente.

Analisando os logs, identificamos que o sistema estava aplicando o mesmo tempo de inatividade (`SILENCE_THRESHOLD_SECONDS` de 1.5 segundos) tanto para visitantes quanto para moradores. O fluxo de comunicação com o morador requer um tempo maior de espera.

## Solução Implementada

### 1. Novo parâmetro de configuração

Adicionamos um novo parâmetro de configuração específico para lidar com o tempo máximo de silêncio permitido nas interações com moradores:

```json
"system": {
    "default_state": "STANDBY",
    "silence_threshold_seconds": 1.5,
    "max_transaction_time_seconds": 60,
    "resident_max_silence_seconds": 45,
    "goodbye_delay_seconds": 3.0
},
```

Este novo parâmetro `resident_max_silence_seconds` permite que o morador tenha até 45 segundos para responder após atender a chamada, sem que a conexão seja encerrada.

### 2. Processamento diferenciado para moradores

Modificamos o handler de áudio do morador para usar este novo parâmetro, permitindo um tempo maior de silêncio antes de considerar que a interação foi encerrada:

```python
# Usar um tempo de silêncio maior para o morador
if silence_duration > RESIDENT_MAX_SILENCE_SECONDS:
    is_speaking = False
    # ...resto do código...
```

### 3. Aumentado tempo máximo de transação

Aumentamos também o `max_transaction_time_seconds` de 30 para 60 segundos, fornecendo mais tempo para toda a interação antes que o sistema inicie um encerramento por timeout.

## Benefícios

1. **Melhor experiência para moradores**: Os moradores agora têm mais tempo para pensar e responder, sem que a chamada seja encerrada.

2. **Redução de chamadas perdidas**: Evita a frustração tanto do visitante quanto do morador quando a chamada cai prematuramente.

3. **Maior personalização do comportamento**: O sistema agora diferencia os tempos de interação entre visitantes (que precisam ser mais rápidos) e moradores (que podem precisar de mais tempo).

## Próximos Passos

- Monitorar se o novo tempo de timeout de 45 segundos é adequado ou se precisa de ajustes
- Considerar implementar um aviso automático quando o morador ficar muito tempo sem responder (ex: "Você ainda está aí?")
- Avaliar a possibilidade de detecção automática de ruído de fundo vs. silêncio real

Data da implementação: 25/04/2025