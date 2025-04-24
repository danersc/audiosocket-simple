import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional, Any, Union
import json

class CallLogger:
    """
    Logger especializado para registrar detalhes de uma chamada específica.
    Cria um arquivo de log único para cada UUID de chamada com timestamps precisos
    para cada etapa do processo.
    """
    
    def __init__(self, call_id: str):
        self.call_id = call_id
        self.start_time = time.time()
        self.log_file = os.path.join('logs', f"{call_id}.log")
        
        # Configurar logger específico para esta chamada
        self.logger = logging.getLogger(f"call.{call_id}")
        
        # Remove handlers existentes para evitar duplicação se o logger já existir
        if self.logger.handlers:
            for handler in self.logger.handlers:
                self.logger.removeHandler(handler)
        
        # Definir nível de logging
        self.logger.setLevel(logging.DEBUG)
        
        # Criar file handler
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        file_handler = logging.FileHandler(self.log_file)
        
        # Definir formato
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Adicionar handler ao logger
        self.logger.addHandler(file_handler)
        
        # Registrar início da chamada
        self.log_event("CALL_STARTED", {
            "timestamp": datetime.now().isoformat()
        })
    
    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Registra um evento com seu timestamp e dados adicionais.
        
        Args:
            event_type: Tipo do evento (ex: SPEECH_DETECTED, TRANSCRIPTION_COMPLETE)
            data: Dicionário com informações adicionais do evento
        """
        # Adicionar timestamp se não fornecido
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        
        # Adicionar tempo decorrido desde o início da chamada
        elapsed = time.time() - self.start_time
        data["elapsed_seconds"] = round(elapsed, 3)
        
        # Formatar mensagem para o log
        message = f"{event_type} | {json.dumps(data)}"
        self.logger.info(message)
    
    def log_speech_detected(self, is_visitor: bool = True) -> None:
        """Registra quando voz é detectada."""
        self.log_event("SPEECH_DETECTED", {
            "source": "visitor" if is_visitor else "resident"
        })
    
    def log_speech_ended(self, duration_ms: float, is_visitor: bool = True) -> None:
        """Registra quando a fala termina."""
        self.log_event("SPEECH_ENDED", {
            "source": "visitor" if is_visitor else "resident",
            "duration_ms": duration_ms
        })
    
    def log_transcription_start(self, audio_size: int, is_visitor: bool = True) -> None:
        """Registra início da transcrição."""
        self.log_event("TRANSCRIPTION_START", {
            "source": "visitor" if is_visitor else "resident",
            "audio_size_bytes": audio_size
        })
    
    def log_transcription_complete(self, text: str, duration_ms: float, is_visitor: bool = True) -> None:
        """Registra conclusão da transcrição."""
        self.log_event("TRANSCRIPTION_COMPLETE", {
            "source": "visitor" if is_visitor else "resident",
            "text": text,
            "duration_ms": duration_ms
        })
    
    def log_ai_processing_start(self, text: str) -> None:
        """Registra início do processamento pela IA."""
        self.log_event("AI_PROCESSING_START", {
            "input_text": text
        })
    
    def log_ai_processing_complete(self, response: Dict[str, Any], duration_ms: float) -> None:
        """Registra conclusão do processamento pela IA."""
        self.log_event("AI_PROCESSING_COMPLETE", {
            "response": response,
            "duration_ms": duration_ms
        })
    
    def log_synthesis_start(self, text: str, is_visitor: bool = True) -> None:
        """Registra início da síntese de voz."""
        self.log_event("SYNTHESIS_START", {
            "target": "visitor" if is_visitor else "resident",
            "text": text
        })
    
    def log_synthesis_complete(self, audio_size: int, duration_ms: float, is_visitor: bool = True) -> None:
        """Registra conclusão da síntese de voz."""
        self.log_event("SYNTHESIS_COMPLETE", {
            "target": "visitor" if is_visitor else "resident",
            "audio_size_bytes": audio_size,
            "duration_ms": duration_ms
        })
    
    def log_state_change(self, old_state: str, new_state: str) -> None:
        """Registra mudança de estado no fluxo de conversa."""
        self.log_event("STATE_CHANGE", {
            "from": old_state,
            "to": new_state
        })
    
    def log_silence_detected(self, duration_ms: float, is_visitor: bool = True) -> None:
        """Registra detecção de silêncio."""
        self.log_event("SILENCE_DETECTED", {
            "source": "visitor" if is_visitor else "resident",
            "duration_ms": duration_ms
        })
    
    def log_error(self, error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Registra ocorrência de erro."""
        data = {
            "error_type": error_type,
            "message": message
        }
        if details:
            data["details"] = details
        
        self.log_event("ERROR", data)
        self.logger.error(f"{error_type}: {message}")
    
    def log_call_ended(self, reason: str, duration_ms: Optional[float] = None) -> None:
        """Registra término da chamada."""
        if duration_ms is None:
            duration_ms = (time.time() - self.start_time) * 1000
            
        self.log_event("CALL_ENDED", {
            "reason": reason,
            "total_duration_ms": duration_ms
        })
        
        # Fechar todos os handlers
        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)


# Singleton para gerenciar os loggers de chamadas
class CallLoggerManager:
    _loggers: Dict[str, CallLogger] = {}
    
    @classmethod
    def get_logger(cls, call_id: str) -> CallLogger:
        """Obtém ou cria um logger para o ID de chamada especificado."""
        if call_id not in cls._loggers:
            cls._loggers[call_id] = CallLogger(call_id)
        return cls._loggers[call_id]
    
    @classmethod
    def remove_logger(cls, call_id: str) -> None:
        """Remove um logger após o término da chamada."""
        if call_id in cls._loggers:
            del cls._loggers[call_id]