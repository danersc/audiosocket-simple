# Arquitetura do Projeto AudioSocket-Simple

Este documento descreve em detalhes a arquitetura do sistema AudioSocket-Simple, seus componentes e como eles interagem.

## Visão Geral

O AudioSocket-Simple é um sistema de atendimento por IA para condomínios que utiliza o protocolo AudioSocket do Asterisk para gerenciar chamadas VoIP. O sistema permite automatizar o atendimento a visitantes e entregas, conectando-os com os moradores através de um assistente virtual inteligente.

## Componentes da Arquitetura

### 1. Servidores AudioSocket

O sistema mantém dois servidores AudioSocket paralelos:
- **Servidor Visitante (porta 8080)**: Atende chamadas provenientes de visitantes no portão.
- **Servidor Morador (porta 8081)**: Atende chamadas para moradores autorizados.
- **Servidor API (porta 8082)**: API HTTP para gerenciamento e testes.

### 2. Gerenciamento de Sessões

- **SessionManager**: Armazena e gerencia o estado das conversas entre visitantes e moradores.
- **SessionData**: Mantém filas de mensagens independentes para visitantes e moradores, além do histórico da conversa.
- **FlowState**: Define o estado do fluxo da conversa (COLETANDO_DADOS, VALIDADO, CHAMANDO_MORADOR, etc.).

### 3. Processamento de Áudio

- **VAD (Voice Activity Detection)**: Detecta quando o usuário começa e termina de falar.
- **Azure Speech Services**: Realiza a transcrição de fala para texto e síntese de texto para fala.
- **Sistema de Cache**: Armazena áudios sintetizados comuns para reduzir latência.

### 4. Integração com IA

- **CrewAI**: Framework utilizado para coordenar agentes especializados na extração de intenções e dados.
- **Agents**: Agentes especializados para diferentes tarefas de entendimento contextual.
- **Tasks**: Tarefas específicas para extrair informações como intenção, nome do visitante, apartamento e morador.
- **Fuzzy Matching**: Sistema de validação de dados utilizando comparação fuzzy para tolerância a erros.

### 5. Comunicação AMQP

- **RabbitMQ**: Utilizado para enviar solicitações de clicktocall para conectar com moradores.

### 6. Gestão de Recursos e Conexões

- **ResourceManager**: Gerencia recursos do sistema e conexões ativas.
- **Encerramento Ativo**: Sistema de envio de KIND_HANGUP para encerramento controlado de chamadas.

## Estados do Sistema

### Estados da StateMachine
- **STANDBY**: Estado inicial, aguardando nova chamada
- **USER_TURN**: Turno do usuário (sistema está ouvindo)
- **WAITING**: Estado intermediário de processamento
- **IA_TURN**: Turno da IA (sistema está respondendo)

### Estados do ConversationFlow
- **COLETANDO_DADOS**: Fase de extração de informações do visitante
- **VALIDADO**: Dados foram validados com sucesso
- **CHAMANDO_MORADOR**: Sistema está tentando contactar o morador
- **ESPERANDO_MORADOR**: Morador atendeu, aguardando resposta
- **FINALIZADO**: Fluxo concluído, chamada encerrada

## Fluxo de Dados

O fluxo de dados no sistema segue este caminho geral:

1. **Entrada de Áudio** → **VAD** → **Transcrição** → **Extração de Intenções** → **Validação** → **Contato com Morador** → **Processamento de Resposta** → **Síntese de Voz** → **Saída de Áudio**

### Comunicação Entre Componentes

```
┌────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│                │       │                 │       │                 │
│  AudioSocket   │<─────>│ SessionManager  │<─────>│ ConversationFlow│
│                │       │                 │       │                 │
└────────────────┘       └─────────────────┘       └─────────────────┘
        ▲                        ▲                         ▲
        │                        │                         │
        ▼                        ▼                         ▼
┌────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│                │       │                 │       │                 │
│ Azure Speech   │       │ ResourceManager │       │     CrewAI      │
│                │       │                 │       │                 │
└────────────────┘       └─────────────────┘       └─────────────────┘
```

## Modelo de Intenções

O sistema extrai e processa intenções estruturadas:
- **intent_type**: Tipo de intenção (visita/entrega)
- **interlocutor_name**: Nome do visitante
- **apartment_number**: Número do apartamento
- **resident_name**: Nome do morador

## Tecnologias Principais

- **Python**: Linguagem principal do projeto
- **asyncio**: Para operações assíncronas e concorrência
- **Azure Speech Services**: Para processamento de fala
- **webrtcvad**: Para detecção de atividade de voz
- **CrewAI + LLMs**: Para processamento de linguagem natural e extração de intenções
- **Socket TCP**: Para comunicação via protocolo AudioSocket
- **aiohttp**: Para API HTTP de gerenciamento
- **AMQP/RabbitMQ**: Para comunicação com sistemas externos

## Pontos Fortes da Arquitetura

1. **Design Assíncrono**: Utiliza `asyncio` para operações não bloqueantes e concorrentes.
2. **Separação de Responsabilidades**: Componentes bem definidos com funções específicas.
3. **Máquina de Estados Robusta**: Transições claras entre estados da conversa.
4. **Pipeline de IA Modular**: Extração de informações em etapas segregadas e especializadas.
5. **Filas de Mensagens**: Comunicação eficiente entre componentes através de filas assíncronas.
6. **Tratamento de Erros**: Sistema robusto de tratamento de exceções e encerramento gracioso.
7. **Cache de Performance**: Sistema de cache para melhorar desempenho de síntese de voz.

## Diagrama de Interação Durante uma Chamada

```
Visitante    AudioSocket    SessionManager    ConversationFlow    Azure      Morador
   │              │                │                │               │            │
   │───chamada───>│                │                │               │            │
   │              │───cria sessão─>│                │               │            │
   │              │<──confirma────┤                │               │            │
   │<──saudação───│                │                │               │            │
   │───fala───────>│                │                │               │            │
   │              │───transcreve──>│                │────────────────────>│            │
   │              │<──texto────────│                │<───────────────────┤            │
   │              │                │───processa────>│                │            │
   │              │                │<──resposta─────│                │            │
   │              │                │                │───valida dados>│            │
   │              │                │                │<──confirmação──│            │
   │              │                │                │────────────────────────────>│
   │              │                │                │<───────────────────────────┤
   │<──resultado──│                │                │               │            │
   │              │───encerra─────>│──────────────>│               │            │
   │─────fim─────>│                │                │               │            │
```

## Próximos Passos

Consulte os documentos seguintes para detalhes específicos sobre:
- Configuração e implantação
- Fluxos de comunicação
- Protocolos e formatos de mensagem
- Gerenciamento de chamadas múltiplas
- Testes e verificação do sistema

---

*Próximo documento: [03-configuracao.md](03-configuracao.md)*