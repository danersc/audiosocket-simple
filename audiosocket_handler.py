#!/usr/bin/env python3
# audiosocket_handler.py - Manipulador de conexão AudioSocket

import struct
import time
import logging
import threading
import asyncio
import webrtcvad
import os
import json
from dotenv import load_dotenv
from state_machine import StateMachine, State
from speech_service import transcrever_audio, sintetizar_fala
from ai_service import enviar_mensagem_para_ia, extrair_mensagem_da_resposta, obter_estado_chamada


# Carrega variáveis de ambiente
load_dotenv()

# Configuração de logging
logger = logging.getLogger(__name__)

# Carregar configuração do sistema
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
    logger.info(f"Configuração carregada de {CONFIG_FILE}")
except Exception as e:
    logger.error(f"Erro ao carregar configuração: {e}")
    CONFIG = {
        "greeting": {
            "message": "Condomínio Apoena, em que posso ajudar?",
            "voice": "pt-BR-AntonioNeural",
            "delay_seconds": 2
        },
        "system": {
            "default_state": "STANDBY",
            "silence_threshold_seconds": 2.0
        }
    }
    logger.info("Usando configuração padrão")

# Definição dos tipos de mensagem do AudioSocket
KIND_HANGUP = 0x00
KIND_ID = 0x01
KIND_SILENCE = 0x02
KIND_SLIN = 0x10
KIND_ERROR = 0xff

# Configurações do VAD (Voice Activity Detection)
VAD_AGRESSIVIDADE = 2  # Nível de agressividade (0-3)
SILENCE_THRESHOLD_SECONDS = float(os.getenv('SILENCE_THRESHOLD_SECONDS', '2.0'))

def next_message(conn):
    """
    Lê a próxima mensagem do AudioSocket.
    
    Args:
        conn: Socket de conexão
        
    Returns:
        Tupla com o tipo da mensagem e o payload, ou (None, None) em caso de erro
    """
    try:
        # Lê o cabeçalho (3 bytes)
        header = conn.recv(3)
        if not header:
            return None, None
        while len(header) < 3:
            more = conn.recv(3 - len(header))
            if not more:
                return None, None
            header += more
            
        kind = header[0]
        length = struct.unpack('>H', header[1:3])[0]  # Big-endian unsigned short
        
        # Lê o payload
        payload = b''
        while len(payload) < length:
            data = conn.recv(length - len(payload))
            if not data:
                break
            payload += data
            
        return kind, payload
    
    except Exception as e:
        logger.error(f"Erro ao ler mensagem: {e}")
        return None, None

async def enviar_audio_para_cliente(conn, dados_audio):
    try:
        chunk_size = 320
        for i in range(0, len(dados_audio), chunk_size):
            chunk = dados_audio[i:i+chunk_size]
            if not chunk:
                continue
            mensagem_slin = struct.pack('>B H', KIND_SLIN, len(chunk)) + chunk
            conn.sendall(mensagem_slin)
            await asyncio.sleep(0.02)  # await aqui é crucial
        logger.info(f"Áudio enviado completamente ({len(dados_audio)} bytes)")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar áudio: {e}")
        return False


async def processar_audio(conn, frames, state_machine):
    try:
        logger.info("Mudando para estado WAITING para processamento de áudio")
        state_machine.transition_to(State.WAITING)

        segmento_audio = b''.join(frames)
        transcricao = transcrever_audio(segmento_audio)
        if not transcricao:
            state_machine.transition_to(State.USER_TURN)
            return

        state_machine.registrar_transcricao_usuario(transcricao)
        state_machine.transition_to(State.IA_TURN)

        resposta = await enviar_mensagem_para_ia(transcricao, state_machine.get_conversation_id())
        mensagem = extrair_mensagem_da_resposta(resposta)
        state_machine.registrar_transcricao_ia(mensagem, resposta)

        if not mensagem:
            state_machine.transition_to(State.USER_TURN)
            return

        dados_audio_slin = sintetizar_fala(mensagem)
        if not dados_audio_slin:
            state_machine.transition_to(State.USER_TURN)
            return

        # Aqui está o ponto crucial:
        enviado = await enviar_audio_para_cliente(conn, dados_audio_slin)

        if not enviado:
            state_machine.transition_to(State.USER_TURN)
            return

        await asyncio.sleep(0.5)  # Pequeno atraso para garantir silêncio absoluto após a IA terminar

        # Agora sim podemos retornar ao USER_TURN
        proximo_estado = obter_estado_chamada(resposta)
        if proximo_estado == "USER_TURN":
            state_machine.transition_to(State.USER_TURN)
        elif proximo_estado == "WAITING":
            state_machine.transition_to(State.WAITING)
        elif proximo_estado == "IA_TURN":
            state_machine.transition_to(State.IA_TURN)
        else:
            state_machine.transition_to(State.USER_TURN)

    except Exception as e:
        logger.error(f"Erro ao processar áudio: {e}")
        state_machine.transition_to(State.USER_TURN)

def iniciar_servidor_audiosocket(conn, endereco, state_machine):
    """
    Inicia o servidor AudioSocket para uma conexão específica.
    
    Args:
        conn: Socket de conexão
        endereco: Endereço do cliente
        state_machine: Máquina de estados
        
    Returns:
        None
    """
    logger.info(f"Iniciando servidor AudioSocket para cliente {endereco}")
    
    # Configuração do VAD
    RATE = 8000  # Taxa de amostragem em Hz
    FRAME_DURATION_MS = 20  # Duração do frame em ms
    FRAME_SIZE = int(RATE * FRAME_DURATION_MS / 1000) * 2  # 320 bytes (8000Hz * 20ms * 2 bytes)
    
    vad = webrtcvad.Vad(VAD_AGRESSIVIDADE)
    
    # Estado do VAD
    is_speaking = False
    silence_start = None
    frames = []
    buffer_vad = b''
    # Flag para indicar se a saudação já foi enviada
    greeting_sent = False
    
    
    # Inicia o event loop para processamento assíncrono
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Lê a mensagem de ID
        kind, payload = next_message(conn)
        if kind != KIND_ID:
            logger.error(f"Esperado mensagem KIND_ID, mas recebido {kind}")
            conn.close()
            return
            
        call_id = payload  # Call ID é um UUID (16 bytes)
        logger.info(f"Recebido Call ID: {call_id.hex()}")
        
        # Inicia uma nova conversa
        # Isso gera um novo ID de conversa e mantém o estado como STANDBY inicialmente
        conversation_id = state_machine.start_new_conversation(standby=True)
        
        # Agenda o envio da mensagem de saudação após o delay configurado
        greeting_delay = CONFIG["greeting"]["delay_seconds"]
        greeting_message = CONFIG["greeting"]["message"]
        
        # Define a função para enviar a saudação
        async def send_greeting():
            nonlocal greeting_sent
            
            # Espera o delay configurado
            await asyncio.sleep(greeting_delay)
            
            logger.info(f"Enviando saudação: '{greeting_message}'")
            
            # Sintetiza a saudação
            dados_audio_slin = sintetizar_fala(greeting_message)
            
            if dados_audio_slin:
                # Envia o áudio para o cliente
                enviar_audio_para_cliente(conn, dados_audio_slin)
                
                # Registra a transcrição da saudação para o debug
                state_machine.registrar_transcricao_sistema(greeting_message)
                
                # Ativa o turno do usuário após enviar a saudação
                state_machine.transition_to(State.USER_TURN)
                greeting_sent = True
                
                logger.info("Saudação enviada, ativando turno do usuário")
            else:
                logger.error("Falha ao sintetizar saudação")
        
        # Agenda o envio da saudação e a executa imediatamente
        # em vez de apenas criar a tarefa assíncrona
        loop.run_until_complete(send_greeting())
        logger.info("Saudação agendada e executada com sucesso")
        
        # Loop principal para receber mensagens
        while True:
            kind, payload = next_message(conn)
            
            if kind is None:
                logger.info("Conexão fechada pelo cliente")
                break
                
            if kind == KIND_HANGUP:
                logger.info("Recebido mensagem de Hangup")
                # Finaliza a conversa atual, retornando ao estado STANDBY
                state_machine.end_conversation()
                break
                
            elif kind == KIND_ERROR:
                logger.error("Recebido mensagem de Erro")
                
            elif kind == KIND_SLIN:
                # Verifica se está no estado adequado para processamento de áudio do usuário
                # IMPORTANTE: Só processamos áudio quando estamos especificamente no estado USER_TURN
                # Durante os estados IA_TURN e WAITING, o áudio é completamente ignorado
                if not state_machine.is_user_turn():
                    # Reset completo quando não está em USER_TURN
                    is_speaking = False
                    silence_start = None
                    frames = []
                    buffer_vad = b''  # Limpa completamente o buffer VAD
                    continue
                    
                # Acumula os dados de áudio SLIN
                buffer_vad += payload
                
                # Processa os dados de áudio com VAD
                while len(buffer_vad) >= FRAME_SIZE:
                    frame = buffer_vad[:FRAME_SIZE]
                    buffer_vad = buffer_vad[FRAME_SIZE:]
                    
                    # Realiza o VAD no frame
                    is_speech_frame = vad.is_speech(frame, RATE)
                    
                    if is_speech_frame:
                        if not is_speaking:
                            logger.info("Detecção de voz iniciada")
                            is_speaking = True
                            silence_start = None
                        frames.append(frame)
                    else:
                        if is_speaking:
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start > SILENCE_THRESHOLD_SECONDS:
                                logger.info(f"Silêncio detectado por {SILENCE_THRESHOLD_SECONDS} segundos. Processando áudio.")
                                is_speaking = False
                                silence_start = None
                                
                                # Verifica novamente se ainda estamos no estado USER_TURN antes de processar
                                # Isso é uma proteção extra contra mudanças de estado durante a detecção
                                if frames and state_machine.is_user_turn():
                                    logger.info(f"Detectado segmento de fala completo, processando {len(frames)} frames")
                                    loop.run_until_complete(processar_audio(conn, frames, state_machine))
                                    frames = []  # Limpa os frames para a próxima interação
                                else:
                                    if not frames:
                                        logger.warning("Detectado silêncio, mas não há frames para processar")
                                    elif not state_machine.is_user_turn():
                                        logger.warning(f"Estado mudou para {state_machine.get_state()}, ignorando áudio detectado")
                                        frames = []  # Limpa os frames já que não estamos mais no estado USER_TURN
                                
                        else:
                            # Não estamos falando, resetar silence_start
                            silence_start = None
    
    except Exception as e:
        logger.error(f"Erro no servidor AudioSocket: {e}")
    finally:
        conn.close()
        loop.close()
        # Encerra a conversa, voltando ao estado STANDBY
        state_machine.end_conversation()
        logger.info(f"Conexão com cliente {endereco} fechada")
