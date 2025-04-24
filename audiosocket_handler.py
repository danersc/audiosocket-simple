# audiosocket_handler.py

import asyncio
import logging
import struct
import os
import time
import json

import webrtcvad

from speech_service import transcrever_audio_async, sintetizar_fala_async
from session_manager import SessionManager  # Importamos o SessionManager
from utils.call_logger import CallLoggerManager  # Importamos o CallLoggerManager

# Constante para o timeout de verificação de terminação
TERMINATE_CHECK_INTERVAL = 0.5  # segundos

# Caso você use um "StateMachine" separado, pode remover ou adaptar:
# from state_machine import State

logger = logging.getLogger(__name__)

# Identificador do formato SLIN
KIND_SLIN = 0x10

# Podemos instanciar um SessionManager aqui como singleton/global.
# Se preferir criar em outro lugar, adapte.
session_manager = SessionManager()

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
        logger.info(f"Configurações carregadas: silence={SILENCE_THRESHOLD_SECONDS}s, resident_max_silence={RESIDENT_MAX_SILENCE_SECONDS}s, transmission_delay={TRANSMISSION_DELAY_MS}s, post_audio_delay={POST_AUDIO_DELAY_SECONDS}s, discard_buffer={DISCARD_BUFFER_FRAMES} frames, goodbye_delay={GOODBYE_DELAY_SECONDS}s")
except Exception as e:
    logger.warning(f"Erro ao carregar config.json, usando valores padrão: {e}")
    SILENCE_THRESHOLD_SECONDS = 2.0
    RESIDENT_MAX_SILENCE_SECONDS = 45.0
    TRANSMISSION_DELAY_MS = 0.02
    POST_AUDIO_DELAY_SECONDS = 0.5
    DISCARD_BUFFER_FRAMES = 25
    GOODBYE_DELAY_SECONDS = 3.0


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


async def send_goodbye_and_terminate(writer, session, call_id, role, call_logger=None):
    """
    Envia uma mensagem de despedida final e encerra a conexão.
    """
    try:
        # Obter mensagem de despedida baseada na configuração
        # Decisão baseada no papel e no estado da conversa
        if role == "visitante":
            if session.intent_data.get("authorization_result") == "authorized":
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
    
    start_time = time.time()
    chunk_size = 320
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i : i + chunk_size]
        header = struct.pack(">B H", KIND_SLIN, len(chunk))
        writer.write(header + chunk)
        await writer.drain()
        # Pequeno atraso para não encher o buffer do lado do Asterisk
        await asyncio.sleep(TRANSMISSION_DELAY_MS)
    
    # Registrar conclusão
    if call_id:
        duration_ms = (time.time() - start_time) * 1000
        call_logger.log_event("AUDIO_SEND_COMPLETE", {
            "target": "visitor" if is_visitor else "resident",
            "duration_ms": round(duration_ms, 2)
        })


async def receber_audio_visitante(reader: asyncio.StreamReader, call_id: str):
    """
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
        if is_listening_mode and kind == KIND_SLIN and len(audio_chunk) == 320:
            # Avalia VAD
            is_voice = vad.is_speech(audio_chunk, 8000)
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
                            
                            # Transcrever com medição de tempo
                            start_time = time.time()
                            texto = await transcrever_audio_async(audio_data)
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
        elif kind != KIND_SLIN or len(audio_chunk) != 320:
            logger.warning(f"[{call_id}] Chunk inválido do visitante. kind={kind}, len={len(audio_chunk)}")
            call_logger.log_error("INVALID_CHUNK", 
                                "Chunk de áudio inválido recebido do visitante", 
                                {"kind": kind, "length": len(audio_chunk)})

    # Ao sair, encerrou a conexão
    logger.info(f"[{call_id}] receber_audio_visitante terminou.")


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
            
            # Sinalizar que o encerramento está concluído
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
            
            # Adicionar um pequeno atraso após o envio do áudio para garantir
            # que o áudio seja totalmente reproduzido antes de voltar a escutar
            await asyncio.sleep(POST_AUDIO_DELAY_SECONDS)
            
            # Mudar de volta para USER_TURN para que o sistema possa escutar o usuário
            session.visitor_state = "USER_TURN"
            call_logger.log_event("STATE_CHANGE", {
                "from": "IA_TURN",
                "to": "USER_TURN",
                "reason": "ia_finished_speaking"
            })


async def iniciar_servidor_audiosocket_visitante(reader, writer):
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    
    # Converter para UUID com formato de traços
    import uuid
    call_id = str(uuid.UUID(bytes=call_id_bytes))

    logger.info(f"[VISITANTE] Recebido Call ID: {call_id}")
    
    # Inicializar logger específico para esta chamada
    call_logger = CallLoggerManager.get_logger(call_id)
    call_logger.log_event("CALL_SETUP", {
        "type": "visitor",
        "call_id": call_id
    })

    session_manager.create_session(call_id)

    # SAUDAÇÃO:
    welcome_msg = "Olá, seja bem-vindo! Em que posso ajudar?"
    call_logger.log_event("GREETING", {"message": welcome_msg})
    
    session_manager.enfileirar_visitor(
        call_id,
        welcome_msg
    )

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
    
    # Remover logger para liberar recursos
    CallLoggerManager.remove_logger(call_id)
    
    writer.close()
    await writer.wait_closed()


# ------------------------
# MORADOR
# ------------------------

async def receber_audio_morador(reader: asyncio.StreamReader, call_id: str):
    """
    Versão equivalente para o morador, com controle de estado para evitar retroalimentação
    e suporte para encerramento gracioso.
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
        if is_listening_mode and kind == KIND_SLIN and len(audio_chunk) == 320:
            # Para morador, usamos uma detecção mais agressiva para palavras curtas como "Sim"
            is_voice = vad.is_speech(audio_chunk, 8000)
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
                            
                            # Transcrever com medição de tempo
                            start_time = time.time()
                            texto = await transcrever_audio_async(audio_data)
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
                                        
                                        # Iniciar processo de encerramento imediato após tratar a resposta
                                        logger.info(f"[{call_id}] Iniciando encerramento da sessão após resposta do morador")
                                        session_manager.end_session(call_id)
                                        
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
                                            final_msg = f"Sua {intent_type if intent_type else 'entrada'} foi autorizada pelo morador. Obrigado por utilizar nossa portaria inteligente."
                                            session_manager.enfileirar_visitor(call_id, final_msg)
                                        elif authorization_result == "denied":
                                            # Enviar mensagem explícita ao visitante sobre negação
                                            visitor_msg = f"Infelizmente o morador não autorizou sua {intent_type if intent_type else 'entrada'} neste momento."
                                            logger.info(f"[{call_id}] Notificando visitante explicitamente da negação: {visitor_msg}")
                                            session_manager.enfileirar_visitor(call_id, visitor_msg)
                                            
                                            # Forçar mensagem final - essencial para fechar o ciclo
                                            final_msg = f"Sua {intent_type if intent_type else 'entrada'} não foi autorizada pelo morador. Obrigado por utilizar nossa portaria inteligente."
                                            session_manager.enfileirar_visitor(call_id, final_msg)
                            else:
                                call_logger.log_error("TRANSCRIPTION_FAILED", 
                                                    "Falha ao transcrever áudio do morador", 
                                                    {"audio_size": len(audio_data)})
                                # Voltar ao modo de escuta, já que não foi possível processar
                                is_listening_mode = True
        elif kind != KIND_SLIN or len(audio_chunk) != 320:
            logger.warning(f"[{call_id}] Chunk inválido do morador. kind={kind}, len={len(audio_chunk)}")
            call_logger.log_error("INVALID_CHUNK", 
                                "Chunk de áudio inválido recebido do morador", 
                                {"kind": kind, "length": len(audio_chunk)})

    logger.info(f"[{call_id}] receber_audio_morador terminou.")


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
            
            # Sinalizar que o encerramento está concluído
            # Não chamamos _complete_session_termination aqui, pois o visitante 
            # tem maior precedência e fará isso
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
            
            # Adicionar um pequeno atraso após o envio do áudio para garantir
            # que o áudio seja totalmente reproduzido antes de voltar a escutar
            await asyncio.sleep(POST_AUDIO_DELAY_SECONDS)
            
            # Mudar de volta para USER_TURN para que o sistema possa escutar o morador
            session.resident_state = "USER_TURN"
            call_logger.log_event("RESIDENT_STATE_CHANGE", {
                "from": "IA_TURN",
                "to": "USER_TURN",
                "reason": "ia_finished_speaking_to_resident"
            })


async def iniciar_servidor_audiosocket_morador(reader, writer):
    header = await reader.readexactly(3)
    kind = header[0]
    length = int.from_bytes(header[1:3], "big")
    call_id_bytes = await reader.readexactly(length)
    
    # Converter para UUID com formato de traços
    import uuid
    call_id = str(uuid.UUID(bytes=call_id_bytes))

    logger.info(f"[MORADOR] Recebido Call ID: {call_id}")
    
    # Inicializar logger específico para esta chamada
    call_logger = CallLoggerManager.get_logger(call_id)
    call_logger.log_event("CALL_SETUP", {
        "type": "resident",
        "call_id": call_id
    })

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

    writer.close()
    await writer.wait_closed()
    
    logger.info(f"[{call_id}] Conexão do morador encerrada.")
    call_logger.log_call_ended("resident_connection_closed", call_duration)
    
    # Remover logger para liberar recursos
    CallLoggerManager.remove_logger(call_id)
