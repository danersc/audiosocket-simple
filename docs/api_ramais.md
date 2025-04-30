# API de Gerenciamento de Ramais

Data: 26/04/2025

## Visão Geral

A API de gerenciamento de ramais é uma interface HTTP que permite administrar os ramais de IA configurados no sistema AudioSocket. Esta documentação detalha os endpoints disponíveis, parâmetros aceitos e exemplos de uso.

## Base URL

Por padrão, a API está disponível em:

```
http://[servidor]:8082/api
```

O número da porta pode ser alterado através da variável de ambiente `API_PORT` no arquivo `.env`.

## Autenticação

Atualmente, a API não utiliza autenticação. Em ambientes de produção, é recomendado implementar algum mecanismo de autenticação como API keys ou tokens JWT.

## Endpoints

### Obter Status dos Ramais

Retorna informações sobre todos os ramais ativos no sistema.

```
GET /api/status
```

#### Resposta

```json
{
  "status": "success",
  "total_extensions": 2,
  "extensions": [
    {
      "id": 1,
      "ramal_ia": "1001",
      "ramal_retorno": "1002",
      "ip": "0.0.0.0",
      "porta_ia": 8080,
      "porta_retorno": 8081,
      "condominio_id": 10,
      "status": "ativo"
    },
    {
      "id": 2,
      "ramal_ia": "1003",
      "ramal_retorno": "1004",
      "ip": "0.0.0.0",
      "porta_ia": 8082,
      "porta_retorno": 8083,
      "condominio_id": 11,
      "status": "ativo"
    }
  ]
}
```

### Atualizar Configurações

Atualiza as configurações de ramais a partir do banco de dados.

```
POST /api/refresh
```

#### Resposta

```json
{
  "status": "success",
  "message": "Configurações atualizadas com sucesso",
  "stats": {
    "removed": 1,
    "updated": 0,
    "added": 2,
    "total_active": 3
  }
}
```

### Listar Configurações do Banco de Dados

Lista todas as configurações de ramais disponíveis no banco de dados, independentemente de estarem ativas ou não.

```
GET /api/extensions
```

#### Resposta

```json
{
  "status": "success",
  "total": 4,
  "extensions": [
    {
      "id": 1,
      "ramal_ia": "1001",
      "ramal_retorno": "1002",
      "ip_servidor": "0.0.0.0",
      "porta_ia": 8080,
      "porta_retorno": 8081,
      "condominio_id": 10
    },
    {
      "id": 2,
      "ramal_ia": "1003",
      "ramal_retorno": "1004",
      "ip_servidor": "0.0.0.0",
      "porta_ia": 8082,
      "porta_retorno": 8083,
      "condominio_id": 11
    },
    {
      "id": 3,
      "ramal_ia": "1005",
      "ramal_retorno": "1006",
      "ip_servidor": "0.0.0.0",
      "porta_ia": 8084,
      "porta_retorno": 8085,
      "condominio_id": 12
    },
    {
      "id": 4,
      "ramal_ia": "1007",
      "ramal_retorno": "1008",
      "ip_servidor": "0.0.0.0",
      "porta_ia": 8086,
      "porta_retorno": 8087,
      "condominio_id": 13
    }
  ]
}
```

### Reiniciar um Ramal Específico

Reinicia um ramal específico, identificado pelo ID ou número do ramal.

```
POST /api/restart
```

#### Parâmetros (body JSON)

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| extension_id | int | ID da extensão a ser reiniciada |
| ramal | string | Número do ramal a ser reiniciado |

**Nota:** É necessário fornecer um dos dois parâmetros (extension_id OU ramal).

#### Exemplo

```json
{
  "extension_id": 2
}
```

ou

```json
{
  "ramal": "1003"
}
```

#### Resposta

```json
{
  "status": "success",
  "message": "Ramal ID 2 reiniciado com sucesso"
}
```

## Códigos de Erro

| Código | Descrição |
|--------|-----------|
| 200 | Sucesso |
| 400 | Requisição inválida (parâmetros faltando ou formato incorreto) |
| 404 | Recurso não encontrado (ramal inexistente) |
| 500 | Erro interno do servidor |

## Monitoramento e Logs

Todas as operações da API são registradas no arquivo de log principal:

```
./logs/audiosocket.log
```

Exemplo de entradas de log:

```
2025-04-26 10:15:23,456 - extensions.api_server - INFO - Requisição recebida: GET /api/status
2025-04-26 10:16:45,123 - extensions.api_server - INFO - Atualizando configurações a partir do banco de dados
2025-04-26 10:16:45,987 - extensions.server_manager - INFO - Iniciando servidor para ramal 1009 na porta 8088
```

## Recomendações para Produção

1. Implementar autenticação (API keys ou JWT tokens)
2. Adicionar rate limiting para prevenir abuso 
3. Configurar HTTPS para comunicação segura
4. Adicionar validação mais robusta de inputs
5. Implementar monitoramento detalhado via métricas Prometheus

## Exemplos de Uso com Curl

### Obter Status dos Ramais

```bash
curl http://localhost:8082/api/status
```

### Atualizar Configurações

```bash
curl -X POST http://localhost:8082/api/refresh
```

### Reiniciar um Ramal Específico

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"ramal": "1003"}' \
  http://localhost:8082/api/restart
```