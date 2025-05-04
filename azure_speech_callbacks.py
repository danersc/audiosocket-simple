import logging
import azure.cognitiveservices.speech as speechsdk
import wave
import os
import time

logger = logging.getLogger(__name__)

DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

SAMPLE_RATE = 8000
CHANNELS = 1
BITS_PER_SAMPLE = 16

class SpeechCallbacks:
    def __init__(self, call_id, session_manager, is_visitor=True, call_logger=None):
        self.call_id = call_id
        self.audio_buffer = []
        self.recognition_count = 0
        self.session_manager = session_manager  # sessão_manager injetado
        self.is_visitor = is_visitor
        self.call_logger = call_logger
        self.process_callback = None

    def set_process_callback(self, callback):
        """Define a função de callback para processar texto reconhecido"""
        self.process_callback = callback

    def log_event(self, event_type, data=None):
        logger.info(f"[{self.call_id}] {event_type}: {data}")
    
    def reset_audio_detection(self):
        """
        Reseta a detecção de áudio e limpa buffers após a IA falar.
        Deve ser chamado sempre que for o turno da IA (estado IA_TURN).
        
        Este método é parte crucial do mecanismo anti-eco:
        1. Ele limpa qualquer áudio que possa ter sido capturado durante a transição de estados
        2. Previne que o áudio da própria IA seja processado como se fosse do usuário
        3. É chamado no início dos turnos da IA (em enviar_mensagens_visitante/morador)
        
        O Azure Speech continuará capturando áudio do socket, mas add_audio_chunk
        verificará o estado atual e ignorará todo o áudio durante o turno da IA.
        """
        self.audio_buffer.clear()
        self.log_event("AUDIO_DETECTION_RESET", "Resetando detecção de áudio após IA falar")

    def on_recognized(self, evt):
        # Verificar se estamos no turno do usuário
        session = self.session_manager.get_session(self.call_id)
        if not session:
            return
            
        role_state = session.visitor_state if self.is_visitor else session.resident_state
        if role_state == "IA_TURN":
            self.log_event("RECOGNITION_IGNORED", f"Reconhecimento ignorado durante turno da IA: {role_state}")
            return
    
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self.log_event("RECOGNIZED", text)

            self.recognition_count += 1
            filename = os.path.join(
                DEBUG_DIR,
                f"{self.call_id}_recognized_{self.recognition_count}_{int(time.time())}.wav"
            )
            self.save_audio_to_wav(filename)
            
            # Processar texto reconhecido
            if self.is_visitor:
                # Enviar texto reconhecido ao session_manager para visitante
                self.session_manager.process_visitor_text(self.call_id, text)
            elif self.process_callback:
                # Usar callback customizado para o morador
                import asyncio
                # Criar uma função que executa a coroutine corretamente em uma thread separada
                def run_async_process():
                    try:
                        asyncio.run(self.process_callback(text, b''.join(self.audio_buffer)))
                        self.log_event("PROCESS_CALLBACK_COMPLETED", f"Processamento de texto concluído para morador")
                    except Exception as e:
                        self.log_event("PROCESS_CALLBACK_ERROR", f"Erro: {e}")
                
                # Executar em uma thread em segundo plano
                import threading
                process_thread = threading.Thread(target=run_async_process)
                process_thread.daemon = True
                process_thread.start()
                self.log_event("PROCESS_CALLBACK_STARTED", "Iniciado processamento de texto do morador em thread separada")
                
            self.audio_buffer.clear()

        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            self.log_event("NO_MATCH", evt.result.no_match_details)

            filename = os.path.join(
                DEBUG_DIR,
                f"{self.call_id}_nomatch_{int(time.time())}.wav"
            )
            self.save_audio_to_wav(filename)
            
            # Processar áudio mesmo sem reconhecimento (fallback para morador)
            if len(self.audio_buffer) > 0 and self.process_callback and not self.is_visitor:
                import asyncio
                self.log_event("PROCESSING_AUDIO_WITHOUT_RECOGNITION", f"Buffer size: {len(self.audio_buffer)}")
                
                # Usar a mesma abordagem de thread separada
                def run_async_process_nomatch():
                    try:
                        asyncio.run(self.process_callback(None, b''.join(self.audio_buffer)))
                        self.log_event("PROCESS_CALLBACK_NOMATCH_COMPLETED", f"Processamento de áudio sem reconhecimento concluído")
                    except Exception as e:
                        self.log_event("PROCESS_CALLBACK_NOMATCH_ERROR", f"Erro: {e}")
                
                # Executar em uma thread em segundo plano
                import threading
                process_thread = threading.Thread(target=run_async_process_nomatch)
                process_thread.daemon = True
                process_thread.start()
                self.log_event("PROCESS_CALLBACK_NOMATCH_STARTED", "Iniciado processamento de áudio sem reconhecimento em thread separada")
                
            self.audio_buffer.clear()

    def on_speech_start_detected(self, evt):
        """Callback para quando o início da fala é detectado pelo Azure Speech"""
        # Verificar se está no turno do usuário (ou seja, se a IA não está falando)
        session = self.session_manager.get_session(self.call_id)
        if not session:
            return
            
        role_state = session.visitor_state if self.is_visitor else session.resident_state
        if role_state == "IA_TURN":
            self.log_event("SPEECH_START_IGNORED", f"Detecção ignorada durante turno da IA: {role_state}")
            return
            
        self.log_event("SPEECH_START_DETECTED", "Início de fala detectado")
    
    def on_speech_end_detected(self, evt):
        """Callback para quando o fim da fala é detectado pelo Azure Speech"""
        # Verificar se está no turno do usuário
        session = self.session_manager.get_session(self.call_id)
        if not session:
            return
            
        role_state = session.visitor_state if self.is_visitor else session.resident_state
        if role_state == "IA_TURN":
            self.log_event("SPEECH_END_IGNORED", f"Detecção ignorada durante turno da IA: {role_state}")
            return
            
        self.log_event("SPEECH_END_DETECTED", "Fim de fala detectado")

    def register_callbacks(self, recognizer):
        recognizer.recognized.connect(self.on_recognized)
        recognizer.canceled.connect(lambda evt: self.log_event("CANCELED", evt.reason))
        recognizer.session_started.connect(lambda evt: self.log_event("SESSION_STARTED", evt.session_id))
        recognizer.session_stopped.connect(lambda evt: self.log_event("SESSION_STOPPED", evt.session_id))
        
        # Adicionar callbacks para detecção de início e fim de fala
        recognizer.speech_start_detected.connect(self.on_speech_start_detected)
        recognizer.speech_end_detected.connect(self.on_speech_end_detected)

    def add_audio_chunk(self, chunk):
        """
        Adiciona um chunk de áudio ao buffer apenas se for o turno do usuário
        """
        session = self.session_manager.get_session(self.call_id)
        if not session:
            return
            
        role_state = session.visitor_state if self.is_visitor else session.resident_state
        role_name = "visitante" if self.is_visitor else "morador"
        
        # Durante o turno da IA, ignorar completamente o áudio recebido
        if role_state == "IA_TURN":
            # Log a cada 50 chunks para não inundar os logs
            if len(self.audio_buffer) % 50 == 0:
                self.log_event("AUDIO_CHUNK_IGNORED", 
                              f"Ignorando áudio durante turno da IA ({role_name}: {role_state})")
            return
            
        # Somente adicionar áudio ao buffer se for o turno do usuário
        self.audio_buffer.append(chunk)
        
        # Log a cada 50 chunks adicionados
        if len(self.audio_buffer) % 50 == 0:
            self.log_event("AUDIO_CHUNK_ADDED", 
                          f"Buffer: {len(self.audio_buffer)} chunks ({role_name}: {role_state})")

    def save_audio_to_wav(self, filename):
        if not self.audio_buffer:
            self.log_event("SAVE_AUDIO_SKIPPED", "Buffer vazio.")
            return

        try:
            audio_data = b''.join(self.audio_buffer)
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(BITS_PER_SAMPLE // 8)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data)

            self.log_event("AUDIO_SAVED", filename)

        except Exception as e:
            self.log_event("ERROR_SAVING_AUDIO", str(e))
