import logging
from ai.main import process_message  # Importação direta do CrewAI
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

async def enviar_mensagem_para_ia(texto: str, conversation_id: str) -> Dict[str, Any]:
    """
    Agora chama diretamente o CrewAI ao invés da API externa.
    """
    try:
        logger.info("=" * 50)
        logger.info(f"Chamando CrewAI diretamente com mensagem: {texto}")
        resposta = process_message(content=texto, id=conversation_id)

        logger.info("=" * 50)
        logger.info(f"Resposta recebida do CrewAI:")
        logger.info(resposta)
        logger.info("=" * 50)

        # Adiciona o timestamp que antes era retornado pela API
        resposta_com_timestamp = {
            "content": resposta,
            "timestamp": ""
        }

        return resposta_com_timestamp

    except Exception as e:
        logger.error(f"Erro ao comunicar com CrewAI diretamente: {e}")
        return {
            "content": {
                "mensagem": "Desculpe, não consegui processar sua solicitação no momento.",
                "dados": {},
                "valid_for_action": False,
                "set_call_status": "USER_TURN"
            },
            "timestamp": ""
        }

def extrair_mensagem_da_resposta(resposta: Dict[str, Any]) -> str:
    return resposta.get("content", {}).get("mensagem", "")

def obter_estado_chamada(resposta: Dict[str, Any]) -> Optional[str]:
    return resposta.get("content", {}).get("set_call_status")
