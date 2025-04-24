# Migração para UUID v7: Melhorando a Compatibilidade das Chamadas

## Problema Identificado

Durante o teste de funcionamento das chamadas entre visitantes e moradores, identificamos que as ligações estavam caindo prematuramente ou perdendo o contexto entre as duas partes da conversa. Após análise dos logs, notamos que o principal problema estava relacionado à forma como os identificadores de sessão (UUIDs) eram gerados e transmitidos entre os diferentes componentes do sistema.

O sistema estava utilizando UUIDs v4 padrão, que são completamente aleatórios. Isso pode causar problemas em alguns sistemas externos e middlewares que esperam UUIDs ordenáveis ou baseados em timestamp.

## Solução Implementada

Implementamos um gerador próprio de UUIDs v7, que oferecem as seguintes vantagens:

1. **Baseados em timestamp**: Incluem o timestamp atual em milissegundos, garantindo ordenação cronológica
2. **Compatibilidade melhorada**: Funcionam melhor com sistemas de banco de dados e middlewares que esperam ordenação
3. **Rastreabilidade**: Facilitam a depuração por incluírem informação temporal
4. **Unicidade garantida**: Mantêm a unicidade através de componentes aleatórios, assim como UUIDs v4

### Arquivos Modificados

1. **utils/uuid_generator.py** (NOVO)
   - Implementação própria de UUIDs v7 sem dependências externas
   - Segue a especificação oficial do RFC em desenvolvimento

2. **session_manager.py**
   - Substituído `from uuid import uuid4` por `from utils.uuid_generator import uuid7`
   - Atualizado gerador de IDs de sessão para usar `uuid7()`
   - Adicionado logging melhorado

3. **state_machine.py** 
   - Atualizado `start_new_conversation()` para usar `uuid7()`
   - Melhorado log das conversações para facilitar rastreabilidade

4. **microfone_client.py**
   - Modificado para usar UUIDs v7 para IDs de chamada
   - Atualizado logging para destacar uso de UUIDs v7

5. **test_logs.py**
   - Migrado código de simulação para utilizar UUIDs v7

6. **audiosocket_handler.py**
   - Implementada verificação de sessão existente antes de criar nova
   - Adicionada transferência de contexto entre sessões

## Benefícios

1. **Ordenação natural**: Os UUIDs v7 são naturalmente ordenáveis por tempo, facilitando processos de organização e busca
2. **Diagnóstico simplificado**: A informação temporal embutida facilita o rastreamento e diagnóstico de problemas
3. **Melhor compatibilidade**: Funciona melhor com sistemas externos que podem ter expectativas especiais sobre o formato do UUID
4. **Contexto preservado**: Melhora a capacidade do sistema de manter o contexto entre diferentes partes da conversa (visitante/morador)

## Exemplo de Comparação

**UUID v4 (anterior)**: `9f9e7f6a-8a5b-4c7d-9e1f-a1b2c3d4e5f6`
- Completamente aleatório
- Sem informação temporal
- Difícil correlacionar com tempo de geração

**UUID v7 (atual)**: `01890ab1-1a1a-72c4-9e1f-a1b2c3d4e5f6`
- Primeiros bytes representam o timestamp em milissegundos
- Ordenação natural por tempo de criação
- Mantém a aleatoriedade nos bytes finais para garantir unicidade
- Facilita correlação com logs de tempo

## Próximos Passos

1. Monitorar o funcionamento das chamadas e verificar se o problema de queda prematura foi resolvido
2. Avaliar a performance e a distribuição dos UUIDs v7 em comparação com UUIDs v4
3. Considerar adicionar uma API para extrair o timestamp de um UUID v7, facilitando o diagnóstico

Data da implementação: 25/04/2025