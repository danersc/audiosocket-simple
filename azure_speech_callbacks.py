"""
Módulo de callbacks do Azure Speech SDK - Versão otimizada para AudioSocket.

Este módulo contém callbacks para interação com o Azure Speech SDK,
com foco na correta detecção e processamento de voz a partir de dados de áudio PCM
recebidos via protocolo AudioSocket.
"""

import asyncio
import logging
import os
import time
from typing import List, Optional, Callable, Any

import azure.cognitiveservices.speech as speechsdk

logger = logging.getLogger(__name__)

class SpeechCallbacks:
    """
    Classe para gerenciar callbacks do Azure Speech SDK.
    
    Esta implementação foi otimizada para trabalhar com o formato de áudio do AudioSocket
    (PCM 16-bit, 8kHz, mono) e garantir que o Azure Speech SDK processe corretamente
    os dados de áudio.
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
        logger.info(f"[{self.call_id}] *** EVENTO ON_RECOGNIZED DISPARADO! ***")
        
        # Logar informações detalhadas do evento
        try:
            # Logar tipo do evento
            logger.info(f"[{self.call_id}] Tipo do evento: {type(evt).__name__}")
            
            # Logar tipo do resultado
            if hasattr(evt, 'result'):
                logger.info(f"[{self.call_id}] Tipo do resultado: {type(evt.result).__name__}")
                
                # Logar reason do resultado
                if hasattr(evt.result, 'reason'):
                    reason_str = f"{evt.result.reason}"
                    reason_int = int(evt.result.reason) if hasattr(evt.result.reason, '__int__') else -1
                    logger.info(f"[{self.call_id}] Reason: {reason_str} (valor: {reason_int})")
                
                # Logar texto do resultado
                if hasattr(evt.result, 'text'):
                    logger.info(f"[{self.call_id}] Texto reconhecido: '{evt.result.text}'")
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro ao logar detalhes do evento recognized: {e}")
        
        logger.info(f"[{self.call_id}] Estado do buffer: {len(self.audio_buffer)} frames, collecting={self.collecting_audio}")
        
        # Log detalhado de propriedades do resultado para diagnóstico
        if hasattr(evt.result, 'properties'):
            try:
                properties = evt.result.properties
                if properties:
                    logger.info(f"[{self.call_id}] Propriedades do resultado: {properties}")
                
                # Capturar resposta JSON completa do serviço, se disponível
                # Verificar se properties é um objeto que tem o método get_property ou se é um dicionário
                if properties:
                    if hasattr(properties, 'get_property'):
                        # É um objeto com método get_property
                        if properties.get_property(speechsdk.PropertyId.SpeechServiceResponse_JsonResult):
                            json_result = properties.get_property(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
                            logger.info(f"[{self.call_id}] JSON do resultado: {json_result}")
                    elif isinstance(properties, dict):
                        # É um dicionário
                        logger.info(f"[{self.call_id}] Propriedades como dicionário: {properties}")
            except Exception as e:
                logger.error(f"[{self.call_id}] Erro ao acessar propriedades: {e}")
        
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
            no_match_details = "N/A"
            if hasattr(evt.result, 'no_match_details'):
                no_match_details = evt.result.no_match_details
            
            logger.info(f"[{self.call_id}] NoMatch detectado. Detalhes: {no_match_details}")
            
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
        
        # Marcar que a coleta terminou - agora vamos aguardar pelo evento on_recognized
        # sem intervenção manual
        logger.info(f"[{self.call_id}] Aguardando evento on_recognized para processar o áudio (buffer: {len(self.audio_buffer)} frames)")
        self.collecting_audio = False
    
    def on_recognizing(self, evt):
        """Callback para resultados parciais de reconhecimento."""
        # Importante para diagnóstico - mostrar resultados parciais
        if evt.result and evt.result.text:
            logger.info(f"[{self.call_id}] Reconhecimento parcial: {evt.result.text}")
    
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
        
        Importante: O chunk deve ser puramente dados de áudio PCM (sem cabeçalhos TLV),
        tipicamente 320 bytes representando 20ms de áudio em 8kHz/16-bit/mono.
        
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
    
    def register_callbacks(self, recognizer, speech_config=None):
        """Registra todos os callbacks com o recognizer."""
        # ATENÇÃO: Corrigido o erro de registro do callback
        logger.info(f"[{self.call_id}] Registrando callbacks para {'visitante' if self.is_visitor else 'morador'}")
        
        # Verificar se o recognizer é válido
        if not recognizer:
            logger.error(f"[{self.call_id}] ERRO: Recognizer é None ou inválido!")
            return
            
        # Registrar callbacks com verificação de erros
        try:
            # Registrar callback para evento recognized (MAIS IMPORTANTE)
            recognizer.recognized.connect(self.on_recognized)
            logger.info(f"[{self.call_id}] Callback 'recognized' registrado com sucesso")
            
            # Registrar outros callbacks
            recognizer.speech_start_detected.connect(self.on_speech_start_detected)
            recognizer.speech_end_detected.connect(self.on_speech_end_detected)
            recognizer.recognizing.connect(self.on_recognizing)
            recognizer.session_started.connect(self.on_session_started)
            recognizer.session_stopped.connect(self.on_session_stopped)
            recognizer.canceled.connect(self.on_canceled)
            
            logger.info(f"[{self.call_id}] Todos os callbacks registrados com sucesso")
        except Exception as e:
            logger.error(f"[{self.call_id}] ERRO AO REGISTRAR CALLBACKS: {e}")
        
        # Configurar arquivo de log do SDK para diagnóstico detalhado
        if speech_config:
            try:
                log_dir = os.path.join("logs", "azure_speech")
                os.makedirs(log_dir, exist_ok=True)
                log_file = os.path.join(log_dir, f"azure_speech_{self.call_id}.txt")
                
                speech_config.set_property(speechsdk.PropertyId.Speech_LogFilename, log_file)
                logger.info(f"[{self.call_id}] Logs internos do Azure Speech SDK ativados: {log_file}")
                
                # Configurar formato de saída detalhado
                speech_config.output_format = speechsdk.OutputFormat.Detailed
                logger.info(f"[{self.call_id}] Formato de saída detalhado ativado")
                
                # Configurar timeout de silêncio e outras propriedades importantes
                speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "2000")
                logger.info(f"[{self.call_id}] Timeout de silêncio final configurado para 2000ms")
                
                # Ajustar propriedades adicionais para melhorar o reconhecimento
                if hasattr(speechsdk.PropertyId, "Speech_SegmentationSilenceTimeoutMs"):
                    speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "1000")
                    logger.info(f"[{self.call_id}] Timeout de segmentação configurado para 1000ms")
                
                # Configurar idioma explicitamente
                speech_config.speech_recognition_language = "pt-BR"
                logger.info(f"[{self.call_id}] Idioma de reconhecimento configurado para pt-BR")
            except Exception as e:
                logger.error(f"[{self.call_id}] Erro ao configurar logs do SDK: {e}")
        
        logger.info(f"[{self.call_id}] Configuração de callbacks concluída para {'visitante' if self.is_visitor else 'morador'}")
    
    def mark_ia_audio_sent(self):
        """
        Limpa o estado após envio de áudio pela IA.
        """
        # Limpar buffer e estado
        self.audio_buffer = []
        self.collecting_audio = False
        self.speech_detected = False