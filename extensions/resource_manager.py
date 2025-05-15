import asyncio
import logging
import os
import psutil
import time
from typing import Dict, Set, Optional

logger = logging.getLogger(__name__)

class ResourceManager:
    """
    Classe responsável por gerenciar recursos do sistema para evitar sobrecarga
    quando múltiplos sockets estão ativos simultaneamente.
    """
    
    def __init__(self):
        # Contadores de recursos em uso
        self.active_sessions: Set[str] = set()
        self.speaking_sessions: Set[str] = set()
        self.transcribing_sessions: Set[str] = set()
        
        # Limites de simultaneidade 
        self.max_concurrent_transcriptions = int(os.getenv('MAX_CONCURRENT_TRANSCRIPTIONS', '3'))
        self.max_concurrent_synthesis = int(os.getenv('MAX_CONCURRENT_SYNTHESIS', '3'))
        
        # Semáforos para controle de acesso
        self.transcription_semaphore = asyncio.Semaphore(self.max_concurrent_transcriptions)
        self.synthesis_semaphore = asyncio.Semaphore(self.max_concurrent_synthesis)
        
        # Métricas de performance
        self.metrics: Dict[str, Dict] = {}
        
        # Conexões ativas para cada sessão (permite enviar KIND_HANGUP)
        self.active_connections: Dict[str, Dict] = {}
        
        # Ajustes dinâmicos baseados no hardware
        self._configure_based_on_hardware()
        
        logger.info(f"ResourceManager inicializado: max_concurrent_transcriptions={self.max_concurrent_transcriptions}, "
                   f"max_concurrent_synthesis={self.max_concurrent_synthesis}")
    
    def _configure_based_on_hardware(self):
        """Configura limites baseados nos recursos do hardware."""
        try:
            cpu_count = psutil.cpu_count(logical=False) or 2
            mem_gb = psutil.virtual_memory().total / (1024**3)
            
            # Ajustar limites com base em CPU e memória
            if cpu_count >= 4 and mem_gb >= 8:
                # Hardware robusto
                self.max_concurrent_transcriptions = max(3, min(cpu_count - 1, 6))
                self.max_concurrent_synthesis = max(3, min(cpu_count - 1, 6))
            elif cpu_count >= 2 and mem_gb >= 4:
                # Hardware médio
                self.max_concurrent_transcriptions = 2
                self.max_concurrent_synthesis = 2
            else:
                # Hardware limitado
                self.max_concurrent_transcriptions = 1
                self.max_concurrent_synthesis = 1
            
            logger.info(f"Configuração baseada em hardware: CPUs={cpu_count}, RAM={mem_gb:.1f}GB, "
                       f"Transcrições={self.max_concurrent_transcriptions}, Sínteses={self.max_concurrent_synthesis}")
        except Exception as e:
            logger.warning(f"Erro ao configurar baseado no hardware: {e}. Usando valores padrão.")
    
    def register_session(self, session_id: str, port: Optional[int] = None):
        """Registra uma nova sessão ativa."""
        self.active_sessions.add(session_id)
        self.metrics[session_id] = {
            'start_time': time.time(),
            'port': port,
            'transcription_count': 0,
            'synthesis_count': 0,
            'transcription_time_ms': 0,
            'synthesis_time_ms': 0
        }
        logger.debug(f"Sessão {session_id} registrada. Total de sessões ativas: {len(self.active_sessions)}")
    
    def unregister_session(self, session_id: str):
        """Remove uma sessão terminada."""
        if session_id in self.active_sessions:
            self.active_sessions.remove(session_id)
        
        if session_id in self.speaking_sessions:
            self.speaking_sessions.remove(session_id)
            
        if session_id in self.transcribing_sessions:
            self.transcribing_sessions.remove(session_id)
            
        # Registrar métricas finais
        if session_id in self.metrics:
            duration = time.time() - self.metrics[session_id]['start_time']
            logger.info(f"Sessão {session_id} encerrada após {duration:.1f}s. "
                       f"Transcrições: {self.metrics[session_id]['transcription_count']}, "
                       f"Sínteses: {self.metrics[session_id]['synthesis_count']}")
            del self.metrics[session_id]
    
    def set_speaking(self, session_id: str, is_speaking: bool):
        """Marca uma sessão como falando ou não."""
        if is_speaking:
            self.speaking_sessions.add(session_id)
        elif session_id in self.speaking_sessions:
            self.speaking_sessions.remove(session_id)
    
    def set_transcribing(self, session_id: str, is_transcribing: bool):
        """Marca uma sessão como transcrevendo ou não."""
        if is_transcribing:
            self.transcribing_sessions.add(session_id)
        elif session_id in self.transcribing_sessions:
            self.transcribing_sessions.remove(session_id)
    
    async def acquire_transcription_lock(self, session_id: str):
        """
        Adquire um lock para transcrição, limitando o número de transcrições
        simultâneas para evitar sobrecarga de CPU/memória.
        """
        await self.transcription_semaphore.acquire()
        self.set_transcribing(session_id, True)
        return True
    
    def release_transcription_lock(self, session_id: str):
        """Libera um lock de transcrição."""
        self.set_transcribing(session_id, False)
        self.transcription_semaphore.release()
    
    async def acquire_synthesis_lock(self, session_id: str):
        """
        Adquire um lock para síntese de voz, limitando o número de sínteses
        simultâneas para evitar sobrecarga.
        """
        await self.synthesis_semaphore.acquire()
        return True
    
    def release_synthesis_lock(self, session_id: str):
        """Libera um lock de síntese."""
        self.synthesis_semaphore.release()
    
    def record_transcription(self, session_id: str, duration_ms: float):
        """Registra métricas de uma transcrição."""
        if session_id in self.metrics:
            self.metrics[session_id]['transcription_count'] += 1
            self.metrics[session_id]['transcription_time_ms'] += duration_ms
    
    def record_synthesis(self, session_id: str, duration_ms: float):
        """Registra métricas de uma síntese."""
        if session_id in self.metrics:
            self.metrics[session_id]['synthesis_count'] += 1
            self.metrics[session_id]['synthesis_time_ms'] += duration_ms
    
    def get_system_load(self):
        """Retorna informações sobre o carregamento atual do sistema."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem_percent = psutil.virtual_memory().percent
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': mem_percent,
                'active_sessions': len(self.active_sessions),
                'speaking_sessions': len(self.speaking_sessions),
                'transcribing_sessions': len(self.transcribing_sessions)
            }
        except Exception as e:
            logger.error(f"Erro ao obter carga do sistema: {e}")
            return {
                'error': str(e)
            }
            
    def should_throttle_audio(self):
        """
        Determina se a transmissão de áudio deve ser limitada com base na carga do sistema.
        Retorna True se o sistema estiver sobrecarregado.
        """
        system_load = self.get_system_load()
        cpu_percent = system_load.get('cpu_percent', 0)
        active_sessions = system_load.get('active_sessions', 0)
        
        # Se temos muitas sessões ativas E a CPU está alta, ativamos throttling
        return active_sessions > 3 and cpu_percent > 85
        
    def register_connection(self, call_id: str, role: str, reader, writer):
        """
        Registra uma conexão de socket ativa para permitir envio do KIND_HANGUP.
        
        Args:
            call_id: ID da chamada
            role: 'visitor' ou 'resident'
            reader: StreamReader da conexão
            writer: StreamWriter da conexão
        """
        if call_id not in self.active_connections:
            self.active_connections[call_id] = {}
            
        self.active_connections[call_id][role] = {
            'reader': reader,
            'writer': writer,
            'timestamp': time.time()
        }
        logger.debug(f"Conexão registrada para {call_id} ({role})")
        
    def unregister_connection(self, call_id: str, role: str):
        """
        Remove uma conexão quando ela é encerrada.
        """
        if call_id in self.active_connections and role in self.active_connections[call_id]:
            del self.active_connections[call_id][role]
            logger.debug(f"Conexão removida para {call_id} ({role})")
            
            # Se não há mais conexões para esta chamada, limpar
            if not self.active_connections[call_id]:
                del self.active_connections[call_id]
                
    def get_active_connection(self, call_id: str, role: str):
        """
        Retorna informações sobre uma conexão ativa.
        
        Args:
            call_id: ID da chamada
            role: 'visitor' ou 'resident'
            
        Returns:
            Dict com reader e writer, ou None se não existir
        """
        if call_id in self.active_connections and role in self.active_connections[call_id]:
            return self.active_connections[call_id][role]
        return None

# Instância global
resource_manager = ResourceManager()