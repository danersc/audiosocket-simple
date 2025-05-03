import asyncio
import logging
import socket
import azure.cognitiveservices.speech as speechsdk
from azure_speech_callbacks import SpeechCallbacks
import os

SAMPLE_RATE = 8000
CHANNELS = 1
CHUNK_SIZE = 320

logger = logging.getLogger(__name__)


async def iniciar_servidor_audiosocket_visitante(reader, writer):
    speech_config = speechsdk.SpeechConfig(subscription=os.getenv("AZURE_SPEECH_KEY"),
                                           region=os.getenv("AZURE_SPEECH_REGION"))
    speech_config.speech_recognition_language = "pt-BR"

    audio_format = speechsdk.audio.AudioStreamFormat(samples_per_second=SAMPLE_RATE,
                                                     bits_per_sample=16,
                                                     channels=CHANNELS)
    push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

    recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)
    callbacks = SpeechCallbacks(call_id="visitante_test")
    callbacks.register_callbacks(recognizer)

    recognizer.start_continuous_recognition_async()

    try:
        while True:
            data = await reader.read(CHUNK_SIZE)
            if not data:
                break
            push_stream.write(data)

    except Exception as e:
        logger.error(f"Erro ao receber dados: {e}")
    finally:
        push_stream.close()
        recognizer.stop_continuous_recognition_async()


async def iniciar_servidor_audiosocket_morador(reader, writer):
    print("Conexão recebida do morador (ignorada nesta versão de teste).")
    writer.close()
    await writer.wait_closed()


def set_extension_manager(ext_manager):
    global extension_manager
    extension_manager = ext_manager
