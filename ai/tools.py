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

        # Regras de pré-processamento para melhorar matches
        # Normalizar nomes comuns
        residentes_alternativos = {
            "daner": ["daniel", "daner", "dani", "danir", "taner"],
            "renata": ["renata", "renato"]
        }
        
        # Log para debug
        print(f"Validando: Apt={apt}, Morador={resident_informado}")

        if not apt or not resident_informado:
            return {
                "status": "inválido",
                "reason": "Faltando número do apartamento ou nome do morador"
            }

        try:
            with open(VALID_APT_PATH, "r", encoding="utf-8") as f:
                apartamentos = json.load(f)
        except Exception as e:
            print(f"Erro ao ler arquivo de apartamentos: {e}")
            # Resposta de fallback para não interromper o fluxo
            return {
                "status": "erro",
                "message": f"Erro ao ler dados: {str(e)}"
            }

        # Primeiro tenta match exato de apartamento
        apt_matches = [a for a in apartamentos if a["apartment_number"] == apt]
        if not apt_matches:
            print(f"Nenhum apartamento {apt} encontrado")
            # Tentativa com fuzzy no apartamento (se for um erro de digitação)
            best_apt_score = 0
            best_apt_match = None
            for apartamento in apartamentos:
                apt_score = fuzz.ratio(apt, apartamento["apartment_number"])
                if apt_score > best_apt_score and apt_score >= 85:
                    best_apt_score = apt_score
                    best_apt_match = apartamento
            
            if best_apt_match:
                print(f"Encontrado apartamento próximo: {best_apt_match['apartment_number']} (score={best_apt_score})")
                apt_matches = [best_apt_match]

        # Se não encontrar o apartamento, retorna inválido
        if not apt_matches:
            return {
                "status": "inválido",
                "reason": f"Apartamento {apt} não encontrado"
            }
            
        # Procura melhor match de residente nos apartamentos encontrados
        best_match = None
        best_score = 0
        best_apt = None
        
        for apartamento in apt_matches:
            for residente in apartamento["residents"]:
                nome_residente = residente.strip().lower()
                
                # Pontuações para diferentes algoritmos de match
                scores = [
                    fuzz.ratio(resident_informado, nome_residente),  # Match completo
                    fuzz.partial_ratio(resident_informado, nome_residente),  # Match parcial
                    fuzz.token_sort_ratio(resident_informado, nome_residente)  # Ignora ordem das palavras
                ]
                
                # Verificar também nomes alternativos comuns
                for nome_base, alternativas in residentes_alternativos.items():
                    if nome_base in nome_residente:
                        for alt in alternativas:
                            if alt in resident_informado:
                                scores.append(95)  # Adiciona alta pontuação para alternativas conhecidas
                
                # Usar o melhor score entre os algoritmos
                score = max(scores)
                print(f"Comparando '{resident_informado}' com '{nome_residente}': score={score}")
                
                if score > best_score:
                    best_score = score
                    best_match = residente
                    best_apt = apartamento

        # Umbral mais baixo para melhorar a taxa de aceitação
        if best_score >= 75:
            print(f"Match encontrado: {best_match} no apt {best_apt['apartment_number']} (score={best_score})")
            return {
                "status": "válido",
                "match_name": best_match,
                "voip_number": best_apt["voip_number"],
                "match_score": best_score,
                "apartment_number": best_apt["apartment_number"]
            }
        else:
            print(f"Melhor match encontrado: {best_match} (score={best_score}), mas abaixo do umbral")

        return {
            "status": "inválido",
            "reason": "Morador não encontrado neste apartamento",
            "best_match": best_match,
            "best_score": best_score
        }
    except Exception as e:
        print(f"Erro na validação fuzzy: {e}")
        return {
            "status": "erro",
            "message": str(e)
        }
