import json

from guardrails import Guard
from typing import Dict

from humanfriendly.terminal import message

from ai.models.intent import IntentData, IntentType, FullIntentResponse

# =======================
# 🛡️ RAILS SCHEMA (sem valid_for_action)
# =======================

INTENT_SCHEMA = """
<rail version="0.1">
<output>
  <object>
    <string name="mensagem" description="Mensagem a ser enviada ao usuário, clara e objetiva"/>
    <object name="dados">
      <string name="intent_type" format="enum" enum-values="visita,entrega,desconhecido"/>
      <string name="interlocutor_name" on-fail-soft="noop"/>
      <string name="apartment_number" on-fail-soft="noop"/>
      <string name="resident_name" on-fail-soft="noop"/>
    </object>
  </object>
</output>
</rail>
"""

guard = Guard.for_rail_string(INTENT_SCHEMA)

# =======================
# 🔍 EXTRACTOR
# =======================

def extract_intent_from_response(response: str) -> Dict:
    """
    Valida e extrai os dados de intenção usando Guardrails e Pydantic.
    Calcula valid_for_action com base nos campos preenchidos.
    """
    try:
        validated  = guard.parse(response)
        raw = validated.validated_output

        if not all(k in raw for k in ["mensagem", "dados"]):
            raise ValueError("Resposta fora do padrão esperado")

        if raw["dados"].get("intent_type") == "":
            raw["dados"]["intent_type"] = IntentType.DESCONHECIDO

        intent = IntentData(**raw["dados"])

        # Cálculo de completude
        campos_preenchidos = all([
            intent.intent_type != IntentType.DESCONHECIDO,
            intent.interlocutor_name.strip(),
            intent.apartment_number.strip(),
            intent.resident_name.strip()
        ])

        call_status = "USER_TURN"
        if campos_preenchidos:
            call_status = "WAITING"

        result = FullIntentResponse(
            mensagem=raw["mensagem"],
            dados=intent,
            valid_for_action=campos_preenchidos,
            set_call_status=call_status
        )

        return result.model_dump()
    except Exception as e:
        # Log do erro para diagnóstico (idealmente seria para um sistema de log)
        print(f"Erro ao extrair intenção: {str(e)}")
        
        # Tenta entender se a mensagem já é um JSON
        if isinstance(response, str) and response.strip().startswith('{') and response.strip().endswith('}'):
            try:
                # Tenta extrair JSON diretamente da resposta
                message_of_non_understanding = json.loads(response)
                if "mensagem" in message_of_non_understanding and "dados" in message_of_non_understanding:
                    # Garante que todos os campos necessários estejam presentes
                    if "intent_type" not in message_of_non_understanding["dados"]:
                        message_of_non_understanding["dados"]["intent_type"] = "desconhecido"
                    if "interlocutor_name" not in message_of_non_understanding["dados"]:
                        message_of_non_understanding["dados"]["interlocutor_name"] = ""
                    if "apartment_number" not in message_of_non_understanding["dados"]:
                        message_of_non_understanding["dados"]["apartment_number"] = ""
                    if "resident_name" not in message_of_non_understanding["dados"]:
                        message_of_non_understanding["dados"]["resident_name"] = ""
                    
                    message_of_non_understanding["valid_for_action"] = False
                    message_of_non_understanding["set_call_status"] = "USER_TURN"
                    return message_of_non_understanding
            except:
                # Se falhar na análise JSON, continua para a resposta padrão
                pass
                
        # Resposta padrão para casos de erro
        message_of_non_understanding = {
            "mensagem": "Desculpe, não consegui entender. Por favor, informe novamente o que deseja.",
            "dados": {
                "intent_type": "desconhecido",
                "interlocutor_name": "",
                "apartment_number": "",
                "resident_name": ""
            },
            "valid_for_action": False,
            "set_call_status": "USER_TURN"
        }
        
        return message_of_non_understanding
