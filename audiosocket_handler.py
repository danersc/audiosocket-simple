# audiosocket_handler.py

import asyncio
import logging
import struct
import os

import webrtcvad

from speech_service import transcrever_audio_async, sintetizar_fala_async
from session_manager import SessionManager  # Importamos o SessionManager

# Caso você use um "StateMachine" separado, pode remover ou adaptar:
# from state_machine import State

logger = logging.getLogger(__name__)

# Identificador do formato SLIN
KIND_SLIN = 0x10

# Podemos instanciar um SessionManager aqui como singleton/global.
# Se preferir criar em outro lugar, adapte.
session_manager = SessionManager()


async def enviar_audio(writer: asyncio.StreamWriter, dados_audio: bytes, origem="desconhecida"):
    """
    Envia dados de áudio (SLIN) ao cliente via 'writer'.
    """
    logger.info(f"[{origem}] Enviando áudio de {len(dados_audio)} bytes.")
    chunk_size = 320
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i : i + chunk_size]
        header = struct.pack(">B H", KIND_SLIN, len(chunk))
        writer.write(header + chunk)
        await writer.drain()
        # Pequeno atraso para não encher o buffer do lado do Asterisk
        await asyncio.sleep(0.02)


async def receber_audio_visitante(reader: asyncio.StreamReader, call_id: str):
    """
    Tarefa que fica lendo o áudio do visitante, detecta quando ele fala (usando VAD)
    e chama `session_manager.process_visitor_text(...)` ao fim de cada frase.
    """
    vad = webrtcvad.Vad(2)  # Agressivo 0-3
    frames = []
    is_speaking = False
    silence_start = None

    while True:
        try:
            header = await reader.readexactly(3)
        except asyncio.IncompleteReadError:
            logger.info(f"[{call_id}] Visitante desconectou (EOF).")
            break

        if not header:
            logger.info(f"[{call_id}] Nenhum dado de header, encerrando.")
            break

        kind = header[0]
        length = int.from_bytes(header[1:3], "big")

        audio_chunk = await reader.readexactly(length)
        if kind == KIND_SLIN and len(audio_chunk) == 320:
            # Avalia VAD
            is_voice = vad.is_speech(audio_chunk, 8000)
            if is_voice:
                frames.append(audio_chunk)
                if not is_speaking:
                    is_speaking = True
                    logger.debug(f"[{call_id}] Visitante começou a falar.")
                silence_start = None
            else:
                if is_speaking:
                    # Já estava falando e agora está em silêncio
                    if silence_start is None:
                        silence_start = asyncio.get_event_loop().time()
                    else:
                        # Se passou 2s em silêncio, considera que a fala terminou
                        if (asyncio.get_event_loop().time() - silence_start) > 2.0:
                            is_speaking = False
                            logger.debug(f"[{call_id}] Visitante parou de falar.")
                            audio_data = b"".join(frames)
                            frames.clear()

                            # Transcrever
                            texto = await transcrever_audio_async(audio_data)
                            if texto:
                                session_manager.process_visitor_text(call_id, texto)
        else:
            logger.warning(f"[{call_id}] Chunk inválido do visitante. kind={kind}, len={len(audio_chunk)}")

    # Ao sair, encerrou a conexão
    logger.info(f"[{call_id}] receber_audio_visitante terminou.")


async def enviar_mensagens_visitante(writer: asyncio.StreamWriter, call_id: str):
    """
    Tarefa que periodicamente verifica se há mensagens pendentes
    para o visitante no SessionManager, sintetiza e envia via áudio.
    """
    while True:
        await asyncio.sleep(0.2)  # Ajuste conforme sua necessidade

        # Tenta buscar uma mensagem
        msg = session_manager.get_message_for_visitor(call_id)
        if msg is not None:
            logger.info(f"[{call_id}] Enviando mensagem ao visitante: {msg}")
            audio_resposta = await sintetizar_fala_async(msg)
            if audio_resposta:
                await enviar_audio(writer, audio_resposta, origem="Visitante")


async def iniciar_servidor_audiosocket_visitante(reader, writer):
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    call_id = call_id_bytes.hex()

    logger.info(f"[VISITANTE] Recebido Call ID: {call_id}")

    session_manager.create_session(call_id)

    # SAUDAÇÃO:
    session_manager.enfileirar_visitor(
        call_id,
        "Olá, seja bem-vindo! Em que posso ajudar?"
    )

    task1 = asyncio.create_task(receber_audio_visitante(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_visitante(writer, call_id))

    # Espera até que alguma das tarefas termine (em geral, quando visitante desconecta).
    done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
    logger.info(f"[{call_id}] Alguma tarefa finalizou, vamos encerrar as duas...")

    # Cancela a outra
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    logger.info(f"[{call_id}] Encerrando conexão do visitante.")
    writer.close()
    await writer.wait_closed()


# ------------------------
# MORADOR
# ------------------------

async def receber_audio_morador(reader: asyncio.StreamReader, call_id: str):
    """
    Versão equivalente para o morador
    """
    vad = webrtcvad.Vad(2)
    frames = []
    is_speaking = False
    silence_start = None

    while True:
        try:
            header = await reader.readexactly(3)
        except asyncio.IncompleteReadError:
            logger.info(f"[{call_id}] Morador desconectou (EOF).")
            break

        if not header:
            logger.info(f"[{call_id}] Nenhum dado de header, encerrando (morador).")
            break

        kind = header[0]
        length = int.from_bytes(header[1:3], "big")

        audio_chunk = await reader.readexactly(length)
        if kind == KIND_SLIN and len(audio_chunk) == 320:
            is_voice = vad.is_speech(audio_chunk, 8000)
            if is_voice:
                frames.append(audio_chunk)
                if not is_speaking:
                    is_speaking = True
                    logger.debug(f"[{call_id}] Morador começou a falar.")
                silence_start = None
            else:
                if is_speaking:
                    if silence_start is None:
                        silence_start = asyncio.get_event_loop().time()
                    else:
                        if (asyncio.get_event_loop().time() - silence_start) > 2.0:
                            is_speaking = False
                            logger.debug(f"[{call_id}] Morador parou de falar.")
                            audio_data = b"".join(frames)
                            frames.clear()

                            texto = await transcrever_audio_async(audio_data)
                            if texto:
                                session_manager.process_resident_text(call_id, texto)
        else:
            logger.warning(f"[{call_id}] Chunk inválido do morador. kind={kind}, len={len(audio_chunk)}")

    logger.info(f"[{call_id}] receber_audio_morador terminou.")


async def enviar_mensagens_morador(writer: asyncio.StreamWriter, call_id: str):
    """
    Fica buscando mensagens para o morador, sintetiza e envia via áudio.
    """
    while True:
        await asyncio.sleep(0.2)
        msg = session_manager.get_message_for_resident(call_id)
        if msg is not None:
            logger.info(f"[{call_id}] Enviando mensagem ao morador: {msg}")
            audio_resposta = await sintetizar_fala_async(msg)
            if audio_resposta:
                await enviar_audio(writer, audio_resposta, origem="Morador")


async def iniciar_servidor_audiosocket_morador(reader, writer):
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    call_id = call_id_bytes.hex()

    logger.info(f"[MORADOR] Recebido Call ID: {call_id}")

    session_manager.create_session(call_id)

    # SAUDAÇÃO MORADOR:
    session_manager.enfileirar_resident(
        call_id,
        "Olá, morador! Você está em ligação com a portaria inteligente."
    )

    task1 = asyncio.create_task(receber_audio_morador(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_morador(writer, call_id))

    done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
    logger.info(f"[{call_id}] Alguma tarefa (morador) finalizou, encerrar.")

    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    writer.close()
    await writer.wait_closed()
    logger.info(f"[{call_id}] Conexão do morador encerrada.")
