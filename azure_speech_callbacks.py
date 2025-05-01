"""
Módulo para funções de callback do Azure Speech SDK.

Este módulo contém implementações de funções de callback que são usadas
ao interagir com o Azure Speech SDK para detecção de voz.
"""

import asyncio
import logging
import time
from typing import List, Optional, Callable, Any

import azure.cognitiveservices.speech as speechsdk

logger = logging.getLogger(__name__)

class SpeechCallbacks:
    """
    Classe para gerenciar callbacks do Azure Speech SDK.
    
    Esta classe gerencia todos os callbacks usados com o Azure Speech SDK
    e resolve problemas de escopo e referência com as funções de callback.
    """
    
    def __init__(self, call_id: str, 
                 is_visitor: bool = True,
                 call_logger=None):
        """
        Inicializa os callbacks do Azure Speech.
        
        Args:
            call_id: ID da chamada
            is_visitor: True se for visitante, False se for morador
            call_logger: Logger específico da chamada
        """
        self.call_id = call_id
        self.is_visitor = is_visitor
        self.call_logger = call_logger
        
        # Estado interno
        self.collecting_audio = False
        self.audio_buffer: List[bytes] = []
        self.speech_detected = False
        
        # Controle do timeout para recognition após speech_end
        self.speech_end_time = None
        self.recognition_timeout = 5.0  # 5 segundos de timeout
        
        # Função de processamento a ser definida pelo chamador
        self.process_callback: Optional[Callable] = None
    
    def set_process_callback(self, callback: Callable[[str, bytes], Any]):
        """Define a função de callback para processar texto reconhecido."""
        self.process_callback = callback
    
    def on_recognized(self, evt):
        """Callback quando a fala é reconhecida completamente."""
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            # Fala foi reconhecida com sucesso
            logger.info(f"[{self.call_id}] Azure Speech reconheceu texto: {evt.result.text}")
            
            # Criar cópia local dos dados para processar para evitar problemas de concorrência
            text_to_process = evt.result.text
            audio_data = b"".join(self.audio_buffer) if self.audio_buffer else b""
            
            # Limpar o timeout já que o reconhecimento foi bem-sucedido
            self.speech_end_time = None
            
            # Processar texto reconhecido via thread-safe
            if self.process_callback:
                logger.info(f"[{self.call_id}] Enviando texto reconhecido para processamento: {text_to_process}")
                loop = asyncio.get_event_loop()
                future = asyncio.run_coroutine_threadsafe(
                    self.process_callback(text_to_process, audio_data), 
                    loop
                )
                # Adicionar callback para log de sucesso/erro
                future.add_done_callback(lambda f: 
                    logger.info(f"[{self.call_id}] Processamento concluído com sucesso") if not f.exception() 
                    else logger.error(f"[{self.call_id}] Erro no processamento: {f.exception()}")
                )
            else:
                logger.error(f"[{self.call_id}] Processo_callback não definido! Não é possível processar texto reconhecido")
            
            # Limpar buffer e preparar para próxima fala
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
        
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            # Nenhuma fala foi reconhecida
            role = "visitante" if self.is_visitor else "morador"
            logger.info(f"[{self.call_id}] Azure Speech não reconheceu fala do {role} (NoMatch)")
            
            # Limpar o timeout já que o reconhecimento foi concluído (mesmo que sem sucesso)
            self.speech_end_time = None
            
            # Se havia coletado algum áudio, ainda processar como possível "sim" curto
            if len(self.audio_buffer) > 0 and self.speech_detected:
                # Criar cópia dos dados para processar
                audio_data = b"".join(self.audio_buffer)
                logger.info(f"[{self.call_id}] Processando áudio não reconhecido (possível fala curta) - {len(audio_data)} bytes")
                
                # Processar como texto vazio (será processado apenas o áudio)
                if self.process_callback:
                    loop = asyncio.get_event_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.process_callback("", audio_data), 
                        loop
                    )
                    # Adicionar callback para log de sucesso/erro
                    future.add_done_callback(lambda f: 
                        logger.info(f"[{self.call_id}] Processamento de áudio concluído com sucesso") if not f.exception() 
                        else logger.error(f"[{self.call_id}] Erro no processamento de áudio: {f.exception()}")
                    )
                else:
                    logger.error(f"[{self.call_id}] Processo_callback não definido! Não é possível processar áudio")
            
            # Limpar buffer e preparar para próxima fala
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
    
    def on_speech_start_detected(self, evt):
        """Callback quando o início de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        logger.info(f"[{self.call_id}] Início de fala do {role} detectado pelo Azure Speech")
        if self.call_logger:
            self.call_logger.log_speech_detected(is_visitor=self.is_visitor)
        self.collecting_audio = True
        self.speech_detected = True
    
    def on_speech_end_detected(self, evt):
        """Callback quando o fim de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        logger.info(f"[{self.call_id}] Fim de fala do {role} detectado pelo Azure Speech - collecting={self.collecting_audio}, buffer={len(self.audio_buffer)}")
        if self.call_logger:
            self.call_logger.log_speech_ended(0, is_visitor=self.is_visitor)  # Duração desconhecida neste ponto
        
        # IMPORTANTE: Quando detectamos o fim da fala, esperamos que em breve on_recognized seja chamado
        # Se isso não acontecer em um tempo razoável, pode ser um problema com o Azure Speech SDK
        
        # Configuramos um timeout para garantir que o áudio será processado mesmo que on_recognized nunca seja chamado
        self.speech_end_time = time.time()
        
        # Agendamos um timer para verificar o timeout
        loop = asyncio.get_event_loop()
        loop.call_later(self.recognition_timeout, self._check_recognition_timeout)
        
        # Mantemos collecting_audio=True até que on_recognized seja chamado
    
    def on_recognizing(self, evt):
        """Callback para resultados parciais de reconhecimento."""
        role = "visitante" if self.is_visitor else "morador"
        logger.info(f"[{self.call_id}] Reconhecimento parcial do {role} via Azure Speech: {evt.result.text}")
        # Importante: Se estamos recebendo resultados parciais, isso significa que o sistema está funcionando
    
    def on_session_started(self, evt):
        """Callback quando a sessão de reconhecimento é iniciada."""
        logger.info(f"[{self.call_id}] Sessão de reconhecimento Azure Speech iniciada: {evt.session_id}")
    
    def on_session_stopped(self, evt):
        """Callback quando a sessão de reconhecimento é encerrada."""
        logger.info(f"[{self.call_id}] Sessão de reconhecimento Azure Speech encerrada: {evt.session_id}")
    
    def on_canceled(self, evt):
        """Callback quando o reconhecimento é cancelado."""
        logger.error(f"[{self.call_id}] Reconhecimento Azure Speech cancelado: {evt.reason}")
        if evt.reason == speechsdk.CancellationReason.Error:
            logger.error(f"[{self.call_id}] Erro no Azure Speech: {evt.error_details}")
    
    def add_audio_chunk(self, chunk: bytes):
        """
        Adiciona um chunk de áudio ao buffer, se estiver coletando.
        
        Returns:
            True se o áudio estiver sendo coletado, False caso contrário
        """
        if self.collecting_audio:
            self.audio_buffer.append(chunk)
            if len(self.audio_buffer) % 50 == 0:  # Log a cada ~1 segundo
                logger.debug(f"[{self.call_id}] Coletando áudio: {len(self.audio_buffer)} frames (~{len(self.audio_buffer)*20}ms)")
            return True
        return False
    
    def is_collecting(self) -> bool:
        """Retorna se está coletando áudio."""
        return self.collecting_audio
    
    def _check_recognition_timeout(self):
        """
        Verifica se o tempo limite para reconhecimento foi atingido após detecção do fim da fala.
        Se sim, força o processamento do áudio coletado.
        """
        # Se ainda estamos coletando áudio e temos buffer, mas on_recognized nunca foi chamado
        # após a detecção do fim da fala, forçamos o processamento
        if (self.collecting_audio and 
            len(self.audio_buffer) > 0 and 
            self.speech_end_time is not None and 
            time.time() - self.speech_end_time > self.recognition_timeout):
            
            logger.warning(f"[{self.call_id}] TIMEOUT de reconhecimento após detecção de fim de fala. Forçando processamento manual.")
            
            # Criar cópia local dos dados para processar
            audio_data = b"".join(self.audio_buffer)
            
            # Limpar buffer e estado
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
            self.speech_end_time = None
            
            # Processar como texto vazio (será processado apenas o áudio)
            if self.process_callback:
                loop = asyncio.get_event_loop()
                future = asyncio.run_coroutine_threadsafe(
                    self.process_callback("", audio_data), 
                    loop
                )
                # Adicionar callback para log de sucesso/erro
                future.add_done_callback(lambda f: 
                    logger.info(f"[{self.call_id}] Processamento de timeout concluído com sucesso") if not f.exception() 
                    else logger.error(f"[{self.call_id}] Erro no processamento de timeout: {f.exception()}")
                )
            else:
                logger.error(f"[{self.call_id}] Processo_callback não definido! Não é possível processar áudio após timeout")
    
    def register_callbacks(self, recognizer):
        """Registra todos os callbacks com o recognizer."""
        recognizer.recognized.connect(self.on_recognized)
        recognizer.speech_start_detected.connect(self.on_speech_start_detected)
        recognizer.speech_end_detected.connect(self.on_speech_end_detected)
        recognizer.recognizing.connect(self.on_recognizing)
        recognizer.session_started.connect(self.on_session_started)
        recognizer.session_stopped.connect(self.on_session_stopped)
        recognizer.canceled.connect(self.on_canceled)
        
        logger.info(f"[{self.call_id}] Callbacks registrados para {'visitante' if self.is_visitor else 'morador'}")