#!/usr/bin/env python3
# state_machine.py - Máquina de estado simplificada para gerenciar turnos de conversa

import enum
import logging
import uuid
from datetime import datetime
from typing import Callable, List, Dict, Optional

logger = logging.getLogger(__name__)

class State(enum.Enum):
    """Estados simplificados para a conversa entre usuário e IA."""
    STANDBY = "STANDBY"      # Estado inicial, aguardando nova chamada
    USER_TURN = "USER_TURN"  # Turno do usuário (sistema está ouvindo)
    WAITING = "WAITING"      # Estado intermediário de processamento
    IA_TURN = "IA_TURN"      # Turno da IA (sistema está respondendo)

class StateMachine:
    """
    Máquina de estados simplificada para controlar o fluxo de comunicação
    entre o usuário e a IA em uma chamada.
    """
    
    def __init__(self):
        # Inicializa no estado STANDBY
        self.current_state = State.STANDBY
        # ID da conversa (será gerado quando uma nova chamada começar)
        self.conversation_id = None
        # Registro de callbacks para mudanças de estado
        self.state_change_callbacks: Dict[State, List[Callable]] = {
            state: [] for state in State
        }
        # Histórico de transcrições para debug
        self.transcricoes = []
        # Última resposta da IA
        self.ultima_resposta = None
        
        logger.info(f"Máquina de estados inicializada em {self.current_state}")
    
    def get_state(self) -> State:
        """Retorna o estado atual."""
        return self.current_state
    
    def transition_to(self, new_state: State) -> None:
        """
        Transiciona para um novo estado e executa callbacks registrados.
        
        Args:
            new_state: O novo estado para o qual transicionar
        """
        if new_state == self.current_state:
            # Já estamos nesse estado, não precisa fazer nada
            return
        
        old_state = self.current_state
        self.current_state = new_state
        logger.info(f"Transição de estado: {old_state} -> {new_state}")
        
        # Se estamos saindo do estado WAITING, registra isso no log
        if old_state == State.WAITING:
            logger.info("Saindo do estado WAITING")
            # Registramos uma mensagem do sistema para indicar a mudança de estado
            self.registrar_transcricao_sistema(f"Estado alterado: {old_state.value} -> {new_state.value}")
        
        # Executa callbacks registrados para este estado
        for callback in self.state_change_callbacks.get(new_state, []):
            try:
                callback()
            except Exception as e:
                logger.error(f"Erro no callback de mudança de estado: {e}")
    
    def on_state_change(self, state: State, callback: Callable) -> None:
        """
        Registra um callback para ser chamado quando a máquina entrar em um estado específico.
        
        Args:
            state: O estado para registrar o callback
            callback: A função a ser chamada
        """
        if state in self.state_change_callbacks:
            self.state_change_callbacks[state].append(callback)
    
    def is_user_turn(self) -> bool:
        """Verifica se é o turno do usuário."""
        return self.current_state == State.USER_TURN
    
    def is_ai_turn(self) -> bool:
        """Verifica se é o turno da IA."""
        return self.current_state == State.IA_TURN
    
    def is_waiting(self) -> bool:
        """Verifica se está no estado de espera/processamento."""
        return self.current_state == State.WAITING
        
    def is_standby(self) -> bool:
        """Verifica se está no estado inicial."""
        return self.current_state == State.STANDBY
        
    def start_new_conversation(self, standby=False) -> str:
        """
        Inicia uma nova conversa, gerando um ID único e mudando para o estado apropriado.
        
        Args:
            standby: Se True, mantém o estado como STANDBY, caso contrário muda para USER_TURN
            
        Returns:
            O ID da conversa gerado
        """
        self.conversation_id = str(uuid.uuid4())
        # Limpa os registros anteriores
        self.transcricoes = []
        self.ultima_resposta = None
        
        # Define o estado inicial
        if not standby:
            self.transition_to(State.USER_TURN)
        else:
            # Já está em STANDBY por padrão, só garante isso
            self.transition_to(State.STANDBY)
            
        logger.info(f"Nova conversa iniciada com ID: {self.conversation_id}")
        return self.conversation_id
        
    def registrar_transcricao_usuario(self, texto: str) -> None:
        """
        Registra uma transcrição do usuário no histórico.
        
        Args:
            texto: O texto transcrito
        """
        self.transcricoes.append({
            "timestamp": datetime.now().isoformat(),
            "origem": "usuario",
            "texto": texto
        })
        logger.info(f"Transcrição do usuário registrada: {texto}")
        
    def registrar_transcricao_ia(self, texto: str, resposta_completa: Optional[Dict] = None) -> None:
        """
        Registra uma transcrição da IA no histórico.
        
        Args:
            texto: O texto da resposta
            resposta_completa: Opcionalmente, a resposta completa da IA (incluindo metadata)
        """
        self.transcricoes.append({
            "timestamp": datetime.now().isoformat(),
            "origem": "ia",
            "texto": texto
        })
        self.ultima_resposta = resposta_completa
        logger.info(f"Resposta da IA registrada: {texto}")
        
    def registrar_transcricao_sistema(self, texto: str) -> None:
        """
        Registra uma mensagem do sistema no histórico.
        
        Args:
            texto: O texto da mensagem do sistema
        """
        self.transcricoes.append({
            "timestamp": datetime.now().isoformat(),
            "origem": "sistema",
            "texto": texto
        })
        logger.info(f"Mensagem do sistema registrada: {texto}")
        
    def obter_historico_transcricoes(self) -> List[Dict]:
        """
        Retorna o histórico de transcrições.
        
        Returns:
            Lista de dicionários com as transcrições
        """
        return self.transcricoes
        
    def get_conversation_id(self) -> Optional[str]:
        """
        Retorna o ID da conversa atual ou None se não houver conversa ativa.
        
        Returns:
            ID da conversa ou None
        """
        return self.conversation_id
        
    def end_conversation(self) -> None:
        """
        Finaliza a conversa atual, volta para o estado STANDBY.
        """
        logger.info(f"Conversa {self.conversation_id} finalizada")
        self.conversation_id = None
        self.transition_to(State.STANDBY)