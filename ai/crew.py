from crewai import Crew

from ai.state_manager import get_user_state, update_user_state, clear_user_state
from ai.tasks import create_conversation_coordinator_task, conversation_extractor_name_task, \
    conversation_extractor_intent_task, conversation_extractor_resident_apartment_task
from ai.tools import validar_intent_com_fuzzy
from ai.utils.intent_extractor import extract_intent_from_response
from ai.models.intent import IntentData
import json

def process_user_message_with_coordinator(id: str, message: str) -> dict:
    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]
    dados_estruturados = None

    # A partir do nome obtido, verifica a intenção do usuário
    if not state["intent"] or state["intent"]["intent_type"] == "":
        task = conversation_extractor_intent_task(
            user_message=message,
            conversation_history=history,
            intent=partial_intent
        )
        crew = Crew(tasks=[task], verbose=True)
        result = str(crew.kickoff())
        try:
            dados_estruturados = extract_intent_from_response(result)
            update_user_state(id, intent=dados_estruturados.get("dados"),
                              message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
        except Exception:
            update_user_state(id, message=f"Usuário: {dados_estruturados.get('mensagem')}")

        if dados_estruturados["dados"]["intent_type"] == "" or dados_estruturados["dados"]["intent_type"] == "desconhecido":
            return dados_estruturados


    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]

    # Verifica se o nome foi obtido, caso contrário interage com o usuário para extrair essa informação
    if state["intent"] and state["intent"]["interlocutor_name"] == "":
        task = conversation_extractor_name_task(
            user_message=message,
            conversation_history=history,
            intent=partial_intent
        )
        crew = Crew(tasks=[task], verbose=True)
        result = str(crew.kickoff())
        try:
            dados_estruturados = extract_intent_from_response(result)
            update_user_state(id, intent=dados_estruturados.get("dados"),
                              message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
        except Exception:
            update_user_state(id, message=f"Usuário: {dados_estruturados.get('mensagem')}")

        if dados_estruturados["dados"]["interlocutor_name"] == "":
            return dados_estruturados

    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]

    if state["intent"] and state["intent"]["apartment_number"] == "" or state["intent"]["resident_name"] == "":
        task = conversation_extractor_resident_apartment_task(
            user_message=message,
            conversation_history=history,
            intent=partial_intent
        )
        crew = Crew(tasks=[task], verbose=True)
        result = str(crew.kickoff())
        try:
            dados_estruturados = extract_intent_from_response(result)
            update_user_state(id, intent=dados_estruturados.get("dados"),
                              message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
        except Exception:
            update_user_state(id, message=f"Usuário: {dados_estruturados.get('mensagem')}")

        if dados_estruturados["dados"]["apartment_number"] == "" or dados_estruturados["dados"]["resident_name"] == "":
            return dados_estruturados

        # É preciso retornar os dados para poder deixar a chamada em waiting enquanto processamos a intenção do usuário

        state = get_user_state(id)
        partial_intent = state["intent"]
        resultado = validar_intent_com_fuzzy(partial_intent)
        print(resultado)

        # gostaria de poder retornar um audio e também poder mudar o statuse o turno da chamada atual diretamente por aqui

        return dados_estruturados









    # # Cria a Task com histórico e dados parciais
    # task = create_conversation_coordinator_task(
    #     user_message=message,
    #     conversation_history=history,
    #     intent=partial_intent
    # )
    #
    # crew = Crew(tasks=[task], verbose=True)
    # result = str(crew.kickoff())
    #
    # # Tenta extrair novos dados (você pode usar OpenAI function calling ou Regex/JSON)
    # try:
    #     dados_estruturados = extract_intent_from_response(result)
    #     update_user_state(id, intent=dados_estruturados.get("dados"), message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
    # except Exception:
    #     update_user_state(id, message=f"Usuário: {dados_estruturados.get('mensagem')}")
    #
    # return dados_estruturados
