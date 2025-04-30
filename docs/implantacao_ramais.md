# Guia de Implantação - Sistema de Ramais Dinâmicos

Data: 26/04/2025

## Introdução

Este documento detalha o processo de implantação e configuração do novo sistema de ramais dinâmicos para a plataforma AudioSocket. O sistema permite configurar múltiplos ramais de IA e portas de forma dinâmica, possibilitando o atendimento simultâneo de vários condomínios.

## Pré-requisitos

- Python 3.8+
- PostgreSQL 12+
- Acesso ao banco de dados com permissões para leitura
- Biblioteca webrtcvad para detecção de voz
- Azure Speech Services para transcrição e síntese de voz
- API de IA para processamento de mensagens

## Configuração do Ambiente

### 1. Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

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

# Configurações do Azure Speech
AZURE_SPEECH_KEY=sua_chave_do_azure
AZURE_SPEECH_REGION=sua_regiao_do_azure

# Outras configurações
SILENCE_THRESHOLD_SECONDS=1.5
AI_API_URL=http://localhost:8000/messages
```

### 2. Banco de Dados

O sistema espera encontrar a tabela `extension_ia` com a seguinte estrutura:

```sql
CREATE TABLE public.extension_ia (
    extension_ia_id INTEGER GENERATED ALWAYS AS IDENTITY,
    extension_ia_number CHAR(50) NOT NULL,
    extension_ia_return CHAR(50) NOT NULL,
    extension_ia_ip CHAR(50) NOT NULL,
    extension_ia_number_port CHAR(50) NOT NULL,
    condominium_id INTEGER NOT NULL,
    extension_ia_return_port CHAR(50)
);
```

Exemplo de inserção de dados:

```sql
INSERT INTO public.extension_ia (
    extension_ia_number, 
    extension_ia_return, 
    extension_ia_ip, 
    extension_ia_number_port, 
    condominium_id, 
    extension_ia_return_port
) VALUES (
    '1001',     -- Ramal da IA
    '1002',     -- Ramal de retorno
    '0.0.0.0',  -- IP (0.0.0.0 para aceitar todas as interfaces)
    '8080',     -- Porta para o ramal da IA
    10,         -- ID do condomínio
    '8081'      -- Porta para o ramal de retorno
);
```

### 3. Dependências Python

Instale as dependências necessárias:

```bash
pip install -r requirements.txt
```

## Instalação

1. Clone o repositório ou coloque os arquivos no diretório desejado
2. Crie o arquivo `.env` conforme descrito acima
3. Certifique-se de que as pastas `logs` e `data` existem:

```bash
mkdir -p logs data
```

## Primeira Execução

Execute o script `main_dynamic.py` para iniciar o sistema:

```bash
python main_dynamic.py
```

Durante a primeira execução:

1. O sistema tentará se conectar ao banco de dados
2. Carregará as configurações de ramais
3. Iniciará um servidor socket para cada par de ramais (IA/retorno)
4. Iniciará a API HTTP para gerenciamento
5. Pré-sintetizará frases comuns para melhorar a performance

Se não houver ramais configurados ou não for possível acessar o banco de dados, o sistema iniciará em "modo de compatibilidade" com um único par de servidores nas portas 8080 e 8081.

## Operação e Manutenção

### Verificando o Status

Você pode verificar o status dos ramais ativos através da API:

```bash
curl http://localhost:8082/api/status
```

### Atualizando Configurações

Para atualizar as configurações de ramais a partir do banco de dados:

```bash
curl -X POST http://localhost:8082/api/refresh
```

### Reiniciando um Ramal Específico

Se um ramal específico apresentar problemas, você pode reiniciá-lo:

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"ramal": "1003"}' \
  http://localhost:8082/api/restart
```

### Logs

Os logs do sistema são armazenados em `./logs/audiosocket.log`. Para acompanhar os logs em tempo real:

```bash
tail -f logs/audiosocket.log
```

## Estrutura de Resiliência

### Arquivos de Configuração Local

O sistema salva as configurações de ramais em um arquivo local:

```
./data/ramais_config.json
```

Isso permite que o sistema inicie mesmo sem acesso ao banco de dados, usando a última configuração conhecida.

### Tratamento de Conflitos de Porta

Se uma porta configurada já estiver em uso, o sistema tentará automaticamente portas alternativas, incrementando o número da porta original até encontrar uma disponível.

### Recuperação de Falhas

O sistema inclui mecanismos para recuperação automática em caso de falhas:

1. **Disconnects de socket**: Tratados graciosamente sem afetar outras sessões
2. **Falhas de banco de dados**: Usa configurações locais persistidas
3. **Problemas na API**: Isolados para não afetar o funcionamento dos servidores socket

## Configuração do Asterisk

O Asterisk deve ser configurado para direcionar as chamadas para os ramais corretos. Exemplo de configuração:

```
[from-internal]
exten => 1001,1,Answer()
exten => 1001,n,AudioSocket(127.0.0.1:8080,${CHANNEL(uniqueid)})
exten => 1001,n,Hangup()

exten => 1003,1,Answer()
exten => 1003,n,AudioSocket(127.0.0.1:8082,${CHANNEL(uniqueid)})
exten => 1003,n,Hangup()
```

## Monitoramento

Recomenda-se configurar monitoramento para os seguintes aspectos:

1. **Disponibilidade dos serviços**:
   - Servidor principal (`main_dynamic.py`)
   - API HTTP (porta 8082)
   - Servidores socket de cada ramal

2. **Performance**:
   - Número de sessões ativas
   - Tempo de resposta da IA
   - Uso de CPU e memória

3. **Logs**:
   - Alertas para erros nos logs
   - Métricas de sucesso/falha em chamadas

## Solução de Problemas

### API não responde

```bash
# Verificar se o processo está rodando
ps aux | grep main_dynamic.py

# Verificar logs
tail -n 100 logs/audiosocket.log

# Reiniciar o serviço
pkill -f main_dynamic.py
python main_dynamic.py &
```

### Conflitos de Porta

Se você receber erros sobre portas já em uso:

```bash
# Verificar quais processos estão usando as portas
sudo lsof -i :8080
sudo lsof -i :8081

# Matar processos conflitantes se necessário
sudo kill <PID>
```

### Problemas de Conexão com Banco de Dados

```bash
# Verificar conectividade
nc -zv dev-postgres-cd.postgres.database.azure.com 5432

# Verificar variáveis de ambiente
cat .env | grep DB_
```

## Atualizações e Upgrades

Para atualizar o sistema:

1. Faça backup das configurações:
   ```bash
   cp -r data data.backup
   cp .env .env.backup
   ```

2. Atualiza os arquivos do código:
   ```bash
   git pull
   # ou substitua os arquivos manualmente
   ```

3. Reinicie o serviço:
   ```bash
   pkill -f main_dynamic.py
   python main_dynamic.py &
   ```

## Considerações de Segurança

1. **Credenciais**: Nunca armazene credenciais diretamente no código ou repositório
2. **API HTTP**: Em produção, considere adicionar autenticação e HTTPS
3. **Firewalls**: Configure regras de firewall para permitir apenas tráfego necessário
4. **Logs**: Não registre informações sensíveis nos logs