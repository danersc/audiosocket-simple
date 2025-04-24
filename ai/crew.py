from crewai import Crew
import time

from ai.state_manager import get_user_state, update_user_state, clear_user_state
from ai.tasks import create_conversation_coordinator_task, conversation_extractor_name_task, \
    conversation_extractor_intent_task, conversation_extractor_resident_apartment_task
from ai.tools import validar_intent_com_fuzzy
from ai.utils.intent_extractor import extract_intent_from_response
from ai.models.intent import IntentData
import json
from utils.call_logger import CallLoggerManager

def process_user_message_with_coordinator(id: str, message: str) -> dict:
    # Obter logger para esta chamada
    call_logger = CallLoggerManager.get_logger(id)
    
    # Marcar início do processamento pela IA
    call_logger.log_ai_processing_start(message)
    total_start_time = time.time()
    
    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]
    dados_estruturados = None

    # A partir do nome obtido, verifica a intenção do usuário
    if not state["intent"] or state["intent"]["intent_type"] == "":
        call_logger.log_event("INTENT_EXTRACTION_START", {
            "stage": "intent_type",
            "current_intent": str(partial_intent)
        })
        
        intent_start_time = time.time()
        task = conversation_extractor_intent_task(
            user_message=message,
            conversation_history=history,
            intent=partial_intent
        )
        crew = Crew(tasks=[task], verbose=True)
        result = str(crew.kickoff())
        intent_duration = (time.time() - intent_start_time) * 1000
        
        try:
            dados_estruturados = extract_intent_from_response(result)
            update_user_state(id, intent=dados_estruturados.get("dados"),
                              message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
            
            call_logger.log_event("INTENT_EXTRACTION_COMPLETE", {
                "stage": "intent_type",
                "result": dados_estruturados["dados"]["intent_type"],
                "duration_ms": round(intent_duration, 2)
            })
        except Exception as e:
            update_user_state(id, message=f"Usuário: {message}")
            call_logger.log_error("INTENT_EXTRACTION_ERROR", 
                                str(e), 
                                {"stage": "intent_type"})
            
            # Criar um dados_estruturados default para evitar erros
            dados_estruturados = {
                "mensagem": "Desculpe, não consegui entender. Poderia repetir?",
                "dados": {"intent_type": "", "interlocutor_name": "", "apartment_number": "", "resident_name": ""},
                "valid_for_action": False
            }

        if dados_estruturados["dados"]["intent_type"] == "" or dados_estruturados["dados"]["intent_type"] == "desconhecido":
            ai_duration = (time.time() - total_start_time) * 1000
            call_logger.log_ai_processing_complete(dados_estruturados, ai_duration)
            return dados_estruturados

    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]

    # Verifica se o nome foi obtido, caso contrário interage com o usuário para extrair essa informação
    if state["intent"] and state["intent"]["interlocutor_name"] == "":
        call_logger.log_event("INTENT_EXTRACTION_START", {
            "stage": "interlocutor_name",
            "current_intent": str(partial_intent)
        })
        
        name_start_time = time.time()
        task = conversation_extractor_name_task(
            user_message=message,
            conversation_history=history,
            intent=partial_intent
        )
        crew = Crew(tasks=[task], verbose=True)
        result = str(crew.kickoff())
        name_duration = (time.time() - name_start_time) * 1000
        
        try:
            dados_estruturados = extract_intent_from_response(result)
            update_user_state(id, intent=dados_estruturados.get("dados"),
                              message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
            
            call_logger.log_event("INTENT_EXTRACTION_COMPLETE", {
                "stage": "interlocutor_name",
                "result": dados_estruturados["dados"]["interlocutor_name"],
                "duration_ms": round(name_duration, 2)
            })
        except Exception as e:
            update_user_state(id, message=f"Usuário: {message}")
            call_logger.log_error("INTENT_EXTRACTION_ERROR", 
                                str(e), 
                                {"stage": "interlocutor_name"})
            
            # Criar um dados_estruturados default
            dados_estruturados = {
                "mensagem": "Desculpe, não consegui entender seu nome. Poderia repetir?",
                "dados": partial_intent,
                "valid_for_action": False
            }

        if dados_estruturados["dados"]["interlocutor_name"] == "":
            ai_duration = (time.time() - total_start_time) * 1000
            call_logger.log_ai_processing_complete(dados_estruturados, ai_duration)
            return dados_estruturados

    state = get_user_state(id)
    history = "\n".join(state["history"])
    partial_intent = state["intent"]

    if state["intent"] and state["intent"]["apartment_number"] == "" or state["intent"]["resident_name"] == "":
        call_logger.log_event("INTENT_EXTRACTION_START", {
            "stage": "apartment_and_resident",
            "current_intent": str(partial_intent)
        })
        
        apt_start_time = time.time()
        task = conversation_extractor_resident_apartment_task(
            user_message=message,
            conversation_history=history,
            intent=partial_intent
        )
        crew = Crew(tasks=[task], verbose=True)
        result = str(crew.kickoff())
        apt_duration = (time.time() - apt_start_time) * 1000
        
        try:
            dados_estruturados = extract_intent_from_response(result)
            update_user_state(id, intent=dados_estruturados.get("dados"),
                              message=f"Usuário: {message}\nResposta LLM: {dados_estruturados.get('mensagem')}")
            
            call_logger.log_event("INTENT_EXTRACTION_COMPLETE", {
                "stage": "apartment_and_resident",
                "result": f"apt: {dados_estruturados['dados']['apartment_number']}, resident: {dados_estruturados['dados']['resident_name']}",
                "duration_ms": round(apt_duration, 2)
            })
        except Exception as e:
            update_user_state(id, message=f"Usuário: {message}")
            call_logger.log_error("INTENT_EXTRACTION_ERROR", 
                                str(e), 
                                {"stage": "apartment_and_resident"})
            
            # Criar um dados_estruturados default
            dados_estruturados = {
                "mensagem": "Desculpe, não consegui entender as informações do apartamento/morador. Poderia repetir?",
                "dados": partial_intent,
                "valid_for_action": False
            }

        if dados_estruturados["dados"]["apartment_number"] == "" or dados_estruturados["dados"]["resident_name"] == "":
            ai_duration = (time.time() - total_start_time) * 1000
            call_logger.log_ai_processing_complete(dados_estruturados, ai_duration)
            return dados_estruturados

        # É preciso retornar os dados para poder deixar a chamada em waiting enquanto processamos a intenção do usuário
        state = get_user_state(id)
        partial_intent = state["intent"]
        
        # Medição de tempo para validação fuzzy
        fuzzy_start_time = time.time()
        call_logger.log_event("FUZZY_VALIDATION_START", {"intent": str(partial_intent)})
        resultado = validar_intent_com_fuzzy(partial_intent)
        fuzzy_duration = (time.time() - fuzzy_start_time) * 1000
        
        call_logger.log_event("FUZZY_VALIDATION_COMPLETE", {
            "status": resultado["status"],
            "reason": resultado.get("reason", ""),
            "match_name": resultado.get("match_name", ""),
            "voip_number": resultado.get("voip_number", ""),
            "duration_ms": round(fuzzy_duration, 2)
        })

        if resultado["status"] == "inválido":
            # Zera apt/resident
            partial_intent["apartment_number"] = ""
            partial_intent["resident_name"] = ""

            invalid_response = {
                "mensagem": "Não encontrei esse apartamento/morador. Poderia repetir?",
                "dados": partial_intent,
                "valid_for_action": False
            }
            
            ai_duration = (time.time() - total_start_time) * 1000
            call_logger.log_ai_processing_complete(invalid_response, ai_duration)
            return invalid_response

        # Adicionar valid_for_action e outros metadados
        dados_estruturados["valid_for_action"] = True

    # Tempo total de processamento
    ai_duration = (time.time() - total_start_time) * 1000
    call_logger.log_ai_processing_complete(dados_estruturados, ai_duration)
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
