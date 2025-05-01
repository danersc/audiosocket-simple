# audiosocket_handler.py

import asyncio
import logging
import struct
import os
import time
import json
import socket
from typing import Optional
from enum import Enum

import webrtcvad
import azure.cognitiveservices.speech as speechsdk

# Importar nossa classe de callbacks para Azure Speech
from azure_speech_callbacks import SpeechCallbacks

from speech_service import transcrever_audio_async, sintetizar_fala_async
from session_manager import SessionManager  # Importamos o SessionManager
from utils.call_logger import CallLoggerManager  # Importamos o CallLoggerManager
from extensions.resource_manager import resource_manager  # Importamos o ResourceManager

# Constante para o timeout de verificação de terminação
TERMINATE_CHECK_INTERVAL = 0.5  # segundos

# Enum para os tipos de detecção de voz
class VoiceDetectionType(Enum):
    WEBRTCVAD = "webrtcvad"
    AZURE_SPEECH = "azure_speech"

logger = logging.getLogger(__name__)

# Identificador do formato SLIN
KIND_SLIN = 0x10

# Podemos instanciar um SessionManager aqui como singleton/global.
# Se preferir criar em outro lugar, adapte.
session_manager = SessionManager()

# Variável global para armazenar o extension_manager
extension_manager = None

def set_extension_manager(manager):
    """
    Define o extension_manager global para ser usado pelo handler.
    """
    global extension_manager
    extension_manager = manager

# Carregar configurações do config.json
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
        SILENCE_THRESHOLD_SECONDS = config['system'].get('silence_threshold_seconds', 2.0)
        RESIDENT_MAX_SILENCE_SECONDS = config['system'].get('resident_max_silence_seconds', 45.0)
        TRANSMISSION_DELAY_MS = config['audio'].get('transmission_delay_ms', 20) / 1000  # Convertido para segundos
        POST_AUDIO_DELAY_SECONDS = config['audio'].get('post_audio_delay_seconds', 0.5)
        DISCARD_BUFFER_FRAMES = config['audio'].get('discard_buffer_frames', 25)
        GOODBYE_DELAY_SECONDS = config['system'].get('goodbye_delay_seconds', 3.0)  # Tempo para ouvir mensagem de despedida
        
        # Configuração de detecção de voz (webrtcvad ou azure_speech)
        VOICE_DETECTION_TYPE = VoiceDetectionType(config['system'].get('voice_detection_type', 'webrtcvad'))
        # Configurações específicas para Azure Speech
        AZURE_SPEECH_SEGMENT_TIMEOUT_MS = config['system'].get('azure_speech_segment_timeout_ms', 800)
        
        logger.info(f"Configurações carregadas: silence={SILENCE_THRESHOLD_SECONDS}s, resident_max_silence={RESIDENT_MAX_SILENCE_SECONDS}s, transmission_delay={TRANSMISSION_DELAY_MS}s, post_audio_delay={POST_AUDIO_DELAY_SECONDS}s, discard_buffer={DISCARD_BUFFER_FRAMES} frames, goodbye_delay={GOODBYE_DELAY_SECONDS}s, voice_detection={VOICE_DETECTION_TYPE.value}")
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


# Função auxiliar para obter a porta local de uma conexão
def get_local_port(writer) -> Optional[int]:
    """
    Obtém a porta local de uma conexão.
    """
    try:
        sock = writer.get_extra_info('socket')
        if sock:
            _, port = sock.getsockname()
            return port
    except:
        pass
    return None


async def check_terminate_flag(session, call_id, role, call_logger=None):
    """
    Tarefa auxiliar que monitora periodicamente se uma sessão deve ser encerrada.
    Retorna True se a terminação foi solicitada.
    """
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
        # Timeout normal, continua verificando
        return False


async def _encerrar_apos_delay(call_id, session_manager, delay_seconds=5.0):
    """
    Função auxiliar para encerrar a sessão após um delay, permitindo que
    as mensagens enfileiradas sejam processadas e enviadas.
    """
    logger.info(f"[{call_id}] Agendando encerramento de sessão após {delay_seconds} segundos")
    await asyncio.sleep(delay_seconds)
    logger.info(f"[{call_id}] Delay concluído, iniciando encerramento da sessão")
    
    # Verificar se a sessão ainda existe antes de tentar encerrá-la
    if session_manager.get_session(call_id):
        logger.info(f"[{call_id}] Sinalizando encerramento via end_session após delay de {delay_seconds}s")
        session_manager.end_session(call_id)
        
        # Aguarda mais um momento para garantir que as tasks de envio de mensagens
        # tiveram chance de processar o evento de encerramento
        await asyncio.sleep(3.0)  # Tempo mais longo para garantir processamento
        
        # Verificar se a sessão ainda existe após o encerramento inicial
        if session_manager.get_session(call_id):
            logger.warning(f"[{call_id}] Sessão ainda existe após tempo adicional, força bruta para remoção")
            # Remove diretamente a sessão como último recurso
            session_manager._complete_session_termination(call_id)
            
            # Loga para confirmar que a sessão foi encerrada
            if not session_manager.get_session(call_id):
                logger.info(f"[{call_id}] Sessão removida com sucesso após tentativa de força bruta")
            else:
                logger.error(f"[{call_id}] FALHA na remoção completa da sessão mesmo após tentativa de força bruta!")
    else:
        logger.info(f"[{call_id}] Sessão já foi encerrada naturalmente, nenhuma ação necessária")


async def send_goodbye_and_terminate(writer, session, call_id, role, call_logger=None):
    """
    Envia uma mensagem de despedida final e encerra a conexão.
    """
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
        logger.info(f"[{call_id}] Conexão com {role} encerrada com sucesso")
        
    except Exception as e:
        logger.error(f"[{call_id}] Erro ao enviar despedida para {role}: {e}")
        # Ainda assim, tentar fechar a conexão em caso de erro
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass


async def enviar_audio(writer: asyncio.StreamWriter, dados_audio: bytes, call_id: str = None, origem="desconhecida"):
    """
    Envia dados de áudio (SLIN) ao cliente via 'writer'.
    """
    logger.info(f"[{origem}] Enviando áudio de {len(dados_audio)} bytes.")
    
    # Registrar no log específico da chamada
    if call_id:
        is_visitor = (origem == "Visitante")
        call_logger = CallLoggerManager.get_logger(call_id)
        call_logger.log_event("AUDIO_SEND_START", {
            "target": "visitor" if is_visitor else "resident",
            "audio_size_bytes": len(dados_audio)
        })
        
        # Registrar sessão no ResourceManager se ainda não estiver registrada
        if call_id not in resource_manager.active_sessions:
            porta = get_local_port(writer)
            resource_manager.register_session(call_id, porta)
    
    start_time = time.time()
    chunk_size = 320
    
    # Verificar se precisamos aplicar throttling baseado na carga do sistema
    should_throttle = resource_manager.should_throttle_audio()
    transmission_delay = TRANSMISSION_DELAY_MS * 1.5 if should_throttle else TRANSMISSION_DELAY_MS
    
    if should_throttle:
        logger.warning(f"[{call_id}] Aplicando throttling na transmissão de áudio devido à alta carga do sistema")
    
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i : i + chunk_size]
        header = struct.pack(">B H", KIND_SLIN, len(chunk))
        writer.write(header + chunk)
        await writer.drain()
        # Pequeno atraso para não encher o buffer do lado do Asterisk
        # Se sistema estiver sobrecarregado, aumentamos o delay
        await asyncio.sleep(transmission_delay)
    
    # Registrar conclusão
    if call_id:
        duration_ms = (time.time() - start_time) * 1000
        call_logger.log_event("AUDIO_SEND_COMPLETE", {
            "target": "visitor" if is_visitor else "resident",
            "duration_ms": round(duration_ms, 2)
        })


async def receber_audio_visitante(reader: asyncio.StreamReader, call_id: str):
    """
    Função que redireciona para a implementação apropriada com base na configuração.
    """
    # Escolher a implementação com base na configuração
    if VOICE_DETECTION_TYPE == VoiceDetectionType.WEBRTCVAD:
        return await receber_audio_visitante_vad(reader, call_id)
    elif VOICE_DETECTION_TYPE == VoiceDetectionType.AZURE_SPEECH:
        return await receber_audio_visitante_azure_speech(reader, call_id)
    else:
        # Fallback para webrtcvad se o tipo não for reconhecido
        logger.warning(f"[{call_id}] Tipo de detecção de voz '{VOICE_DETECTION_TYPE}' não reconhecido, usando webrtcvad")
        return await receber_audio_visitante_vad(reader, call_id)

async def receber_audio_visitante_vad(reader: asyncio.StreamReader, call_id: str):
    """
    Implementação usando webrtcvad para detecção de voz e silêncio.
    
    Tarefa que fica lendo o áudio do visitante, detecta quando ele fala (usando VAD)
    e chama `session_manager.process_visitor_text(...)` ao fim de cada frase.
    
    Agora com controle de estado para evitar retroalimentação durante a fala da IA
    e suporte para encerramento gracioso da conexão.
    """
    call_logger = CallLoggerManager.get_logger(call_id)
    vad = webrtcvad.Vad(2)  # Agressivo 0-3
    frames = []
    is_speaking = False
    silence_start = None
    speech_start = None
    
    # Para controlar se estamos no modo de escuta ativa
    is_listening_mode = True
    
    # Acessar a sessão para verificar o estado
    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada para iniciar recebimento de áudio")
        return
    
    # Flag de buffer para descartar áudio residual após IA falar
    discard_buffer_frames = 0
    
    while True:
        # Verificar sinal de terminação
        if session.terminate_visitor_event.is_set():
            logger.info(f"[{call_id}] Detectado sinal para encerrar recebimento de áudio do visitante")
            call_logger.log_event("TERMINATE_VISITOR_AUDIO", {
                "reason": "session_terminated",
                "timestamp": time.time()
            })
            break
        
        try:
            # Uso de wait_for com timeout para permitir verificação de terminação
            header = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
        except asyncio.TimeoutError:
            # Timeout apenas para verificação de terminação, continuamos normalmente
            continue
        except asyncio.IncompleteReadError:
            logger.info(f"[{call_id}] Visitante desconectou (EOF).")
            call_logger.log_call_ended("visitor_disconnected")
            break

        if not header:
            logger.info(f"[{call_id}] Nenhum dado de header, encerrando.")
            call_logger.log_call_ended("invalid_header")
            break

        kind = header[0]
        length = int.from_bytes(header[1:3], "big")

        audio_chunk = await reader.readexactly(length)
        
        # Verificar o estado atual da sessão
        current_state = session.visitor_state
        
        # Se estamos em IA_TURN, significa que a IA está falando - não devemos processar VAD
        if current_state == "IA_TURN":
            is_listening_mode = False
            continue  # Pula processamento durante fala da IA
            
        # Período de transição: após IA falar, descartamos alguns frames para evitar eco
        if discard_buffer_frames > 0:
            discard_buffer_frames -= 1
            continue
            
        # Se acabamos de transitar de IA_TURN para USER_TURN, ativamos modo de escuta e descartamos frames iniciais
        if not is_listening_mode and current_state == "USER_TURN":
            is_listening_mode = True
            discard_buffer_frames = DISCARD_BUFFER_FRAMES  # Descartar quadros para evitar eco
            logger.debug(f"[{call_id}] Ativando modo de escuta de visitante")
            call_logger.log_event("LISTENING_MODE_ACTIVATED", {"timestamp": time.time()})
            
            # Limpar quaisquer frames acumulados anteriormente
            frames = []
            is_speaking = False
            silence_start = None
            speech_start = None
            continue

        # Processamos VAD apenas quando estamos em modo de escuta
        if is_listening_mode and kind == KIND_SLIN and (len(audio_chunk) == 320 or len(audio_chunk) == 640):
            # Se o chunk for de 640 bytes (320 amostras de 16 bits), precisamos garantir que seja processado corretamente
            chunk_to_process = audio_chunk
            if len(audio_chunk) == 640:
                # O WebRTCVAD espera PCM de 16 bits em 320 bytes, então estamos recebendo o dobro do tamanho esperado
                logger.debug(f"[{call_id}] Recebido chunk de 640 bytes do cliente - formato PCM 16-bit")
                
            # Avalia VAD
            is_voice = vad.is_speech(chunk_to_process, 8000)
            if is_voice:
                frames.append(audio_chunk)
                if not is_speaking:
                    is_speaking = True
                    speech_start = asyncio.get_event_loop().time()
                    logger.debug(f"[{call_id}] Visitante começou a falar.")
                    call_logger.log_speech_detected(is_visitor=True)
                silence_start = None
            else:
                if is_speaking:
                    # Já estava falando e agora está em silêncio
                    if silence_start is None:
                        silence_start = asyncio.get_event_loop().time()
                    else:
                        # Se passou 2s em silêncio, considera que a fala terminou
                        silence_duration = asyncio.get_event_loop().time() - silence_start
                        if silence_duration > SILENCE_THRESHOLD_SECONDS:
                            is_speaking = False
                            
                            # Se não temos frames suficientes (< 1s), provavelmente é ruído
                            if len(frames) < 50:  # ~1 segundo de áudio (50 frames de 20ms)
                                logger.debug(f"[{call_id}] Descartando fala curta demais ({len(frames)} frames)")
                                frames = []
                                continue
                            
                            # Calcular duração total da fala
                            speech_duration = (asyncio.get_event_loop().time() - speech_start) * 1000
                            logger.debug(f"[{call_id}] Visitante parou de falar após {speech_duration:.0f}ms.")
                            call_logger.log_speech_ended(speech_duration, is_visitor=True)
                            call_logger.log_silence_detected(silence_duration * 1000, is_visitor=True)
                            
                            audio_data = b"".join(frames)
                            frames.clear()

                            # Desativar escuta durante processamento para evitar retroalimentação
                            is_listening_mode = False
                            
                            # Log antes da transcrição
                            call_logger.log_transcription_start(len(audio_data), is_visitor=True)
                            
                            # Mudar estado para WAITING durante processamento
                            session.visitor_state = "WAITING"
                            
                            # Transcrever com medição de tempo e monitoramento de recursos
                            start_time = time.time()
                            texto = await transcrever_audio_async(audio_data, call_id=call_id)
                            transcription_time = (time.time() - start_time) * 1000
                            
                            if texto:
                                call_logger.log_transcription_complete(texto, transcription_time, is_visitor=True)
                                
                                # Medição do tempo de processamento da IA
                                start_time = time.time()
                                session_manager.process_visitor_text(call_id, texto)
                                ai_processing_time = (time.time() - start_time) * 1000
                                
                                call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                                    "text": texto,
                                    "processing_time_ms": round(ai_processing_time, 2)
                                })
                                
                                # Agora, mesmo que o estado tenha mudado para IA_TURN durante o processamento,
                                # vamos respeitar isso (is_listening_mode já está False)
                            else:
                                call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                    "Falha ao transcrever áudio do visitante", 
                                                    {"audio_size": len(audio_data)})
                                # Voltar ao modo de escuta, já que não conseguimos processar o áudio
                                is_listening_mode = True
        elif kind != KIND_SLIN or (len(audio_chunk) != 320 and len(audio_chunk) != 640):
            logger.warning(f"[{call_id}] Chunk inválido do visitante. kind={kind}, len={len(audio_chunk)}")
            call_logger.log_error("INVALID_CHUNK", 
                                "Chunk de áudio inválido recebido do visitante", 
                                {"kind": kind, "length": len(audio_chunk)})

    # Ao sair, encerrou a conexão
    logger.info(f"[{call_id}] receber_audio_visitante_vad terminou.")

async def receber_audio_visitante_azure_speech(reader: asyncio.StreamReader, call_id: str):
    """
    Implementação usando Azure Speech SDK para detecção de voz e silêncio.
    
    Esta implementação usa o Azure Speech SDK para detectar início e fim da fala
    com melhor resistência a ruídos de fundo.
    """
    call_logger = CallLoggerManager.get_logger(call_id)
    
    # Para controlar se estamos no modo de escuta ativa
    is_listening_mode = True
    
    # Acessar a sessão para verificar o estado
    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada para iniciar recebimento de áudio")
        return
    
    # Flag de buffer para descartar áudio residual após IA falar
    discard_buffer_frames = 0
    
    # Verificar se as variáveis de ambiente necessárias estão definidas
    azure_key = os.getenv('AZURE_SPEECH_KEY')
    azure_region = os.getenv('AZURE_SPEECH_REGION')
    
    if not azure_key or not azure_region:
        logger.error(f"[{call_id}] Variáveis de ambiente AZURE_SPEECH_KEY e/ou AZURE_SPEECH_REGION não configuradas!")
        logger.error(f"[{call_id}] AZURE_SPEECH_KEY: {azure_key and 'Configurada' or 'NÃO CONFIGURADA!'}")
        logger.error(f"[{call_id}] AZURE_SPEECH_REGION: {azure_region and 'Configurada' or 'NÃO CONFIGURADA!'}")
    
    # Configurações do Azure Speech SDK
    speech_config = speechsdk.SpeechConfig(
        subscription=azure_key,
        region=azure_region or "eastus"  # Valor de fallback se não estiver configurado
    )
    speech_config.speech_recognition_language = 'pt-BR'
    
    # Log para debug
    logger.info(f"[{call_id}] Configuração Azure Speech: Language=pt-BR, Subscription={azure_key and '****' + azure_key[-4:] or 'NÃO CONFIGURADA'}, Region={azure_region or 'NÃO CONFIGURADA'}")
    
    # Configurações importantes para o reconhecimento de fala
    # Ajuste o timeout de silêncio para segmentação - valor vem da configuração
    speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, 
                              str(AZURE_SPEECH_SEGMENT_TIMEOUT_MS))
    
    # Configurações adicionais para melhorar o reconhecimento - valores mais agressivos
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "8000")   # 8 segundos para timeout inicial
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "500")       # 0.5 segundos de silêncio para encerrar
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText")   # Melhor reconhecimento de texto
    
    # Configurações para qualidade e reconhecimento melhorados
    speech_config.enable_audio_logging()                                                # Habilita logging de áudio no Azure
    speech_config.enable_dictation()                                                    # Habilita modo ditado (melhor para frases curtas)
    speech_config.set_profanity(speechsdk.ProfanityOption.Raw)                          # Não filtra palavrões
    
    # Removendo propriedades não suportadas que causam erro
    # speech_config.set_property("AdaptationInitialSilenceTimeoutMs", "1000")          
    # speech_config.set_property("AdaptationEndSilenceTimeoutMs", "300")
    
    # Criar o stream de áudio para alimentar o reconhecedor
    # Usar formato específico para áudio - SLIN é raw PCM 16-bit a 8kHz
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=speechsdk.audio.AudioStreamFormat(samples_per_second=8000, 
                                                                                                    bits_per_sample=16,
                                                                                                    channels=1))
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    
    # Criar o reconhecedor
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    # Flag para controlar loop de reconhecimento
    recognizer_running = False
    recognition_started = False
    last_audio_time = time.time()
    
    # Contadores para controle periódico
    silence_check_counter = 0
    frame_counter = 0
    
    # Função para processar texto reconhecido
    async def process_recognized_text(text, audio_data):
        nonlocal is_listening_mode
        
        # Verificações de segurança para os dados de áudio
        if not audio_data or len(audio_data) == 0:
            logger.warning(f"[{call_id}] Recebido process_recognized_text com audio_data vazio - ignorando")
            return
        
        # Desativar escuta durante processamento para evitar retroalimentação
        is_listening_mode = False
        
        # Mudar estado para WAITING durante processamento
        session.visitor_state = "WAITING"
        
        # Log antes da transcrição
        audio_size = len(audio_data)
        call_logger.log_transcription_start(audio_size, is_visitor=True)
        logger.info(f"[{call_id}] Iniciando transcrição/processamento de {audio_size} bytes de áudio")
        
        # Se o Azure Speech já transcreveu, usamos esse texto
        if text and text.strip():
            logger.info(f"[{call_id}] Usando texto já reconhecido pelo Azure: '{text}'")
            call_logger.log_transcription_complete(text, 0, is_visitor=True)
            
            # Medição do tempo de processamento da IA
            start_time = time.time()
            session_manager.process_visitor_text(call_id, text)
            ai_processing_time = (time.time() - start_time) * 1000
            
            call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                "text": text,
                "processing_time_ms": round(ai_processing_time, 2)
            })
        else:
            # Caso o Azure Speech não tenha retornado texto, tentamos transcrever normalmente
            # Isso pode acontecer para falas muito curtas ou quando o evento foi forçado
            
            # Verificar se o áudio é muito curto - poderia ser um "sim" rápido
            is_short_audio = audio_size < 8000  # ~0.5 segundo de áudio
            if is_short_audio:
                logger.info(f"[{call_id}] Áudio muito curto ({audio_size} bytes) - possível 'sim'")
            
            # Transcrever usando o método padrão
            start_time = time.time()
            texto = await transcrever_audio_async(audio_data, call_id=call_id)
            transcription_time = (time.time() - start_time) * 1000
            
            if texto:
                logger.info(f"[{call_id}] Áudio transcrito com sucesso: '{texto}' em {transcription_time:.1f}ms")
                call_logger.log_transcription_complete(texto, transcription_time, is_visitor=True)
                
                # Medição do tempo de processamento da IA
                start_time = time.time()
                session_manager.process_visitor_text(call_id, texto)
                ai_processing_time = (time.time() - start_time) * 1000
                
                call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                    "text": texto,
                    "processing_time_ms": round(ai_processing_time, 2)
                })
            else:
                # Se for um áudio curto e a transcrição falhou, podemos tentar considerar como "sim"
                if is_short_audio:
                    logger.info(f"[{call_id}] Áudio curto não transcrito - interpretando como resposta curta")
                    texto = "sim"  # Assumir resposta curta afirmativa
                    
                    # Processar mesmo sem transcrição bem-sucedida
                    start_time = time.time()
                    session_manager.process_visitor_text(call_id, texto)
                    ai_processing_time = (time.time() - start_time) * 1000
                    
                    call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                        "text": texto,
                        "processing_time_ms": round(ai_processing_time, 2),
                        "note": "Áudio curto não transcrito - assumido resposta curta"
                    })
                else:
                    # Transcricão falhou para áudio de tamanho normal
                    logger.error(f"[{call_id}] Falha ao transcrever {audio_size} bytes de áudio")
                    call_logger.log_error("TRANSCRIPTION_FAILED", 
                                        "Falha ao transcrever áudio do visitante", 
                                        {"audio_size": audio_size})
                    # Voltar ao modo de escuta, já que não conseguimos processar o áudio
                    is_listening_mode = True
    
    # Criar gerenciador de callbacks do Azure Speech
    speech_callbacks = SpeechCallbacks(call_id, is_visitor=True, call_logger=call_logger)
    speech_callbacks.set_process_callback(process_recognized_text)
    
    # Registrar callbacks com o recognizer
    speech_callbacks.register_callbacks(recognizer)
    
    # Inicia o reconhecimento contínuo e aguarda o início da sessão
    recognizer.start_continuous_recognition_async()
    recognizer_running = True
    logger.info(f"[{call_id}] Iniciado reconhecimento contínuo com Azure Speech")
    
    try:
        while True:
            # Verificar sinal de terminação
            if session.terminate_visitor_event.is_set():
                logger.info(f"[{call_id}] Detectado sinal para encerrar recebimento de áudio do visitante")
                call_logger.log_event("TERMINATE_VISITOR_AUDIO", {
                    "reason": "session_terminated",
                    "timestamp": time.time()
                })
                break
            
            try:
                # Uso de wait_for com timeout para permitir verificação de terminação
                header = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
            except asyncio.TimeoutError:
                # Timeout apenas para verificação de terminação, continuamos normalmente
                continue
            except asyncio.IncompleteReadError:
                logger.info(f"[{call_id}] Visitante desconectou (EOF).")
                call_logger.log_call_ended("visitor_disconnected")
                break

            if not header:
                logger.info(f"[{call_id}] Nenhum dado de header, encerrando.")
                call_logger.log_call_ended("invalid_header")
                break

            kind = header[0]
            length = int.from_bytes(header[1:3], "big")

            audio_chunk = await reader.readexactly(length)
            
            # Verificar o estado atual da sessão
            current_state = session.visitor_state
            
            # Se estamos em IA_TURN, significa que a IA está falando - não devemos processar áudio
            if current_state == "IA_TURN":
                is_listening_mode = False
                continue  # Pula processamento durante fala da IA
                
            # Período de transição: após IA falar, descartamos alguns frames para evitar eco
            if discard_buffer_frames > 0:
                discard_buffer_frames -= 1
                continue
                
            # Se acabamos de transitar de IA_TURN para USER_TURN, ativamos modo de escuta
            if not is_listening_mode and current_state == "USER_TURN":
                is_listening_mode = True
                discard_buffer_frames = DISCARD_BUFFER_FRAMES  # Descartar quadros para evitar eco
                logger.debug(f"[{call_id}] Ativando modo de escuta de visitante")
                call_logger.log_event("LISTENING_MODE_ACTIVATED", {"timestamp": time.time()})
                continue

            # Processamos o áudio apenas quando estamos em modo de escuta
            if is_listening_mode and kind == KIND_SLIN and (len(audio_chunk) == 320 or len(audio_chunk) == 640):
                try:
                    # Guardar o formato original do áudio para diagnóstico
                    original_audio_size = len(audio_chunk)
                    
                    # Mantenha o formato original para aumentar chance de compatibilidade
                    # O microfone_client.py envia 640 bytes (320 samples * 2 bytes/sample)
                    # Importante: NÃO modifique o formato do áudio, deixe como está
                    chunk_to_process = audio_chunk
                    
                    # Log para analisar formato dos dados a cada ~10s
                    if frame_counter % 500 == 0:
                        # Exibir primeiros bytes como hex para debug
                        try:
                            hex_representation = " ".join(f"{b:02x}" for b in audio_chunk[:16])
                            logger.info(f"[{call_id}] Formato do áudio: tamanho={len(audio_chunk)}, primeiros bytes={hex_representation}")
                        except:
                            pass
                    
                    # Enviar áudio para o Azure Speech e guardar no buffer
                    if recognition_started:
                        # Sempre adicionar ao buffer para garantir que temos o áudio completo
                        speech_callbacks.add_audio_chunk(audio_chunk)
                        
                        # Enviar para o push_stream para processamento em tempo real
                        try:
                            # Enviar o chunk inteiro sem modificação
                            push_stream.write(audio_chunk)
                            
                            # A cada 200 frames enviar um marcador de debug
                            if frame_counter % 200 == 0:
                                logger.info(f"[{call_id}] Enviado {frame_counter} frames para Azure Speech")
                        except Exception as e:
                            logger.error(f"[{call_id}] Erro ao enviar áudio para push_stream: {e}")
                        last_audio_time = time.time()
                        
                        # Incrementar contadores
                        frame_counter += 1
                        
                        # Verificar se estamos em um longo período de silêncio (sem speech_detected)
                        # Isso serve como failsafe se o Azure Speech não disparar os eventos corretamente
                        silence_check_counter += 1
                        
                        # A cada 100 frames (~2 segundos), verifique se temos um silêncio prolongado
                        if silence_check_counter >= 100:
                            silence_check_counter = 0
                            current_time = time.time()
                            
                            # Log para debug do estado atual
                            buffer_size = len(speech_callbacks.audio_buffer) if hasattr(speech_callbacks, 'audio_buffer') else 0
                            logger.info(f"[{call_id}] Estado da detecção: coletando={speech_callbacks.is_collecting()}, detectou_fala={speech_callbacks.speech_detected}, buffer_size={buffer_size}, último_áudio={current_time - last_audio_time:.1f}s atrás")
                            
                            # Sempre forçamos o processamento periodicamente, compatível com método VAD
                            force_processing = False  # Por padrão, avaliamos condições específicas
                            reason = "verificação periódica de áudio"
                            
                            # Se temos silêncio prolongado, buffer grande ou fala detectada com silêncio, processar
                            if speech_callbacks.is_collecting() and (current_time - last_audio_time) > 2.0:
                                force_processing = True
                                reason = f"silêncio prolongado de {current_time - last_audio_time:.1f}s"
                            elif speech_callbacks.speech_detected and (current_time - last_audio_time) > 1.5:
                                force_processing = True
                                reason = "fala detectada com silêncio de 1.5s"
                            elif buffer_size > 50:
                                force_processing = True
                                reason = f"buffer grande ({buffer_size} frames)"
                            # Verificação extra: Se temos uma quantidade razoável de áudio após um período sem processamento
                            elif buffer_size > 10 and (current_time - last_audio_time) > 3.0:
                                force_processing = True
                                reason = f"buffer médio ({buffer_size} frames) com {current_time - last_audio_time:.1f}s sem processamento"
                            # Failsafe: Processar periodicamente para garantir que nada fique preso
                            elif (frame_counter % 1000 == 0) and buffer_size > 5:  # A cada ~20 segundos se tiver pelo menos alguns frames
                                force_processing = True
                                reason = f"verificação periódica preventiva (a cada ~20s) - buffer={buffer_size} frames"
                            
                            # IMPORTANTE: Verificações de segurança para casos de falha do Azure Speech
                            
                            # Caso 0: Verificar timeout de reconhecimento pendente
                            if hasattr(speech_callbacks, 'timeout_check_needed') and speech_callbacks.timeout_check_needed:
                                current_time = time.time()
                                timeout_time = speech_callbacks.timeout_check_time if hasattr(speech_callbacks, 'timeout_check_time') else (current_time - 1)
                                
                                if current_time >= timeout_time:
                                    logger.info(f"[{call_id}] Verificando timeout de reconhecimento pendente")
                                    
                                    # Limpar flag para evitar reprocessamento
                                    speech_callbacks.timeout_check_needed = False
                                    
                                    # Verificar se existem dados no buffer
                                    if hasattr(speech_callbacks, 'audio_buffer') and len(speech_callbacks.audio_buffer) > 0:
                                        # Processar áudio do buffer
                                        audio_data = b"".join(speech_callbacks.audio_buffer)
                                        speech_callbacks.audio_buffer = []
                                        speech_callbacks.collecting_audio = False
                                        speech_callbacks.speech_detected = False
                                        
                                        logger.info(f"[{call_id}] Processando {len(audio_data)} bytes de áudio após timeout")
                                        
                                        # Desativar escuta durante processamento
                                        is_listening_mode = False
                                        
                                        # Mudar estado para WAITING durante processamento
                                        session.visitor_state = "WAITING"
                                        
                                        # Log antes da transcrição
                                        call_logger.log_transcription_start(len(audio_data), is_visitor=True)
                                        
                                        # Transcrever com medição de tempo
                                        start_time = time.time()
                                        texto = await transcrever_audio_async(audio_data, call_id=call_id)
                                        transcription_time = (time.time() - start_time) * 1000
                                        
                                        if texto:
                                            call_logger.log_transcription_complete(texto, transcription_time, is_visitor=True)
                                            
                                            # Processar texto com IA
                                            start_time = time.time()
                                            session_manager.process_visitor_text(call_id, texto)
                                            ai_processing_time = (time.time() - start_time) * 1000
                                            
                                            call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                                                "text": texto,
                                                "processing_time_ms": round(ai_processing_time, 2),
                                                "source": "timeout_check"
                                            })
                                        else:
                                            logger.error(f"[{call_id}] Falha ao transcrever áudio de timeout ({len(audio_data)} bytes)")
                                            call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                          "Falha ao transcrever áudio de timeout do visitante", 
                                                          {"audio_size": len(audio_data)})
                                            is_listening_mode = True
                                        
                                        # Continuar para próximo ciclo
                                        continue
                                    else:
                                        logger.info(f"[{call_id}] Timeout de reconhecimento, mas buffer está vazio - nada a processar")
                            
                            # Caso 1: Verificar se há buffer grande com fala detectada (possivelmente preso)
                            if hasattr(speech_callbacks, 'long_buffer_flag') and speech_callbacks.long_buffer_flag and \
                               hasattr(speech_callbacks, 'audio_buffer') and len(speech_callbacks.audio_buffer) > 0:
                                logger.warning(f"[{call_id}] Detectado buffer grande ({len(speech_callbacks.audio_buffer)} frames) com fala em andamento - forçando processamento")
                                
                                # Limpar flag para evitar reprocessamento
                                speech_callbacks.long_buffer_flag = False
                                
                                # Forçar o mesmo comportamento que ocorreria no fim da fala
                                audio_data = b"".join(speech_callbacks.audio_buffer)
                                speech_callbacks.audio_buffer = []
                                speech_callbacks.collecting_audio = False
                                
                                # Desativar escuta durante processamento
                                is_listening_mode = False
                                
                                # Mudar estado para WAITING durante processamento
                                session.visitor_state = "WAITING"
                                
                                # Log antes da transcrição
                                call_logger.log_transcription_start(len(audio_data), is_visitor=True)
                                logger.info(f"[{call_id}] Processando {len(audio_data)} bytes de áudio de buffer grande")
                                
                                # Transcrever diretamente
                                start_time = time.time()
                                texto = await transcrever_audio_async(audio_data, call_id=call_id)
                                transcription_time = (time.time() - start_time) * 1000
                                
                                if texto:
                                    call_logger.log_transcription_complete(texto, transcription_time, is_visitor=True)
                                    
                                    # Processamento de IA
                                    start_time = time.time()
                                    session_manager.process_visitor_text(call_id, texto)
                                    ai_processing_time = (time.time() - start_time) * 1000
                                    
                                    call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                                        "text": texto,
                                        "processing_time_ms": round(ai_processing_time, 2),
                                        "source": "buffer_large"
                                    })
                                else:
                                    logger.error(f"[{call_id}] Falha ao transcrever buffer grande de {len(audio_data)} bytes")
                                    call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                    "Falha ao transcrever buffer grande do visitante", 
                                                    {"audio_size": len(audio_data)})
                                    # Volta ao modo de escuta
                                    is_listening_mode = True
                                
                                # Continuar para próximo ciclo
                                continue
                            
                            # Caso 2: Verificar se há dados pendentes do callback para processar
                            # Este é o método mais seguro para processar dados detectados pelo Azure Speech
                            if hasattr(speech_callbacks, 'pending_processing_flag') and speech_callbacks.pending_processing_flag:
                                if hasattr(speech_callbacks, 'pending_audio_for_processing') and speech_callbacks.pending_audio_for_processing:
                                    # Usar os dados pendentes e limpar a flag
                                    audio_data = speech_callbacks.pending_audio_for_processing
                                    speech_callbacks.pending_processing_flag = False
                                    speech_callbacks.pending_audio_for_processing = None
                                    
                                    logger.info(f"[{call_id}] Processando {len(audio_data)} bytes de áudio pendente do callback")
                                    
                                    # Desativar escuta durante processamento
                                    is_listening_mode = False
                                    
                                    # Mudar estado para WAITING durante processamento
                                    session.visitor_state = "WAITING"
                                    
                                    # Log antes da transcrição
                                    call_logger.log_transcription_start(len(audio_data), is_visitor=True)
                                    
                                    # Transcrever com medição de tempo e monitoramento
                                    start_time = time.time()
                                    texto = await transcrever_audio_async(audio_data, call_id=call_id)
                                    transcription_time = (time.time() - start_time) * 1000
                                    
                                    if texto:
                                        call_logger.log_transcription_complete(texto, transcription_time, is_visitor=True)
                                        
                                        # Medição do tempo de processamento da IA
                                        start_time = time.time()
                                        session_manager.process_visitor_text(call_id, texto)
                                        ai_processing_time = (time.time() - start_time) * 1000
                                        
                                        call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                                            "text": texto,
                                            "processing_time_ms": round(ai_processing_time, 2),
                                            "source": "pending_audio"
                                        })
                                    else:
                                        call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                          "Falha ao transcrever áudio pendente do visitante", 
                                                          {"audio_size": len(audio_data)})
                                        # Voltar ao modo de escuta, já que não conseguimos processar o áudio
                                        is_listening_mode = True
                                        
                                    # Ignoramos o processamento normal neste ciclo, pois já processamos os dados pendentes
                                    continue
                            
                            # Forçar processamento usando exatamente o mesmo método do VAD
                            if force_processing and buffer_size > 0:
                                logger.info(f"[{call_id}] Forçando processamento de áudio: {reason}")
                                
                                # Copiar exatamente o mesmo código de receber_audio_visitante_vad
                                # para garantir compatibilidade de processamento
                                audio_data = b"".join(speech_callbacks.audio_buffer)
                                speech_callbacks.audio_buffer = []
                                speech_callbacks.collecting_audio = False
                                speech_callbacks.speech_detected = False
                                
                                # Desativar escuta durante processamento
                                is_listening_mode = False
                                
                                # Mudar estado para WAITING durante processamento
                                session.visitor_state = "WAITING"
                                
                                # Log antes da transcrição
                                call_logger.log_transcription_start(len(audio_data), is_visitor=True)
                                
                                # Transcrever com medição de tempo e monitoramento
                                start_time = time.time()
                                texto = await transcrever_audio_async(audio_data, call_id=call_id)
                                transcription_time = (time.time() - start_time) * 1000
                                
                                if texto:
                                    call_logger.log_transcription_complete(texto, transcription_time, is_visitor=True)
                                    
                                    # Medição do tempo de processamento da IA
                                    start_time = time.time()
                                    session_manager.process_visitor_text(call_id, texto)
                                    ai_processing_time = (time.time() - start_time) * 1000
                                    
                                    call_logger.log_event("VISITOR_PROCESSING_COMPLETE", {
                                        "text": texto,
                                        "processing_time_ms": round(ai_processing_time, 2)
                                    })
                                else:
                                    call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                        "Falha ao transcrever áudio do visitante", 
                                                        {"audio_size": len(audio_data)})
                                    # Voltar ao modo de escuta, já que não conseguimos processar o áudio
                                    is_listening_mode = True
                    else:
                        # Iniciar reconhecimento na primeira vez que recebemos áudio
                        recognition_started = True
                        push_stream.write(chunk_to_process)
                        
                        # Também adicionamos ao buffer para capturar início da fala
                        speech_callbacks.add_audio_chunk(audio_chunk)
                        
                        last_audio_time = time.time()
                        logger.info(f"[{call_id}] Primeiro áudio enviado para Azure Speech ({original_audio_size} bytes)")
                except Exception as e:
                    logger.error(f"[{call_id}] Erro ao processar áudio para Azure Speech: {e}", exc_info=True)
            
            elif kind != KIND_SLIN or (len(audio_chunk) != 320 and len(audio_chunk) != 640):
                logger.warning(f"[{call_id}] Chunk inválido do visitante. kind={kind}, len={len(audio_chunk)}")
                call_logger.log_error("INVALID_CHUNK", 
                                    "Chunk de áudio inválido recebido do visitante", 
                                    {"kind": kind, "length": len(audio_chunk)})
    
    finally:
        # Finalizar o reconhecedor
        if recognizer_running:
            logger.info(f"[{call_id}] Parando reconhecimento contínuo com Azure Speech")
            recognizer.stop_continuous_recognition_async()
        
    # Ao sair, encerrou a conexão
    logger.info(f"[{call_id}] receber_audio_visitante_azure_speech terminou.")


async def enviar_mensagens_visitante(writer: asyncio.StreamWriter, call_id: str):
    """
    Tarefa que periodicamente verifica se há mensagens pendentes
    para o visitante no SessionManager, sintetiza e envia via áudio.
    
    Atualiza o estado da sessão durante a fala da IA para evitar retroalimentação.
    Suporte para encerramento gracioso.
    """
    call_logger = CallLoggerManager.get_logger(call_id)
    
    # Verificar se a sessão existe
    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada para enviar mensagens")
        return
    
    # Flag para controlar encerramento com mensagem final
    final_message_sent = False
    
    while True:
        # Verificar sinal de terminação
        if session.terminate_visitor_event.is_set() and not final_message_sent:
            # Enviar mensagem de despedida e encerrar
            logger.info(f"[{call_id}] Iniciando despedida para visitante")
            await send_goodbye_and_terminate(writer, session, call_id, "visitante", call_logger)
            
            # Marcar que a mensagem de despedida foi enviada
            final_message_sent = True
            
            # Forçar encerramento imediato após despedida do visitante
            logger.info(f"[{call_id}] Forçando encerramento da sessão após despedida do visitante")
            session_manager._complete_session_termination(call_id)
            break
            
        await asyncio.sleep(0.2)  # Ajuste conforme sua necessidade

        # Se já está em modo de encerramento, não processa novas mensagens
        if session.terminate_visitor_event.is_set():
            continue

        # Tenta buscar uma mensagem
        msg = session_manager.get_message_for_visitor(call_id)
        if msg is not None:
            logger.info(f"[{call_id}] Enviando mensagem ao visitante: {msg}")
            
            # IMPORTANTE: Mudar estado para IA_TURN antes de começar a falar
            # Isso sinaliza para o VAD parar de processar durante a fala
            old_state = session.visitor_state
            session.visitor_state = "IA_TURN"
            
            call_logger.log_event("STATE_CHANGE", {
                "from": old_state,
                "to": "IA_TURN",
                "reason": "ia_speaking"
            })
            
            call_logger.log_synthesis_start(msg, is_visitor=True)
            
            # Medir tempo de síntese
            start_time = time.time()
            audio_resposta = await sintetizar_fala_async(msg)
            synthesis_time = (time.time() - start_time) * 1000
            
            # Se falhou na síntese, voltamos ao estado anterior
            if not audio_resposta:
                call_logger.log_error("SYNTHESIS_FAILED", 
                                     "Falha ao sintetizar mensagem para o visitante", 
                                     {"message": msg})
                
                # Voltar ao estado anterior
                session.visitor_state = old_state
                call_logger.log_event("STATE_CHANGE", {
                    "from": "IA_TURN",
                    "to": old_state,
                    "reason": "synthesis_failed"
                })
                continue
                
            # Síntese bem-sucedida, enviar áudio
            call_logger.log_synthesis_complete(len(audio_resposta), synthesis_time, is_visitor=True)
            
            # Tempo estimado para reprodução (baseado no tamanho do áudio)
            # A taxa de amostragem é 8000Hz com 16 bits por amostra
            # Aproximadamente (len(audio_resposta) / 16000) segundos de áudio
            playback_duration_ms = (len(audio_resposta) / 16) * 1000
            call_logger.log_event("ESTIMATED_PLAYBACK_DURATION", {
                "duration_ms": playback_duration_ms,
                "audio_size_bytes": len(audio_resposta)
            })
            
            # Enviar o áudio (isso já registra logs de envio)
            await enviar_audio(writer, audio_resposta, call_id=call_id, origem="Visitante")
            
            # Adicionar um atraso maior após o envio do áudio para garantir
            # que o áudio seja totalmente reproduzido E evitar eco/retroalimentação
            # Aumentamos para 2.0 segundos mínimo para dar mais margem de segurança
            safe_delay = max(POST_AUDIO_DELAY_SECONDS, 2.0)
            logger.info(f"[{call_id}] Aguardando {safe_delay}s após envio do áudio para evitar eco")
            await asyncio.sleep(safe_delay)
            
            # PROTEÇÃO ANTI-ECO ADICIONAL: Limpar quaisquer dados coletados durante o período
            # em que a IA estava falando - isso evita processamento de eco
            if 'speech_callbacks' in locals() or hasattr(session, 'speech_callbacks'):
                speech_callbacks_obj = speech_callbacks if 'speech_callbacks' in locals() else session.speech_callbacks
                
                if hasattr(speech_callbacks_obj, 'audio_buffer'):
                    buffer_size = len(speech_callbacks_obj.audio_buffer)
                    if buffer_size > 0:
                        logger.info(f"[{call_id}] Limpando buffer de {buffer_size} frames coletados durante fala da IA")
                        speech_callbacks_obj.audio_buffer = []
                        
                    # Resetar outros estados de detecção
                    speech_callbacks_obj.collecting_audio = False  # Será ativado novamente quando necessário
                    speech_callbacks_obj.speech_detected = False
                    
                    # Limpar quaisquer flags pendentes
                    if hasattr(speech_callbacks_obj, 'pending_processing_flag'):
                        speech_callbacks_obj.pending_processing_flag = False
                    if hasattr(speech_callbacks_obj, 'pending_audio_for_processing'):
                        speech_callbacks_obj.pending_audio_for_processing = None
                        
                    # Resetar contadores de frames após silêncio
                    if hasattr(speech_callbacks_obj, 'frames_after_silence'):
                        speech_callbacks_obj.frames_after_silence = 0
            
            # Mudar de volta para USER_TURN para que o sistema possa escutar o usuário
            session.visitor_state = "USER_TURN"
            
            # PROTEÇÃO ANTI-LOOP: Registrar timestamp de quando a IA terminou de falar
            # Isto será usado para ignorar detecções de fala muito próximas ao fim da fala da IA
            if not hasattr(session, 'last_ai_speech_end_time'):
                session.last_ai_speech_end_time = {}
            # Marcar o momento exato em que o áudio terminou de ser enviado
            session.last_ai_speech_end_time['visitor'] = time.time()
            logger.info(f"[{call_id}] Marcando timestamp de fim de fala da IA: {session.last_ai_speech_end_time['visitor']}")
            
            call_logger.log_event("STATE_CHANGE", {
                "from": "IA_TURN",
                "to": "USER_TURN",
                "reason": "ia_finished_speaking"
            })


async def iniciar_servidor_audiosocket_visitante(reader, writer):
    """
    Versão modificada que registra a porta local usada pela conexão.
    """
    # Recuperar porta local
    local_port = get_local_port(writer)
    
    # Resto do código atual
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    
    # Converter para UUID com formato de traços
    import uuid
    call_id = str(uuid.UUID(bytes=call_id_bytes))
    
    # Registrar porta usada para este call_id
    if extension_manager and local_port:
        ext_info = extension_manager.get_extension_info(porta=local_port)
        logger.info(f"[VISITANTE] Call ID: {call_id} na porta {local_port}, ramal: {ext_info.get('ramal_ia', 'desconhecido')}")
    else:
        logger.info(f"[VISITANTE] Call ID: {call_id}")
    
    # Inicializar logger específico para esta chamada
    call_logger = CallLoggerManager.get_logger(call_id)
    call_logger.log_event("CALL_SETUP", {
        "type": "visitor",
        "call_id": call_id,
        "local_port": local_port,
        "voice_detection": VOICE_DETECTION_TYPE.value
    })

    session_manager.create_session(call_id)

    # Registrar a conexão ativa no ResourceManager para permitir KIND_HANGUP
    resource_manager.register_connection(call_id, "visitor", reader, writer)
    logger.info(f"[{call_id}] Conexão do visitante registrada no ResourceManager")

    # SAUDAÇÃO:
    welcome_msg = "Olá, seja bem-vindo! Em que posso ajudar?"
    call_logger.log_event("GREETING", {"message": welcome_msg})
    
    session_manager.enfileirar_visitor(
        call_id,
        welcome_msg
    )

    # Iniciar as tarefas de recebimento e envio de áudio
    task1 = asyncio.create_task(receber_audio_visitante(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_visitante(writer, call_id))

    # Espera até que alguma das tarefas termine (em geral, quando visitante desconecta).
    start_time = time.time()
    done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
    call_duration = (time.time() - start_time) * 1000
    
    logger.info(f"[{call_id}] Alguma tarefa finalizou, vamos encerrar as duas...")
    call_logger.log_event("TASKS_ENDING", {
        "done_tasks": len(done),
        "pending_tasks": len(pending),
        "call_duration_ms": round(call_duration, 2)
    })

    # Cancela a outra
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    logger.info(f"[{call_id}] Encerrando conexão do visitante.")
    call_logger.log_call_ended("visitor_connection_closed", call_duration)
    
    # Remover conexão do ResourceManager
    resource_manager.unregister_connection(call_id, "visitor")
    
    # Remover logger para liberar recursos
    CallLoggerManager.remove_logger(call_id)
    
    # Tratar fechamento do socket com robustez para lidar com desconexões abruptas
    try:
        writer.close()
        # Usar um timeout para wait_closed para evitar bloqueio indefinido 
        # em caso de desconexão súbita (Connection reset by peer)
        await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.info(f"[{call_id}] Timeout ao aguardar fechamento do socket - provavelmente já foi fechado pelo cliente")
    except ConnectionResetError:
        # Isso é esperado se o cliente desconectar abruptamente após receber KIND_HANGUP
        logger.info(f"[{call_id}] Conexão resetada pelo cliente após KIND_HANGUP - comportamento normal")
    except Exception as e:
        # Capturar qualquer outro erro durante o fechamento da conexão
        logger.warning(f"[{call_id}] Erro ao fechar conexão: {str(e)}")
    
    logger.info(f"[{call_id}] Socket encerrado e liberado para novas conexões")


# ------------------------
# MORADOR
# ------------------------

async def receber_audio_morador(reader: asyncio.StreamReader, call_id: str):
    """
    Função que redireciona para a implementação apropriada com base na configuração.
    """
    # Escolher a implementação com base na configuração
    if VOICE_DETECTION_TYPE == VoiceDetectionType.WEBRTCVAD:
        return await receber_audio_morador_vad(reader, call_id)
    elif VOICE_DETECTION_TYPE == VoiceDetectionType.AZURE_SPEECH:
        return await receber_audio_morador_azure_speech(reader, call_id)
    else:
        # Fallback para webrtcvad se o tipo não for reconhecido
        logger.warning(f"[{call_id}] Tipo de detecção de voz '{VOICE_DETECTION_TYPE}' não reconhecido, usando webrtcvad")
        return await receber_audio_morador_vad(reader, call_id)

async def receber_audio_morador_vad(reader: asyncio.StreamReader, call_id: str):
    """
    Implementação usando webrtcvad para detecção de voz e silêncio do morador.
    """
    call_logger = CallLoggerManager.get_logger(call_id)
    vad = webrtcvad.Vad(3)  # Aumentando a sensibilidade do VAD para detectar falas curtas
    frames = []
    is_speaking = False
    silence_start = None
    speech_start = None
    
    # Para controlar se estamos no modo de escuta ativa
    is_listening_mode = True
    
    # Acessar a sessão para verificar o estado
    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada para iniciar recebimento de áudio do morador")
        return
    
    # Flag de buffer para descartar áudio residual após IA falar
    discard_buffer_frames = 0

    while True:
        # Verificar sinal de terminação
        if session.terminate_resident_event.is_set():
            logger.info(f"[{call_id}] Detectado sinal para encerrar recebimento de áudio do morador")
            call_logger.log_event("TERMINATE_RESIDENT_AUDIO", {
                "reason": "session_terminated",
                "timestamp": time.time()
            })
            break
        
        try:
            # Uso de wait_for com timeout para permitir verificação de terminação
            header = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
        except asyncio.TimeoutError:
            # Timeout apenas para verificação de terminação, continuamos normalmente
            continue
        except asyncio.IncompleteReadError:
            logger.info(f"[{call_id}] Morador desconectou (EOF).")
            call_logger.log_call_ended("resident_disconnected")
            break

        if not header:
            logger.info(f"[{call_id}] Nenhum dado de header, encerrando (morador).")
            call_logger.log_call_ended("invalid_header_resident")
            break

        kind = header[0]
        length = int.from_bytes(header[1:3], "big")

        audio_chunk = await reader.readexactly(length)
        
        # Verificar o estado atual da sessão
        current_state = session.resident_state
        
        # Se estamos em IA_TURN, significa que a IA está falando com o morador - não processamos
        if current_state == "IA_TURN":
            is_listening_mode = False
            continue  # Pula processamento durante fala da IA
            
        # Período de transição: após IA falar, descartamos alguns frames para evitar eco
        if discard_buffer_frames > 0:
            discard_buffer_frames -= 1
            continue
            
        # Se acabamos de transitar de IA_TURN para USER_TURN, ativamos modo de escuta
        if not is_listening_mode and current_state == "USER_TURN":
            is_listening_mode = True
            discard_buffer_frames = DISCARD_BUFFER_FRAMES  # Descartar quadros para evitar eco
            logger.debug(f"[{call_id}] Ativando modo de escuta de morador")
            call_logger.log_event("RESIDENT_LISTENING_MODE_ACTIVATED", {"timestamp": time.time()})
            
            # Limpar quaisquer frames acumulados anteriormente
            frames = []
            is_speaking = False
            silence_start = None
            speech_start = None
            continue
        
        # Processamos VAD apenas quando estamos em modo de escuta
        if is_listening_mode and kind == KIND_SLIN and (len(audio_chunk) == 320 or len(audio_chunk) == 640):
            # Para morador, usamos uma detecção mais agressiva para palavras curtas como "Sim"
            # Se o chunk for de 640 bytes (320 amostras de 16 bits), precisamos garantir que seja processado corretamente
            chunk_to_process = audio_chunk
            if len(audio_chunk) == 640:
                # O WebRTCVAD espera PCM de 16 bits em 320 bytes, então estamos recebendo o dobro do tamanho esperado
                logger.debug(f"[{call_id}] Recebido chunk de 640 bytes do morador - formato PCM 16-bit")
                
            is_voice = vad.is_speech(chunk_to_process, 8000)
            if is_voice:
                frames.append(audio_chunk)
                if not is_speaking:
                    is_speaking = True
                    speech_start = asyncio.get_event_loop().time()
                    logger.info(f"[{call_id}] Morador começou a falar.")  # Aumentado para INFO para melhor visibilidade
                    call_logger.log_speech_detected(is_visitor=False)
                silence_start = None
            else:
                if is_speaking:
                    if silence_start is None:
                        silence_start = asyncio.get_event_loop().time()
                    else:
                        silence_duration = asyncio.get_event_loop().time() - silence_start
                        # Usar um tempo de silêncio muito mais curto para respostas rápidas do morador
                        if silence_duration > SILENCE_THRESHOLD_SECONDS:
                            is_speaking = False
                            logger.info(f"[{call_id}] Silêncio de {silence_duration:.2f}s detectado após fala do morador")
                            
                            # Mesmo com fala muito curta, processamos, pois pode ser um "Sim" rápido
                            if len(frames) < 20:  # ~0.4 segundo de áudio (20 frames de 20ms)
                                logger.info(f"[{call_id}] Fala CURTA do morador detectada: {len(frames)} frames (~{len(frames)*20}ms) - Processando mesmo assim")
                                # NÃO descartamos frames curtos para capturar "Sim" rápidos
                            
                            # Calcular duração total da fala
                            speech_duration = (asyncio.get_event_loop().time() - speech_start) * 1000
                            logger.debug(f"[{call_id}] Morador parou de falar após {speech_duration:.0f}ms.")
                            call_logger.log_speech_ended(speech_duration, is_visitor=False)
                            call_logger.log_silence_detected(silence_duration * 1000, is_visitor=False)
                            
                            audio_data = b"".join(frames)
                            frames.clear()
                            
                            # Desativar escuta durante processamento
                            is_listening_mode = False

                            # Log antes da transcrição
                            call_logger.log_transcription_start(len(audio_data), is_visitor=False)
                            
                            # Mudar estado para WAITING durante processamento
                            session.resident_state = "WAITING"
                            
                            # Transcrever com medição de tempo e monitoramento de recursos
                            start_time = time.time()
                            texto = await transcrever_audio_async(audio_data, call_id=call_id)
                            transcription_time = (time.time() - start_time) * 1000
                            
                            if texto:
                                call_logger.log_transcription_complete(texto, transcription_time, is_visitor=False)
                                
                                # Medição do tempo de processamento
                                start_time = time.time()
                                session_manager.process_resident_text(call_id, texto)
                                processing_time = (time.time() - start_time) * 1000
                                
                                call_logger.log_event("RESIDENT_PROCESSING_COMPLETE", {
                                    "text": texto,
                                    "processing_time_ms": round(processing_time, 2)
                                })
                                
                                logger.info(f"[{call_id}] Resposta do morador processada: '{texto}'")
                                
                                # Verificar se a sessão tem flag de finalização após processamento
                                session = session_manager.get_session(call_id)
                                if session and hasattr(session.flow, 'state'):
                                    flow_state = session.flow.state
                                    if str(flow_state) == 'FlowState.FINALIZADO':
                                        logger.info(f"[{call_id}] Flow detectado como FINALIZADO após resposta do morador")
                                        
                                        # Garantir que o visitor receba notificação da autorização
                                        intent_data = session.flow.intent_data if hasattr(session.flow, 'intent_data') else {}
                                        authorization_result = intent_data.get("authorization_result", "")
                                        intent_type = intent_data.get("intent_type", "entrada")
                                        
                                        if authorization_result == "authorized":
                                            # Enviar mensagem explícita ao visitante sobre autorização
                                            if intent_type == "entrega":
                                                visitor_msg = "Ótima notícia! O morador autorizou sua entrega."
                                            elif intent_type == "visita":
                                                visitor_msg = "Ótima notícia! O morador autorizou sua visita."
                                            else:
                                                visitor_msg = "Ótima notícia! O morador autorizou sua entrada."
                                            
                                            logger.info(f"[{call_id}] Notificando visitante explicitamente da autorização: {visitor_msg}")
                                            session_manager.enfileirar_visitor(call_id, visitor_msg)
                                            
                                            # Forçar mensagem final - essencial para fechar o ciclo
                                            final_msg = f"Sua {intent_type} foi autorizada pelo morador. Obrigado por utilizar nossa portaria inteligente."
                                            session_manager.enfileirar_visitor(call_id, final_msg)
                                            
                                            # Não finalizar a sessão imediatamente, permitir que as mensagens sejam enviadas
                                            # Agendamos um encerramento após um delay longo para garantir que todas as mensagens sejam ouvidas
                                            logger.info(f"[{call_id}] Agendando encerramento da sessão em 10 segundos após autorização do morador")
                                            asyncio.create_task(_encerrar_apos_delay(call_id, session_manager, 10.0))  # Delay mais longo para garantir processamento completo
                                        elif authorization_result == "denied":
                                            # Enviar mensagem explícita ao visitante sobre negação
                                            visitor_msg = f"Infelizmente o morador não autorizou sua {intent_type if intent_type else 'entrada'} neste momento."
                                            logger.info(f"[{call_id}] Notificando visitante explicitamente da negação: {visitor_msg}")
                                            session_manager.enfileirar_visitor(call_id, visitor_msg)
                                            
                                            # Forçar mensagem final - essencial para fechar o ciclo
                                            final_msg = f"Sua {intent_type} NÃO foi autorizada pelo morador. Obrigado por utilizar nossa portaria inteligente."
                                            session_manager.enfileirar_visitor(call_id, final_msg)
                                            
                                            # Não finalizar a sessão imediatamente, permitir que as mensagens sejam enviadas
                                            # Agendamos um encerramento após um delay longo para garantir que todas as mensagens sejam ouvidas
                                            logger.info(f"[{call_id}] Agendando encerramento da sessão em 10 segundos após negação do morador")
                                            asyncio.create_task(_encerrar_apos_delay(call_id, session_manager, 10.0))  # Delay mais longo para garantir processamento completo
                            else:
                                call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                    "Falha ao transcrever áudio do morador", 
                                                    {"audio_size": len(audio_data)})
                                # Voltar ao modo de escuta, já que não foi possível processar
                                is_listening_mode = True
        elif kind != KIND_SLIN or (len(audio_chunk) != 320 and len(audio_chunk) != 640):
            logger.warning(f"[{call_id}] Chunk inválido do morador. kind={kind}, len={len(audio_chunk)}")
            call_logger.log_error("INVALID_CHUNK", 
                                "Chunk de áudio inválido recebido do morador", 
                                {"kind": kind, "length": len(audio_chunk)})

    logger.info(f"[{call_id}] receber_audio_morador_vad terminou.")

async def receber_audio_morador_azure_speech(reader: asyncio.StreamReader, call_id: str):
    """
    Implementação usando Azure Speech SDK para detecção de voz e silêncio para o morador.
    
    Esta implementação usa o Azure Speech SDK para detectar início e fim da fala
    com melhor resistência a ruídos de fundo e otimizada para respostas curtas do morador.
    Segue o mesmo fluxo de verificação e finalização do receber_audio_morador_vad.
    """
    call_logger = CallLoggerManager.get_logger(call_id)
    
    # Para controlar se estamos no modo de escuta ativa
    is_listening_mode = True
    
    # Acessar a sessão para verificar o estado
    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada para iniciar recebimento de áudio do morador")
        return
    
    # Flag de buffer para descartar áudio residual após IA falar
    discard_buffer_frames = 0
    
    # Verificar se as variáveis de ambiente necessárias estão definidas
    azure_key = os.getenv('AZURE_SPEECH_KEY')
    azure_region = os.getenv('AZURE_SPEECH_REGION')
    
    if not azure_key or not azure_region:
        logger.error(f"[{call_id}] Variáveis de ambiente AZURE_SPEECH_KEY e/ou AZURE_SPEECH_REGION não configuradas!")
        logger.error(f"[{call_id}] AZURE_SPEECH_KEY: {azure_key and 'Configurada' or 'NÃO CONFIGURADA!'}")
        logger.error(f"[{call_id}] AZURE_SPEECH_REGION: {azure_region and 'Configurada' or 'NÃO CONFIGURADA!'}")
    
    # Configurações do Azure Speech SDK
    speech_config = speechsdk.SpeechConfig(
        subscription=azure_key,
        region=azure_region or "eastus"  # Valor de fallback se não estiver configurado
    )
    speech_config.speech_recognition_language = 'pt-BR'
    
    # Log para debug
    logger.info(f"[{call_id}] Configuração Azure Speech para morador: Language=pt-BR, Subscription={azure_key and '****' + azure_key[-4:] or 'NÃO CONFIGURADA'}, Region={azure_region or 'NÃO CONFIGURADA'}")
    
    # Ajuste o timeout de silêncio para segmentação - valor mais curto que o do visitante
    # Usamos um valor mais curto para capturar mais rapidamente respostas como "sim"
    speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, 
                              str(AZURE_SPEECH_SEGMENT_TIMEOUT_MS - 100))  # 100ms mais curto que o padrão
    
    # Configurações adicionais para melhorar o reconhecimento - valores mais agressivos
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "5000")   # 5 segundos para timeout inicial
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "300")       # 0.3 segundos de silêncio para encerrar
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText")   # Melhor reconhecimento de texto
    
    # Configurações para qualidade e reconhecimento melhorados - otimizadas para respostas curtas
    speech_config.enable_audio_logging()                                                # Habilita logging de áudio no Azure
    speech_config.enable_dictation()                                                    # Habilita modo ditado (melhor para frases curtas)
    speech_config.set_profanity(speechsdk.ProfanityOption.Raw)                          # Não filtra palavrões
    
    # Removendo propriedades não suportadas que causam erro
    # speech_config.set_property("AdaptationInitialSilenceTimeoutMs", "800")
    # speech_config.set_property("AdaptationEndSilenceTimeoutMs", "200")
    
    # Criar o stream de áudio para alimentar o reconhecedor
    # Usar formato específico para áudio - SLIN é raw PCM 16-bit a 8kHz
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=speechsdk.audio.AudioStreamFormat(samples_per_second=8000, 
                                                                                                    bits_per_sample=16,
                                                                                                    channels=1))
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    
    # Criar o reconhecedor
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    # Flag para controlar loop de reconhecimento
    recognizer_running = False
    recognition_started = False
    last_audio_time = time.time()
    
    # Função para processar texto reconhecido
    async def process_recognized_text(text, audio_data):
        nonlocal is_listening_mode
        
        # Verificações de segurança para os dados de áudio
        if not audio_data or len(audio_data) == 0:
            logger.warning(f"[{call_id}] Recebido process_recognized_text com audio_data vazio - ignorando")
            return
        
        # Desativar escuta durante processamento para evitar retroalimentação
        is_listening_mode = False
        
        # Mudar estado para WAITING durante processamento
        session.resident_state = "WAITING"
        
        # Log antes da transcrição
        audio_size = len(audio_data)
        call_logger.log_transcription_start(audio_size, is_visitor=False)
        logger.info(f"[{call_id}] Iniciando transcrição/processamento de {audio_size} bytes de áudio do morador")
        
        # Se o Azure Speech já transcreveu, usamos esse texto
        if text and text.strip():
            logger.info(f"[{call_id}] Usando texto do morador já reconhecido pelo Azure: '{text}'")
            call_logger.log_transcription_complete(text, 0, is_visitor=False)
            
            # Medição do tempo de processamento
            start_time = time.time()
            session_manager.process_resident_text(call_id, text)
            processing_time = (time.time() - start_time) * 1000
            
            call_logger.log_event("RESIDENT_PROCESSING_COMPLETE", {
                "text": text,
                "processing_time_ms": round(processing_time, 2)
            })
            
            logger.info(f"[{call_id}] Resposta do morador processada: '{text}'")
        else:
            # Caso o Azure Speech não tenha retornado texto, tentamos transcrever normalmente
            # Isso é essencial para o morador onde respostas curtas como "sim" são importantes
            
            # Verificar se o áudio é muito curto - poderia ser um "sim" rápido
            is_short_audio = audio_size < 8000  # ~0.5 segundo de áudio
            if is_short_audio:
                logger.info(f"[{call_id}] Áudio do morador muito curto ({audio_size} bytes) - possível 'sim'")
            
            # Transcrever usando o método padrão
            start_time = time.time()
            texto = await transcrever_audio_async(audio_data, call_id=call_id)
            transcription_time = (time.time() - start_time) * 1000
            
            if texto:
                logger.info(f"[{call_id}] Áudio do morador transcrito com sucesso: '{texto}' em {transcription_time:.1f}ms")
                call_logger.log_transcription_complete(texto, transcription_time, is_visitor=False)
                
                # Medição do tempo de processamento
                start_time = time.time()
                session_manager.process_resident_text(call_id, texto)
                processing_time = (time.time() - start_time) * 1000
                
                call_logger.log_event("RESIDENT_PROCESSING_COMPLETE", {
                    "text": texto,
                    "processing_time_ms": round(processing_time, 2)
                })
                
                logger.info(f"[{call_id}] Resposta do morador processada: '{texto}'")
            else:
                # Se for um áudio curto e a transcrição falhou, podemos tentar considerar como "sim"
                if is_short_audio:
                    logger.info(f"[{call_id}] Áudio curto do morador não transcrito - interpretando como 'sim'")
                    texto = "sim"  # Assumir resposta curta afirmativa
                    
                    # Processar mesmo sem transcrição bem-sucedida
                    start_time = time.time()
                    session_manager.process_resident_text(call_id, texto)
                    processing_time = (time.time() - start_time) * 1000
                    
                    call_logger.log_event("RESIDENT_PROCESSING_COMPLETE", {
                        "text": texto,
                        "processing_time_ms": round(processing_time, 2),
                        "note": "Áudio curto não transcrito - assumido 'sim'"
                    })
                    
                    logger.info(f"[{call_id}] Resposta curta do morador assumida como '{texto}'")
                else:
                    # Transcricão falhou para áudio de tamanho normal
                    logger.error(f"[{call_id}] Falha ao transcrever {audio_size} bytes de áudio do morador")
                    call_logger.log_error("TRANSCRIPTION_FAILED", 
                                       "Falha ao transcrever áudio do morador", 
                                       {"audio_size": audio_size})
                    # Voltar ao modo de escuta, já que não conseguimos processar o áudio
                    is_listening_mode = True
                    return
        
        # Verificar se a sessão tem flag de finalização após processamento
        session = session_manager.get_session(call_id)
        if session and hasattr(session.flow, 'state'):
            flow_state = session.flow.state
            if str(flow_state) == 'FlowState.FINALIZADO':
                logger.info(f"[{call_id}] Flow detectado como FINALIZADO após resposta do morador")
                
                # Garantir que o visitor receba notificação da autorização
                intent_data = session.flow.intent_data if hasattr(session.flow, 'intent_data') else {}
                authorization_result = intent_data.get("authorization_result", "")
                intent_type = intent_data.get("intent_type", "entrada")
                
                if authorization_result == "authorized":
                    # Enviar mensagem explícita ao visitante sobre autorização
                    if intent_type == "entrega":
                        visitor_msg = "Ótima notícia! O morador autorizou sua entrega."
                    elif intent_type == "visita":
                        visitor_msg = "Ótima notícia! O morador autorizou sua visita."
                    else:
                        visitor_msg = "Ótima notícia! O morador autorizou sua entrada."
                    
                    logger.info(f"[{call_id}] Notificando visitante explicitamente da autorização: {visitor_msg}")
                    session_manager.enfileirar_visitor(call_id, visitor_msg)
                    
                    # Forçar mensagem final - essencial para fechar o ciclo
                    final_msg = f"Sua {intent_type} foi autorizada pelo morador. Obrigado por utilizar nossa portaria inteligente."
                    session_manager.enfileirar_visitor(call_id, final_msg)
                    
                    # Não finalizar a sessão imediatamente, permitir que as mensagens sejam enviadas
                    # Agendamos um encerramento após um delay longo para garantir que todas as mensagens sejam ouvidas
                    logger.info(f"[{call_id}] Agendando encerramento da sessão em 10 segundos após autorização do morador")
                    asyncio.create_task(_encerrar_apos_delay(call_id, session_manager, 10.0))  # Delay mais longo para garantir processamento completo
                elif authorization_result == "denied":
                    # Enviar mensagem explícita ao visitante sobre negação
                    visitor_msg = f"Infelizmente o morador não autorizou sua {intent_type if intent_type else 'entrada'} neste momento."
                    logger.info(f"[{call_id}] Notificando visitante explicitamente da negação: {visitor_msg}")
                    session_manager.enfileirar_visitor(call_id, visitor_msg)
                    
                    # Forçar mensagem final - essencial para fechar o ciclo
                    final_msg = f"Sua {intent_type} NÃO foi autorizada pelo morador. Obrigado por utilizar nossa portaria inteligente."
                    session_manager.enfileirar_visitor(call_id, final_msg)
                    
                    # Não finalizar a sessão imediatamente, permitir que as mensagens sejam enviadas
                    # Agendamos um encerramento após um delay longo para garantir que todas as mensagens sejam ouvidas
                    logger.info(f"[{call_id}] Agendando encerramento da sessão em 10 segundos após negação do morador")
                    asyncio.create_task(_encerrar_apos_delay(call_id, session_manager, 10.0))  # Delay mais longo para garantir processamento completo
    
    # Criar gerenciador de callbacks do Azure Speech
    speech_callbacks = SpeechCallbacks(call_id, is_visitor=False, call_logger=call_logger)
    speech_callbacks.set_process_callback(process_recognized_text)
    
    # Registrar callbacks com o recognizer
    speech_callbacks.register_callbacks(recognizer)
    
    # Inicia o reconhecimento contínuo
    recognizer.start_continuous_recognition_async()
    recognizer_running = True
    logger.info(f"[{call_id}] Iniciado reconhecimento contínuo do morador com Azure Speech")
    
    try:
        while True:
            # Verificar sinal de terminação
            if session.terminate_resident_event.is_set():
                logger.info(f"[{call_id}] Detectado sinal para encerrar recebimento de áudio do morador")
                call_logger.log_event("TERMINATE_RESIDENT_AUDIO", {
                    "reason": "session_terminated",
                    "timestamp": time.time()
                })
                break
            
            try:
                # Uso de wait_for com timeout para permitir verificação de terminação
                header = await asyncio.wait_for(reader.readexactly(3), timeout=0.5)
            except asyncio.TimeoutError:
                # Timeout apenas para verificação de terminação, continuamos normalmente
                continue
            except asyncio.IncompleteReadError:
                logger.info(f"[{call_id}] Morador desconectou (EOF).")
                call_logger.log_call_ended("resident_disconnected")
                break

            if not header:
                logger.info(f"[{call_id}] Nenhum dado de header, encerrando (morador).")
                call_logger.log_call_ended("invalid_header_resident")
                break

            kind = header[0]
            length = int.from_bytes(header[1:3], "big")

            audio_chunk = await reader.readexactly(length)
            
            # Verificar o estado atual da sessão
            current_state = session.resident_state
            
            # Se estamos em IA_TURN, significa que a IA está falando com o morador - não processamos
            if current_state == "IA_TURN":
                is_listening_mode = False
                continue  # Pula processamento durante fala da IA
                
            # Período de transição: após IA falar, descartamos alguns frames para evitar eco
            if discard_buffer_frames > 0:
                discard_buffer_frames -= 1
                continue
                
            # Se acabamos de transitar de IA_TURN para USER_TURN, ativamos modo de escuta
            if not is_listening_mode and current_state == "USER_TURN":
                is_listening_mode = True
                discard_buffer_frames = DISCARD_BUFFER_FRAMES  # Descartar quadros para evitar eco
                logger.debug(f"[{call_id}] Ativando modo de escuta de morador")
                call_logger.log_event("RESIDENT_LISTENING_MODE_ACTIVATED", {"timestamp": time.time()})
                continue

            # Processamos o áudio apenas quando estamos em modo de escuta
            if is_listening_mode and kind == KIND_SLIN and (len(audio_chunk) == 320 or len(audio_chunk) == 640):
                try:
                    # Enviar áudio para o Azure Speech
                    if recognition_started:
                        push_stream.write(audio_chunk)
                        last_audio_time = time.time()
                        
                        # Sempre tentamos adicionar ao buffer, independente do estado atual
                        # O método add_audio_chunk vai decidir se armazena no buffer principal ou no pre-buffer
                        speech_callbacks.add_audio_chunk(audio_chunk)
                        
                        # Incrementar contador de frames
                        frame_counter += 1
                        
                        # A cada 300 frames (~6 segundos), logamos o estado atual para debug
                        if frame_counter % 300 == 0:
                            logger.debug(f"[{call_id}] Estado do reconhecimento de morador: coletando={speech_callbacks.is_collecting()}, buffer_size={len(speech_callbacks.audio_buffer) if hasattr(speech_callbacks, 'audio_buffer') else 0}")
                    else:
                        # Iniciar reconhecimento na primeira vez que recebemos áudio
                        recognition_started = True
                        push_stream.write(audio_chunk)
                        last_audio_time = time.time()
                        logger.info(f"[{call_id}] Primeiro áudio do morador enviado para Azure Speech")
                except Exception as e:
                    logger.error(f"[{call_id}] Erro ao processar áudio para Azure Speech: {e}")
            
            elif kind != KIND_SLIN or (len(audio_chunk) != 320 and len(audio_chunk) != 640):
                logger.warning(f"[{call_id}] Chunk inválido do morador. kind={kind}, len={len(audio_chunk)}")
                call_logger.log_error("INVALID_CHUNK", 
                                    "Chunk de áudio inválido recebido do morador", 
                                    {"kind": kind, "length": len(audio_chunk)})
    
    finally:
        # Finalizar o reconhecedor
        if recognizer_running:
            logger.info(f"[{call_id}] Parando reconhecimento contínuo do morador com Azure Speech")
            recognizer.stop_continuous_recognition_async()
        
    # Ao sair, encerrou a conexão
    logger.info(f"[{call_id}] receber_audio_morador_azure_speech terminou.")


async def enviar_mensagens_morador(writer: asyncio.StreamWriter, call_id: str):
    """
    Fica buscando mensagens para o morador, sintetiza e envia via áudio.
    
    Atualiza o estado da sessão durante a fala da IA para evitar retroalimentação.
    Suporte para encerramento gracioso.
    """
    call_logger = CallLoggerManager.get_logger(call_id)
    
    # Verificar se a sessão existe
    session = session_manager.get_session(call_id)
    if not session:
        logger.error(f"[{call_id}] Sessão não encontrada para enviar mensagens ao morador")
        return
    
    # Flag para controlar encerramento com mensagem final
    final_message_sent = False
    
    while True:
        # Verificar sinal de terminação
        if session.terminate_resident_event.is_set() and not final_message_sent:
            # Enviar mensagem de despedida e encerrar
            logger.info(f"[{call_id}] Iniciando despedida para morador")
            await send_goodbye_and_terminate(writer, session, call_id, "morador", call_logger)
            
            # Marcar que a mensagem de despedida foi enviada
            final_message_sent = True
            
            # NÃO forçar encerramento completo aqui
            # Apenas registrar que o morador foi desconectado, 
            # deixar que o visitante receba suas mensagens e encerre a sessão
            logger.info(f"[{call_id}] Conexão do morador encerrada, aguardando ciclo do visitante")
            
            break
        
        await asyncio.sleep(0.2)
        
        # Se já está em modo de encerramento, não processa novas mensagens
        if session.terminate_resident_event.is_set():
            continue
            
        msg = session_manager.get_message_for_resident(call_id)
        if msg is not None:
            logger.info(f"[{call_id}] Enviando mensagem ao morador: {msg}")
            
            # IMPORTANTE: Mudar estado para IA_TURN antes de começar a falar
            # Isso sinaliza para o VAD parar de processar durante a fala
            old_state = session.resident_state
            session.resident_state = "IA_TURN"
            
            call_logger.log_event("RESIDENT_STATE_CHANGE", {
                "from": old_state,
                "to": "IA_TURN",
                "reason": "ia_speaking_to_resident"
            })
            
            call_logger.log_synthesis_start(msg, is_visitor=False)
            
            # Medir tempo de síntese
            start_time = time.time()
            audio_resposta = await sintetizar_fala_async(msg)
            synthesis_time = (time.time() - start_time) * 1000
            
            # Se falhou na síntese, voltamos ao estado anterior
            if not audio_resposta:
                call_logger.log_error("SYNTHESIS_FAILED", 
                                     "Falha ao sintetizar mensagem para o morador", 
                                     {"message": msg})
                
                # Voltar ao estado anterior
                session.resident_state = old_state
                call_logger.log_event("RESIDENT_STATE_CHANGE", {
                    "from": "IA_TURN",
                    "to": old_state,
                    "reason": "synthesis_failed"
                })
                continue
                
            # Síntese bem-sucedida, enviar áudio
            call_logger.log_synthesis_complete(len(audio_resposta), synthesis_time, is_visitor=False)
            
            # Tempo estimado para reprodução (baseado no tamanho do áudio)
            # A taxa de amostragem é 8000Hz com 16 bits por amostra
            # Aproximadamente (len(audio_resposta) / 16000) segundos de áudio
            playback_duration_ms = (len(audio_resposta) / 16) * 1000
            call_logger.log_event("RESIDENT_ESTIMATED_PLAYBACK_DURATION", {
                "duration_ms": playback_duration_ms,
                "audio_size_bytes": len(audio_resposta)
            })
            
            # Enviar o áudio (isso já registra logs de envio)
            await enviar_audio(writer, audio_resposta, call_id=call_id, origem="Morador")
            
            # Adicionar um atraso maior após o envio do áudio para garantir
            # que o áudio seja totalmente reproduzido E evitar eco/retroalimentação
            # Aumentamos para 2.0 segundos mínimo para dar mais margem de segurança
            safe_delay = max(POST_AUDIO_DELAY_SECONDS, 2.0)
            logger.info(f"[{call_id}] Aguardando {safe_delay}s após envio do áudio para evitar eco")
            await asyncio.sleep(safe_delay)
            
            # PROTEÇÃO ANTI-ECO ADICIONAL: Limpar quaisquer dados coletados durante o período
            # em que a IA estava falando - isso evita processamento de eco
            if 'resident_speech_callbacks' in locals() or hasattr(session, 'resident_speech_callbacks'):
                speech_callbacks_obj = resident_speech_callbacks if 'resident_speech_callbacks' in locals() else session.resident_speech_callbacks
                
                if hasattr(speech_callbacks_obj, 'audio_buffer'):
                    buffer_size = len(speech_callbacks_obj.audio_buffer)
                    if buffer_size > 0:
                        logger.info(f"[{call_id}] Limpando buffer de {buffer_size} frames coletados durante fala da IA para o morador")
                        speech_callbacks_obj.audio_buffer = []
                        
                    # Resetar outros estados de detecção
                    speech_callbacks_obj.collecting_audio = False  # Será ativado novamente quando necessário
                    speech_callbacks_obj.speech_detected = False
                    
                    # Limpar quaisquer flags pendentes
                    if hasattr(speech_callbacks_obj, 'pending_processing_flag'):
                        speech_callbacks_obj.pending_processing_flag = False
                    if hasattr(speech_callbacks_obj, 'pending_audio_for_processing'):
                        speech_callbacks_obj.pending_audio_for_processing = None
                        
                    # Resetar contadores de frames após silêncio
                    if hasattr(speech_callbacks_obj, 'frames_after_silence'):
                        speech_callbacks_obj.frames_after_silence = 0
            
            # Mudar de volta para USER_TURN para que o sistema possa escutar o morador
            session.resident_state = "USER_TURN"
            call_logger.log_event("RESIDENT_STATE_CHANGE", {
                "from": "IA_TURN",
                "to": "USER_TURN",
                "reason": "ia_finished_speaking_to_resident"
            })


async def iniciar_servidor_audiosocket_morador(reader, writer):
    """
    Versão modificada que registra a porta local usada pela conexão.
    """
    # Recuperar porta local
    local_port = get_local_port(writer)
    
    # Resto do código atual
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    
    # Converter para UUID com formato de traços
    import uuid
    call_id = str(uuid.UUID(bytes=call_id_bytes))
    
    # Registrar porta usada para este call_id
    if extension_manager and local_port:
        ext_info = extension_manager.get_extension_info(porta=local_port)
        logger.info(f"[MORADOR] Call ID: {call_id} na porta {local_port}, ramal: {ext_info.get('ramal_retorno', 'desconhecido')}")
    else:
        logger.info(f"[MORADOR] Call ID: {call_id}")
    
    # Inicializar logger específico para esta chamada
    call_logger = CallLoggerManager.get_logger(call_id)
    call_logger.log_event("CALL_SETUP", {
        "type": "resident",
        "call_id": call_id,
        "local_port": local_port,
        "voice_detection": VOICE_DETECTION_TYPE.value
    })

    # Registrar a conexão ativa no ResourceManager para permitir KIND_HANGUP
    resource_manager.register_connection(call_id, "resident", reader, writer)
    logger.info(f"[{call_id}] Conexão do morador registrada no ResourceManager")

    # Verificar se sessão já existe (deve existir se o fluxo estiver correto)
    existing_session = session_manager.get_session(call_id)
    if not existing_session:
        logger.warning(f"[MORADOR] Call ID {call_id} não encontrado como sessão existente. Criando nova sessão.")
        
        # Criar uma nova sessão - isto não deveria acontecer em circunstâncias normais
        session = session_manager.create_session(call_id)
        
        # SAUDAÇÃO MORADOR para nova sessão:
        welcome_msg = "Olá, morador! Você está em ligação com a portaria inteligente."
        call_logger.log_event("GREETING_RESIDENT", {"message": welcome_msg})
        session_manager.enfileirar_resident(call_id, welcome_msg)
        
        # Atualizar estado do morador para USER_TURN para permitir interação inicial
        session.resident_state = "USER_TURN"
    else:
        logger.info(f"[MORADOR] Sessão existente encontrada para Call ID: {call_id}. Conectando morador ao fluxo existente.")
        
        # Transferir intent_data para a sessão do morador se necessário
        if hasattr(existing_session.flow, 'intent_data') and existing_session.flow.intent_data:
            existing_session.intent_data = existing_session.flow.intent_data
            logger.info(f"[MORADOR] Intent data transferido para sessão: {existing_session.intent_data}")
            
        # Atualizar estado do morador para USER_TURN para permitir interação
        existing_session.resident_state = "USER_TURN"
        
        # IMPORTANTE: Indicar ao conversation_flow que o morador atendeu
        try:
            flow = existing_session.flow
            previous_state = flow.state
            
            # Este é o trigger que indica que o morador atendeu
            call_logger.log_event("MORADOR_CONNECTED", {
                "voip_number": flow.voip_number_morador if hasattr(flow, 'voip_number_morador') else "unknown",
                "previous_state": previous_state.name if hasattr(previous_state, 'name') else str(previous_state)
            })
            
            # Simular primeira mensagem do morador para acionar o fluxo
            session_manager.process_resident_text(call_id, "AUDIO_CONNECTION_ESTABLISHED")
            
            logger.info(f"[MORADOR] Conexão de áudio estabelecida, notificado o flow para iniciar comunicação")
        except Exception as e:
            logger.error(f"[MORADOR] Erro ao notificar atendimento: {e}", exc_info=True)

    # Iniciar as tarefas de recebimento e envio de áudio
    task1 = asyncio.create_task(receber_audio_morador(reader, call_id))
    task2 = asyncio.create_task(enviar_mensagens_morador(writer, call_id))

    start_time = time.time()
    done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
    call_duration = (time.time() - start_time) * 1000
    
    logger.info(f"[{call_id}] Alguma tarefa (morador) finalizou, encerrar.")
    call_logger.log_event("RESIDENT_TASKS_ENDING", {
        "done_tasks": len(done),
        "pending_tasks": len(pending),
        "call_duration_ms": round(call_duration, 2)
    })

    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    # Remover conexão do ResourceManager
    resource_manager.unregister_connection(call_id, "resident")

    # Tratar fechamento do socket com robustez para lidar com desconexões abruptas
    try:
        writer.close()
        # Usar um timeout para wait_closed para evitar bloqueio indefinido 
        # em caso de desconexão súbita (Connection reset by peer)
        await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.info(f"[{call_id}] Timeout ao aguardar fechamento do socket do morador - provavelmente já foi fechado pelo cliente")
    except ConnectionResetError:
        # Isso é esperado se o cliente desconectar abruptamente após receber KIND_HANGUP
        logger.info(f"[{call_id}] Conexão do morador resetada pelo cliente após KIND_HANGUP - comportamento normal")
    except Exception as e:
        # Capturar qualquer outro erro durante o fechamento da conexão
        logger.warning(f"[{call_id}] Erro ao fechar conexão do morador: {str(e)}")
    
    logger.info(f"[{call_id}] Conexão do morador encerrada.")
    call_logger.log_call_ended("resident_connection_closed", call_duration)
    
    # Remover logger para liberar recursos
    CallLoggerManager.remove_logger(call_id)
    
    logger.info(f"[{call_id}] Socket do morador encerrado e liberado para novas conexões")
