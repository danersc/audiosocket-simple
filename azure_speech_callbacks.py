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
        role = "visitante" if self.is_visitor else "morador"
        
        # Log detalhado para entender o que está acontecendo com o evento
        logger.info(f"[{self.call_id}] Evento on_recognized disparado! Reason: {evt.result.reason}, Buffer: {len(self.audio_buffer)} frames")
        
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            # Fala foi reconhecida com sucesso
            logger.info(f"[{self.call_id}] Azure Speech reconheceu texto do {role}: '{evt.result.text}'")
            
            # Criar cópia local dos dados para processar para evitar problemas de concorrência
            text_to_process = evt.result.text
            audio_data = b"".join(self.audio_buffer) if self.audio_buffer else b""
            audio_size = len(audio_data)
            
            # Limpar o timeout já que o reconhecimento foi bem-sucedido
            self.speech_end_time = None
            
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
            
            # Limpar buffer e preparar para próxima fala
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
        
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            # Nenhuma fala foi reconhecida - analisar detalhes do NoMatch
            try:
                no_match_details = evt.result.no_match_details
                no_match_reason = no_match_details.reason
                logger.info(f"[{self.call_id}] NoMatch com detalhes - Reason: {no_match_reason}")
            except Exception as e:
                logger.info(f"[{self.call_id}] NoMatch sem detalhes disponíveis: {e}")
            
            logger.info(f"[{self.call_id}] Azure Speech não reconheceu fala do {role} (NoMatch)")
            
            # Limpar o timeout já que o reconhecimento foi concluído (mesmo que sem sucesso)
            self.speech_end_time = None
            
            # Se havia coletado algum áudio, ainda processar como possível "sim" curto
            if len(self.audio_buffer) > 0 and self.speech_detected:
                # Criar cópia dos dados para processar
                audio_data = b"".join(self.audio_buffer)
                audio_size = len(audio_data)
                
                # Log com tamanho baseado em frames (~20ms por frame)
                frames_estimate = audio_size / 640
                logger.info(f"[{self.call_id}] Processando áudio não reconhecido - {audio_size} bytes (~{frames_estimate:.1f} frames)")
                
                # Processar como texto vazio (será processado apenas o áudio)
                if self.process_callback:
                    loop = asyncio.get_event_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        self.process_callback("", audio_data), 
                        loop
                    )
                    # Adicionar callback para log de sucesso/erro
                    future.add_done_callback(lambda f: 
                        logger.info(f"[{self.call_id}] Processamento de áudio não reconhecido concluído com sucesso") if not f.exception() 
                        else logger.error(f"[{self.call_id}] Erro no processamento de áudio não reconhecido: {f.exception()}")
                    )
                else:
                    logger.error(f"[{self.call_id}] Processo_callback não definido! Não é possível processar áudio")
            else:
                logger.warning(f"[{self.call_id}] NoMatch sem áudio no buffer ou sem speech_detected={self.speech_detected}")
            
            # Limpar buffer e preparar para próxima fala
            self.audio_buffer = []
            self.collecting_audio = False
            self.speech_detected = False
        
        else:
            # Outros casos como cancelamento ou erro
            logger.warning(f"[{self.call_id}] on_recognized com reason desconhecido: {evt.result.reason}")
            
            # Ainda assim, tentar processar o áudio se tivermos buffer
            if len(self.audio_buffer) > 0:
                audio_data = b"".join(self.audio_buffer)
                audio_size = len(audio_data)
                logger.info(f"[{self.call_id}] Tentando processar {audio_size} bytes de áudio com reason desconhecido")
                
                if self.process_callback:
                    loop = asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(
                        self.process_callback("", audio_data), 
                        loop
                    )
                
                # Limpar estado
                self.audio_buffer = []
                self.collecting_audio = False
                self.speech_detected = False
    
    def on_speech_start_detected(self, evt):
        """Callback quando o início de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        
        # PROTEÇÃO ANTI-ECO SIMPLIFICADA: 
        # Verificar quanto tempo se passou desde o início da fala (usando timestamp do próprio callback)
        # Isso evita que o sistema fique processando constantemente o eco de sua própria resposta
        try:
            # Verificar se já registramos um "último momento de reset" do sistema
            if not hasattr(self, 'last_system_reset_time'):
                self.last_system_reset_time = 0
            
            current_time = time.time()
            time_since_last_reset = current_time - self.last_system_reset_time
            
            # Se a detecção ocorrer menos de 1.5 segundos após o último reset, ignoramos
            # Este valor é mais generoso que o anterior para garantir que funcione
            ANTI_ECHO_GUARD_PERIOD = 1.5  # segundos
            
            if time_since_last_reset < ANTI_ECHO_GUARD_PERIOD:
                logger.warning(f"[{self.call_id}] IGNORANDO detecção de fala por estar muito próxima ao reset do sistema "
                              f"({time_since_last_reset:.2f}s < {ANTI_ECHO_GUARD_PERIOD}s)")
                return  # Simplesmente ignoramos esta detecção
                
            # Atualizar o timestamp do último reset sempre que uma fala válida for detectada
            self.last_system_reset_time = current_time
            logger.info(f"[{self.call_id}] Atualizado timestamp de último reset: {current_time}")
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro na proteção anti-eco simplificada: {e}")
        
        # Se chegou aqui, a detecção é válida
        logger.info(f"[{self.call_id}] Início de fala do {role} detectado pelo Azure Speech")
        if self.call_logger:
            self.call_logger.log_speech_detected(is_visitor=self.is_visitor)
            
        # Resetar quaisquer flags pendentes e limpar estado anterior
        if hasattr(self, 'pending_processing_flag'):
            self.pending_processing_flag = False
        if hasattr(self, 'pending_audio_for_processing'):
            self.pending_audio_for_processing = None
        
        # Iniciar coleta de áudio - com verificação de dupla inicialização
        self.collecting_audio = True
        self.speech_detected = True
        
        # Verificar se temos um buffer inicializado
        if not hasattr(self, 'audio_buffer') or self.audio_buffer is None:
            self.audio_buffer = []
            
        # Utilizar o pre-buffer (se existir) para capturar o início da fala que pode ter ocorrido antes da detecção
        if hasattr(self, 'pre_buffer') and self.pre_buffer:
            # Adicionar o pre-buffer ao início do buffer principal
            pre_buffer_size = len(self.pre_buffer)
            logger.info(f"[{self.call_id}] Adicionando {pre_buffer_size} frames (~{pre_buffer_size*20}ms) do pre-buffer ao início da fala")
            self.audio_buffer = self.pre_buffer + self.audio_buffer
            self.pre_buffer = []  # Limpar o pre-buffer após usar
            
        logger.info(f"[{self.call_id}] Iniciada coleta de áudio de {role} com buffer_size={len(self.audio_buffer)}")
    
    def on_speech_end_detected(self, evt):
        """Callback quando o fim de fala é detectado."""
        role = "visitante" if self.is_visitor else "morador"
        
        # PROTEÇÃO ANTI-ECO SIMPLIFICADA para fim de fala
        # Reutilizamos a mesma lógica do início de fala para garantir consistência
        try:
            # Usar o mesmo mecanismo de tempo mínimo entre eventos que usamos no on_speech_start
            if not hasattr(self, 'last_end_reset_time'):
                self.last_end_reset_time = 0
            
            current_time = time.time()
            time_since_last_reset = current_time - self.last_end_reset_time
            
            # O mesmo período de guarda usado para início de fala
            ANTI_ECHO_GUARD_PERIOD = 1.5  # segundos
            
            if time_since_last_reset < ANTI_ECHO_GUARD_PERIOD:
                logger.warning(f"[{self.call_id}] IGNORANDO fim de fala por estar muito próximo ao último evento "
                              f"({time_since_last_reset:.2f}s < {ANTI_ECHO_GUARD_PERIOD}s)")
                return  # Simplesmente ignoramos esta detecção
                
            # Atualizar timestamp para próxima verificação
            self.last_end_reset_time = current_time
            logger.info(f"[{self.call_id}] Atualizado timestamp de fim de fala: {current_time}")
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro na proteção anti-eco (fim de fala): {e}")
        
        # Verificação de segurança para garantir que temos um áudio_buffer válido
        if not hasattr(self, 'audio_buffer'):
            self.audio_buffer = []
            logger.warning(f"[{self.call_id}] Fim de fala detectado, mas audio_buffer não estava inicializado!")
            
        # Log do fim de fala
        buffer_size = len(self.audio_buffer) if hasattr(self, 'audio_buffer') else 0
        logger.info(f"[{self.call_id}] Fim de fala do {role} detectado - collecting={self.collecting_audio}, buffer_size={buffer_size}")
        
        # *** FILTRAGEM RIGOROSA DE EVENTOS DE FIM DE FALA ***
        # Se não temos detecção de início de fala (collecting=False), vamos ser MUITO criteriosos
        if not self.collecting_audio:
            # Verificar se já tivemos alguma detecção de fala antes - Se não, isso é provavelmente um falso positivo
            if not self.speech_detected:
                logger.warning(f"[{self.call_id}] IGNORANDO fim de fala por não haver início de fala detectado anteriormente")
                return
            
            # Verificar se temos algo no pre-buffer e se tem energia suficiente
            if not hasattr(self, 'pre_buffer') or not self.pre_buffer or len(self.pre_buffer) < 10:  # Mínimo de 10 frames (~200ms)
                logger.warning(f"[{self.call_id}] IGNORANDO fim de fala - pre-buffer muito pequeno ou inexistente")
                return
                
            # Verificar energia do áudio no pre-buffer para confirmar que é uma fala real
            try:
                import struct
                
                # Analisar apenas os últimos 10 frames para economia de processamento
                frames_to_analyze = self.pre_buffer[-10:]
                total_energy = 0
                
                for frame in frames_to_analyze:
                    samples = struct.unpack('<' + 'h' * (len(frame) // 2), frame)
                    frame_energy = sum(sample ** 2 for sample in samples) / len(samples)
                    total_energy += frame_energy
                
                avg_energy = total_energy / len(frames_to_analyze)
                ENERGY_THRESHOLD = 800  # Threshold mais alto para confirmar que é fala real
                
                if avg_energy < ENERGY_THRESHOLD:
                    logger.warning(f"[{self.call_id}] IGNORANDO fim de fala - energia muito baixa no pre-buffer ({avg_energy:.2f} < {ENERGY_THRESHOLD})")
                    return
                    
                logger.info(f"[{self.call_id}] Fim de fala CONFIRMADO por energia do áudio ({avg_energy:.2f} > {ENERGY_THRESHOLD})")
            except Exception as e:
                logger.error(f"[{self.call_id}] Erro ao verificar energia do pre-buffer: {e}")
                # Em caso de erro na verificação, agimos conservadoramente e ignoramos o evento
                return
        
        # Registrar evento no log APENAS se passou pelas verificações
        if self.call_logger:
            self.call_logger.log_speech_ended(0, is_visitor=self.is_visitor)  # Duração desconhecida neste ponto
        
        # IMPORTANTE: Forçar a coleta e verificar pre-buffer independentemente do estado collecting_audio
        # Inicializamos o audio_buffer com pré-buffer MESMO se collecting_audio já estiver True
        
        # Verificar dados no pre-buffer que podem ser utilizados
        if hasattr(self, 'pre_buffer') and self.pre_buffer and len(self.pre_buffer) > 0:
            pre_buffer_size = len(self.pre_buffer) 
            
            # Se não estamos coletando, inicializamos com pre-buffer
            if not self.collecting_audio:
                logger.warning(f"[{self.call_id}] Fim de fala detectado com collecting=False - ativando coleta retroativamente")
                self.collecting_audio = True
                self.speech_detected = True
                logger.info(f"[{self.call_id}] Usando {pre_buffer_size} frames do pre-buffer para recuperar áudio")
                self.audio_buffer = self.pre_buffer.copy()
            # Se já estamos coletando, garantimos que os dados do pre-buffer estejam no início do buffer principal
            else:
                # Verificar se os dados do pre-buffer já estão no início do audio_buffer
                # Comparando os primeiros frames
                # Se o audio_buffer tiver menos frames que o pre-buffer ou se os frames iniciais forem diferentes
                if len(self.audio_buffer) < len(self.pre_buffer) or not all(a == b for a, b in zip(self.pre_buffer, self.audio_buffer[:len(self.pre_buffer)])):
                    logger.info(f"[{self.call_id}] Adicionando {pre_buffer_size} frames do pre-buffer ao início do buffer já existente com {len(self.audio_buffer)} frames")
                    # Adicionamos o pre-buffer no início do audio_buffer existente
                    self.audio_buffer = self.pre_buffer + self.audio_buffer
                
            # Limpar pre-buffer após uso
            self.pre_buffer = []
        # Se não temos pre-buffer mas também não estamos coletando, ativamos a coleta
        elif not self.collecting_audio:
            logger.warning(f"[{self.call_id}] Fim de fala detectado com collecting=False mas sem pre-buffer disponível")
            self.collecting_audio = True
            self.speech_detected = True
        
        # Se após as tentativas de recuperação ainda não temos áudio, verificamos mais uma vez o pre-buffer
        if len(self.audio_buffer) == 0:
            # Última tentativa - verificar se o pre-buffer foi atualizado desde que entramos neste método
            if hasattr(self, 'pre_buffer') and len(self.pre_buffer) > 0:
                logger.warning(f"[{self.call_id}] Última tentativa: pre-buffer contém {len(self.pre_buffer)} frames")
                self.audio_buffer = self.pre_buffer.copy()
                self.pre_buffer = []
                self.collecting_audio = True
                self.speech_detected = True
            else:
                logger.warning(f"[{self.call_id}] Fim de fala detectado, mas buffer está vazio mesmo após tentativas de recuperação")
                return
                
        # *** VERIFICAÇÃO FINAL DE TAMANHO MÍNIMO DO BUFFER ***
        # Exigimos um mínimo de frames para considerar como fala válida
        MINIMUM_VALID_FRAMES = 15  # Aproximadamente 300ms de áudio
        
        if len(self.audio_buffer) < MINIMUM_VALID_FRAMES:
            logger.warning(f"[{self.call_id}] Buffer muito pequeno para processamento ({len(self.audio_buffer)} < {MINIMUM_VALID_FRAMES} frames) - descartando evento")
            # Limpar buffer e cancelar evento
            self.audio_buffer = []
            self.collecting_audio = False
            return
        
        # Criar cópia dos dados para processar
        audio_data = b"".join(self.audio_buffer)
        buffer_size = len(self.audio_buffer)
        audio_bytes = len(audio_data)
        audio_duration_ms = buffer_size * 20  # cada frame tem ~20ms
        
        logger.info(f"[{self.call_id}] Processando áudio após fim de fala: {buffer_size} frames (~{audio_duration_ms}ms), {audio_bytes} bytes")
        
        # Garantir tamanho mínimo de áudio para evitar ruído e falsos positivos
        # 5 frames = ~100ms de áudio, mínimo razoável para uma expressão curta como "sim"
        if buffer_size >= 5:
            # Processar via ciclo principal - método mais seguro e thread-safe
            if audio_data:
                logger.info(f"[{self.call_id}] Preparando {len(audio_data)} bytes para processamento seguro")
                
                try:
                    # Configurar para processamento no próximo ciclo
                    self.pending_audio_for_processing = audio_data
                    self.pending_processing_flag = True
                    logger.info(f"[{self.call_id}] Áudio marcado para processamento no próximo ciclo: {len(audio_data)} bytes")
                    
                    # Limpar buffer para próxima fala
                    self.audio_buffer = []
                    logger.info(f"[{self.call_id}] Buffer limpo, dados salvos para processamento")
                except Exception as e:
                    logger.error(f"[{self.call_id}] Erro ao preparar áudio para processamento: {e}")
            else:
                logger.warning(f"[{self.call_id}] Sem dados de áudio válidos para processar")
        else:
            logger.warning(f"[{self.call_id}] Buffer muito pequeno ({buffer_size} frames) - possível ruído")
        
        # Configurar timeout de segurança
        self.speech_end_time = time.time()
        self.recognition_timeout = 3.0
        
        # Não usamos mais o timeout baseado em loop.call_later, pois causa problemas com threads
        # Em vez disso, apenas marcamos para verificação no próximo ciclo de processamento
        try:
            # Opção mais segura - marcar para verificação regular no próximo ciclo
            if not hasattr(self, 'timeout_check_needed'):
                self.timeout_check_needed = True
                self.timeout_check_time = time.time() + self.recognition_timeout
                logger.info(f"[{self.call_id}] Timeout de {self.recognition_timeout}s marcado para verificação no próximo ciclo")
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro ao configurar timeout: {e}")
            
        # Mantemos collecting_audio=False para evitar duplo processamento
        self.collecting_audio = False
    
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
        Adiciona um chunk de áudio ao buffer, com mecanismos de segurança avançados.
        
        Returns:
            True se o áudio estiver sendo coletado, False caso contrário
        """
        # Verificar se o chunk é válido
        if not chunk or len(chunk) == 0:
            logger.warning(f"[{self.call_id}] Tentativa de adicionar chunk vazio ignorada")
            return False
        
        # VERIFICAÇÃO DE ENERGIA DO ÁUDIO
        # Calcular energia do áudio para garantir que não estamos processando ruído
        try:
            # Convertendo bytes para valores PCM (16-bit signed little-endian)
            import struct
            
            # Pares de bytes para valores de 16 bits
            samples = struct.unpack('<' + 'h' * (len(chunk) // 2), chunk)
            
            # Calcular energia do áudio (soma dos quadrados)
            energy = sum(sample ** 2 for sample in samples) / len(samples)
            
            # Se a energia for muito baixa, considerar como silêncio ou ruído de fundo
            ENERGY_THRESHOLD = 500  # valor ajustável dependendo do ambiente
            
            if energy < ENERGY_THRESHOLD:
                if not hasattr(self, 'low_energy_counter'):
                    self.low_energy_counter = 0
                self.low_energy_counter += 1
                
                # Log a cada 20 frames para não poluir demais (a cada ~0.4 segundos)
                if self.low_energy_counter % 20 == 0:
                    logger.debug(f"[{self.call_id}] Baixa energia detectada ({energy:.2f} < {ENERGY_THRESHOLD})")
                
                # Se estamos coletando áudio e a energia é baixa, vamos adicionar mesmo assim
                # para não perder o final das palavras onde a energia cai
                if not self.collecting_audio:
                    # Se não estamos coletando, manteremos no pre-buffer de qualquer forma
                    pass
                
            else:
                # Energia suficiente para ser considerada fala potencial
                if hasattr(self, 'low_energy_counter'):
                    self.low_energy_counter = 0
                
                # Essa pode ser uma boa oportunidade para ativar a coleta
                # se ainda não estiver coletando mas a energia subiu significativamente
                if not self.collecting_audio and energy > ENERGY_THRESHOLD * 2:  # 2x o threshold para ter certeza
                    # Isso pode indicar um início de fala que o Azure Speech não detectou
                    logger.info(f"[{self.call_id}] Alta energia detectada ({energy:.2f}) - possível fala não detectada pelo Azure")
                    # Não vamos ativar a coleta aqui, deixamos o detector de fala fazer isso 
                    # para evitar falsos positivos
        
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro no cálculo de energia do áudio: {e}")
        
        # PROTEÇÃO ANTI-ECO: Verifique há quanto tempo recebemos o último FRAME
        # Isso ajuda a detectar quando a IA acabou de falar e está detectando seu próprio áudio
        try:
            # Inicializar o timestamp do último frame, se necessário
            if not hasattr(self, 'last_frame_time'):
                self.last_frame_time = 0
                
            current_time = time.time()
            
            # Se estamos no período imediatamente após o áudio da IA (1 a 2 segundos)
            # e o buffer está vazio, é provável que seja eco da própria IA
            if current_time - self.last_frame_time > 1.0 and len(self.audio_buffer) == 0:
                # Registrar que recebemos um frame, mas não coletar ainda
                # Isso faz com que os primeiros frames após um período sem áudio sejam ignorados
                # até que tenhamos certeza de que não é eco
                self.last_frame_time = current_time
                
                # Reiniciar a contagem para os primeiros 5 frames após um silêncio longo
                # Este é um mecanismo adicional de segurança
                if not hasattr(self, 'frames_after_silence'):
                    self.frames_after_silence = 0
                self.frames_after_silence += 1
                
                # Ignorar os primeiros frames após um período longo de silêncio
                # Isso elimina o eco inicial da própria IA
                if self.frames_after_silence <= 5:
                    # Simplesmente ignorar os frames iniciais
                    return False
        except Exception as e:
            logger.error(f"[{self.call_id}] Erro na proteção anti-eco (add_audio_chunk): {e}")
            
        # Verificação de segurança para inicializar buffers se necessário
        if not hasattr(self, 'audio_buffer') or self.audio_buffer is None:
            self.audio_buffer = []
            logger.debug(f"[{self.call_id}] audio_buffer inicializado durante add_audio_chunk")
            
        if not hasattr(self, 'pre_buffer') or self.pre_buffer is None:
            self.pre_buffer = []
            logger.debug(f"[{self.call_id}] pre_buffer inicializado durante add_audio_chunk")
        
        # Atualizar o timestamp do último frame recebido
        self.last_frame_time = time.time()
            
        # Lógica principal de coleta
        if self.collecting_audio:
            # Adicionar ao buffer principal
            self.audio_buffer.append(chunk)
            
            # Log para monitoramento (a cada 20 frames = ~0.4s)
            if len(self.audio_buffer) % 20 == 0:
                logger.debug(f"[{self.call_id}] Coletando áudio: {len(self.audio_buffer)} frames (~{len(self.audio_buffer)*20}ms)")
            
            # Limitar tamanho do buffer para evitar estouro de memória
            buffer_limit = 750  # 15 segundos de áudio (750 frames de 20ms)
            if len(self.audio_buffer) > buffer_limit:
                # Manter apenas os frames mais recentes
                excess = len(self.audio_buffer) - buffer_limit
                self.audio_buffer = self.audio_buffer[excess:]
                
                # Log apenas ocasionalmente para não poluir
                if excess % 50 == 0:
                    logger.warning(f"[{self.call_id}] Buffer grande demais! Removidos {excess} frames antigos, mantendo {buffer_limit} frames recentes.")
            
            # Verificar se temos muito tempo de silêncio com fala detectada anteriormente
            if self.speech_detected and len(self.audio_buffer) > 150:  # Mais de 3s de áudio
                # Forçar processamento via flag para próxima verificação
                if not hasattr(self, 'long_buffer_flag') or not self.long_buffer_flag:
                    logger.info(f"[{self.call_id}] Buffer grande ({len(self.audio_buffer)} frames) com fala detectada - marcar para verificação")
                    self.long_buffer_flag = True
            
            return True
        else:
            # Manter buffer de pré-detecção para capturar início da fala
            self.pre_buffer.append(chunk)
            
            # Tamanho do pre-buffer aumentado para 2 segundos de áudio para melhor captura
            # Isto é importante para casos onde o sistema detecta o fim da fala sem ter detectado o início
            pre_buffer_limit = 100  # 2 segundos (100 frames de 20ms)
            if len(self.pre_buffer) > pre_buffer_limit:
                self.pre_buffer.pop(0)  # Remove o frame mais antigo
                
            # Verificação periódica para detecção proativa de fala
            if len(self.pre_buffer) % 50 == 0:  # A cada ~1s verificamos atividade
                logger.debug(f"[{self.call_id}] Pre-buffer mantendo {len(self.pre_buffer)} frames")
                
            return False
    
    def is_collecting(self) -> bool:
        """Retorna se está coletando áudio."""
        return self.collecting_audio
    
    def _check_recognition_timeout(self):
        """
        Função mantida por compatibilidade, mas não é mais usada diretamente.
        O timeout agora é verificado pelo ciclo principal em audiosocket_handler.py.
        
        Isso resolve problemas com "There is no current event loop in thread" que
        ocorriam quando esta função era chamada via loop.call_later().
        """
        logger.info(f"[{self.call_id}] _check_recognition_timeout chamado, mas não é mais usado diretamente")
        
        # Marcar para verificação no ciclo principal
        self.timeout_check_needed = True
        self.timeout_check_time = time.time()  # Verificar imediatamente
    
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