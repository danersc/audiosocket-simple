# Processamento de IA e Extração de Intenções

Este documento detalha como o sistema AudioSocket-Simple processa as mensagens do usuário utilizando IA para extrair intenções e informações estruturadas.

## Visão Geral

O sistema utiliza um pipeline de processamento de linguagem natural para extrair progressivamente informações do visitante. Este pipeline é construído usando o framework CrewAI com LLMs (Large Language Models) para processar cada etapa da extração de informações.

## Arquitetura do Pipeline de IA

O sistema divide o processamento de intenções em etapas sequenciais:

1. **Extração do Tipo de Intenção**: Identificar se é uma visita, entrega ou serviço
2. **Extração do Nome do Visitante**: Capturar o nome de quem está na portaria
3. **Extração de Apartamento e Morador**: Identificar número do apartamento e nome do morador
4. **Validação via Fuzzy Matching**: Validar as informações contra um banco de dados

Esta abordagem em etapas permite:
- Maior precisão em cada extração
- Mensagens contextuais específicas para cada informação faltante
- Controle granular da conversa

## Componentes Principais

### 1. Gerenciamento de Estado

O sistema mantém o estado da conversa entre mensagens:

```python
def get_user_state(id: str):
    """Obtém o estado atual da conversa com o usuário."""
    
def update_user_state(id: str, intent=None, message=None):
    """Atualiza o estado da conversa com novos dados de intenção e histórico."""
```

### 2. Extração de Intenções

A função principal que orquestra o processo de extração:

```python
def process_user_message_with_coordinator(id: str, message: str) -> dict:
    """
    Processa a mensagem do usuário para extrair intenções e dados estruturados.
    Retorna um dicionário com a resposta e os dados extraídos.
    """
    # Etapas progressivas de extração...
```

### 3. Tarefas Especializadas

Para cada tipo de informação, uma tarefa especializada é criada:

```python
# Extração de tipo de intenção (entrega, visita, etc.)
task = conversation_extractor_intent_task(
    user_message=message,
    conversation_history=history,
    intent=partial_intent
)

# Extração de nome do visitante
task = conversation_extractor_name_task(
    user_message=message,
    conversation_history=history,
    intent=partial_intent
)

# Extração de apartamento e morador
task = conversation_extractor_resident_apartment_task(
    user_message=message,
    conversation_history=history,
    intent=partial_intent
)
```

### 4. Validação via Fuzzy Matching

Após coletar as informações, o sistema valida-as usando fuzzy matching:

```python
def validar_intent_com_fuzzy(intent: Dict) -> Dict:
    """
    Verifica se a combinação apartment_number e resident_name da intent
    corresponde (mesmo que parcialmente) a um morador real.
    """
    # Processar com fuzzy matching...
```

O sistema calcula a similaridade entre as informações fornecidas e os dados reais, utilizando diferentes algoritmos de comparação fuzzy:

```python
# Pontuações para diferentes algoritmos de match
scores = [
    fuzz.ratio(resident_informado, nome_residente),  # Match completo
    fuzz.partial_ratio(resident_informado, nome_residente),  # Match parcial
    fuzz.token_sort_ratio(resident_informado, nome_residente)  # Ignora ordem das palavras
]
```

## Fluxo de Execução Detalhado

### 1. Processamento Inicial

Quando o visitante envia uma mensagem, o processo começa:

```python
texto = await transcrever_audio_async(audio_data, call_id=call_id)
session_manager.process_visitor_text(call_id, texto)
```

### 2. Encaminhamento para o ConversationFlow

```python
def process_visitor_text(self, session_id: str, text: str):
    """Processa o texto do visitante via ConversationFlow."""
    session = self.get_session(session_id)
    if not session:
        session = self.create_session(session_id)
    
    # Registrar no histórico
    session.history.append(f"[Visitor] {text}")
    
    # Repassar para o ConversationFlow
    session.flow.on_visitor_message(session_id, text, self)
```

### 3. Extração Progressiva de Intenções

```python
def on_visitor_message(self, session_id: str, text: str, session_manager):
    """Processa a mensagem do visitante no ConversationFlow."""
    if self.state == FlowState.COLETANDO_DADOS:
        # Processar com IA para extrair intenções
        result = process_user_message_with_coordinator(session_id, text)
        
        # Analisar resultado e verificar completude
        if result.get("valid_for_action"):
            # Validação fuzzy dos dados
            fuzzy_res = validar_intent_com_fuzzy(self.intent_data)
            
            if fuzzy_res["status"] == "válido":
                self.state = FlowState.VALIDADO
                # Avançar para próxima etapa...
```

### 4. Extração em Etapas

O sistema extrai as informações em etapas sequenciais:

1. **Intent Type**:
   - Se não existe intenção ou intent_type está vazio
   - Executa `conversation_extractor_intent_task`
   - Atualiza o estado com o tipo de intenção (visita, entrega, etc.)

2. **Nome do Visitante**:
   - Se intent_type está preenchido mas interlocutor_name está vazio
   - Executa `conversation_extractor_name_task`
   - Atualiza o estado com o nome do visitante

3. **Apartamento e Morador**:
   - Se interlocutor_name está preenchido mas apartment_number ou resident_name estão vazios
   - Executa `conversation_extractor_resident_apartment_task`
   - Atualiza o estado com o número do apartamento e nome do morador

### 5. Validação Fuzzy

```python
def validar_intent_com_fuzzy(intent: Dict) -> Dict:
    apt = intent.get("apartment_number", "").strip().lower()
    resident_informado = intent.get("resident_name", "").strip().lower()
    
    # Verificar se apartamento existe
    apt_matches = [a for a in apartamentos if a["apartment_number"] == apt]
    
    # Procurar melhor match de residente
    for apartamento in apt_matches:
        for residente in apartamento["residents"]:
            nome_residente = residente.strip().lower()
            
            # Calcular scores com diferentes algoritmos...
            score = max(scores)
            
            if score > best_score:
                best_score = score
                best_match = residente
                best_apt = apartamento
    
    # Se score é suficiente, validar
    if best_score >= 75:
        return {
            "status": "válido",
            "match_name": best_match,
            "voip_number": best_apt["voip_number"],
            # ...
        }
    else:
        return {
            "status": "inválido",
            "reason": "Morador não encontrado neste apartamento",
            # ...
        }
```

## Formato das Respostas

As funções de processamento de IA retornam um formato padronizado:

```json
{
    "mensagem": "Texto para responder ao usuário",
    "dados": {
        "intent_type": "entrega",
        "interlocutor_name": "Pedro da Silva",
        "apartment_number": "501",
        "resident_name": "Daniel dos Reis"
    },
    "valid_for_action": true
}
```

O campo `valid_for_action` indica se todos os dados necessários foram coletados e podem ser considerados completos para a próxima ação (como contatar o morador).

## Medição de Performance

O sistema monitora o tempo de processamento de cada etapa:

```python
start_time = time.time()
texto = await transcrever_audio_async(audio_data, call_id=call_id)
transcription_time = (time.time() - start_time) * 1000

start_time = time.time()
result = process_user_message_with_coordinator(session_id, text)
ai_processing_time = (time.time() - start_time) * 1000
```

Estas métricas ajudam a identificar gargalos e otimizar o desempenho.

## Melhorias Recentes (Groq)

O sistema foi migrado da OpenAI para Groq para melhorar o desempenho:

| Etapa de processamento | Antes (OpenAI) | Depois (Groq) | Melhoria |
|------------------------|----------------|---------------|----------|
| Intent type | 3600ms | 889ms | 75% mais rápido |
| Nome do interlocutor | 4285ms | 773-1307ms | 81% mais rápido |
| Apartment/resident | 1788-2763ms | 1207-1318ms | 52% mais rápido |
| Total AI | 3974-7900ms | 1213-2636ms | 67% mais rápido |

## Considerações para o Futuro

1. **Paralelização**: Em vez de extrair informações sequencialmente, elas poderiam ser extraídas em paralelo com `asyncio.gather()`

2. **Ajuste Fino de LLMs**: Treinamento específico para o domínio da portaria

3. **Cache de Respostas Comuns**: Armazenar respostas para perguntas frequentes

4. **Análise Contínua**: Monitoramento de acurácia e performance para identificação de áreas de melhoria

---

*Próximo documento: [08-otimizacoes.md](08-otimizacoes.md)*