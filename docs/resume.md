# Arquitetura do Projeto AudioSocket-Simple

## Visão Geral

O AudioSocket-Simple é um sistema de atendimento por IA para condomínios que utiliza o protocolo AudioSocket do Asterisk para gerenciar chamadas VoIP. O sistema permite automatizar o atendimento a visitantes e entregas, conectando-os com os moradores através de um assistente virtual inteligente.

## Componentes Principais

### 1. Servidores AudioSocket

O sistema mantém dois servidores AudioSocket paralelos:
- **Servidor Visitante (porta 8080)**: Atende chamadas provenientes de visitantes no portão.
- **Servidor Morador (porta 8081)**: Atende chamadas para moradores autorizados.

### 2. Gerenciamento de Sessões

- **SessionManager**: Armazena e gerencia o estado das conversas entre visitantes e moradores.
- **SessionData**: Mantém filas de mensagens independentes para visitantes e moradores, além do histórico da conversa.
- **FlowState**: Define o estado do fluxo da conversa (COLETANDO_DADOS, VALIDADO, CHAMANDO_MORADOR, etc.).

### 3. Processamento de Áudio

- **VAD (Voice Activity Detection)**: Detecta quando o usuário começa e termina de falar.
- **Azure Speech Services**: Realiza a transcrição de fala para texto e síntese de texto para fala.

### 4. Integração com IA

- **CrewAI**: Framework utilizado para coordenar agentes especializados na extração de intenções e dados.
- **Agents**: Agentes especializados para diferentes tarefas de entendimento contextual.
- **Tasks**: Tarefas específicas para extrair informações como intenção, nome do visitante, apartamento e morador.

### 5. Comunicação AMQP

- **RabbitMQ**: Utilizado para enviar solicitações de clicktocall para conectar com moradores.

## Fluxo de Uma Chamada Completa

1. **Inicialização**:
   - O sistema inicia dois servidores (visitante e morador) para receber conexões.

2. **Atendimento ao Visitante**:
   - Visitante realiza uma chamada para o sistema.
   - O sistema inicia uma nova sessão e responde com mensagem de saudação.
   - Duas tarefas assíncronas são iniciadas: uma para receber áudio e outra para enviar respostas.

3. **Extração de Intenções**:
   - O sistema usa VAD para detectar quando o visitante está falando.
   - Quando o visitante termina de falar, o áudio é transcrito pelo Azure Speech.
   - A transcrição é enviada ao `SessionManager.process_visitor_text()`.
   - O `ConversationFlow` processa a mensagem através de `on_visitor_message()`.

4. **Pipeline de Compreensão**:
   - A mensagem é processada pelo `process_user_message_with_coordinator()`.
   - A IA extrai informações em etapas sequenciais:
     1. Identificação do tipo de intenção (entrega/visita)
     2. Extração do nome do visitante
     3. Extração do número do apartamento e nome do morador

5. **Validação dos Dados**:
   - Após coletar todos os dados, o sistema valida as informações usando `validar_intent_com_fuzzy()`.
   - Verifica se o apartamento existe e se o morador corresponde aos registros.

6. **Contato com o Morador**:
   - Quando os dados são validados, o estado muda para `CHAMANDO_MORADOR`.
   - O sistema envia uma mensagem AMQP via RabbitMQ para iniciar uma chamada com o morador.
   - Inicia um monitor assíncrono para verificar se o morador atendeu dentro de 10 segundos.
   - Se não atender, tenta novamente (até 2 tentativas).

7. **Interação com o Morador**:
   - Quando o morador atende, o estado muda para `ESPERANDO_MORADOR`.
   - O sistema informa o morador sobre o visitante aguardando.
   - O morador responde "SIM" ou "NÃO" para autorizar ou negar a entrada.

8. **Conclusão**:
   - Baseado na resposta do morador, o sistema informa o visitante.
   - O estado muda para `FINALIZADO`.
   - A sessão é encerrada e removida do gerenciador.

## Estados da Máquina de Fluxo de Conversa

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

## Modelo de Intenções

O sistema extrai e processa intenções estruturadas:
- **intent_type**: Tipo de intenção (visita/entrega)
- **interlocutor_name**: Nome do visitante
- **apartment_number**: Número do apartamento
- **resident_name**: Nome do morador

## Pontos Fortes da Arquitetura

1. **Design Assíncrono**: Utiliza `asyncio` para operações não bloqueantes e concorrentes.
2. **Separação de Responsabilidades**: Componentes bem definidos com funções específicas.
3. **Máquina de Estados Robusta**: Transições claras entre estados da conversa.
4. **Pipeline de IA Modular**: Extração de informações em etapas segregadas e especializadas.
5. **Filas de Mensagens**: Comunicação eficiente entre componentes através de filas assíncronas.
6. **Integração com Sistemas Externos**: Azure Speech Services e RabbitMQ.

## Possíveis Melhorias

1. **Tratamento de Erros**: Implementar estratégias mais robustas para falhas na transcrição ou comunicação.
2. **Testes Automatizados**: Adicionar testes unitários e de integração.
3. **Configuração Externalizada**: Mover valores hardcoded para arquivos de configuração.
4. **Logging Estruturado**: Melhorar o sistema de logs para facilitar depuração.
5. **Métricas e Monitoramento**: Adicionar telemetria para monitorar desempenho e identificar gargalos.
6. **Cache**: Implementar cache para respostas de IA frequentes.
7. **Autenticação e Segurança**: Adicionar camadas de segurança para o protocolo AudioSocket.