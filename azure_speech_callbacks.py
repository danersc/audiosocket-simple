"""
Módulo de callbacks do Azure Speech SDK - Versão Simplificada.

Este módulo contém callbacks básicos para interação com o Azure Speech SDK,
focando apenas na detecção de voz e no processamento do áudio reconhecido.
"""

import asyncio
import logging
import time
from typing import List, Optional, Callable, Any

import azure.cognitiveservices.speech as speechsdk

logger = logging.getLogger(__name__)

class SpeechCallbacks:
    """
    Classe simplificada para gerenciar callbacks do Azure Speech SDK.
    
    Esta versão mantém apenas o essencial para detecção de voz e 
    processamento de texto reconhecido, sem lógicas complexas de filtragem.
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
        
        # Estado interno básico
        self.collecting_audio = False
        self.audio_buffer: List[bytes] = []
        self.speech_detected = False
        
        # Timestamps para cálculos de duração
        self.speech_start_time = None
        
        # Função de processamento a ser definida pelo chamador
        self.process_callback: Optional[Callable] = None
        
        logger.info(f"[{self.call_id}] Inicializando callbacks para {'visitante' if is_visitor else 'morador'}")
    
    def set_process_callback(self, callback: Callable[[str, bytes], Any]):
        """Define a função de callback para processar texto reconhecido."""
        self.process_callback = callback
    
    def on_recognized(self, evt):
        """Callback quando a fala é reconhecida completamente."""
        role = "visitante" if self.is_visitor else "morador"
        
        # Log detalhado do evento - IMPORTANTE PARA DIAGNÓSTICO
        logger.info(f"[{self.call_id}] EVENTO ON_RECOGNIZED DISPARADO! Reason: {evt.result.reason}")
        logger.info(f"[{self.call_id}] Estado do buffer: {len(self.audio_buffer)} frames, collecting={self.collecting_audio}")
        
        # Log detalhado de propriedades do resultado para diagnóstico
        if hasattr(evt.result, 'properties'):
            properties = evt.result.properties
            if properties:
                logger.info(f"[{self.call_id}] Propriedades do resultado: {properties}")
        
        # Tratamento baseado na razão do evento
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            # Fala reconhecida com sucesso
            logger.info(f"[{self.call_id}] RECONHECIMENTO BEM-SUCEDIDO: '{evt.result.text}'")
            
            # Processar o texto reconhecido
            if len(self.audio_buffer) > 0 and self.process_callback:
                audio_data = b"".join(self.audio_buffer) 
                
                # Executar callback de processamento
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    self.process_callback(evt.result.text, audio_data), 
                    loop
                )
            else:
                logger.warning(f"[{self.call_id}] Texto reconhecido, mas sem dados de áudio para processar")
        
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            # Tratamento para quando o Azure detecta fala mas não consegue transcrever
            logger.info(f"[{self.call_id}] NoMatch detectado. Detalhes: {evt.result.no_match_details if hasattr(evt.result, 'no_match_details') else 'N/A'}")
            
            # Processar o áudio mesmo sem reconhecimento se tiver buffer
            if len(self.audio_buffer) > 0 and self.process_callback:
                audio_data = b"".join(self.audio_buffer)
                
                # Executar callback com texto vazio
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    self.process_callback("", audio_data), 
                    loop
                )
        
        else:
            # Outros casos (cancelamento, erro, etc.)
            logger.warning(f"[{self.call_id}] on_recognized com reason desconhecido: {evt.result.reason}")
        
        # Limpar buffer e resetar estado
        self.audio_buffer = []
        self.collecting_audio = False
        self.speech_detected = False
    
    def on_speech_start_detected(self, evt):
        """Callback quando o início de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        logger.info(f"[{self.call_id}] INÍCIO DE FALA DETECTADO ({role})")
        
        # Registrar no logger específico da chamada se disponível
        if self.call_logger:
            self.call_logger.log_speech_detected(is_visitor=self.is_visitor)
        
        # Resetar buffer e iniciar coleta
        self.audio_buffer = []
        self.collecting_audio = True
        self.speech_detected = True
        self.speech_start_time = time.time()
    
    def on_speech_end_detected(self, evt):
        """Callback quando o fim de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        logger.info(f"[{self.call_id}] FIM DE FALA DETECTADO ({role})")
        
        # Calcular duração da fala se possível
        if self.speech_start_time:
            duration_ms = (time.time() - self.speech_start_time) * 1000
            logger.info(f"[{self.call_id}] Duração da fala: {duration_ms:.1f}ms")
            
            if self.call_logger:
                self.call_logger.log_speech_ended(duration_ms, is_visitor=self.is_visitor)
        
        # Verificar se temos dados para processar
        if not self.collecting_audio or len(self.audio_buffer) == 0:
            logger.warning(f"[{self.call_id}] Fim de fala detectado, mas sem dados para processar")
            return
        
        # Verificar se on_recognized será chamado
        async def check_recognition_timeout():
            await asyncio.sleep(3.0)  # Esperar 3 segundos
            
            # Se ainda temos o mesmo áudio no buffer, o evento on_recognized não foi disparado
            if not self.collecting_audio and len(self.audio_buffer) > 0:
                logger.warning(f"[{self.call_id}] TIMEOUT: on_recognized não foi disparado após 3s. Processando manualmente.")
                
                # Processar o áudio diretamente
                if self.process_callback:
                    audio_data = b"".join(self.audio_buffer)
                    
                    # Executar callback
                    loop = asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(
                        self.process_callback("", audio_data),
                        loop
                    )
                    
                    # Limpar buffer após processamento
                    self.audio_buffer = []
        
        # Iniciar verificação de timeout
        asyncio.create_task(check_recognition_timeout())
        
        # Apenas marcar que a coleta terminou
        # O áudio será processado quando o evento on_recognized for disparado
        # ou após o timeout se o evento não ocorrer
        self.collecting_audio = False
    
    def on_session_started(self, evt):
        """Callback quando a sessão de reconhecimento é iniciada."""
        logger.info(f"[{self.call_id}] Sessão de reconhecimento iniciada: {evt.session_id}")
    
    def on_session_stopped(self, evt):
        """Callback quando a sessão de reconhecimento é encerrada."""
        logger.info(f"[{self.call_id}] Sessão de reconhecimento encerrada: {evt.session_id}")
    
    def on_canceled(self, evt):
        """Callback quando o reconhecimento é cancelado."""
        logger.error(f"[{self.call_id}] Reconhecimento cancelado: {evt.reason}")
        if evt.reason == speechsdk.CancellationReason.Error:
            logger.error(f"[{self.call_id}] Erro: {evt.error_details}")
            
            # Processar o áudio mesmo com erro se tiver dados
            if len(self.audio_buffer) > 0 and self.process_callback:
                audio_data = b"".join(self.audio_buffer)
                
                # Executar callback
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    self.process_callback("", audio_data),
                    loop
                )
        
        # Limpar buffer e resetar estado
        self.audio_buffer = []
        self.collecting_audio = False
        self.speech_detected = False
    
    def add_audio_chunk(self, chunk: bytes):
        """
        Adiciona um chunk de áudio ao buffer quando estiver coletando.
        
        Returns:
            True se o áudio estiver sendo coletado, False caso contrário
        """
        # Verificação básica do chunk
        if not chunk or len(chunk) == 0:
            return False
        
        # Se fala foi detectada, garantir que estamos coletando
        if self.speech_detected and not self.collecting_audio:
            self.collecting_audio = True
        
        # Se estamos coletando, adicionar ao buffer
        if self.collecting_audio:
            self.audio_buffer.append(chunk)
            
            # Log periódico para informar status do buffer
            if len(self.audio_buffer) % 20 == 0:  # Log a cada 20 chunks
                buffer_duration_ms = len(self.audio_buffer) * 20  # Aproximadamente 20ms por chunk
                logger.info(f"[{self.call_id}] Buffer: {len(self.audio_buffer)} chunks (~{buffer_duration_ms}ms)")
            
            return True
        
        return False
    
    def is_collecting(self) -> bool:
        """Retorna se está coletando áudio."""
        return self.collecting_audio
    
    def register_callbacks(self, recognizer):
        """Registra todos os callbacks com o recognizer."""
        # ATENÇÃO: Aqui estava o erro! A linha abaixo tinha um erro de digitação
        # recognizer.recognized.connect(s) deveria ser recognizer.recognized.connect(self.on_recognized)
        recognizer.recognized.connect(self.on_recognized)
        recognizer.speech_start_detected.connect(self.on_speech_start_detected)
        recognizer.speech_end_detected.connect(self.on_speech_end_detected)
        recognizer.session_started.connect(self.on_session_started)
        recognizer.session_stopped.connect(self.on_session_stopped)
        recognizer.canceled.connect(self.on_canceled)
        
        logger.info(f"[{self.call_id}] Callbacks registrados com sucesso para {'visitante' if self.is_visitor else 'morador'}")
    
    def mark_ia_audio_sent(self):
        """
        Limpa o estado após envio de áudio pela IA.
        """
        # Limpar buffer e estado
        self.audio_buffer = []
        self.collecting_audio = False
        self.speech_detected = False