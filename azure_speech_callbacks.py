"""
Módulo para funções de callback do Azure Speech SDK - Versão Simplificada.

Este módulo contém implementações de funções de callback que são usadas
ao interagir com o Azure Speech SDK para detecção de voz, com foco em simplicidade
e confiança no serviço Azure Speech.
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
    
    Esta implementação simplificada confia mais nos recursos nativos do Azure Speech SDK
    para detecção de voz em ambientes ruidosos, com mínima interferência local.
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
        
        # Timestamps para cálculos de duração e controle de eco
        self.last_ia_audio_time = 0
        self.speech_start_time = None
        
        # Contadores para diagnóstico
        self.chunks_received = 0
        self.chunks_collected = 0
        
        # Função de processamento a ser definida pelo chamador
        self.process_callback: Optional[Callable] = None
        
        logger.info(f"[{self.call_id}] Inicializando SpeechCallbacks para {'visitante' if is_visitor else 'morador'}")
    
    def set_process_callback(self, callback: Callable[[str, bytes], Any]):
        """Define a função de callback para processar texto reconhecido."""
        self.process_callback = callback
    
    def on_recognized(self, evt):
        """Callback quando a fala é reconhecida completamente."""
        role = "visitante" if self.is_visitor else "morador"
        
        # Log detalhado do evento
        logger.info(f"[{self.call_id}] Evento on_recognized disparado! Reason: {evt.result.reason}, Buffer: {len(self.audio_buffer)} frames")
        
        # Verificar e registrar propriedades do resultado para diagnóstico
        if hasattr(evt.result, 'properties'):
            properties = evt.result.properties
            if properties:
                logger.info(f"[{self.call_id}] Propriedades do resultado: {properties}")
            
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            # Fala foi reconhecida com sucesso
            logger.info(f"[{self.call_id}] Azure Speech reconheceu texto do {role}: '{evt.result.text}'")
            
            # Criar cópia local dos dados para processar
            text_to_process = evt.result.text
            audio_data = b"".join(self.audio_buffer) if self.audio_buffer else b""
            audio_size = len(audio_data)
            
            # Verificar se temos dados para processar
            if audio_size > 0:
                # Processar texto reconhecido via thread-safe
                if self.process_callback:
                    logger.info(f"[{self.call_id}] Enviando texto reconhecido para processamento: '{text_to_process}' (buffer: {audio_size} bytes)")
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
            else:
                logger.warning(f"[{self.call_id}] Texto reconhecido, mas sem dados de áudio para processar")
                
                # Tentar salvar arquivo de diagnóstico vazio
                try:
                    import os
                    import hashlib
                    
                    debug_dir = os.path.join("audio", "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    
                    file_hash = hashlib.md5(f"{self.call_id}_empty_recognized".encode()).hexdigest()[:16]
                    file_path = os.path.join(debug_dir, f"{file_hash}_empty_{role}.txt")
                    
                    with open(file_path, "w") as f:
                        f.write(f"Evento recognized com texto '{text_to_process}' mas buffer vazio.")
                    
                    logger.info(f"[{self.call_id}] Diagnóstico salvo: {file_path}")
                except Exception as e:
                    logger.error(f"[{self.call_id}] Erro ao salvar diagnóstico: {e}")
            
            # Limpar buffer e preparar para próxima fala
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
        
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            # IMPORTANTE: Tratamento explícito do caso NoMatch (quando o Azure detecta fala mas não consegue transcrever)
            logger.info(f"[{self.call_id}] Azure Speech NoMatch. Detalhes: {evt.result.no_match_details if hasattr(evt.result, 'no_match_details') else 'N/A'}")
            
            # Verificar se temos um áudio curto do morador que pode ser uma resposta rápida
            is_short_audio = not self.is_visitor and len(self.audio_buffer) > 0 and len(self.audio_buffer) < 20
            
            # Verificar se temos áudio disponível para processar mesmo sem reconhecimento
            have_audio = len(self.audio_buffer) > 0
            
            if is_short_audio:
                # Morador com fala curta (possível "sim" ou "não")
                audio_data = b"".join(self.audio_buffer)
                audio_size = len(audio_data)
                logger.info(f"[{self.call_id}] NoMatch com áudio curto do morador: {audio_size} bytes, tentando processar como resposta curta")
                
                # Processar como texto vazio para tratamento de áudio curto
                if self.process_callback:
                    loop = asyncio.get_event_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.process_callback("sim", audio_data),  # Usamos "sim" como valor padrão para áudios curtos
                        loop
                    )
                    future.add_done_callback(lambda f: 
                        logger.info(f"[{self.call_id}] Processamento de áudio curto concluído com sucesso") if not f.exception() 
                        else logger.error(f"[{self.call_id}] Erro no processamento de áudio curto: {f.exception()}")
                    )
            elif have_audio:
                # Temos áudio mas não foi reconhecido - salvar para diagnóstico
                audio_data = b"".join(self.audio_buffer)
                audio_size = len(audio_data)
                
                # Salvar o áudio para análise
                try:
                    import os
                    import hashlib
                    import time
                    
                    debug_dir = os.path.join("audio", "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    
                    timestamp = int(time.time())
                    file_hash = hashlib.md5(f"{self.call_id}_{timestamp}_nomatch".encode()).hexdigest()[:16]
                    file_path = os.path.join(debug_dir, f"{file_hash}_nomatch_{role}.slin")
                    
                    with open(file_path, "wb") as f:
                        f.write(audio_data)
                    
                    logger.info(f"[{self.call_id}] Áudio não reconhecido (NoMatch) salvo: {file_path} ({audio_size} bytes)")
                except Exception as e:
                    logger.error(f"[{self.call_id}] Erro ao salvar áudio NoMatch: {e}")
                
                # Mesmo com NoMatch, tentar processar o áudio
                if self.process_callback:
                    logger.info(f"[{self.call_id}] Tentando processar áudio mesmo com NoMatch: {audio_size} bytes")
                    loop = asyncio.get_event_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.process_callback("", audio_data),  # Texto vazio para processamento alternativo
                        loop
                    )
                    future.add_done_callback(lambda f: 
                        logger.info(f"[{self.call_id}] Processamento de NoMatch concluído com sucesso") if not f.exception() 
                        else logger.error(f"[{self.call_id}] Erro no processamento de NoMatch: {f.exception()}")
                    )
            else:
                logger.info(f"[{self.call_id}] Azure Speech não reconheceu fala (NoMatch) e buffer está vazio")
            
            # Limpar buffer e resetar estado
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
        
        else:
            # Outros casos como cancelamento ou erro
            logger.warning(f"[{self.call_id}] on_recognized com reason desconhecido: {evt.result.reason}")
            
            # Limpar estado
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
    
    def on_speech_start_detected(self, evt):
        """Callback quando o início de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        
        # Proteção anti-eco simples: ignorar detecções de fala logo após a IA falar
        current_time = time.time()
        anti_echo_delay = 0.8  # 800ms (ajustável)
        
        if current_time - self.last_ia_audio_time < anti_echo_delay:
            logger.info(f"[{self.call_id}] Ignorando detecção de fala por estar muito próxima ao último áudio da IA ({(current_time - self.last_ia_audio_time):.2f}s < {anti_echo_delay}s)")
            return
        
        # Se chegou aqui, a detecção é válida
        logger.info(f"[{self.call_id}] Início de fala do {role} detectado pelo Azure Speech")
        
        if self.call_logger:
            self.call_logger.log_speech_detected(is_visitor=self.is_visitor)
        
        # Resetar buffer antes de iniciar nova coleta
        # Isso evita misturar áudio de eventos diferentes
        self.audio_buffer = []
        
        # Iniciar coleta de áudio - essencial para que o add_audio_chunk funcione
        self.collecting_audio = True
        self.speech_detected = True
        
        # Registrar tempo de início para cálculo de duração
        self.speech_start_time = time.time()
    
    def on_speech_end_detected(self, evt):
        """Callback quando o fim de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        logger.info(f"[{self.call_id}] Fim de fala do {role} detectado")
        
        if self.call_logger:
            self.call_logger.log_speech_ended(0, is_visitor=self.is_visitor)
        
        # Verificar se temos dados válidos para processar
        if not self.collecting_audio or len(self.audio_buffer) == 0:
            logger.warning(f"[{self.call_id}] Fim de fala detectado, mas sem dados válidos para processar (collecting={self.collecting_audio}, buffer_size={len(self.audio_buffer)})")
            return
        
        # Salvar o áudio capturado em um arquivo para análise
        try:
            import os
            import hashlib
            import time
            
            # Criar diretório audio/debug se não existir
            debug_dir = os.path.join("audio", "debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            # Gerar nome de arquivo único baseado no timestamp e call_id
            timestamp = int(time.time())
            audio_data = b"".join(self.audio_buffer)
            file_hash = hashlib.md5(f"{self.call_id}_{timestamp}".encode()).hexdigest()[:16]
            file_path = os.path.join(debug_dir, f"{file_hash}_{role}.slin")
            
            # Salvar o arquivo
            with open(file_path, "wb") as f:
                f.write(audio_data)
            
            logger.info(f"[{self.call_id}] Áudio salvo para análise: {file_path} ({len(audio_data)} bytes)")
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro ao salvar áudio para debug: {e}")
            
        # Apenas marcar que a coleta terminou
        # O áudio será processado quando o evento on_recognized for disparado
        self.collecting_audio = False
    
    def on_recognizing(self, evt):
        """Callback para resultados parciais de reconhecimento."""
        # Apenas log para debug, sem ações adicionais
        if evt.result and evt.result.text:
            logger.debug(f"[{self.call_id}] Reconhecimento parcial: {evt.result.text}")
    
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
            
            # Se temos dados de áudio quando ocorreu um erro, vamos salvar para diagnóstico
            if hasattr(self, 'audio_buffer') and len(self.audio_buffer) > 0:
                try:
                    import os
                    import hashlib
                    import time
                    
                    # Criar diretório audio/debug se não existir
                    debug_dir = os.path.join("audio", "debug")
                    os.makedirs(debug_dir, exist_ok=True)
                    
                    # Gerar nome de arquivo único para o erro
                    timestamp = int(time.time())
                    audio_data = b"".join(self.audio_buffer)
                    role = "visitante" if self.is_visitor else "morador"
                    file_hash = hashlib.md5(f"{self.call_id}_{timestamp}_error".encode()).hexdigest()[:16]
                    file_path = os.path.join(debug_dir, f"{file_hash}_error_{role}.slin")
                    
                    # Salvar o arquivo
                    with open(file_path, "wb") as f:
                        f.write(audio_data)
                    
                    logger.info(f"[{self.call_id}] Áudio salvo após erro: {file_path} ({len(audio_data)} bytes)")
                except Exception as e:
                    logger.error(f"[{self.call_id}] Erro ao salvar áudio de erro: {e}")
    
    def add_audio_chunk(self, chunk: bytes):
        """
        Adiciona um chunk de áudio ao buffer.
        Versão simplificada que confia mais no Azure Speech para detecção, mas com
        melhorias para garantir que o áudio seja capturado corretamente.
        
        Returns:
            True se o áudio estiver sendo coletado, False caso contrário
        """
        # Incrementar contador total de chunks recebidos para diagnóstico
        self.chunks_received += 1
        
        # Verificação básica do chunk
        if not chunk or len(chunk) == 0:
            return False
        
        # MELHORIA PRINCIPAL: Sempre coletar áudio quando estiver no modo de detecção de fala
        # ou quando a coleta já estiver ativa - isso garante que não perdemos partes do áudio
        if self.speech_detected:
            # Se fala foi detectada mas a coleta ainda não está ativa, ativar
            if not self.collecting_audio:
                logger.info(f"[{self.call_id}] Ativando coleta de áudio após detecção de fala")
                self.collecting_audio = True
        
        # Se estamos coletando, adicionar ao buffer
        if self.collecting_audio:
            self.audio_buffer.append(chunk)
            self.chunks_collected += 1
            
            # Log para informar status do buffer periodicamente
            if len(self.audio_buffer) % 20 == 0:  # Log a cada 20 chunks
                buffer_duration_ms = len(self.audio_buffer) * 20  # Aproximadamente 20ms por chunk
                logger.info(f"[{self.call_id}] Buffer de áudio: {len(self.audio_buffer)} chunks (~{buffer_duration_ms}ms)")
            
            # Limitar tamanho do buffer para evitar estouro de memória
            max_buffer_size = 1500  # ~30 segundos de áudio
            if len(self.audio_buffer) > max_buffer_size:
                # Remover os frames mais antigos
                excess = len(self.audio_buffer) - max_buffer_size
                self.audio_buffer = self.audio_buffer[excess:]
                logger.warning(f"[{self.call_id}] Buffer limitado a {max_buffer_size} frames, removendo {excess} frames antigos")
            
            return True
        
        # Estatísticas de diagnóstico ocasionais
        if self.chunks_received % 100 == 0:
            collection_rate = (self.chunks_collected / self.chunks_received) * 100 if self.chunks_received > 0 else 0
            logger.debug(f"[{self.call_id}] Estatísticas: {self.chunks_collected}/{self.chunks_received} chunks coletados ({collection_rate:.1f}%)")
        
        return False
    
    def is_collecting(self) -> bool:
        """Retorna se está coletando áudio."""
        return self.collecting_audio
    
    def register_callbacks(self, recognizer):
        """Registra todos os callbacks com o recognizer."""
        recognizer.recognized.connect(self.on_recognized)
        recognizer.speech_start_detected.connect(self.on_speech_start_detected)
        recognizer.speech_end_detected.connect(self.on_speech_end_detected)
        recognizer.recognizing.connect(self.on_recognizing)
        recognizer.session_started.connect(self.on_session_started)
        recognizer.session_stopped.connect(self.on_session_stopped)
        recognizer.canceled.connect(self.on_canceled)
        
        # Registramos o reconhecedor para usar em outras funções, se necessário
        self.recognizer = recognizer
        
        logger.info(f"[{self.call_id}] Callbacks registrados para {'visitante' if self.is_visitor else 'morador'}")
        
        # Logar as propriedades do Azure Speech para depuração
        try:
            logger.info(f"[{self.call_id}] Configurações do Azure Speech:")
            if hasattr(recognizer, 'properties'):
                for key in recognizer.properties:
                    logger.info(f"[{self.call_id}]   - {key}: {recognizer.properties[key]}")
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro ao logar configurações: {e}")
    
    def mark_ia_audio_sent(self):
        """
        Marca que a IA acabou de enviar áudio, para evitar detecção de eco.
        Chamado após o envio de áudio pelo sistema para atualizar o timestamp.
        """
        self.last_ia_audio_time = time.time()
        # Limpar qualquer buffer que possa ter sido coletado acidentalmente
        self.audio_buffer = []
        self.collecting_audio = False
        self.speech_detected = False
        logger.debug(f"[{self.call_id}] Marcado timestamp de áudio da IA: {self.last_ia_audio_time}")