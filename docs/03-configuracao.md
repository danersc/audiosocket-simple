# Configuração e Implantação do AudioSocket-Simple

Este documento descreve como configurar, instalar e executar o sistema AudioSocket-Simple no ambiente de desenvolvimento e produção.

## Requisitos do Sistema

### Software
- Python 3.8 ou superior
- Node.js v20.12.0 (para ferramentas de desenvolvimento)
- Bibliotecas Python listadas em `requirements.txt`
- Acesso a uma API de LLM (OpenAI, Groq, etc.)
- Azure Speech Services (conta e chave de API)

### Hardware Recomendado
- CPU: 2 núcleos ou mais
- RAM: 4GB ou mais
- Armazenamento: 1GB disponível
- Conexão de rede estável

## Instalação e Configuração

### 1. Preparação do Ambiente

```bash
# Clonar o repositório
git clone https://github.com/seu-usuario/audiosocket-simple.git
cd audiosocket-simple

# Ativar o Node.js correto via NVM
nvm use v20.12.0

# Criar e ativar ambiente virtual Python
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

### 2. Configuração do Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```
# Configurações do Azure Speech
AZURE_SPEECH_KEY=sua_chave_do_azure
AZURE_SPEECH_REGION=sua_regiao_do_azure

# Configurações da API de IA
AI_API_KEY=sua_chave_da_api_llm
AI_API_URL=https://api.url/v1

# Configurações do sistema
SILENCE_THRESHOLD_SECONDS=1.5
API_PORT=8082
```

### 3. Configuração de Arquivos do Sistema

#### config.json

O arquivo `config.json` na raiz do projeto controla vários aspectos do comportamento do sistema:

```json
{
  "greeting": {
    "message": "Condomínio Apoena, em que posso ajudar?",
    "voice": "pt-BR-AntonioNeural",
    "delay_seconds": 1.5
  },
  "system": {
    "silence_threshold_seconds": 1.5,
    "resident_max_silence_seconds": 45.0,
    "goodbye_delay_seconds": 3.0
  },
  "audio": {
    "transmission_delay_ms": 10,
    "post_audio_delay_seconds": 0.3,
    "discard_buffer_frames": 15
  },
  "call_termination": {
    "enabled": true,
    "goodbye_messages": {
      "visitor": {
        "authorized": "Sua entrada foi autorizada. Obrigado por utilizar nossa portaria inteligente.",
        "denied": "Sua entrada não foi autorizada. Obrigado por utilizar nossa portaria inteligente.",
        "default": "Obrigado por utilizar nossa portaria inteligente. Até a próxima!"
      },
      "resident": {
        "default": "Obrigado pela sua resposta. Encerrando a chamada."
      }
    }
  }
}
```

#### data/apartamentos.json

Este arquivo contém informações sobre apartamentos e moradores para validação:

```json
[
  {
    "apartment_number": "501",
    "residents": ["Daniel dos Reis", "Rafaela Silva"],
    "voip_number": "1003021"
  },
  {
    "apartment_number": "502",
    "residents": ["Maria Oliveira", "João Santos"],
    "voip_number": "1003022"
  }
]
```

## Execução da Aplicação

### Modo de Desenvolvimento

Para iniciar o sistema em modo de desenvolvimento:

```bash
# Ativar ambiente
source /Users/danerdosreis/development/environments/audiosocket-simple/bin/activate
nvm use v20.12.0

# Iniciar a aplicação principal
python main.py
```

Isto iniciará:
- Servidor AudioSocket para visitantes na porta 8080
- Servidor AudioSocket para moradores na porta 8081
- Servidor API HTTP na porta 8082

### Testes Locais sem Asterisk

Para testar o sistema sem um Asterisk real:

```bash
# Terminal 1: Iniciar servidor principal
python main.py

# Terminal 2: Iniciar cliente de microfone simulando um visitante
python microfone_client.py
```

## Configuração do Socket TCP

A otimização dos servidores de socket é importante para garantir a qualidade do áudio. As principais opções de configuração são definidas em `server_manager.py`:

```python
# Servidor para visitante (IA) - com parâmetros para melhor qualidade de áudio
ia_server = await asyncio.start_server(
    iniciar_servidor_audiosocket_visitante,
    binding_ip,  # Use 0.0.0.0 para binding
    porta_ia,
    # Manter apenas parâmetros essenciais e alguns importantes para qualidade
    limit=1024*1024,  # 1MB buffer
    start_serving=True
)
```

## Parâmetros Otimizados para Desempenho

Estes parâmetros foram ajustados para melhorar o desempenho do sistema:

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `silence_threshold_seconds` | 1.5 | Tempo de silêncio necessário para considerar que o usuário parou de falar |
| `transmission_delay_ms` | 10 | Delay entre transmissões de pacotes de áudio (ms) |
| `post_audio_delay_seconds` | 0.3 | Atraso após envio de áudio antes de retornar ao modo de escuta |
| `discard_buffer_frames` | 15 | Quantidade de frames a descartar após IA falar (evita eco) |

## Integração com o Asterisk

Para integrar o sistema com Asterisk, configure o `extensions.conf`:

```
[from-internal]
exten => 1001,1,Answer()
exten => 1001,n,AudioSocket(127.0.0.1:8080,${CHANNEL(uniqueid)})
exten => 1001,n,Hangup()
```

## Verificação da Instalação

Para verificar se a instalação está funcionando corretamente:

1. Inicie o sistema: `python main.py`
2. Verifique os logs em tempo real: `tail -f logs/audiosocket.log`
3. Teste a API: `curl http://localhost:8082/api/status`
4. Teste o encerramento de chamadas: `curl -X POST -H "Content-Type: application/json" -d '{"call_id":"UUID-DA-CHAMADA", "role":"visitor"}' http://localhost:8082/api/hangup`

## Solução de Problemas

### Portas em Uso
Se encontrar erros sobre portas já em uso:
```bash
sudo lsof -i :8080
sudo lsof -i :8081
sudo kill <PID>
```

### Erros de Transcrição
Verifique suas credenciais do Azure Speech:
```bash
curl -s -X POST "https://<region>.api.cognitive.microsoft.com/sts/v1.0/issuetoken" \
     -H "Ocp-Apim-Subscription-Key: <key>" \
     -H "Content-type: application/x-www-form-urlencoded" \
     -d ""
```

---

*Próximo documento: [04-fluxos-comunicacao.md](04-fluxos-comunicacao.md)*