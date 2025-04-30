# Guia Completo de Testes com test_dual_client.py

Este guia apresenta uma metodologia detalhada para testar efetivamente o sistema AudioSocket Simple utilizando a ferramenta `test_dual_client.py`.

## Preparação do Ambiente

### 1. Configuração Básica

```bash
# Ativação do ambiente virtual (se aplicável)
source venv/bin/activate

# Execução do servidor AudioSocket
python main_dynamic.py

# Em outro terminal, execute o cliente de teste
./test_dual_client.py
```

### 2. Configurações Avançadas

Para testar configurações específicas de ramais:

```bash
./test_dual_client.py --visitor-port 9000 --resident-port 9001 --host 127.0.0.1
```

Para depuração com ID de sessão específico:

```bash
./test_dual_client.py --session-id "f8e7d6c5-b4a3-2c1d-9e0f-a1b2c3d4e5f6"
```

## Casos de Teste Essenciais

### Caso 1: Fluxo Completo Padrão (Autorização)

1. Inicie o cliente de teste
2. Selecione **1. Conectar visitante**
3. Fale no microfone simulando um visitante
4. Selecione **2. Avançar para Coleta de Dados**
5. Selecione **3. Conectar morador**
6. Selecione **4. Avançar para Decisão do Morador**
7. Selecione **5. Simular Autorização do Morador**
8. Selecione **7. Finalizar sessão**

**Resultado esperado:** O fluxo deve completar sem erros, com transições suaves entre os estados.

### Caso 2: Fluxo de Negação de Acesso

1. Inicie o cliente de teste
2. Selecione **1. Conectar visitante**
3. Fale no microfone simulando um visitante
4. Selecione **2. Avançar para Coleta de Dados**
5. Selecione **3. Conectar morador**
6. Selecione **4. Avançar para Decisão do Morador**
7. Selecione **6. Simular Negação do Morador**
8. Selecione **7. Finalizar sessão**

**Resultado esperado:** O sistema deve processar corretamente a negação e finalizar o fluxo.

### Caso 3: Recuperação de Desconexão do Visitante

1. Inicie o cliente de teste
2. Selecione **1. Conectar visitante**
3. Fale no microfone simulando um visitante
4. Selecione **8. Desconectar todos os clientes**
5. Selecione **1. Conectar visitante** (mesma sessão)
6. Continue com o fluxo normal

**Resultado esperado:** O sistema deve permitir a reconexão e continuar o fluxo.

### Caso 4: Teste de Carga Básica (Múltiplas Sessões)

Execute múltiplas instâncias do cliente em terminais diferentes:

```bash
# Terminal 1
./test_dual_client.py --visitor-port 9000 --resident-port 9001

# Terminal 2
./test_dual_client.py --visitor-port 9002 --resident-port 9003
```

**Resultado esperado:** Todas as sessões devem funcionar simultaneamente sem interferência.

## Metodologia de Validação

### 1. Validação de Áudio

Durante os testes, verifique:

- **Qualidade de áudio**: O áudio deve estar claro em ambas as direções
- **Latência**: A transmissão deve ocorrer sem atrasos perceptíveis
- **Cortes de áudio**: Não deve haver interrupções na transmissão

### 2. Verificação de Estados

Observe os logs durante a transição entre estados:

```bash
tail -f logs/audiosocket.log
```

Confirme que cada mudança de estado é registrada corretamente no log.

### 3. Verificação de Recursos

Monitore o uso de recursos durante o teste:

```bash
# Em outro terminal
top -pid $(pgrep -f "python main_dynamic.py")
```

### 4. Testes de Resiliência

#### Teste de Recuperação de Erro

1. Durante um teste ativo, force um erro (como desconexão de rede temporária)
2. Verifique se o sistema se recupera adequadamente

#### Teste de Timeout

1. Durante uma conversa, fique em silêncio por 30-60 segundos
2. Verifique se o sistema trata corretamente o timeout

## Roteiro de Testes Completo

### 1. Validação Inicial

| Etapa | Ação | Resultado Esperado |
|-------|------|-------------------|
| 1 | Conectar visitante | Conexão estabelecida, audio bidirecional |
| 2 | Avançar para coleta de dados | Transição bem-sucedida |
| 3 | Conectar morador | Conexão estabelecida, audio bidirecional |
| 4 | Avançar para decisão | Estado atualizado corretamente |
| 5 | Simular autorização | Fluxo de autorização executado |

### 2. Verificação de Logs

Após o teste, verifique:

1. IDs de sessão consistentes nos logs
2. Transições de estado registradas
3. Mensagens de erro (não deve haver erros inesperados)

### 3. Validação de Desempenho

| Métrica | Aceitável | Investigar se |
|---------|-----------|--------------|
| Latência de áudio | <200ms | >500ms |
| Uso de CPU | <30% | >70% |
| Uso de memória | <200MB | >500MB |
| Tempo de resposta | <1s | >3s |

## Dicas para Teste Eficiente

### Gerar Áudio de Teste

Para testes mais consistentes, use áudio pré-gravado:

```bash
# Reproduza um arquivo de áudio durante o teste
while true; do
  afplay test_audio.mp3
  sleep 2
done
```

### Automação de Testes

Script básico para automação de testes:

```bash
#!/bin/bash
# test_automation.sh

echo "Iniciando teste automatizado"
echo "1" | ./test_dual_client.py &
PID=$!
sleep 5
echo "2" > /dev/tty  # Simula entrada do usuário
sleep 3
echo "3" > /dev/tty
sleep 3
# Continue...
kill $PID
echo "Teste concluído"
```

### Verificação Pós-teste

Após cada sessão de teste, analise:

1. Arquivo de log completo
2. Uso de recursos durante o teste
3. Qualquer comportamento inesperado

## Resolução de Problemas Comuns

| Problema | Possível Causa | Solução |
|----------|---------------|---------|
| Falha na conexão do visitante | Servidor não está rodando | Verifique se `main_dynamic.py` está em execução |
| Sem áudio | Problema no microfone/alto-falante | Verifique as configurações de áudio do sistema |
| Erro "Address already in use" | Porta já em uso | Use portas diferentes ou encerre processos anteriores |
| Conexão intermitente | Problemas de rede | Teste em rede local estável |
| Áudio com ruído | Configurações de áudio | Ajuste o volume e verifique o microfone |

## Estratégia de Teste Incremental

### Nível 1: Testes Básicos

- Fluxo completo com autorização
- Fluxo completo com negação

### Nível 2: Testes de Casos de Borda

- Reconexão após desconexão
- Tempos limite e inatividade

### Nível 3: Testes de Carga

- Múltiplas sessões simultâneas
- Operações de longa duração

### Nível 4: Testes de Integração

- Integração com outras partes do sistema
- Verificação end-to-end com componentes reais quando possível

## Conclusão

O `test_dual_client.py` é uma ferramenta poderosa para validar o sistema AudioSocket Simple. Seguindo esta metodologia de testes, você pode identificar e resolver problemas antes que eles afetem o ambiente de produção.

Lembre-se de documentar quaisquer problemas encontrados e suas soluções para referência futura e melhoria contínua do sistema.