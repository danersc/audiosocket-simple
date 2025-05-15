# Testes e Verificação do Sistema

Este documento descreve as metodologias, ferramentas e abordagens para testar o sistema AudioSocket-Simple em diferentes cenários.

## Ambientes de Teste

### 1. Ambiente de Desenvolvimento Local

Testes locais sem dependência de sistemas externos (Asterisk, RabbitMQ):

```bash
# Terminal 1: Servidor principal
python main.py

# Terminal 2: Cliente de teste simulando visitante
python microfone_client.py

# Terminal 3 (opcional): Cliente simulando morador
python microfone_client.py --port 8081
```

### 2. Ambiente de Integração

Testes com integração parcial:
- AudioSocket-Simple conectado a Asterisk de teste
- Sistema de portaria real ou simulado
- Azure Speech Services real

### 3. Ambiente de Produção

Testes completos em ambiente de produção com monitoramento detalhado.

## Ferramentas de Teste

### 1. Cliente de Microfone

O `microfone_client.py` permite simular chamadas sem necessidade do Asterisk:

```bash
# Simular visitante
python microfone_client.py --host 127.0.0.1 --port 8080

# Simular morador 
python microfone_client.py --host 127.0.0.1 --port 8081
```

### 2. API de Testes

A API HTTP na porta 8082 oferece endpoints para testes e controle:

```bash
# Verificar status do sistema
curl http://localhost:8082/api/status

# Testar encerramento de chamadas
curl -X POST -H "Content-Type: application/json" \
  -d '{"call_id":"UUID-DA-CHAMADA", "role":"visitor"}' \
  http://localhost:8082/api/hangup
```

### 3. Logs Detalhados

O sistema mantém logs detalhados para cada chamada:

```bash
# Logs gerais
tail -f logs/audiosocket.log

# Logs específicos de chamada (quando criados)
tail -f logs/UUID-DA-CHAMADA.log
```

## Cenários de Teste

### 1. Fluxo Básico de Visitante

Teste do fluxo completo onde visitante é autorizado:

1. Visitante liga
2. Informa nome, apartamento e morador
3. Sistema conecta com morador
4. Morador autoriza
5. Visitante recebe autorização
6. Chamada encerrada corretamente

### 2. Fluxo de Negação

Teste onde morador nega entrada:

1. Visitante liga
2. Informa nome, apartamento e morador
3. Sistema conecta com morador
4. Morador nega entrada
5. Visitante recebe negação
6. Chamada encerrada corretamente

### 3. Testes de Validação Fuzzy

Teste de reconhecimento aproximado de nomes:

```
Visitante: "Apartamento 501, para Daniel" 
# Sistema deve reconhecer como "Daniel dos Reis"

Visitante: "Apartamento 501, para o Daner"
# Sistema deve reconhecer como "Daniel dos Reis" via fuzzy
```

### 4. Teste de Encerramento Ativo

Teste do mecanismo KIND_HANGUP:

```
# Via API
curl -X POST -H "Content-Type: application/json" \
  -d '{"call_id":"UUID-DA-CHAMADA", "role":"visitor"}' \
  http://localhost:8082/api/hangup

# Via teste especial em conversa
Visitante: "test hangup"
```

### 5. Teste de Desconexão Abrupta

Para testar a recuperação de desconexões abruptas:

1. Iniciar chamada normal
2. Desconectar cliente abruptamente (Ctrl+C)
3. Verificar logs para confirmar tratamento adequado
4. Confirmar que nova chamada pode ser atendida na mesma porta

### 6. Teste de Carregamento

Para testar comportamento sob carga:

1. Iniciar múltiplas chamadas simultâneas
2. Monitorar uso de CPU e memória
3. Verificar throttling adaptativo
4. Verificar que cada chamada é processada corretamente

## Teste da Síntese e Transcrição

### Teste de Síntese

```bash
# Criar arquivo de texto com frases para teste
echo "Olá, como posso ajudar?" > test_phrases.txt
echo "Entendi, você quer entrar no apartamento 501" >> test_phrases.txt

# Script para testar síntese
python -c "
import asyncio
from speech_service import sintetizar_fala_async

async def test_synthesis():
    with open('test_phrases.txt', 'r') as f:
        for line in f:
            start = time.time()
            audio = await sintetizar_fala_async(line.strip())
            duration = (time.time() - start) * 1000
            print(f'Sintetizado em {duration:.2f}ms: {line.strip()}')

asyncio.run(test_synthesis())
"
```

### Teste de Transcrição

```bash
# Usar o cliente de microfone para gravar e transcrever em tempo real
python microfone_client.py --transcribe-only
```

## Testes de Componentes Específicos

### 1. Teste de ResourceManager

```python
# Teste de throttling
resource_manager.register_session("test1", 8080)
resource_manager.register_session("test2", 8080)
resource_manager.register_session("test3", 8080)
resource_manager.register_session("test4", 8080)

# Deve retornar True quando há muitas sessões e CPU alta
should_throttle = resource_manager.should_throttle_audio()
```

### 2. Teste de SessionManager

```python
# Criar sessão e enfileirar mensagens
session_id = "test-session"
session_manager.create_session(session_id)
session_manager.enfileirar_visitor(session_id, "Mensagem de teste")

# Verificar mensagem enfileirada
message = session_manager.get_message_for_visitor(session_id)
assert message == "Mensagem de teste"
```

### 3. Teste de ConversationFlow

```python
# Simular mensagem de visitante
flow = ConversationFlow()
flow.on_visitor_message(session_id, "Eu gostaria de fazer uma entrega para o apartamento 501", session_manager)

# Verificar extração de intenção
assert flow.intent_data.get("intent_type") == "entrega"
```

## Verificações Automáticas

Durante a execução de testes, observe os seguintes indicadores:

1. **Logs sem Erros**: Não deve haver erros não tratados
2. **Uso de Recursos**: CPU e memória devem permanecer em níveis aceitáveis
3. **Tempos de Resposta**: Respostas dentro dos limites esperados (veja [08-otimizacoes.md](08-otimizacoes.md))
4. **Recuperação de Erros**: Sistema deve se recuperar de falhas sem intervenção

## Documentação de Resultados de Teste

Registre os resultados dos testes:

```
Data: 01/05/2025
Teste: Fluxo completo com autorização
Resultado: SUCESSO
Observações: 
- Tempo total do fluxo: 32 segundos
- Nenhum erro observado
- Mensagens de despedida audíveis antes de KIND_HANGUP
```

## Monitoramento em Produção

Recomendações para monitoramento contínuo:

1. **Logs Centralizados**: Consolidar logs para análise
2. **Métricas de Performance**: Registrar tempos de resposta, taxas de sucesso/falha
3. **Alertas**: Configurar alertas para comportamentos anômalos
4. **Revisão Periódica**: Analisar logs e métricas regularmente para identificar melhorias

---

*Próximo documento: [10-desenvolvimento-futuro.md](10-desenvolvimento-futuro.md)*