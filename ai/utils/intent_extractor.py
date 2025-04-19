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
        try:
            message_of_non_understanding = json.loads(message)
        except:
            message_of_non_understanding = {
                "mensagem": "Não foi possível identificar sua intenção e seu nome, por favor, me informe seu nome e o que deseja.",
                "dados": {
                    "intent_type": "",
                    "interlocutor_name": "",
                    "apartment_number": "",
                    "resident_name": "",
                    "set_call_status": "USER_TURN"
                }
            }
        message_of_non_understanding['dados']['intent_type'] = IntentType.DESCONHECIDO
        message_of_non_understanding['valid_for_action'] = False
        return message_of_non_understanding
