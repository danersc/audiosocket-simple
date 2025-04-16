import asyncio
import logging
import webrtcvad
import struct
from speech_service import transcrever_audio_async, sintetizar_fala_async
from ai_service import enviar_mensagem_para_ia, extrair_mensagem_da_resposta, obter_estado_chamada
from state_machine import State
import os

KIND_SLIN = 0x10
logger = logging.getLogger(__name__)

async def receber_audio(reader, state_machine, audio_queue):
    try:
        while True:
            header = await reader.readexactly(3)
            kind = header[0]
            length = int.from_bytes(header[1:3], 'big')
            audio_chunk = await reader.readexactly(length)
            if kind == KIND_SLIN and len(audio_chunk) == 320 and state_machine.is_user_turn():
                await audio_queue.put(audio_chunk)
    except asyncio.IncompleteReadError:
        logger.info("Cliente desconectado")
    except Exception as e:
        logger.error(f"Erro ao receber áudio: {e}")

async def enviar_audio(writer, dados_audio, origem="desconhecida"):
    logger.info(f"Iniciando envio de áudio sintetizado (origem: {origem}), tamanho total: {len(dados_audio)} bytes")
    chunk_size = 320
    for i in range(0, len(dados_audio), chunk_size):
        chunk = dados_audio[i:i + chunk_size]
        if chunk:
            writer.write(struct.pack('>B H', KIND_SLIN, len(chunk)) + chunk)
            await writer.drain()
            await asyncio.sleep(0.02)
    logger.info(f"Envio de áudio concluído (origem: {origem})")

async def enviar_audio_em_loop(writer, caminho_audio):
    with open(caminho_audio, 'rb') as f:
        dados_audio = f.read()

    chunk_size = 320
    try:
        while True:
            for i in range(0, len(dados_audio), chunk_size):
                chunk = dados_audio[i:i + chunk_size]
                if chunk:
                    writer.write(struct.pack('>B H', KIND_SLIN, len(chunk)) + chunk)
                    await writer.drain()
                    await asyncio.sleep(0.02)
    except asyncio.CancelledError:
        logger.info("Áudio de espera cancelado.")

async def monitorar_waiting(state_machine, writer, caminho_audio):
    waiting_task = None
    while True:
        await state_machine.wait_for_state(State.WAITING)
        logger.info("Estado WAITING detectado, aguardando 3 segundos antes de iniciar áudio de espera.")
        try:
            await asyncio.wait_for(state_machine.wait_for_state_change(), timeout=3.0)
            logger.info("Estado WAITING terminou antes dos 3 segundos, áudio de espera não será iniciado.")
        except asyncio.TimeoutError:
            if state_machine.is_waiting():
                logger.info("Timeout atingido em WAITING, iniciando áudio de espera.")
                waiting_task = asyncio.create_task(enviar_audio_em_loop(writer, caminho_audio))

                await state_machine.wait_for_state_change()
                if waiting_task:
                    waiting_task.cancel()
                    waiting_task = None

async def processar_audio(audio_queue, vad, state_machine, writer):
    frames = []
    is_speaking = False
    silence_start = None

    while True:
        chunk = await audio_queue.get()
        is_voice = vad.is_speech(chunk, 8000)

        if is_voice:
            frames.append(chunk)
            is_speaking = True
            silence_start = None
        elif is_speaking:
            if silence_start is None:
                silence_start = asyncio.get_event_loop().time()
            elif asyncio.get_event_loop().time() - silence_start > 2.0:
                is_speaking = False
                audio_data = b''.join(frames)
                frames.clear()

                if audio_data:
                    state_machine.transition_to(State.WAITING)
                    logger.info("Áudio capturado completo, iniciando transcrição.")

                    texto = await transcrever_audio_async(audio_data)

                    if not texto:
                        logger.warning("Nenhuma transcrição obtida.")
                        state_machine.transition_to(State.USER_TURN)
                        continue

                    logger.info(f"Texto transcrito: {texto}")

                    resposta = await enviar_mensagem_para_ia(texto, state_machine.get_conversation_id())
                    mensagem = extrair_mensagem_da_resposta(resposta)
                    proximo_estado = obter_estado_chamada(resposta)

                    logger.info(f"Mensagem recebida da IA: {mensagem}")
                    logger.info(f"Estado sugerido pela API: {proximo_estado}")

                    if mensagem:
                        audio_resposta = await sintetizar_fala_async(mensagem)
                        if audio_resposta and len(audio_resposta) > 0:
                            state_machine.transition_to(State.IA_TURN)
                            logger.info("Enviando áudio sintetizado ao usuário.")
                            await enviar_audio(writer, audio_resposta, origem="IA Response")
                            await asyncio.sleep(0.5)
                        else:
                            logger.warning("Resposta de áudio vazia.")

                    if proximo_estado:
                        logger.info(f"Aplicando estado '{proximo_estado}' após envio completo do áudio.")
                        state_machine.transition_to(State[proximo_estado])
                    else:
                        state_machine.transition_to(State.USER_TURN)

async def iniciar_servidor_audiosocket(reader, writer, state_machine):
    vad = webrtcvad.Vad(2)
    audio_queue = asyncio.Queue()
    caminho_audio_espera = os.path.join('audio', 'waiting.slin')

    logger.info("Iniciando síntese de áudio para mensagem de saudação.")
    greeting_audio = await sintetizar_fala_async("Condomínio Apoena, em que posso ajudar?")
    if greeting_audio:
        state_machine.transition_to(State.IA_TURN)
        logger.info("Enviando áudio da mensagem inicial ao cliente.")
        await enviar_audio(writer, greeting_audio, origem="Greeting")
        await asyncio.sleep(0.5)

    state_machine.transition_to(State.USER_TURN)

    # Adiciona a tarefa de monitoramento do WAITING independentemente
    await asyncio.gather(
        receber_audio(reader, state_machine, audio_queue),
        processar_audio(audio_queue, vad, state_machine, writer),
        monitorar_waiting(state_machine, writer, caminho_audio_espera)
    )
