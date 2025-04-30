# Testando AudioSocket Simple de Ponta a Ponta

Esta documentação descreve como testar o sistema AudioSocket Simple localmente de ponta a ponta, sem necessidade do Asterisk ou RabbitMQ/AMQP.

## Ferramenta de Teste: `test_dual_client.py`

A ferramenta `test_dual_client.py` foi desenvolvida para simular o fluxo completo de comunicação entre um visitante e um morador, permitindo testar toda a lógica da aplicação localmente.

### Funcionalidades Principais

- **Simulação Dupla**: Conecta-se simultaneamente à porta do visitante (IA) e à porta do morador
- **Fluxo Completo**: Permite avançar através de todos os estados da conversa de forma controlada
- **Áudio Bidirecional**: Transmite e recebe áudio via microfone/alto-falantes do seu computador
- **Interface Interativa**: Menu de console para controlar o fluxo do teste
- **ID de Sessão Compartilhado**: Mantém a continuidade entre as conexões do visitante e morador

### Pré-requisitos

- Python 3.8+
- PyAudio instalado (já incluído em `requirements.txt`)
- Aplicação AudioSocket Simple em execução (via `main.py` ou `main_dynamic.py`)

### Como Usar

1. Certifique-se de que a aplicação AudioSocket está rodando:
   ```bash
   # Para sistema com ramais fixos
   python main.py
   
   # OU para sistema com ramais dinâmicos
   python main_dynamic.py
   ```

2. Em outro terminal, execute o script de teste:
   ```bash
   python test_dual_client.py
   ```

3. Siga o menu interativo:
   - Conecte primeiro o visitante (opção 1)
   - Avance para coleta de dados (opção 2)
   - Conecte o morador (opção 3)
   - Avance para decisão do morador (opção 4)
   - Simule autorização (opção 5) ou negação (opção 6)
   - Finalize a sessão (opção 7) quando concluir o teste

### Opções de Linha de Comando

```bash
python test_dual_client.py --visitor-port 8080 --resident-port 8081 --host 127.0.0.1
```

- `--visitor-port`: Porta para conexão do visitante (padrão: 8080)
- `--resident-port`: Porta para conexão do morador (padrão: 8081)
- `--host`: Endereço do servidor (padrão: 127.0.0.1)
- `--session-id`: ID de sessão específico (opcional, útil para depuração)

### Testando Ramais Dinâmicos

Se estiver usando o sistema de ramais dinâmicos, especifique as portas configuradas:

```bash
python test_dual_client.py --visitor-port 9000 --resident-port 9001
```

### Resolução de Problemas

1. **Erro de conexão**: Verifique se a aplicação principal está rodando e se as portas especificadas estão corretas

2. **Sem áudio**: Certifique-se de que o microfone está funcionando (teste em outra aplicação como Zoom ou Google Meet)

3. **Erros de PyAudio**: Verifique se o PyAudio está instalado corretamente

4. **Interrupção**: Use Ctrl+C para interromper o teste a qualquer momento

### Fluxo de Teste Recomendado

1. **Visitante chama o condomínio**:
   - Conecte o visitante (opção 1)
   - Fale no microfone para interagir com a IA

2. **IA coleta dados do visitante**:
   - Após interação, avance para o estado de coleta de dados (opção 2)

3. **IA liga para o morador**:
   - Conecte o morador (opção 3)
   - Fale no microfone para simular o morador recebendo informações

4. **Morador toma decisão**:
   - Avance para o estado de decisão (opção 4)
   - Escolha autorizar (opção 5) ou negar acesso (opção 6)

5. **Finalização**:
   - Finalize a sessão (opção 7)
   - Desconecte os clientes (opção 8)

### Dicas Adicionais

- Use este script para testar novas funcionalidades sem precisar de hardware real
- Para testar com múltiplos ramais dinâmicos, execute o script diversas vezes com diferentes portas
- O script é uma excelente ferramenta para depuração de problemas no fluxo de conversação