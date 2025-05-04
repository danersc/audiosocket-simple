# audiosocket_handler.py (versão consolidada e simplificada)

import asyncio
import json
import logging
import struct
from enum import Enum

import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

from azure_speech_callbacks import SpeechCallbacks
import os
import time
import wave
import uuid
from session_manager import SessionManager
from extensions.resource_manager import resource_manager
from speech_service import sintetizar_fala_async, transcrever_audio_async
from utils.call_logger import CallLoggerManager

load_dotenv()

SAMPLE_RATE = 8000
CHANNELS = 1
DEBUG_DIR = "audio/debug"
TERMINATE_CHECK_INTERVAL = 1
os.makedirs(DEBUG_DIR, exist_ok=True)

class VoiceDetectionType(Enum):
    WEBRTCVAD = "webrtcvad"
    AZURE_SPEECH = "azure_speech"

logger = logging.getLogger(__name__)
session_manager = SessionManager()

# Variável global para armazenar o extension_manager
extension_manager = None

# ----------------------------------------------------------------------------
# Sistema de Turnos e Detecção de Voz
# ----------------------------------------------------------------------------
#
# Este sistema implementa um controle de turnos simples para evitar problemas
# de retroalimentação de áudio. O fluxo básico é:
#
# 1. Quando a IA vai falar (enviar_mensagens_):
#    - Define o estado como "IA_TURN"
#    - Limpa qualquer buffer de áudio pendente (reset_audio_detection)
#    - Sintetiza e envia o áudio
#    - Aguarda um pequeno delay após o áudio (POST_AUDIO_DELAY_SECONDS)
#    - Define o estado como "USER_TURN"
#
# 2. Quando o Azure Speech detecta voz (SpeechCallbacks):
#    - Verifica se é o turno do usuário (USER_TURN)
#    - Se for IA_TURN, ignora completamente o áudio
#    - Somente processa o áudio durante USER_TURN
#
# Este sistema evita que o Azure Speech reconheça o áudio da própria IA como
# fala do usuário, prevenindo loops de retroalimentação.
# ----------------------------------------------------------------------------

try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        SILENCE_THRESHOLD_SECONDS = config['system'].get('silence_threshold_seconds', 2.0)
        RESIDENT_MAX_SILENCE_SECONDS = config['system'].get('resident_max_silence_seconds', 45.0)
        TRANSMISSION_DELAY_MS = config['audio'].get('transmission_delay_ms', 20) / 1000  # Convertido para segundos
        POST_AUDIO_DELAY_SECONDS = config['audio'].get('post_audio_delay_seconds', 0.5)
        DISCARD_BUFFER_FRAMES = config['audio'].get('discard_buffer_frames', 25)
        GOODBYE_DELAY_SECONDS = config['system'].get('goodbye_delay_seconds',
                                                     3.0)  # Tempo para ouvir mensagem de despedida

        # Configuração de detecção de voz (webrtcvad ou azure_speech)
        VOICE_DETECTION_TYPE = VoiceDetectionType(config['system'].get('voice_detection_type', 'webrtcvad'))
        # Configurações específicas para Azure Speech
        AZURE_SPEECH_SEGMENT_TIMEOUT_MS = config['system'].get('azure_speech_segment_timeout_ms', 800)

        logger.info(
            f"Configurações carregadas: silence={SILENCE_THRESHOLD_SECONDS}s, resident_max_silence={RESIDENT_MAX_SILENCE_SECONDS}s, transmission_delay={TRANSMISSION_DELAY_MS}s, post_audio_delay={POST_AUDIO_DELAY_SECONDS}s, discard_buffer={DISCARD_BUFFER_FRAMES} frames, goodbye_delay={GOODBYE_DELAY_SECONDS}s, voice_detection={VOICE_DETECTION_TYPE.value}")
except Exception as e:
    logger.warning(f"Erro ao carregar config.json, usando valores padrão: {e}")
    SILENCE_THRESHOLD_SECONDS = 2.0
    RESIDENT_MAX_SILENCE_SECONDS = 45.0
    TRANSMISSION_DELAY_MS = 0.02
    POST_AUDIO_DELAY_SECONDS = 0.5
    DISCARD_BUFFER_FRAMES = 25
    GOODBYE_DELAY_SECONDS = 3.0
    VOICE_DETECTION_TYPE = VoiceDetectionType.WEBRTCVAD
    AZURE_SPEECH_SEGMENT_TIMEOUT_MS = 800

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

async def check_terminate_flag(session, call_id, role, call_logger=None):
    event = session.terminate_visitor_event if role == "visitante" else session.terminate_resident_event

    try:
        await asyncio.wait_for(event.wait(), timeout=TERMINATE_CHECK_INTERVAL)
        logger.info(f"[{call_id}] Sinal de terminação detectado para {role}")
        if call_logger:
            call_logger.log_event("TERMINATION_SIGNAL_DETECTED", {
                "role": role,
                "timestamp": time.time()
            })
        return True
    except asyncio.TimeoutError:
        return False

async def send_goodbye_and_terminate(writer, session, call_id, role, call_logger=None):
    """
    Envia uma mensagem de despedida final e encerra a conexão.
    """
    global config
    try:
        # Obter mensagem de despedida baseada na configuração
        # Decisão baseada no papel e no estado da conversa
        if role == "visitante":
            # Verificar se estamos no teste específico com a mensagem de finalização
            if session.intent_data.get("test_hangup") == True:
                goodbye_msg = "A chamada com o morador foi finalizada. Obrigado por utilizar nosso sistema."
            elif session.intent_data.get("authorization_result") == "authorized":
                goodbye_msg = config.get('call_termination', {}).get('goodbye_messages', {}).get('visitor', {}).get(
                    'authorized', "Sua entrada foi autorizada. Obrigado por utilizar nossa portaria inteligente.")
            elif session.intent_data.get("authorization_result") == "denied":
                goodbye_msg = config.get('call_termination', {}).get('goodbye_messages', {}).get('visitor', {}).get(
                    'denied', "Sua entrada não foi autorizada. Obrigado por utilizar nossa portaria inteligente.")
            else:
                goodbye_msg = config.get('call_termination', {}).get('goodbye_messages', {}).get('visitor', {}).get(
                    'default', "Obrigado por utilizar nossa portaria inteligente. Até a próxima!")
        else:
            goodbye_msg = config.get('call_termination', {}).get('goodbye_messages', {}).get('resident', {}).get(
                'default', "Obrigado pela sua resposta. Encerrando a chamada.")

        # Registrar evento de envio de despedida
        if call_logger:
            call_logger.log_event("SENDING_GOODBYE", {
                "role": role,
                "message": goodbye_msg
            })

        # Sintetizar a mensagem de despedida e enviar diretamente (sem enfileirar)
        logger.info(f"[{call_id}] Enviando mensagem de despedida diretamente para {role}: {goodbye_msg}")
        audio_resposta = await sintetizar_fala_async(goodbye_msg)

        if audio_resposta:
            # Enviar o áudio diretamente
            await enviar_audio(writer, audio_resposta, call_id=call_id, origem=role.capitalize())

            # Registrar evento de envio bem-sucedido
            if call_logger:
                call_logger.log_event("GOODBYE_SENT_SUCCESSFULLY", {
                    "role": role,
                    "message": goodbye_msg,
                    "audio_size": len(audio_resposta)
                })

            # Aguardar um tempo para que a mensagem seja ouvida
            logger.info(f"[{call_id}] Aguardando {GOODBYE_DELAY_SECONDS}s para o {role} ouvir a despedida")
            await asyncio.sleep(GOODBYE_DELAY_SECONDS)

            # Verificar se é o teste específico com a mensagem de finalização
            if role == "visitante" and session.intent_data.get("test_hangup") == True:
                # Enviar KIND_HANGUP explicitamente para finalizar a conexão
                logger.info(f"[{call_id}] Enviando KIND_HANGUP para finalizar a conexão ativamente")
                try:
                    # Enviar KIND_HANGUP (0x00) com payload length 0
                    writer.write(struct.pack('>B H', 0x00, 0))
                    await writer.drain()
                    if call_logger:
                        call_logger.log_event("HANGUP_SENT", {
                            "role": role,
                            "reason": "active_termination_test"
                        })
                except Exception as hangup_error:
                    logger.error(f"[{call_id}] Erro ao enviar KIND_HANGUP: {hangup_error}")
                    if call_logger:
                        call_logger.log_error("HANGUP_SEND_FAILED",
                                              f"Erro ao enviar KIND_HANGUP",
                                              {"error": str(hangup_error)})
        else:
            logger.error(f"[{call_id}] Falha ao sintetizar mensagem de despedida para {role}")
            if call_logger:
                call_logger.log_error("GOODBYE_SYNTHESIS_FAILED",
                                      f"Falha ao sintetizar mensagem de despedida para {role}",
                                      {"message": goodbye_msg})

        # Fechar a conexão
        if call_logger:
            call_logger.log_event("CONNECTION_CLOSING", {
                "role": role,
                "reason": "controlled_termination"
            })

        writer.close()
        await writer.wait_closed()
        await encerrar_conexao(call_id, role)
        logger.info(f"[{call_id}] Conexão com {role} encerrada com sucesso")

    except Exception as e:
        logger.error(f"[{call_id}] Erro ao enviar despedida para {role}: {e}")
        # Ainda assim, tentar fechar a conexão em caso de erro
        try:
            await encerrar_conexao(call_id, role)
        except:
            pass

async def iniciar_servidor_audiosocket_visitante(reader, writer):
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    call_id = str(uuid.UUID(bytes=call_id_bytes))

    session_manager.create_session(call_id)
    resource_manager.register_connection(call_id, "visitor", reader, writer)
    
    # Inicializar a sessão para o visitante
    session = session_manager.get_session(call_id)
    if session:
        # Definir estado inicial como IA_TURN para evitar captura de áudio durante boas-vindas
        session.visitor_state = "IA_TURN"
        logger.info(f"[{call_id}] [TURNO] Estado inicial definido como IA_TURN para evitar captura durante boas-vindas")

    # Preparar configuração do Azure Speech, mas não iniciar ainda
    speech_config = speechsdk.SpeechConfig(
        subscription=os.getenv("AZURE_SPEECH_KEY"),
        region=os.getenv("AZURE_SPEECH_REGION")
    )
    speech_config.speech_recognition_language = "pt-BR"

    audio_format = speechsdk.audio.AudioStreamFormat(samples_per_second=SAMPLE_RATE, bits_per_sample=16, channels=CHANNELS)
    push_stream = speechsdk.audio.PushAudioInputStream(audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

    recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)

    # Criar objeto SpeechCallbacks e configurar como visitante
    callbacks = SpeechCallbacks(call_id=call_id, session_manager=session_manager, is_visitor=True)
    callbacks.register_callbacks(recognizer)
    
    # Armazenar referência ao objeto callbacks na sessão
    if session:
        session.speech_callbacks = callbacks
    
    # IMPORTANTE: Não iniciar o reconhecimento ainda
    # Vamos primeiro enviar a mensagem de boas-vindas
    
    audio_buffer = []
    
    # Enviar mensagem de boas-vindas diretamente (sem reconhecimento ativo)
    welcome_message = "Olá, seja bem-vindo! Por favor, informe o que deseja: se entrega ou visita."
    logger.info(f"[{call_id}] Enviando mensagem de boas-vindas antes de iniciar reconhecimento")
    
    welcome_audio = await sintetizar_fala_async(welcome_message)
    if welcome_audio:
        await enviar_audio(writer, welcome_audio, call_id=call_id, origem="Visitante-Boas-Vindas")
        
        # Aguardar um delay adicional após a mensagem de boas-vindas
        delay_after_welcome = GOODBYE_DELAY_SECONDS  # Usar o mesmo delay da despedida
        logger.info(f"[{call_id}] Aguardando {delay_after_welcome}s após boas-vindas para iniciar reconhecimento")
        await asyncio.sleep(delay_after_welcome)
    
    # Agora sim, iniciar tarefas de reconhecimento e mudamos para USER_TURN
    if session:
        session.visitor_state = "USER_TURN"
        logger.info(f"[{call_id}] Alterando estado para USER_TURN e iniciando reconhecimento")
    
    # Iniciar o reconhecimento só agora, após a mensagem de boas-vindas
    recognizer.start_continuous_recognition_async()
    
    # Iniciar tarefas de processamento
    task1 = asyncio.create_task(receber_audio_visitante(reader, call_id, push_stream, callbacks, audio_buffer))
    task2 = asyncio.create_task(enviar_mensagens_visitante(writer, call_id))

    session = session_manager.get_session(call_id)

    while True:
        if await check_terminate_flag(session, call_id, "visitante", call_logger=CallLoggerManager.get_logger(call_id)):
            logger.info(f"[{call_id}] Encerrando sessão do visitante.")
            await send_goodbye_and_terminate(writer, session, call_id, "visitante", call_logger=CallLoggerManager.get_logger(call_id))
            break
        done, pending = await asyncio.wait([task1, task2], timeout=TERMINATE_CHECK_INTERVAL,
                                           return_when=asyncio.FIRST_COMPLETED)

        if done:
            logger.info(f"[{call_id}] Uma das tarefas do visitante foi encerrada.")
            break
    
    # Cancelar quaisquer tarefas pendentes
    for task in [t for t in [task1, task2] if not t.done()]:
        task.cancel()

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
        await encerrar_conexao(call_id, "morador")
        logger.warning("Conexão fechada abruptamente.")
    except Exception as e:
        logger.error(f"Erro ao receber dados: {e}")

async def enviar_mensagens_visitante(writer, call_id):
    session = session_manager.get_session(call_id)
    call_logger = CallLoggerManager.get_logger(call_id)
    speech_callbacks = getattr(session, 'speech_callbacks', None)
    
    while True:
        if session and session.terminate_visitor_event.is_set():
            break
            
        msg = session_manager.get_message_for_visitor(call_id)
        if msg:
            # Definir o estado como IA_TURN antes de começar a falar
            if session:
                logger.info(f"[{call_id}] [TURNO] Alterando estado para IA_TURN antes de sintetizar fala (msg: {msg[:30]}...)")
                session.visitor_state = "IA_TURN"
                
                # Resetar a detecção de áudio para evitar eco
                if speech_callbacks:
                    speech_callbacks.reset_audio_detection()
                else:
                    logger.warning(f"[{call_id}] [TURNO] Speech callbacks não encontrado para reset!")
            else:
                logger.warning(f"[{call_id}] [TURNO] Sessão não encontrada para definir estado!")
            
            if call_logger:
                call_logger.log_synthesis_start(msg, is_visitor=True)
                
            logger.info(f"[{call_id}] [TURNO] Sintetizando áudio durante IA_TURN")
            audio_resposta = await sintetizar_fala_async(msg)
            
            if audio_resposta:
                logger.info(f"[{call_id}] [TURNO] Enviando áudio durante IA_TURN ({len(audio_resposta)} bytes)")
                await enviar_audio(writer, audio_resposta, call_id=call_id, origem="Visitante")
                
                # Aguardar um pequeno delay após enviar o áudio para evitar capturar o próprio áudio
                logger.info(f"[{call_id}] [TURNO] Aguardando {POST_AUDIO_DELAY_SECONDS}s após enviar áudio")
                await asyncio.sleep(POST_AUDIO_DELAY_SECONDS)
                
                # Mudar para USER_TURN após terminar de falar
                if session:
                    logger.info(f"[{call_id}] [TURNO] Alterando estado para USER_TURN após enviar áudio")
                    session.visitor_state = "USER_TURN"
                else:
                    logger.warning(f"[{call_id}] [TURNO] Sessão não encontrada para definir estado USER_TURN!")
        
        await asyncio.sleep(0.2)

async def iniciar_servidor_audiosocket_morador(reader, writer):
    logger.info("Conexão recebida do morador.")

    # Aqui você DEVE receber o call_id do Asterisk
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    call_id = str(uuid.UUID(bytes=call_id_bytes))

    session = session_manager.get_session(call_id)
    if not session:
        session = session_manager.create_session(call_id)

    # CRÍTICO: Definir fluxo se não existir
    from conversation_flow import ConversationFlow
    if not hasattr(session, "flow") or session.flow is None:
        session.flow = ConversationFlow(extension_manager=extension_manager)

    resource_manager.register_connection(call_id, "resident", reader, writer)

    # Processar evento especial que indica que o morador atendeu
    session_manager.process_resident_text(call_id, "AUDIO_CONNECTION_ESTABLISHED")

    task1 = asyncio.create_task(receber_audio_morador(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_morador(writer, call_id))

    while True:
        if await check_terminate_flag(session, call_id, "morador", call_logger=CallLoggerManager.get_logger(call_id)):
            logger.info(f"[{call_id}] Encerrando sessão do morador.")
            await send_goodbye_and_terminate(writer, session, call_id, "morador", call_logger=CallLoggerManager.get_logger(call_id))
            break

        done, pending = await asyncio.wait([task1, task2], timeout=TERMINATE_CHECK_INTERVAL,
                                           return_when=asyncio.FIRST_COMPLETED)

        if done:
            logger.info(f"[{call_id}] Uma das tarefas do morador foi encerrada.")
            break

    # Cancelar quaisquer tarefas pendentes
    for task in [t for t in [task1, task2] if not t.done()]:
        task.cancel()

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
        if not audio_data or len(audio_data) < 2000:
            logger.warning(f"[{call_id}] Áudio do morador muito curto ({len(audio_data)} bytes), ignorando")
            return

        session = session_manager.get_session(call_id)
        session.resident_state = "WAITING"
        call_logger.log_transcription_start(len(audio_data), is_visitor=False)

        logger.info(f"[{call_id}] Texto reconhecido do morador: '{text}'")

        if text and text.strip():
            call_logger.log_transcription_complete(text, 0, is_visitor=False)
            session_manager.process_resident_text(call_id, text)
        else:
            texto = await transcrever_audio_async(audio_data, call_id=call_id)
            if texto:
                call_logger.log_transcription_complete(texto, 0, is_visitor=False)
                session_manager.process_resident_text(call_id, texto)

    speech_callbacks = SpeechCallbacks(call_id, session_manager=session_manager, is_visitor=False, call_logger=call_logger)
    speech_callbacks.set_process_callback(process_recognized_text)
    speech_callbacks.register_callbacks(recognizer)
    
    # Armazenar referência ao objeto callbacks na sessão para controle de estado
    session = session_manager.get_session(call_id)
    if session:
        session.speech_callbacks = speech_callbacks
        
        # Morador já tem primeira mensagem reproduzida pelo sistema antes
        # Definir estado inicial como USER_TURN para permitir que o morador fale
        session.resident_state = "USER_TURN"
        logger.info(f"[{call_id}] Estado do morador definido como USER_TURN para iniciar escuta")

    # Para o morador, já iniciamos o reconhecimento de voz 
    # A mensagem inicial do morador é enviada separadamente
    recognizer.start_continuous_recognition_async()
    logger.info(f"[{call_id}] Reconhecimento de voz do morador iniciado")

    try:
        while True:
            header = await reader.readexactly(3)
            kind = header[0]
            length = int.from_bytes(header[1:3], "big")
            audio_chunk = await reader.readexactly(length)
            session = session_manager.get_session(call_id)
            if session and session.resident_state != "USER_TURN":
                logger.debug(f"[{call_id}] Ignorando áudio: estado atual é {session.resident_state}")
                continue  # Não processar o áudio
            push_stream.write(audio_chunk)
    except asyncio.IncompleteReadError:
        await encerrar_conexao(call_id, "morador")
        logger.info(f"[{call_id}] Morador desconectado.")
    finally:
        recognizer.stop_continuous_recognition_async()

async def enviar_mensagens_morador(writer: asyncio.StreamWriter, call_id: str):
    call_logger = CallLoggerManager.get_logger(call_id)

    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada.")
        return
        
    speech_callbacks = getattr(session, 'speech_callbacks', None)

    while True:
        await asyncio.sleep(0.2)

        if session.terminate_resident_event.is_set():
            break

        msg = session_manager.get_message_for_resident(call_id)
        if msg:
            # Definir o estado como IA_TURN antes de começar a falar
            logger.info(f"[{call_id}] [TURNO] Morador: Alterando estado para IA_TURN antes de sintetizar fala (msg: {msg[:30]}...)")
            session.resident_state = "IA_TURN"
            
            # Resetar a detecção de áudio para evitar eco
            if speech_callbacks:
                speech_callbacks.reset_audio_detection()
            else:
                logger.warning(f"[{call_id}] [TURNO] Morador: Speech callbacks não encontrado para reset!")
                
            call_logger.log_synthesis_start(msg, is_visitor=False)

            logger.info(f"[{call_id}] [TURNO] Morador: Sintetizando áudio durante IA_TURN")
            audio_resposta = await sintetizar_fala_async(msg)

            if audio_resposta:
                logger.info(f"[{call_id}] [TURNO] Morador: Enviando áudio durante IA_TURN ({len(audio_resposta)} bytes)")
                await enviar_audio(writer, audio_resposta, call_id=call_id, origem="Morador")
                
                # Aguardar um pequeno delay após enviar o áudio para evitar capturar o próprio áudio
                logger.info(f"[{call_id}] [TURNO] Morador: Aguardando {POST_AUDIO_DELAY_SECONDS}s após enviar áudio")
                await asyncio.sleep(POST_AUDIO_DELAY_SECONDS)
                
                # Mudar para USER_TURN após terminar de falar
                logger.info(f"[{call_id}] [TURNO] Morador: Alterando estado para USER_TURN após enviar áudio")
                session.resident_state = "USER_TURN"

async def enviar_audio(writer, dados_audio, call_id=None, origem=None):
    """
    Envia dados de áudio para o cliente AudioSocket.
    
    Args:
        writer: StreamWriter para enviar os dados
        dados_audio: Bytes contendo os dados de áudio
        call_id: ID opcional da chamada para logs
        origem: String opcional indicando a origem (Visitante/Morador) para logs
    """
    chunk_size = 320
    log_prefix = f"[{call_id}]" if call_id else ""
    
    if origem and call_id:
        logger.debug(f"{log_prefix} Enviando áudio de {origem} ({len(dados_audio)} bytes)")
        
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i:i + chunk_size]
        header = struct.pack(">B H", 0x10, len(chunk))
        writer.write(header + chunk)
        await writer.drain()
        await asyncio.sleep(TRANSMISSION_DELAY_MS)  # Usar o valor configurado

async def encerrar_conexao(call_id: str, role: str):
    """
    Encerra a conexão do visitante ou morador de forma segura e controlada.
    Envia o byte de HANGUP (0x00) e fecha a conexão.
    """
    try:
        session = session_manager.get_session(call_id)
        if not session:
            logger.warning(f"[{call_id}] Sessão não encontrada para encerrar conexão do {role}")
            return

        conn = resource_manager.get_active_connection(call_id, role)
        if not conn or 'writer' not in conn:
            logger.warning(f"[{call_id}] Writer do {role} não encontrado ou já encerrado")
        else:
            writer = conn['writer']
            try:
                logger.info(f"[{call_id}] Enviando byte de HANGUP (0x00) para {role}")
                writer.write(struct.pack('>B H', 0x00, 0))
                await writer.drain()
            except ConnectionResetError:
                logger.info(f"[{call_id}] Conexão já estava encerrada ao tentar enviar HANGUP para {role}")
            except Exception as e:
                logger.warning(f"[{call_id}] Erro ao enviar HANGUP para {role}: {e}")

            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
                logger.info(f"[{call_id}] Conexão do {role} encerrada com sucesso")
            except Exception as e:
                logger.warning(f"[{call_id}] Erro ao fechar writer do {role}: {e}")

        # Marcar evento de encerramento
        if role == "visitante":
            session.terminate_visitor_event.set()
        elif role == "morador":
            session.terminate_resident_event.set()

        # Se ambos encerraram, removemos a sessão por completo
        if session.terminate_visitor_event.is_set() and session.terminate_resident_event.is_set():
            logger.info(f"[{call_id}] Ambos encerraram, finalizando sessão completa")
            session_manager.end_session(call_id)
            session_manager._complete_session_termination(call_id)

        # Remover do resource manager
        resource_manager.unregister_connection(call_id, role)

    except Exception as e:
        logger.error(f"[{call_id}] Erro ao encerrar conexão de {role}: {e}", exc_info=True)
