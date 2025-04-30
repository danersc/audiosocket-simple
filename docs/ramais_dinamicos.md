# Sistema de Ramais Dinâmicos

Data: 26/04/2025

## Visão Geral

Foi implementado um sistema de gerenciamento dinâmico de ramais de IA que permite configurar múltiplos ramais e portas simultaneamente. Essa atualização possibilita:

1. Configurar diferentes ramais para diferentes condomínios
2. Gerenciar as portas dos servidores socket dinamicamente
3. Associar cada ramal de IA a um ramal de retorno específico
4. Atualizar configurações em tempo real sem reiniciar o sistema

## Componentes Implementados

### 1. Módulo de Extensões (`extensions/`)

Novo pacote para gerenciar toda a infraestrutura de ramais:

- **DBConnector**: Gerencia conexão com PostgreSQL para obter configurações
- **ServerManager**: Controla a criação e gerenciamento dos servidores socket
- **ConfigPersistence**: Salva configurações localmente para resiliência offline
- **APIServer**: Fornece endpoints HTTP para gerenciamento remoto
- **ExtensionManager**: Coordena todos os componentes acima

### 2. Alterações em Módulos Existentes

#### `conversation_flow.py`

- Modificado para receber o `extension_manager` como parâmetro
- Atualizado `enviar_clicktocall()` para obter o ramal de retorno correto baseado no `call_id`
- Adicionado suporte para múltiplos ramais no processo de chamada ao morador

#### `audiosocket_handler.py`

- Adicionada função `set_extension_manager()` para definir o gerenciador globalmente
- Implementada função `get_local_port()` para detectar a porta sendo usada por uma conexão
- Modificados `iniciar_servidor_audiosocket_visitante` e `iniciar_servidor_audiosocket_morador` para registrar porta e ramal
- Melhorado logging para incluir informações do ramal e porta

#### `session_manager.py`

- Atualizado para receber e propagar o `extension_manager`
- Modificado `SessionData` para passar o extension_manager para o ConversationFlow
- Aprimorado o gerenciamento de sessões para suportar múltiplos ramais

### 3. Novos Scripts

#### `main_dynamic.py`

Novo ponto de entrada que substitui o `main.py` original, com recursos de:
- Inicialização do sistema de ramais dinâmicos
- Monitoramento contínuo dos servidores
- Atualização periódica de configurações (opcional)
- Encerramento gracioso

#### `setup_system.py`

Script auxiliar para inicialização que:
- Configura todos os componentes do sistema
- Estabelece conexão com banco de dados
- Inicializa o sistema de ramais
- Pré-sintetiza frases comuns para cache

## Banco de Dados e Configuração

As configurações de ramais são armazenadas na tabela `extension_ia` com a estrutura:

```sql
create table public.extension_ia
(
    extension_ia_id          integer generated always as identity,
    extension_ia_number      char(50) not null, -- Ramal da IA
    extension_ia_return      char(50) not null, -- Ramal de retorno 
    extension_ia_ip          char(50) not null, -- IP do servidor (normalmente 0.0.0.0)
    extension_ia_number_port char(50) not null, -- Porta para o ramal da IA
    condominium_id           integer  not null, -- ID do condomínio
    extension_ia_return_port char(50)           -- Porta para o ramal de retorno
);
```

## Arquivo de Configuração .env

```
# Configurações do banco de dados
DB_NAME=postgres
DB_USER=admincd
DB_PASSWORD=Isabela@2022!!
DB_HOST=dev-postgres-cd.postgres.database.azure.com
DB_PORT=5432

# Configurações do servidor
API_PORT=8082
AUTO_REFRESH=false

# Outras configurações
SILENCE_THRESHOLD_SECONDS=1.5
AI_API_URL=http://localhost:8000/messages
```

## API de Gerenciamento

Uma API HTTP está disponível para gerenciar os ramais:

- **GET /api/status**: Lista todos os ramais ativos com suas configurações
- **POST /api/refresh**: Atualiza as configurações a partir do banco de dados
- **GET /api/extensions**: Lista todas as configurações disponíveis no banco
- **POST /api/restart**: Reinicia um ramal específico (por ID ou número)

## Fluxo de Inicialização

1. Carrega variáveis de ambiente do arquivo `.env`
2. Tenta conectar ao banco de dados PostgreSQL
3. Carrega configurações de ramais (do banco ou arquivo local)
4. Cria servidores socket para cada ramal configurado
5. Inicia a API HTTP para gerenciamento
6. Mantém os servidores rodando indefinidamente

## Persistência e Resiliência

- Configurações são salvas localmente em `./data/ramais_config.json`
- Se não conseguir acessar o banco, usa as configurações locais
- Em caso de conflito de portas, tenta portas alternativas automaticamente
- Encerramento gracioso dos servidores em caso de interrupção

## Integração com o Sistema Existente

O mecanismo de chamada para o morador foi aprimorado:
- Usa o ramal correto baseado no contexto da chamada
- Associa o UUID da sessão com a porta e ramal corretos
- Mantém a compatibilidade com todas as funcionalidades existentes

## Exemplo de Uso

Para iniciar o sistema com ramais dinâmicos:

```bash
python main_dynamic.py
```

Para atualizar as configurações de ramais:

```bash
curl -X POST http://localhost:8082/api/refresh
```

Para verificar o status dos ramais ativos:

```bash
curl http://localhost:8082/api/status
```

## Conclusão

O sistema de ramais dinâmicos permite escalar o atendimento de IA para múltiplos condomínios simultaneamente, com cada condomínio podendo ter seus próprios ramais de IA e retorno. A implementação mantém toda a lógica de negócio existente enquanto adiciona flexibilidade na infraestrutura de comunicação.