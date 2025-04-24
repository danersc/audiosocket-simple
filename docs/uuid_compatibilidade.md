# Preservação de Contexto em Chamadas VoIP

## Problema Identificado

Durante o teste de funcionamento das chamadas entre visitantes e moradores, identificamos que as ligações estavam caindo prematuramente ou perdendo o contexto entre as duas partes da conversa. Após análise dos logs, notamos que o principal problema estava relacionado à forma como os identificadores de sessão (UUIDs) eram transmitidos entre os diferentes componentes do sistema.

## Solução Implementada

Após experimentar diferentes abordagens, decidimos manter a implementação com UUIDs v4 padrão do Python, mas melhoramos o gerenciamento e compartilhamento dos UUIDs:

1. **Formato preservado**: Mantemos o formato completo do UUID com traços, pois é necessário para compatibilidade com o AudioSocket
2. **Reutilização de sessões**: Modificamos o código para garantir que o mesmo UUID seja usado entre a chamada do visitante e do morador
3. **Verificação de contexto**: Implementamos validações para garantir que o contexto da sessão seja mantido entre os diferentes componentes

### Exemplo de UUID compatível

```
e69439e9-1489-4bba-b55d-37612b5dffaf
```

Este formato com traços e o tamanho padrão garante que o sistema externo de telefonia (AudioSocket) possa manter o contexto da conversa.

### Arquivos Modificados

1. **session_manager.py**
   - Melhoria no gerenciamento de sessões com UUIDs
   - Implementação de log para rastreamento de UUIDs

2. **audiosocket_handler.py**
   - Adicionada verificação de sessão existente para evitar duplicação
   - Implementada transferência de contexto entre sessões do visitante e do morador

3. **conversation_flow.py**
   - Melhorado o fluxo de chamadas para manter o contexto entre visitante e morador

## Benefícios

1. **Comunicação fluida**: Com a preservação do UUID entre as duas partes, a comunicação flui sem interrupções
2. **Consistência de dados**: O contexto da conversa é mantido durante todo o fluxo
3. **Diagnóstico simplificado**: Os logs melhorados facilitam o rastreamento de problemas
4. **Compatibilidade**: Garantimos que o formato do UUID seja compatível com todos os componentes do sistema

## Próximos Passos

1. Monitorar o funcionamento das chamadas e verificar que o problema de queda prematura foi resolvido
2. Considerar melhorias adicionais no protocolo de comunicação para maior robustez
3. Avaliar a possibilidade de implementar um mecanismo de recuperação de contexto caso ocorra perda de sessão

Data da implementação: 25/04/2025