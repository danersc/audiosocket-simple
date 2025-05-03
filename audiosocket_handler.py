import asyncio
import logging
import azure.cognitiveservices.speech as speechsdk
from azure_speech_callbacks import SpeechCallbacks
import os
import wave
from session_manager import SessionManager  # <- importado aqui para usar após transcrição

SAMPLE_RATE = 8000
CHANNELS = 1
DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

# Podemos instanciar um SessionManager aqui como singleton/global.
# Se preferir criar em outro lugar, adapte.
session_manager = SessionManager()

async def read_tlv_packet(reader):
    header = await reader.readexactly(3)
    if len(header) < 3:
        return None, None

    packet_type = header[0]
    length = int.from_bytes(header[1:3], "big")

    payload = await reader.readexactly(length)
    if len(payload) < length:
        return None, None

    return packet_type, payload

async def iniciar_servidor_audiosocket_visitante(reader, writer):
    speech_config = speechsdk.SpeechConfig(
        subscription=os.getenv("AZURE_SPEECH_KEY"),
        region=os.getenv("AZURE_SPEECH_REGION")
    )
    speech_config.speech_recognition_language = "pt-BR"

    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=SAMPLE_RATE,
        bits_per_sample=16,
        channels=CHANNELS
    )
    push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

    recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)
    session_id = "visitante_test"  # Aqui pode vir de uma lógica dinâmica depois
    callbacks = SpeechCallbacks(call_id=session_id, session_manager=session_manager)
    callbacks.register_callbacks(recognizer)

    recognizer.start_continuous_recognition_async()

    audio_buffer = []

    try:
        while True:
            packet_type, payload = await read_tlv_packet(reader)
            if packet_type is None:
                break

            if packet_type == 0x10:  # Áudio PCM
                audio_buffer.append(payload)
                push_stream.write(payload)
                callbacks.add_audio_chunk(payload)

            elif packet_type == 0x01:  # UUID
                uuid = payload.hex()
                logger.info(f"UUID recebido: {uuid}")

            elif packet_type == 0x00:  # Término
                logger.info("Pacote de término recebido.")
                break

    except asyncio.IncompleteReadError:
        logger.warning("Conexão fechada abruptamente.")
    except Exception as e:
        logger.error(f"Erro ao receber dados: {e}")
    finally:
        push_stream.close()
        recognizer.stop_continuous_recognition_async()

        audio_data = b''.join(audio_buffer)
        filename = os.path.join(DEBUG_DIR, "audio_recebido_socket.wav")
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data)

        logger.info(f"Áudio salvo em {filename}")

async def iniciar_servidor_audiosocket_morador(reader, writer):
    logger.info("Conexão recebida do morador (ignorada nesta versão de teste).")
    writer.close()
    await writer.wait_closed()

def set_extension_manager(ext_manager):
    global extension_manager
    extension_manager = ext_manager
