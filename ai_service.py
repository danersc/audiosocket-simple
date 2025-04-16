#!/usr/bin/env python3
# ai_service.py - Serviço para integração com a API de IA

import json
import logging
import httpx
import os
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def enviar_mensagem_para_ia(texto: str, conversation_id: str) -> Dict[str, Any]:
    """
    Envia uma mensagem para a API de IA e retorna a resposta.

    Args:
        texto: O texto a ser enviado para a API
        conversation_id: ID da conversa para manter contexto entre mensagens

    Returns:
        Dicionário com a resposta da API ou um dicionário com mensagem de erro
    """
    try:
        payload = {
            "id": conversation_id,
            "content": texto
        }

        api_url = os.getenv('AI_API_URL', 'http://localhost:8000/messages')
        if api_url.endswith('/'):
            api_url = api_url.rstrip('/')

        headers = {"Content-Type": "application/json"}

        logger.info("=" * 50)
        logger.info(f"ENVIANDO REQUISIÇÃO PARA API")
        logger.info(f"URL: {api_url}")
        logger.info(f"ID da Conversa: {conversation_id}")
        logger.info(f"Mensagem enviada: {texto}")
        logger.info(f"Payload completo enviado: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        logger.info("=" * 50)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            start_time = time.time()
            response = await client.post(api_url, json=payload, headers=headers, timeout=30.0)
            response_time = time.time() - start_time

            if response.status_code == 200:
                data = response.json()

                # LOG detalhado do retorno da IA:
                logger.info("=" * 50)
                logger.info(f"RESPOSTA COMPLETA RECEBIDA DA API DA IA (tempo: {response_time:.2f}s):")
                logger.info(json.dumps(data, ensure_ascii=False, indent=2))
                logger.info("=" * 50)

                return data
            else:
                logger.error("=" * 50)
                logger.error(f"ERRO NA REQUISIÇÃO PARA API (tempo: {response_time:.2f}s)")
                logger.error(f"Status: {response.status_code}")
                logger.error(f"Resposta da API: {response.text}")
                logger.error("=" * 50)

                return {
                    "content": {
                        "mensagem": "Desculpe, ocorreu um erro ao processar sua solicitação.",
                        "dados": {},
                        "valid_for_action": False
                    },
                    "timestamp": "",
                    "set_call_status": "USER_TURN"
                }

    except Exception as e:
        logger.error("=" * 50)
        logger.error(f"EXCEÇÃO AO COMUNICAR COM API DA IA")
        logger.error(f"ID da Conversa: {conversation_id}")
        logger.error(f"Mensagem que seria enviada: {texto}")
        logger.error(f"Erro: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.error("=" * 50)

        return {
            "content": {
                "mensagem": "Desculpe, não foi possível me conectar ao serviço neste momento.",
                "dados": {},
                "valid_for_action": False
            },
            "timestamp": "",
            "set_call_status": "USER_TURN"
        }

def extrair_mensagem_da_resposta(resposta: Dict[str, Any]) -> str:
    """
    Extrai a mensagem de texto da resposta da API.
    
    Args:
        resposta: Resposta da API
        
    Returns:
        Mensagem de texto para sintetizar
    """
    try:
        return resposta.get("content", {}).get("mensagem", "")
    except Exception as e:
        logger.error(f"Erro ao extrair mensagem da resposta: {e}")
        return "Desculpe, ocorreu um erro ao processar sua solicitação."

def obter_estado_chamada(resposta: Dict[str, Any]) -> Optional[str]:
    """
    Obtém o estado da chamada da resposta da API.

    Args:
        resposta: Resposta da API

    Returns:
        Estado da chamada (USER_TURN, WAITING, IA_TURN) ou None caso não especificado
    """
    try:
        return resposta.get("content", {}).get("set_call_status")
    except Exception as e:
        logger.error(f"Erro ao obter estado da chamada: {e}")
        return None
