# Desenvolvimento Futuro e Backlog

Este documento lista melhorias planejadas, backlog de funcionalidades e direções futuras para o projeto AudioSocket-Simple. Ele serve como um registro das próximas etapas e considerações para o desenvolvimento contínuo do sistema.

## Itens de Backlog

### Melhorias de Performance

- [ ] **Paralelização de Processamento de IA**
  - Implementar extração simultânea de intenções usando `asyncio.gather()`
  - Prioridade: Alta
  - Benefício: Redução de ~30-40% no tempo total de processamento de IA

- [ ] **Transcrição em Streaming**
  - Implementar processamento de áudio em streaming em vez de batch
  - Prioridade: Média
  - Benefício: Feedback mais rápido durante fala longa

- [ ] **Otimização de Modelos LLM**
  - Testar modelos LLM menores e mais rápidos para tarefas específicas
  - Prioridade: Média
  - Benefício: Redução de custos e latência

### Novos Recursos

- [ ] **Timeout Automático de Sessões**
  - Implementar encerramento automático após inatividade prolongada
  - Prioridade: Alta
  - Detalhes: Encerrar chamada após 2 minutos sem interação

- [ ] **Síntese de Voz Aprimorada**
  - Explorar vozes mais naturais e expressivas
  - Prioridade: Baixa
  - Detalhes: Testar novos modelos de síntese com prosódia melhorada

### Monitoramento e Observabilidade

- [ ] **Dashboard em Tempo Real**
  - Implementar dashboard para monitoramento de chamadas ativas
  - Prioridade: Média
  - Detalhes: Métricas de tempo real, estado das chamadas, logs

- [ ] **Sistema de Métricas Detalhadas**
  - Coletar métricas detalhadas sobre todos os aspectos do sistema
  - Prioridade: Média
  - Detalhes: Tempo médio de chamada, taxa de sucesso, uso de cache

- [ ] **Alarmes e Notificações**
  - Sistema para alertar sobre problemas ou anomalias
  - Prioridade: Alta
  - Detalhes: Notificações via e-mail ou Slack para erros críticos

### Infraestrutura e Arquitetura

- [ ] **Sistema de Multi-Servidores**
  - Implementar uma aplicação supervisora para gerenciar ramais dinâmicos
  - Prioridade: Alta
  - Detalhes: Aplicação separada que escuta alterações no banco de dados e inicia/para servidores AudioSocket

- [ ] **Containerização**
  - Preparar sistema para execução em contêineres Docker
  - Prioridade: Média
  - Detalhes: Dockerfile, docker-compose.yml, considerações para estado

- [ ] **Configuração Externalizada**
  - Mover todas as configurações para variáveis de ambiente ou arquivo externo
  - Prioridade: Média
  - Detalhes: Separar completamente código e configuração

### Segurança e Resiliência

- [ ] **Autenticação na API**
  - Adicionar autenticação para endpoints da API HTTP
  - Prioridade: Alta
  - Detalhes: Implementar sistema de API keys ou tokens JWT

- [ ] **TLS para AudioSocket**
  - Investigar possibilidade de usar TLS para conexões AudioSocket
  - Prioridade: Baixa
  - Detalhes: Pesquisar suporte no Asterisk, implementar se possível

- [ ] **Persistência de Estado**
  - Salvar estado das sessões para recuperação em caso de reinício
  - Prioridade: Média
  - Detalhes: Serializar estado mínimo para arquivo ou banco de dados

## Ramais Dinâmicos

> **Nota**: A funcionalidade de ramais dinâmicos gerenciados pela própria aplicação foi removida desta implementação devido à complexidade de gerenciar múltiplos sockets em diversas portas. Em vez disso, planejamos criar uma aplicação supervisora separada que gerenciará os servidores AudioSocket.

### Plano de Implementação:

1. **Aplicação Supervisora**
   - Lê configurações do banco de dados PostgreSQL
   - Inicia instâncias separadas do AudioSocket-Simple
   - Monitora saúde e reinicia quando necessário

2. **Arquitetura Proposta**
   ```
   ┌───────────────┐      ┌─────────────────┐
   │ PostgreSQL DB │ ←──→ │ Supervisor App  │
   └───────────────┘      └────────┬────────┘
                                    │
                                    ↓
         ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
         │ AudioSocket   │  │ AudioSocket   │  │ AudioSocket   │
         │ Instance #1   │  │ Instance #2   │  │ Instance #3   │
         └───────────────┘  └───────────────┘  └───────────────┘
   ```

## Integração e APIs

- [ ] **API para Gestão de Chamadas**
  - Endpoints para visualizar, iniciar e finalizar chamadas
  - Prioridade: Média
  - Detalhes: Expandir a API HTTP atual com mais funcionalidades

- [ ] **Webhook para Eventos**
  - Sistema de notificação via webhook para eventos importantes
  - Prioridade: Baixa
  - Detalhes: Notificar sistemas externos sobre início/fim de chamadas

- [ ] **Integração com Sistemas de Condomínio**
  - APIs para interagir com sistemas de gestão de condomínio
  - Prioridade: Média
  - Detalhes: Registro de visitas, consulta de moradores autorizados

## Testes e Qualidade

- [ ] **Testes Unitários**
  - Desenvolver suite completa de testes unitários
  - Prioridade: Alta
  - Detalhes: Cobertura para componentes críticos como SessionManager, ConversationFlow

- [ ] **Testes de Integração**
  - Testes automatizados para verificar integrações
  - Prioridade: Média
  - Detalhes: Verificar comunicação entre componentes

- [ ] **Testes de Carga**
  - Verificar comportamento sob carga pesada
  - Prioridade: Média
  - Detalhes: Simular múltiplas chamadas simultâneas

## Experiência do Usuário

- [ ] **Detecção de Interrupção**
  - Melhorar detecção quando visitante ou morador interrompem a IA
  - Prioridade: Média
  - Detalhes: Detectar fala durante reprodução de áudio

- [ ] **Personalização de Vozes**
  - Permitir escolha de vozes por condomínio
  - Prioridade: Baixa
  - Detalhes: Configuração por condomínio no banco de dados

- [ ] **Confirmações Mais Naturais**
  - Melhorar as respostas de confirmação para soarem mais naturais
  - Prioridade: Média
  - Detalhes: Variar respostas, utilizar contexto melhor

## Como Contribuir

Se você deseja implementar algum destes itens ou sugerir novos:

1. Selecione um item do backlog
2. Crie uma branch feature/[nome-da-funcionalidade]
3. Implementa a funcionalidade
4. Abra um Pull Request
5. Atualize este documento marcando o item como concluído

## Status de Implementação

Para marcar um item como concluído, atualize o documento substituindo `[ ]` por `[x]` e adicione a data de conclusão:

```markdown
- [x] **Nome da Funcionalidade** (Concluído: 15/05/2025)
  - Descrição da funcionalidade
  - Detalhes da implementação
```

## Priorização

A priorização dos itens acima é baseada em:

1. **Valor para o Usuário**: Impacto na experiência do usuário
2. **Viabilidade Técnica**: Facilidade de implementação
3. **Dependências**: Requisitos de outros componentes

A ordem de implementação deve seguir geralmente a prioridade indicada, mas pode ser ajustada conforme necessidades específicas do projeto.

---

*Fim da documentação - Voltar ao [01-introducao.md](01-introducao.md)*
