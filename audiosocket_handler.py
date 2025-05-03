# audiosocket_handler.py (versão consolidada e simplificada)

import asyncio
import logging
import struct

import azure.cognitiveservices.speech as speechsdk
from azure_speech_callbacks import SpeechCallbacks
import os
import wave
import uuid
from session_manager import SessionManager
from extensions.resource_manager import resource_manager
from speech_service import sintetizar_fala_async, transcrever_audio_async
from utils.call_logger import CallLoggerManager

SAMPLE_RATE = 8000
CHANNELS = 1
DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

logger = logging.getLogger(__name__)
session_manager = SessionManager()

# Variável global para armazenar o extension_manager
extension_manager = None

def set_extension_manager(manager):
    """
    Define o extension_manager global para ser usado pelo handler.
    """
    global extension_manager
    extension_manager = manager

async def read_tlv_packet(reader):
    header = await reader.readexactly(3)
    packet_type = header[0]
    length = int.from_bytes(header[1:3], "big")
    payload = await reader.readexactly(length)
    return packet_type, payload

async def iniciar_servidor_audiosocket_visitante(reader, writer):
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    call_id = str(uuid.UUID(bytes=call_id_bytes))

    session_manager.create_session(call_id)
    resource_manager.register_connection(call_id, "visitor", reader, writer)

    speech_config = speechsdk.SpeechConfig(
        subscription=os.getenv("AZURE_SPEECH_KEY"),
        region=os.getenv("AZURE_SPEECH_REGION")
    )
    speech_config.speech_recognition_language = "pt-BR"

    audio_format = speechsdk.audio.AudioStreamFormat(samples_per_second=SAMPLE_RATE, bits_per_sample=16, channels=CHANNELS)
    push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

    recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)

    session_manager.enfileirar_visitor(
        call_id,
        "Olá, seja bem-vindo! Por favor, informe o que deseja: se entrega ou visita."
    )

    callbacks = SpeechCallbacks(call_id=call_id, session_manager=session_manager)
    callbacks.register_callbacks(recognizer)

    recognizer.start_continuous_recognition_async()

    audio_buffer = []

    task1 = asyncio.create_task(receber_audio_visitante(reader, call_id, push_stream, callbacks, audio_buffer))
    task2 = asyncio.create_task(enviar_mensagens_visitante(writer, call_id))

    await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)

    push_stream.close()
    recognizer.stop_continuous_recognition_async()

    audio_data = b''.join(audio_buffer)
    filename = os.path.join(DEBUG_DIR, f"audio_{call_id}.wav")
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    logger.info(f"Áudio salvo em {filename}")

async def receber_audio_visitante(reader, call_id, push_stream, callbacks, audio_buffer):
    try:
        while True:
            packet_type, payload = await read_tlv_packet(reader)
            if packet_type == 0x10:
                audio_buffer.append(payload)
                push_stream.write(payload)
                callbacks.add_audio_chunk(payload)
            elif packet_type == 0x01:
                logger.info(f"UUID recebido: {payload.hex()}")
            elif packet_type == 0x00:
                logger.info("Pacote de término recebido.")
                break
    except asyncio.IncompleteReadError:
        logger.warning("Conexão fechada abruptamente.")
    except Exception as e:
        logger.error(f"Erro ao receber dados: {e}")

async def enviar_mensagens_visitante(writer, call_id):
    session = session_manager.get_session(call_id)
    while True:
        msg = session_manager.get_message_for_visitor(call_id)
        if msg:
            audio_resposta = await sintetizar_fala_async(msg)
            await enviar_audio(writer, audio_resposta)
        await asyncio.sleep(0.2)

async def iniciar_servidor_audiosocket_morador(reader, writer):
    logger.info("Conexão recebida do morador.")

    # Aqui você DEVE receber o call_id do Asterisk
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    call_id = str(uuid.UUID(bytes=call_id_bytes))

    # Cria sessão com o call_id fornecido
    session_manager.create_session(call_id)
    resource_manager.register_connection(call_id, "resident", reader, writer)

    task1 = asyncio.create_task(receber_audio_morador(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_morador(writer, call_id))

    await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)

async def receber_audio_morador(reader: asyncio.StreamReader, call_id: str):
    call_logger = CallLoggerManager.get_logger(call_id)

    azure_key = os.getenv('AZURE_SPEECH_KEY')
    azure_region = os.getenv('AZURE_SPEECH_REGION')

    speech_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
    speech_config.speech_recognition_language = 'pt-BR'

    push_stream = speechsdk.audio.PushAudioInputStream(
        stream_format=speechsdk.audio.AudioStreamFormat(samples_per_second=8000, bits_per_sample=16, channels=1)
    )

    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    # Callbacks
    async def process_recognized_text(text, audio_data):
        if not audio_data:
            return

        session = session_manager.get_session(call_id)
        session.resident_state = "WAITING"
        call_logger.log_transcription_start(len(audio_data), is_visitor=False)

        if text and text.strip():
            call_logger.log_transcription_complete(text, 0, is_visitor=False)
            session_manager.process_resident_text(call_id, text)
        else:
            texto = await transcrever_audio_async(audio_data, call_id=call_id)
            if texto:
                call_logger.log_transcription_complete(texto, 0, is_visitor=False)
                session_manager.process_resident_text(call_id, texto)

    speech_callbacks = SpeechCallbacks(call_id, is_visitor=False, call_logger=call_logger)
    speech_callbacks.set_process_callback(process_recognized_text)
    speech_callbacks.register_callbacks(recognizer)

    recognizer.start_continuous_recognition_async()

    try:
        while True:
            header = await reader.readexactly(3)
            kind = header[0]
            length = int.from_bytes(header[1:3], "big")
            audio_chunk = await reader.readexactly(length)

            push_stream.write(audio_chunk)
    except asyncio.IncompleteReadError:
        logger.info(f"[{call_id}] Morador desconectado.")
    finally:
        recognizer.stop_continuous_recognition_async()

async def enviar_mensagens_morador(writer: asyncio.StreamWriter, call_id: str):
    call_logger = CallLoggerManager.get_logger(call_id)

    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada.")
        return

    while True:
        await asyncio.sleep(0.2)

        if session.terminate_resident_event.is_set():
            break

        msg = session_manager.get_message_for_resident(call_id)
        if msg:
            session.resident_state = "IA_TURN"
            call_logger.log_synthesis_start(msg, is_visitor=False)

            audio_resposta = await sintetizar_fala_async(msg)

            if audio_resposta:
                await enviar_audio(writer, audio_resposta, call_id=call_id, origem="Morador")
                session.resident_state = "USER_TURN"

async def enviar_audio(writer, dados_audio):
    chunk_size = 320
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i:i + chunk_size]
        header = struct.pack(">B H", 0x10, len(chunk))
        writer.write(header + chunk)
        await writer.drain()
        await asyncio.sleep(0.02)
