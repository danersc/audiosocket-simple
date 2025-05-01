# Teste de Finalização Ativa com KIND_HANGUP

Este documento descreve como testar a funcionalidade de finalização ativa de chamadas usando o sinal KIND_HANGUP no protocolo AudioSocket.

## Objetivo do teste

O objetivo é verificar se o servidor consegue ativamente terminar uma chamada enviando o sinal KIND_HANGUP (0x00) ao cliente, em vez de apenas esperar receber esse sinal quando o cliente se desconecta.

## Mecanismos Implementados

### 1. Mecanismo original (via flag test_hangup)

Foi implementado um mecanismo de teste que:

1. Detecta uma flag específica `test_hangup` nos dados da sessão
2. Quando a mensagem "A chamada com o morador foi finalizada. Obrigado por utilizar nosso sistema." é enviada ao visitante
3. Após reproduzir a mensagem de áudio, o servidor envia explicitamente um pacote KIND_HANGUP (0x00) com tamanho de payload 0
4. Isso deve fazer com que o cliente AudioSocket se desconecte imediatamente

### 2. Nova API REST para encerramento direto

Agora também implementamos um endpoint na API HTTP que permite enviar KIND_HANGUP diretamente para qualquer chamada ativa:

```
POST /api/hangup
```

Payload:
```json
{
  "call_id": "uuid-da-chamada",
  "role": "visitor|resident"
}
```

## Como testar

### 1. Usando a API REST (novo método recomendado)

Este método é o mais direto para testar o encerramento de chamadas:

```bash
# Obter a lista de sessões ativas para identificar o call_id
curl http://localhost:8082/api/status

# Encerrar uma chamada específica (substituir UUID-DA-CHAMADA pelo ID real)
curl -X POST -H "Content-Type: application/json" \
  -d '{"call_id":"UUID-DA-CHAMADA", "role":"visitor"}' \
  http://localhost:8082/api/hangup
```

### 2. Método via conversa (comando direto)

Basta enviar o texto "test hangup" durante a conversa com o visitante. O sistema detectará este comando especial, ativará a flag de teste e iniciará o processo de finalização imediatamente.

```
Visitante: test hangup
IA: Teste de KIND_HANGUP ativado. Ao finalizar, o sistema enviará ativamente o comando de desconexão.
[Sistema envia mensagem de despedida e depois KIND_HANGUP]
```

### 3. Outros métodos para ativar a flag

#### Opção 1: Via ConversationFlow

Defina a flag `test_hangup` como `True` nos dados de intent:

```python
self.intent_data["test_hangup"] = True
```

Isso foi implementado na função `_finalizar()` do ConversationFlow para facilitar o teste.

#### Opção 2: Modificando a sessão manualmente

Durante uma sessão ativa, você pode definir manualmente a flag:

```python
session = session_manager.get_session(session_id)
if session:
    session.intent_data["test_hangup"] = True
```

### Validar nos logs

Durante o encerramento, procure por estas mensagens nos logs:

```
# Para API:
KIND_HANGUP enviado com sucesso para [call_id] (visitor)
Sessão [call_id] encerrada após KIND_HANGUP

# Para flag de teste:
[CALL_ID] Verificar se é o teste específico com a mensagem de finalização
[CALL_ID] Enviando KIND_HANGUP para finalizar a conexão ativamente 
[CALL_ID] HANGUP_SENT event logged
```

### Comportamento esperado

1. O cliente deverá se desconectar imediatamente após receber o KIND_HANGUP
2. Você deverá ver logs de desconexão no cliente
3. A sessão será devidamente encerrada no servidor

## Como o Encerramento Funciona

1. A função identifica o StreamWriter associado ao socket
2. Envia um pacote KIND_HANGUP (0x00) com tamanho 0 ao socket
3. Define a flag `test_hangup` na sessão
4. Agenda uma tarefa para encerrar completamente a sessão após um breve delay

## Formato do pacote KIND_HANGUP

O pacote KIND_HANGUP é formatado como:

```
struct.pack('>B H', 0x00, 0)
```

Onde:
- `>` indica ordenação big-endian
- `B` representa um byte unsigned (o tipo KIND_HANGUP = 0x00)
- `H` representa um unsigned short (2 bytes) para o tamanho do payload (0)

## Integração no Fluxo Normal

Após validar com testes, este mecanismo pode ser integrado ao fluxo normal da conversa. Possíveis usos:

1. Encerrar automaticamente após atingir um timeout de inatividade
2. Finalizar chamadas após o morador decidir (autorizar/negar)
3. Encerrar em caso de erro irrecuperável

## Solução de Problemas

Se o comando não funcionar:
1. Verifique se o call_id está correto (use a API /api/status)
2. Verifique se a chamada ainda está ativa
3. Verifique os logs para mensagens de erro
4. Verifique a versão do Asterisk e sua compatibilidade com KIND_HANGUP

## Notas importantes

1. Esta abordagem segue o padrão do protocolo AudioSocket, onde tanto cliente quanto servidor podem enviar KIND_HANGUP para sinalizar encerramento
2. Quando o KIND_HANGUP é recebido, qualquer lado da conexão deve encerrar graciosamente
3. Este mecanismo permite implementações futuras para timeout de sessões ou encerramento forçado quando necessário