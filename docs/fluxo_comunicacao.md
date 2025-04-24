# Fluxo de Comunicação entre Visitante e Morador

Este documento descreve o fluxo otimizado de comunicação entre visitante e morador implementado em 24/04/2025.

## Estado Inicial e Coleta de Dados

1. Visitante inicia a chamada
2. Sistema envia saudação e inicia coleta de dados:
   - Tipo de visita (entrega, visita, etc.)
   - Nome do visitante
   - Apartamento e morador de destino
3. Após coletar todos os dados, o sistema valida com fuzzy matching

## Processo de Chamada ao Morador (Melhorado)

O fluxo de comunicação com o morador foi otimizado para não expor detalhes técnicos ao visitante:

### Antes (Comportamento Problemático)

```
Visitante: "Apartamento 501, morador Daniel dos Reis"
Sistema: "Obrigado Pedro da Silva, aguarde um instante"
Sistema: "Ok, vamos entrar em contato com o morador. Aguarde, por favor."
Sistema: "Discando para 1003030... (Tentativa 1)"
Sistema: "Discando para 1003030... (Tentativa 2)"
...
```

### Depois (Comportamento Melhorado)

```
Visitante: "Apartamento 501, morador Daniel dos Reis"
Sistema: "Obrigado Pedro da Silva, aguarde um instante"
Sistema: "Aguarde enquanto entramos em contato com o morador..."
[Processo de chamada ocorre silenciosamente em background]
...
Sistema: "O morador atendeu. Aguarde enquanto verificamos sua autorização..."
```

## Diagrama de Estados

```
┌─────────────────┐           ┌───────────────┐           ┌────────────────────┐
│  COLETANDO      │           │               │           │                    │
│  DADOS          ├──────────►│   VALIDADO    ├──────────►│  CHAMANDO_MORADOR  │
└─────────────────┘           └───────────────┘           └──────────┬─────────┘
                                                                      │
                                                                      ▼
┌─────────────────┐           ┌───────────────┐           ┌────────────────────┐
│                 │           │               │           │                    │
│   FINALIZADO    │◄──────────┤ ESPERANDO     │◄──────────┤ CALLING_IN_PROGRESS│
│                 │           │ MORADOR       │           │                    │
└─────────────────┘           └───────────────┘           └────────────────────┘
```

## Detalhes Técnicos

### Estados do Fluxo

- **COLETANDO_DADOS**: Coleta informações iniciais do visitante
- **VALIDADO**: Dados validados com sucesso via fuzzy matching
- **CHAMANDO_MORADOR**: Estado inicial de chamada (mostra mensagem ao visitante)
- **CALLING_IN_PROGRESS**: Processo de tentativas de chamada em andamento (silencioso)
- **ESPERANDO_MORADOR**: Morador atendeu, aguardando autorização
- **FINALIZADO**: Fluxo concluído (com autorização ou sem resposta)

### Mudanças Implementadas

1. **Ocultação de detalhes técnicos**:
   - Mensagens como "Tentativa X" não são mais exibidas ao visitante
   - Mensagem única de "Aguarde enquanto entramos em contato" durante todo o processo

2. **Processo assíncrono de chamada**:
   - Implementado como um loop de tentativas independente
   - Gerencia múltiplas tentativas sem notificar o visitante

3. **Tratamento de erros robusto**:
   - Timeout configurável entre tentativas
   - Número máximo de tentativas parametrizável
   - Resposta clara e concisa em caso de falha

4. **Ignorando entradas do visitante durante chamada**:
   - Sistema ignora novas mensagens do visitante durante o processo de chamada
   - Evita confusão ou interrupção do fluxo durante comunicação com morador

## Benefícios

1. **Experiência do usuário melhorada**:
   - Comunicação mais natural e focada na tarefa
   - Sem detalhes técnicos desnecessários
   - Redução da ansiedade durante espera

2. **Operação mais robusta**:
   - Verificação periódica do estado durante chamada
   - Gerenciamento de falhas mais eficiente
   - Transições de estado mais claras