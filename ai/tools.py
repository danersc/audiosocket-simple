from rapidfuzz import fuzz
import json
from pathlib import Path
from typing import Dict
from ai.models.intent import IntentData
from crewai.tools import tool

VALID_APT_PATH = Path("data/apartamentos.json")

@tool("SendMessageTool")
def identify_user_intent(message: str) -> str:
    """
    Extrai intenção do usuário com base na mensagem utilizando um modelo LLM.
    Retorna um JSON no formato esperado por UserIntent.
    """
    return message


# @tool("ValidarIntentComFuzzyTool")
def validar_intent_com_fuzzy(intent: Dict) -> Dict:
    """
    Verifica se a combinação apartment_number e resident_name da intent
    corresponde (mesmo que parcialmente) a um morador real.

    Retorna um dicionário:
    {
      "status": "válido" ou "inválido",
      "match_name": "Fulano de Tal",
      "voip_number": "1003031"
    }
    """
    try:
        apt = intent.get("apartment_number", "").strip().lower()  # 'apartment_number
        resident_informado = intent.get("resident_name", "").strip().lower()

        if not apt or not resident_informado:
            return {
                "status": "inválido",
                "reason": "Faltando número do apartamento ou nome do morador"
            }

        with open(VALID_APT_PATH, "r", encoding="utf-8") as f:
            apartamentos = json.load(f)

        for apartamento in apartamentos:
            if apartamento["apartment_number"] != apt:
                continue

            for residente in apartamento["residents"]:
                nome_residente = residente.strip().lower()
                score = fuzz.partial_ratio(resident_informado, nome_residente)

                if score >= 85:
                    return {
                        "status": "válido",
                        "match_name": residente,
                        "voip_number": apartamento["voip_number"]
                    }

        return {
            "status": "inválido",
            "reason": "Morador não encontrado neste apartamento"
        }
    except Exception as e:
        return {
            "status": "erro",
            "message": str(e)
        }
