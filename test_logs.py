#!/usr/bin/env python3
"""
Script de teste para demonstrar o sistema de logs.
Este script simula uma chamada e gera logs para análise.
"""

import asyncio
import time
from uuid_v7 import uuid_v7
import logging
from utils.call_logger import CallLoggerManager
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def simulate_call(call_duration=30):
    """Simula uma chamada completa com visitante e morador."""
    # Gerar um ID único para a chamada usando UUID v7 baseado em timestamp
    call_id = str(uuid_v7())
    logger.info(f"Iniciando chamada simulada com ID: {call_id}")
    
    # Obter o logger para esta chamada
    call_logger = CallLoggerManager.get_logger(call_id)
    call_logger.log_event("CALL_SETUP", {
        "type": "visitor",
        "call_id": call_id
    })
    
    # Simular saudação
    welcome_msg = "Olá, seja bem-vindo! Em que posso ajudar?"
    call_logger.log_event("GREETING", {"message": welcome_msg})
    
    # Simular visitante falando
    await asyncio.sleep(1.5)  # Tempo até o visitante começar a falar
    call_logger.log_speech_detected(is_visitor=True)
    
    # Visitante fala por um tempo
    speech_duration = random.uniform(2.0, 4.0) * 1000  # 2-4 segundos
    await asyncio.sleep(speech_duration / 1000)
    
    # Visitante para de falar, silêncio detectado
    call_logger.log_speech_ended(speech_duration, is_visitor=True)
    call_logger.log_silence_detected(2000, is_visitor=True)
    
    # Simular transcrição do áudio
    audio_size = int(speech_duration * 8)  # Simulação de tamanho de áudio
    call_logger.log_transcription_start(audio_size, is_visitor=True)
    
    # Simular tempo de transcrição
    transcription_time = random.uniform(0.5, 2.0) * 1000  # 500ms - 2s
    await asyncio.sleep(transcription_time / 1000)
    
    visitor_text = "Olá, sou o João e estou aqui para entregar uma encomenda para o apartamento 501 da Renata Oliveira."
    call_logger.log_transcription_complete(visitor_text, transcription_time, is_visitor=True)
    
    # Simular processamento de IA
    call_logger.log_ai_processing_start(visitor_text)
    
    # Simular extração de intenção (tipo)
    call_logger.log_event("INTENT_EXTRACTION_START", {
        "stage": "intent_type",
        "current_intent": "{}"
    })
    
    intent_time = random.uniform(1.0, 3.0) * 1000
    await asyncio.sleep(intent_time / 1000)
    
    call_logger.log_event("INTENT_EXTRACTION_COMPLETE", {
        "stage": "intent_type",
        "result": "entrega",
        "duration_ms": intent_time
    })
    
    # Simular extração de nome
    call_logger.log_event("INTENT_EXTRACTION_START", {
        "stage": "interlocutor_name",
        "current_intent": '{"intent_type": "entrega"}'
    })
    
    name_time = random.uniform(1.0, 2.0) * 1000
    await asyncio.sleep(name_time / 1000)
    
    call_logger.log_event("INTENT_EXTRACTION_COMPLETE", {
        "stage": "interlocutor_name",
        "result": "João",
        "duration_ms": name_time
    })
    
    # Simular extração de apartamento e morador
    call_logger.log_event("INTENT_EXTRACTION_START", {
        "stage": "apartment_and_resident",
        "current_intent": '{"intent_type": "entrega", "interlocutor_name": "João"}'
    })
    
    apt_time = random.uniform(1.0, 2.0) * 1000
    await asyncio.sleep(apt_time / 1000)
    
    call_logger.log_event("INTENT_EXTRACTION_COMPLETE", {
        "stage": "apartment_and_resident",
        "result": "apt: 501, resident: Renata Oliveira",
        "duration_ms": apt_time
    })
    
    # Simular validação fuzzy
    call_logger.log_event("FUZZY_VALIDATION_START", {
        "intent": '{"intent_type": "entrega", "interlocutor_name": "João", "apartment_number": "501", "resident_name": "Renata Oliveira"}'
    })
    
    fuzzy_time = random.uniform(0.1, 0.5) * 1000
    await asyncio.sleep(fuzzy_time / 1000)
    
    call_logger.log_event("FUZZY_VALIDATION_COMPLETE", {
        "status": "válido",
        "match_name": "Renata Oliveira",
        "voip_number": "1003030",
        "duration_ms": fuzzy_time
    })
    
    # Finalizar processamento de IA
    ai_total_time = intent_time + name_time + apt_time + fuzzy_time
    response = {
        "mensagem": "Entrega registrada para Renata Oliveira no apartamento 501. Vou chamar a moradora.",
        "dados": {
            "intent_type": "entrega",
            "interlocutor_name": "João",
            "apartment_number": "501",
            "resident_name": "Renata Oliveira"
        },
        "valid_for_action": True
    }
    
    call_logger.log_ai_processing_complete(response, ai_total_time)
    
    # Simular resposta para o visitante
    call_logger.log_synthesis_start(response["mensagem"], is_visitor=True)
    
    synthesis_time = random.uniform(0.5, 1.5) * 1000
    await asyncio.sleep(synthesis_time / 1000)
    
    audio_size = len(response["mensagem"]) * 100  # Tamanho simulado do áudio
    call_logger.log_synthesis_complete(audio_size, synthesis_time, is_visitor=True)
    
    # Simular chamada para o morador
    call_logger.log_event("CALL_MORADOR", {
        "voip_number": "1003030",
        "attempt": 1
    })
    
    await asyncio.sleep(2.0)  # Tempo até morador atender
    
    # Morador atende
    call_logger.log_event("MORADOR_CONNECTED", {
        "voip_number": "1003030"
    })
    
    # Saudação para o morador
    morador_welcome = "Olá, morador! Há uma entrega para você na portaria."
    call_logger.log_synthesis_start(morador_welcome, is_visitor=False)
    
    synthesis_time = random.uniform(0.5, 1.5) * 1000
    await asyncio.sleep(synthesis_time / 1000)
    
    audio_size = len(morador_welcome) * 100
    call_logger.log_synthesis_complete(audio_size, synthesis_time, is_visitor=False)
    
    # Morador responde
    await asyncio.sleep(1.0)
    call_logger.log_speech_detected(is_visitor=False)
    
    speech_duration = random.uniform(1.0, 2.0) * 1000
    await asyncio.sleep(speech_duration / 1000)
    
    call_logger.log_speech_ended(speech_duration, is_visitor=False)
    call_logger.log_silence_detected(2000, is_visitor=False)
    
    # Transcrição da resposta do morador
    audio_size = int(speech_duration * 8)
    call_logger.log_transcription_start(audio_size, is_visitor=False)
    
    transcription_time = random.uniform(0.5, 1.5) * 1000
    await asyncio.sleep(transcription_time / 1000)
    
    morador_text = "Sim, pode deixar entrar."
    call_logger.log_transcription_complete(morador_text, transcription_time, is_visitor=False)
    
    # Processamento da resposta do morador
    start_time = time.time()
    await asyncio.sleep(0.2)  # Tempo de processamento (simples)
    processing_time = (time.time() - start_time) * 1000
    
    call_logger.log_event("RESIDENT_PROCESSING_COMPLETE", {
        "text": morador_text,
        "processing_time_ms": processing_time
    })
    
    # Resposta final para o visitante
    final_message = "Morador autorizou sua entrada! Pode entrar."
    call_logger.log_synthesis_start(final_message, is_visitor=True)
    
    synthesis_time = random.uniform(0.5, 1.0) * 1000
    await asyncio.sleep(synthesis_time / 1000)
    
    audio_size = len(final_message) * 100
    call_logger.log_synthesis_complete(audio_size, synthesis_time, is_visitor=True)
    
    # Terminar chamada
    await asyncio.sleep(1.0)
    call_logger.log_call_ended("call_completed", call_duration * 1000)
    
    # Remover logger
    CallLoggerManager.remove_logger(call_id)
    
    logger.info(f"Chamada simulada finalizada: {call_id}")
    return call_id


async def simulate_error_call():
    """Simula uma chamada com erros."""
    # Usando UUID v7 baseado em timestamp para melhor ordenação
    call_id = str(uuid_v7())
    logger.info(f"Iniciando chamada com erros - ID: {call_id}")
    
    call_logger = CallLoggerManager.get_logger(call_id)
    call_logger.log_event("CALL_SETUP", {
        "type": "visitor",
        "call_id": call_id
    })
    
    # Simular visitante falando
    await asyncio.sleep(1.0)
    call_logger.log_speech_detected(is_visitor=True)
    
    speech_duration = random.uniform(1.0, 3.0) * 1000
    await asyncio.sleep(speech_duration / 1000)
    
    call_logger.log_speech_ended(speech_duration, is_visitor=True)
    
    # Simular erro na transcrição
    audio_size = int(speech_duration * 8)
    call_logger.log_transcription_start(audio_size, is_visitor=True)
    
    await asyncio.sleep(1.0)
    
    call_logger.log_error("TRANSCRIPTION_FAILED", 
                        "Falha ao transcrever áudio do visitante", 
                        {"audio_size": audio_size, "reason": "Audio clarity too low"})
    
    # Simular mensagem de erro para o visitante
    error_message = "Desculpe, não consegui entender. Pode repetir por favor?"
    call_logger.log_synthesis_start(error_message, is_visitor=True)
    
    synthesis_time = random.uniform(0.5, 1.0) * 1000
    await asyncio.sleep(synthesis_time / 1000)
    
    audio_size = len(error_message) * 100
    call_logger.log_synthesis_complete(audio_size, synthesis_time, is_visitor=True)
    
    # Terminar chamada
    await asyncio.sleep(1.0)
    call_logger.log_call_ended("transcription_error", 5000)
    
    # Remover logger
    CallLoggerManager.remove_logger(call_id)
    
    logger.info(f"Chamada com erro finalizada: {call_id}")
    return call_id


async def main():
    """Executa simulações de chamada."""
    print("Iniciando simulações de chamadas...")
    
    # Simular 3 chamadas bem-sucedidas
    calls = []
    for i in range(3):
        calls.append(simulate_call(random.randint(20, 40)))
    
    # Simular 1 chamada com erro
    calls.append(simulate_error_call())
    
    # Executar todas as chamadas em paralelo
    call_ids = await asyncio.gather(*calls)
    
    print("\nSimulações concluídas!")
    print("IDs das chamadas simuladas:")
    for call_id in call_ids:
        print(f"  - {call_id}")
    
    print(f"\nOs logs foram gerados na pasta 'logs/'")
    print("Para analisar os logs, execute:")
    print(f"  python utils/log_analyzer.py --call_id {call_ids[0]}")
    print("  ou")
    print("  python utils/log_analyzer.py --all --summary")


if __name__ == "__main__":
    asyncio.run(main())