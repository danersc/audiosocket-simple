# Teste de Finalização Ativa com KIND_HANGUP

Este documento descreve como testar a funcionalidade de finalização ativa de chamadas usando o sinal KIND_HANGUP no protocolo AudioSocket.

## Objetivo do teste

O objetivo é verificar se o servidor consegue ativamente terminar uma chamada enviando o sinal KIND_HANGUP (0x00) ao cliente, em vez de apenas esperar receber esse sinal quando o cliente se desconecta.

## Mecanismo implementado

Foi implementado um mecanismo de teste que:

1. Detecta uma flag específica `test_hangup` nos dados da sessão
2. Quando a mensagem "A chamada com o morador foi finalizada. Obrigado por utilizar nosso sistema." é enviada ao visitante
3. Após reproduzir a mensagem de áudio, o servidor envia explicitamente um pacote KIND_HANGUP (0x00) com tamanho de payload 0
4. Isso deve fazer com que o cliente AudioSocket se desconecte imediatamente

## Como testar

### Método mais simples (comando direto)

Basta enviar o texto "test hangup" durante a conversa com o visitante. O sistema detectará este comando especial, ativará a flag de teste e iniciará o processo de finalização imediatamente.

```
Visitante: test hangup
IA: Teste de KIND_HANGUP ativado. Ao finalizar, o sistema enviará ativamente o comando de desconexão.
[Sistema envia mensagem de despedida e depois KIND_HANGUP]
```

### Outros métodos para ativar a flag

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
[CALL_ID] Verificar se é o teste específico com a mensagem de finalização
[CALL_ID] Enviando KIND_HANGUP para finalizar a conexão ativamente 
[CALL_ID] HANGUP_SENT event logged
```

### Comportamento esperado

1. O cliente deverá se desconectar imediatamente após receber o KIND_HANGUP
2. Você deverá ver logs de desconexão no cliente
3. A sessão será devidamente encerrada no servidor

## Formato do pacote KIND_HANGUP

O pacote KIND_HANGUP é formatado como:

```
struct.pack('>B H', 0x00, 0)
```

Onde:
- `>` indica ordenação big-endian
- `B` representa um byte unsigned (o tipo KIND_HANGUP = 0x00)
- `H` representa um unsigned short (2 bytes) para o tamanho do payload (0)

## Notas importantes

1. Esta abordagem segue o padrão do protocolo AudioSocket, onde tanto cliente quanto servidor podem enviar KIND_HANGUP para sinalizar encerramento
2. Quando o KIND_HANGUP é recebido, qualquer side da conexão deve encerrar graciosamente
3. Este mecanismo permite implementações futuras para timeout de sessões ou encerramento forçado quando necessário