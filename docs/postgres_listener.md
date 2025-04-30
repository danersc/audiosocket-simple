# Listener de Notificações PostgreSQL

Data: 29/04/2025

## Visão Geral

Esta documentação descreve o novo sistema de escuta automática de notificações do PostgreSQL implementado para permitir atualizações dinâmicas de ramais no sistema de portaria inteligente.

## Funcionalidade

O sistema agora monitora em tempo real as alterações na tabela `extension_ia` do banco de dados, permitindo que novas configurações de ramais sejam aplicadas instantaneamente sem necessidade de reiniciar a aplicação ou fazer requisições manuais à API.

## Componentes Principais

### 1. PostgresListener

Classe assíncrona que estabelece uma conexão com o PostgreSQL e escuta notificações em um canal específico:

```python
class PostgresListener:
    def __init__(self, callback: Callable[[dict], None], channel: str = "change_record_extension_ia")
    async def connect(self) -> bool
    async def listen(self)
    async def start(self)
    async def stop()
```

### 2. Integração com ExtensionManager

O `ExtensionManager` foi ampliado para processar notificações recebidas e aplicar as alterações no sistema:

```python
class ExtensionManager:
    # Novo método para processar notificações
    async def handle_db_notification(self, payload: Dict[str, Any])
```

## Fluxo de Funcionamento

1. **Inicialização**:
   - Durante a inicialização do sistema, o PostgresListener é criado e iniciado
   - Estabelece conexão com o banco de dados PostgreSQL
   - Registra-se no canal "change_record_extension_ia"

2. **Escuta Contínua**:
   - Uma tarefa assíncrona monitora o canal de notificações
   - Usa polling não-bloqueante com select.select() para verificar notificações
   - Continua executando em segundo plano sem interferir nas outras operações

3. **Processamento de Eventos**:
   - Quando uma alteração ocorre na tabela `extension_ia`, o banco envia uma notificação
   - A notificação contém um payload JSON com a ação ('INSERT', 'UPDATE', 'DELETE') e os dados
   - O callback do ExtensionManager é chamado assincronamente com os dados recebidos

4. **Ações Automáticas**:
   - **INSERT**: Inicia um novo servidor socket para o ramal adicionado
   - **UPDATE**: Interrompe o servidor atual e reinicia com a configuração atualizada
   - **DELETE**: Remove o servidor do ramal excluído

5. **Persistência**:
   - Todas as alterações são salvas no arquivo de configuração local (fallback)
   - Garante que as alterações permaneçam mesmo após reinicialização

## Configuração do Banco de Dados

Para que este sistema funcione, é necessário ter triggers e funções configuradas no PostgreSQL:

```sql
-- Função que envia notificações quando há alterações na tabela
CREATE OR REPLACE FUNCTION notify_extension_ia_changes()
RETURNS trigger AS $$
DECLARE
  data JSON;
BEGIN
  -- Prepara os dados baseados na operação
  IF (TG_OP = 'DELETE') THEN
    data = row_to_json(OLD);
  ELSE
    data = row_to_json(NEW);
  END IF;

  -- Envia notificação com a ação e os dados
  PERFORM pg_notify(
    'change_record_extension_ia',
    json_build_object(
      'action', TG_OP,
      'data', data
    )::text
  );

  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger para INSERT
CREATE TRIGGER extension_ia_insert_trigger
AFTER INSERT ON extension_ia
FOR EACH ROW
EXECUTE PROCEDURE notify_extension_ia_changes();

-- Trigger para UPDATE
CREATE TRIGGER extension_ia_update_trigger
AFTER UPDATE ON extension_ia
FOR EACH ROW
EXECUTE PROCEDURE notify_extension_ia_changes();

-- Trigger para DELETE
CREATE TRIGGER extension_ia_delete_trigger
AFTER DELETE ON extension_ia
FOR EACH ROW
EXECUTE PROCEDURE notify_extension_ia_changes();
```

## Benefícios

1. **Atualizações Instantâneas**:
   - Alterações no banco de dados são refletidas imediatamente no sistema
   - Não há necessidade de reinicialização ou chamadas de API manuais

2. **Resiliência**:
   - Reconexão automática em caso de perda de conexão com o banco
   - Tratamento de erros robusto para evitar falhas no sistema principal

3. **Escalabilidade**:
   - Suporte natural para adição/remoção dinâmica de ramais em produção
   - Permite gerenciamento centralizado dos ramais via ferramentas de banco de dados

4. **Baixo Impacto**:
   - Implementação assíncrona não bloqueante
   - Uso eficiente de recursos de sistema

## Testando o Listener

Um script de teste foi incluído para validar o funcionamento do listener:

```bash
python test_db_listener.py
```

Este script conecta-se ao PostgreSQL e exibe no console as notificações recebidas em tempo real.

## Próximas Melhorias

1. **Cancelamento de Chamadas Ativas**:
   - Ao remover um ramal, fornecer opção para encerrar graciosamente chamadas em andamento

2. **Estatísticas em Tempo Real**:
   - Adicionar métricas para monitorar disponibilidade e uso de cada ramal

3. **Notificações Administrativas**:
   - Enviar alertas por e-mail/SMS quando ramais são modificados