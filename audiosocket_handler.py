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
from speech_service import sintetizar_fala_async

SAMPLE_RATE = 8000
CHANNELS = 1
DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

logger = logging.getLogger(__name__)
session_manager = SessionManager()

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

async def enviar_audio(writer, dados_audio):
    chunk_size = 320
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i:i + chunk_size]
        header = struct.pack(">B H", 0x10, len(chunk))
        writer.write(header + chunk)
        await writer.drain()
        await asyncio.sleep(0.02)

async def iniciar_servidor_audiosocket_morador(reader, writer):
    logger.info("Conexão recebida do morador.")
    call_id = str(uuid.uuid4())
    session_manager.create_session(call_id)

    task1 = asyncio.create_task(receber_audio_morador(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_morador(writer, call_id))

    await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)

async def receber_audio_morador(reader, call_id):
    pass

async def enviar_mensagens_morador(writer, call_id):
    pass
