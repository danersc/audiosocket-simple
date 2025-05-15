# Documentação Técnica Consolidada - AudioSocket-Simple

Este documento apresenta uma visão técnica consolidada do sistema AudioSocket-Simple, um serviço de atendimento automatizado por IA para portarias de condomínios. O sistema utiliza processamento de linguagem natural e reconhecimento de voz para automatizar o processo de atendimento de visitantes, coleta de informações e comunicação com moradores.

## 1. Visão Geral do Sistema

### 1.1 Propósito

O AudioSocket-Simple automatiza o atendimento em portarias de condomínios, permitindo:
- Atender chamadas de visitantes no portão
- Coletar informações como nome, apartamento e motivo da visita
- Validar dados fornecidos usando fuzzy matching
- Contatar moradores para autorização de entrada
- Gerenciar todo o fluxo conversacional entre visitantes e moradores

### 1.2 Arquitetura de Alto Nível

O sistema consiste em quatro componentes principais:

1. **Servidores AudioSocket**: Estabelecem comunicação com o Asterisk para transmissão de áudio
   - Servidor para visitantes (porta 8080)
   - Servidor para moradores (porta 8081)
   - API HTTP para gerenciamento (porta 8082)

2. **Processamento de Áudio**: Gerencia a captura, transcrição e síntese de áudio
   - Detecção de atividade de voz (VAD)
   - Transcrição de fala para texto
   - Síntese de texto para fala

3. **Processamento de Linguagem Natural**: Analisa e extrai informações das mensagens
   - Extração de intenções (tipo de visita, nomes, apartamentos)
   - Validação de informações via fuzzy matching
   - Determinação de fluxos de diálogo

4. **Gerenciamento de Sessões**: Coordena o estado das conversas
   - Rastreamento de sessões ativas
   - Gerenciamento de estado das conversas
   - Encerramento de chamadas

## 2. Componentes Técnicos

### 2.1 Servidores AudioSocket

#### 2.1.1 Protocolo AudioSocket

O sistema implementa o protocolo AudioSocket do Asterisk, que permite a transmissão bidirecional de áudio via socket TCP. O protocolo define diferentes tipos de pacotes:

- **KIND_ID (0x01)**: Identifica a chamada
- **KIND_SLIN (0x10)**: Transporta áudio no formato SLIN (PCM 16-bit 8kHz)
- **KIND_HANGUP (0x00)**: Sinaliza encerramento da chamada

#### 2.1.2 Configuração de Socket

```python
server = await asyncio.start_server(
    handler,
    binding_ip,
    porta,
    limit=1024*1024,  # 1MB buffer
    start_serving=True
)
```

### 2.2 Processamento de Áudio

#### 2.2.1 Detecção de Atividade de Voz (VAD)

O sistema suporta dois métodos de detecção de voz:

1. **WebRTCVAD**:
   - Leve e rápido, ideal para ambientes silenciosos
   - Configurável através de `silence_threshold_seconds` (padrão: 1.5s)

2. **Azure Speech**:
   - Mais robusto para ambientes ruidosos
   - Usa IA para distinguir voz humana de ruídos de fundo
   - Configurável através de `azure_speech_segment_timeout_ms` (padrão: 800ms)

Algoritmos adicionais são implementados para detectar falsos positivos e evitar loops de eco, incluindo:
- Filtragem de eventos de fala por energia do áudio
- Verificação de tamanho mínimo de buffer
- Períodos de guarda após síntese de áudio

#### 2.2.2 Transcrição de Fala

O sistema usa Azure Speech Services para transcrição de fala para texto:

- Formato de áudio: SLIN (8kHz, 16-bit, mono)
- Língua configurada: pt-BR (Português Brasileiro)
- Mecanismo de timeout para garantir resposta mesmo sem transcrição
- Cache de resultados frequentes para melhorar desempenho

#### 2.2.3 Síntese de Voz

O Azure Speech Services também é usado para síntese de voz:

- Vozes personalizáveis via configuração (`pt-BR-AntonioNeural` padrão)
- Sistema de cache para mensagens frequentes
- Parâmetros otimizados para transmissão de áudio

### 2.3 Gerenciamento de Sessões

#### 2.3.1 SessionManager

Classe responsável por rastrear todas as sessões ativas:

```python
def create_session(self, session_id: str) -> Session:
    """Cria uma nova sessão com ID único."""
    session = Session(session_id)
    self.sessions[session_id] = session
    return session

def get_session(self, session_id: str) -> Optional[Session]:
    """Obtém uma sessão existente pelo ID."""
    return self.sessions.get(session_id)

def end_session(self, session_id: str):
    """Marca uma sessão para encerramento."""
    # Lógica de encerramento...
```

#### 2.3.2 SessionData

Mantém o estado de cada sessão, incluindo:

- Filas de mensagens para visitante e morador
- Histórico de conversas
- Estado do fluxo conversacional
- Timestamps para monitoramento

#### 2.3.3 Encerramento Ativo

O sistema implementa encerramento ativo de chamadas:

1. Envia mensagens de despedida
2. Aguarda tempo configurável para que as mensagens sejam ouvidas
3. Envia pacote KIND_HANGUP para sinalizar encerramento
4. Libera recursos associados à sessão

### 2.4 Processamento de Linguagem Natural

#### 2.4.1 Extração de Intenções

O sistema usa o framework CrewAI com LLMs para extrair informações em etapas sequenciais:

1. **Tipo de Intenção**: Identifica propósito (visita, entrega, serviço)
2. **Nome do Visitante**: Extrai o nome de quem está na portaria
3. **Apartamento e Morador**: Captura número do apartamento e nome do morador

Cada etapa é executada por uma tarefa especializada que entende contexto e histórico.

#### 2.4.2 Validação via Fuzzy Matching

Após coletar informações, o sistema valida os dados contra o banco de dados:

```python
def validar_intent_com_fuzzy(intent: Dict) -> Dict:
    # Extrai dados da intenção
    apt = intent.get("apartment_number", "").strip().lower()
    resident_informado = intent.get("resident_name", "").strip().lower()
    
    # Compara com dados conhecidos usando fuzzy matching
    for apartamento in apt_matches:
        for residente in apartamento["residents"]:
            scores = [
                fuzz.ratio(resident_informado, nome_residente),
                fuzz.partial_ratio(resident_informado, nome_residente),
                fuzz.token_sort_ratio(resident_informado, nome_residente)
            ]
            score = max(scores)
            
            # Atualiza melhor match se score é maior
            if score > best_score:
                best_score = score
                best_match = residente
                best_apt = apartamento
    
    # Retorna resultado da validação
    if best_score >= 75:  # Threshold configurável
        return {
            "status": "válido",
            "match_name": best_match,
            "voip_number": best_apt["voip_number"],
            # ...
        }
```

### 2.5 Máquina de Estados

O sistema usa uma máquina de estados para controlar o fluxo da conversa:

#### 2.5.1 Estados da StateMachine

- **STANDBY**: Estado inicial, aguardando nova chamada
- **USER_TURN**: Turno do usuário (sistema está ouvindo)
- **WAITING**: Estado intermediário de processamento
- **IA_TURN**: Turno da IA (sistema está respondendo)

#### 2.5.2 Estados do ConversationFlow

- **COLETANDO_DADOS**: Fase de extração de informações do visitante
- **VALIDADO**: Dados foram validados com sucesso
- **CHAMANDO_MORADOR**: Sistema está tentando contactar o morador
- **ESPERANDO_MORADOR**: Morador atendeu, aguardando resposta
- **FINALIZADO**: Fluxo concluído, chamada encerrada

## 3. Fluxos de Comunicação

### 3.1 Atendimento do Visitante

1. **Inicialização**:
   - Visitante liga para o ramal da portaria
   - Asterisk encaminha chamada para o AudioSocket na porta 8080
   - Sistema cria nova sessão e envia saudação

2. **Coleta de Dados**:
   - Sistema detecta quando visitante fala usando VAD
   - Transcreve áudio para texto usando Azure Speech
   - Processa texto para extrair intenções progressivamente
   - Valida dados usando fuzzy matching

3. **Resposta Dinâmica**:
   - Com base no estado atual e informações faltantes, gera perguntas específicas
   - Sintetiza respostas e envia ao visitante
   - Continua ciclo até coletar todas as informações necessárias

### 3.2 Contato com o Morador

1. **Estabelecimento de Chamada**:
   - Sistema envia comando clicktocall via AMQP/RabbitMQ
   - Processa URIs SIP ou números diretos conforme necessário
   - Morador recebe chamada telefônica
   - Quando atendida, chamada é conectada ao AudioSocket na porta 8081

2. **Apresentação do Contexto**:
   ```
   Olá morador do apartamento 501! Pedro da Silva está na portaria 
   solicitando uma entrega. Você autoriza a entrada? Responda SIM ou NÃO.
   ```

3. **Processamento da Resposta**:
   - Sistema reconhece três tipos de resposta:
     - Pedido de mais informações ("Quem é?" ou "?")
     - Autorização ("sim", "autorizo", "pode entrar")
     - Negação ("não", "nego", "não autorizo")

### 3.3 Conclusão da Chamada

1. **Informação da Decisão**:
   - Sistema informa visitante sobre autorização ou negação
   - Envia mensagem adequada ao visitante e morador

2. **Encerramento Ativo**:
   - Envia mensagens de despedida para ambos
   - Aguarda tempo configurado para ouvir mensagens
   - Envia pacote KIND_HANGUP para encerrar as conexões
   - Libera recursos associados à sessão

## 4. Otimizações e Performance

### 4.1 Sistema de Cache para Síntese

Uma das otimizações mais significativas é o cache de áudio sintetizado:

```python
# Verificar cache antes de sintetizar
hash_texto = hashlib.md5(texto.encode('utf-8')).hexdigest()
cache_path = os.path.join(CACHE_DIR, f"{hash_texto}.slin")

# Se já existe no cache, retornar o arquivo de áudio
if os.path.exists(cache_path):
    with open(cache_path, 'rb') as f:
        return f.read()
```

Resultados:
- Redução de latência: De 652-972ms para <1ms em frases cacheadas
- Economia de recursos e chamadas de API

### 4.2 Parâmetros Otimizados

Parâmetros foram ajustados para melhorar performance:

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `silence_threshold_seconds` | 1.5 | Tempo de silêncio para considerar fim da fala |
| `transmission_delay_ms` | 10 | Delay entre transmissões de pacotes (ms) |
| `post_audio_delay_seconds` | 0.3 | Atraso após envio de áudio |
| `discard_buffer_frames` | 15 | Frames a descartar após IA falar |

### 4.3 Migração para Modelos de IA Mais Rápidos

A troca da API da OpenAI para Groq trouxe melhorias significativas:

| Etapa de processamento | Antes (OpenAI) | Depois (Groq) | Melhoria |
|------------------------|----------------|---------------|----------|
| Intent type | 3600ms | 889ms | 75% mais rápido |
| Nome do interlocutor | 4285ms | 773-1307ms | 81% mais rápido |
| Apartment/resident | 1788-2763ms | 1207-1318ms | 52% mais rápido |
| Total AI | 3974-7900ms | 1213-2636ms | 67% mais rápido |

### 4.4 Semáforos para Controle de Recursos

Para evitar sobrecarga, o sistema implementa semáforos:

```python
# Limite de simultaneidade
self.max_concurrent_transcriptions = int(os.getenv('MAX_CONCURRENT_TRANSCRIPTIONS', '3'))
self.max_concurrent_synthesis = int(os.getenv('MAX_CONCURRENT_SYNTHESIS', '3'))

# Semáforos para controle de acesso
self.transcription_semaphore = asyncio.Semaphore(self.max_concurrent_transcriptions)
self.synthesis_semaphore = asyncio.Semaphore(self.max_concurrent_synthesis)
```

## 5. Integrações

### 5.1 Integração com Asterisk

O sistema integra-se com o Asterisk via protocolo AudioSocket:

```
[from-internal]
exten => 1001,1,Answer()
exten => 1001,n,AudioSocket(127.0.0.1:8080,${CHANNEL(uniqueid)})
exten => 1001,n,Hangup()
```

### 5.2 Integração com Azure Speech Services

O sistema usa Azure Speech Services para:
- Transcrição de fala para texto
- Síntese de texto para fala
- Detecção avançada de atividade de voz

### 5.3 Integração com RabbitMQ/AMQP

O sistema usa RabbitMQ para enviar comandos clicktocall que iniciam chamadas para moradores:

```python
connection = pika.BlockingConnection(parameters)
channel = connection.channel()

# Publicar mensagem clicktocall
channel.basic_publish(
    exchange=rabbit_exchange,
    routing_key=rabbit_routing_key,
    body=json.dumps(mensagem_clicktocall)
)
```

## 6. Tratamento de Erros e Resiliência

### 6.1 Tratamento de Erros de Conexão

```python
try:
    writer.close()
    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
except asyncio.TimeoutError:
    logger.info(f"[{call_id}] Timeout ao aguardar fechamento do socket")
except ConnectionResetError:
    # Isso é esperado se o cliente desconectar abruptamente
    logger.info(f"[{call_id}] Conexão resetada pelo cliente - comportamento normal")
```

### 6.2 Solução para Problema Asyncio em Múltiplas Threads

Para operações assíncronas em threads diferentes:

```python
def run_async_call():
    """Função auxiliar para executar a coroutine em uma thread separada"""
    try:
        # asyncio.run() cria um novo event loop e executa a coroutine
        asyncio.run(self.iniciar_processo_chamada(session_id, session_manager))
    except Exception as e:
        logger.error(f"[Flow] Erro em thread de chamada: {e}", exc_info=True)

# Iniciar a thread
call_thread = threading.Thread(target=run_async_call)
call_thread.daemon = True
call_thread.start()
```

### 6.3 Mecanismo Anti-Deadlock

```python
# Verificação de deadlock no Azure Speech
if self.collecting_audio and time.time() - self.speech_start_time > 10.0:
    logger.warning(f"[{self.call_id}] Detectado possível deadlock no Azure Speech! "
                  f"Forçando processamento após {time.time() - self.speech_start_time:.1f}s")
    # Forçar processamento do áudio coletado até agora
    self.process_collected_audio()
```

## 7. Configuração e Implantação

### 7.1 Requisitos do Sistema

#### Software
- Python 3.8 ou superior
- Bibliotecas listadas em `requirements.txt`
- Acesso a APIs (Azure Speech, LLM)
- Opcional: RabbitMQ para clicktocall

#### Hardware Recomendado
- CPU: 2+ núcleos
- RAM: 4GB+ 
- Armazenamento: 1GB+ disponível
- Conexão de rede estável

### 7.2 Configuração via Arquivos

#### .env
```
# Configurações do Azure Speech
AZURE_SPEECH_KEY=sua_chave_do_azure
AZURE_SPEECH_REGION=sua_regiao_do_azure

# Configurações da API de IA
AI_API_KEY=sua_chave_da_api_llm
AI_API_URL=https://api.url/v1
```

#### config.json
```json
{
  "greeting": {
    "message": "Condomínio Apoena, em que posso ajudar?",
    "voice": "pt-BR-AntonioNeural",
    "delay_seconds": 1.5
  },
  "system": {
    "voice_detection_type": "azure_speech",
    "silence_threshold_seconds": 1.5,
    "resident_max_silence_seconds": 45.0
  },
  "audio": {
    "transmission_delay_ms": 10,
    "post_audio_delay_seconds": 0.3,
    "discard_buffer_frames": 15
  }
}
```

#### data/apartamentos.json
```json
[
  {
    "apartment_number": "501",
    "residents": ["Daniel dos Reis", "Rafaela Silva"],
    "voip_number": "1003021"
  }
]
```

### 7.3 Execução do Sistema

```bash
# Ativar ambiente Python
source /path/to/venv/bin/activate

# Iniciar o sistema
python main.py
```

Isto iniciará:
- Servidor AudioSocket para visitantes (porta 8080)
- Servidor AudioSocket para moradores (porta 8081)
- API HTTP para gerenciamento (porta 8082)

## 8. API HTTP e Monitoramento

### 8.1 Endpoints da API

```
GET /api/status - Retorna status do sistema e sessões ativas
POST /api/hangup - Encerra uma chamada específica
    Body: {"call_id":"UUID-DA-CHAMADA", "role":"visitor"}
```

### 8.2 Logs e Diagnóstico

O sistema mantém logs detalhados em `logs/audiosocket.log`:

```
INFO:[call_id] Atualizado timestamp de fim de fala: <timestamp>
WARNING:[call_id] IGNORANDO fim de fala - energia muito baixa no pre-buffer
INFO:[call_id] Fim de fala CONFIRMADO por energia do áudio
INFO:[call_id] Enviando KIND_HANGUP ativo para visitante na sessão
```

## 9. Desenvolvimentos Futuros

### 9.1 Prioridades Altas

- Paralelização de processamento de IA
- Timeout automático de sessões
- Sistema de multi-servidores (supervisor app)
- Autenticação na API

### 9.2 Prioridades Médias

- Dashboard em tempo real
- Otimização de modelos LLM
- Aprimoramento da síntese de voz
- Integração com sistemas de condomínio

### 9.3 Prioridades Baixas

- TLS para AudioSocket
- Webhooks para eventos
- Personalização de vozes por condomínio

## 10. Conclusão

O AudioSocket-Simple representa uma solução robusta e eficiente para automação de portarias de condomínios, combinando tecnologias de processamento de áudio, linguagem natural e integração com sistemas VoIP. O sistema foi projetado com foco em performance, resiliência e experiência do usuário, implementando várias camadas de otimização e tratamento de erros.

As melhorias constantes no processamento de áudio, detecção de voz e velocidade de resposta garantem uma experiência conversacional cada vez mais natural e fluida. O design modular permite fácil extensão e adição de novas funcionalidades no futuro.