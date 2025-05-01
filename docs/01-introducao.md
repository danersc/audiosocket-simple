# Introdução ao AudioSocket-Simple

Este documento fornece uma visão geral do projeto AudioSocket-Simple, um sistema de atendimento por IA para condomínios que utiliza o protocolo AudioSocket do Asterisk.

## Contexto

O AudioSocket-Simple é uma aplicação desenvolvida para automatizar o atendimento de chamadas em portarias de condomínios, permitindo:

1. Atender visitantes no portão
2. Coletar informações como nome, apartamento e motivo da visita
3. Contatar moradores para autorização
4. Gerenciar todo o fluxo conversacional entre visitante e morador

## Configuração do Ambiente de Desenvolvimento

### Pré-requisitos

- Python 3.8+ 
- Node.js v20.12.0
- Banco de dados PostgreSQL (opcional, para testes locais)
- Bibliotecas Python (webrtcvad, Azure Speech SDK, etc.)

### Preparando o Ambiente

Antes de começar a trabalhar com o código, configure o ambiente de desenvolvimento:

```bash
# Ativar o Node.js correto via NVM
nvm use v20.12.0

# Ativar o ambiente virtual Python
source /Users/danerdosreis/development/environments/audiosocket-simple/bin/activate

# Instalar dependências Python
pip install -r requirements.txt
```

## Arquitetura do Sistema

### Componentes Principais

1. **Servidores AudioSocket**
   - Socket TCP para visitantes (porta 8080)
   - Socket TCP para moradores (porta 8081)
   - API HTTP para gerenciamento e testes (porta 8082)

2. **Gerenciamento de Sessões**
   - SessionManager: armazena e gerencia o estado das conversas
   - ConversationFlow: controla o fluxo de interação e lógica de negócio

3. **Processamento de Áudio**
   - VAD (Voice Activity Detection): detecta quando o usuário fala e para
   - Transcrição de áudio via Azure Speech Services
   - Síntese de voz via Azure Speech Services

4. **Inteligência Artificial**
   - Sistema de extração de intenções usando LLMs
   - Processamento estruturado por etapas (intent, nome, apartamento)
   - Fuzzy matching para validação de dados

## Fluxo Básico de Operação

1. **Inicialização**:
   - Sistema inicia servidores na porta 8080 (visitante) e 8081 (morador)
   - Pré-sintetiza frases comuns para melhor desempenho

2. **Atendimento do Visitante**:
   - Visitante liga para o ramal do condomínio
   - Sistema responde com mensagem de boas-vindas
   - Coleta informações (nome, apartamento, motivo)
   - Valida dados informados

3. **Contato com o Morador**:
   - Sistema inicia chamada para o morador
   - Informa sobre o visitante aguardando
   - Recebe autorização ou negação

4. **Conclusão**:
   - Informa o visitante sobre a decisão do morador
   - Encerra ativamente a chamada (KIND_HANGUP)
   - Libera recursos da sessão

## Próximos Passos

Consulte os outros documentos desta série para informações detalhadas sobre:

- Configuração e implantação
- Fluxos de comunicação detalhados
- Sistema de gerenciamento de chamadas
- Tratamento de erros e encerramento de chamadas
- Otimizações e melhorias de desempenho
- Testes e verificações

---

*Próximo documento: [02-arquitetura.md](02-arquitetura.md)*