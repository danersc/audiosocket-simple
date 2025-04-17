from crewai import Crew

from ai.state_manager import get_user_state, update_user_state, clear_user_state
from ai.tasks import create_conversation_coordinator_task
from ai.utils.intent_extractor import extract_intent_from_response
from ai.models.intent import IntentData
import json

def process_user_message_with_coordinator(id: str, message: str) -> dict:
    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]

    # Cria a Task com histórico e dados parciais
    task = create_conversation_coordinator_task(
        user_message=message,
        conversation_history=history,
        intent=partial_intent
    )

    crew = Crew(tasks=[task], verbose=True)
    result = str(crew.kickoff())

    # Tenta extrair novos dados (você pode usar OpenAI function calling ou Regex/JSON)
    try:
        dados_estruturados = extract_intent_from_response(result)
        update_user_state(id, intent=dados_estruturados.get("dados"), message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
    except Exception:
        update_user_state(id, message=f"Usuário: {dados_estruturados.get('mensagem')}")

    return dados_estruturados
