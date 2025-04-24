#!/usr/bin/env python3
# state_machine.py - Máquina de estado simplificada para gerenciar turnos de conversa

import enum
import logging
from uuid_v7 import uuid_v7
from datetime import datetime
from typing import Callable, List, Dict, Optional
import asyncio  # <-- necessário para as funções assíncronas adicionadas

logger = logging.getLogger(__name__)


class State(enum.Enum):
    """Estados simplificados para a conversa entre usuário e IA."""
    STANDBY = "STANDBY"  # Estado inicial, aguardando nova chamada
    USER_TURN = "USER_TURN"  # Turno do usuário (sistema está ouvindo)
    WAITING = "WAITING"  # Estado intermediário de processamento
    IA_TURN = "IA_TURN"  # Turno da IA (sistema está respondendo)


class StateMachine:
    """
    Máquina de estados simplificada para controlar o fluxo de comunicação
    entre o usuário e a IA em uma chamada.
    """

    def __init__(self):
        self.current_state = State.STANDBY
        self.conversation_id = None
        self.state_change_callbacks: Dict[State, List[Callable]] = {
            state: [] for state in State
        }
        self.transcricoes = []
        self.ultima_resposta = None
        logger.info(f"Máquina de estados inicializada em {self.current_state}")

    def get_state(self) -> State:
        return self.current_state

    def transition_to(self, new_state: State) -> None:
        if new_state == self.current_state:
            logger.debug(f"Ignorando transição redundante para {new_state}")
            return

        old_state = self.current_state
        self.current_state = new_state
        logger.info(f"Transição de estado: {old_state} -> {new_state}")

        if old_state == State.IA_TURN and new_state == State.USER_TURN:
            logger.info("*** IMPORTANTE: Transição de IA_TURN para USER_TURN - ativando escuta ***")
            self.registrar_transcricao_sistema("Sistema ativou escuta - aguardando fala do usuário")
        elif old_state == State.WAITING:
            logger.info(f"Saindo do estado WAITING para {new_state}")
            self.registrar_transcricao_sistema(f"Estado alterado: {old_state.value} -> {new_state.value}")
        if new_state == State.USER_TURN:
            logger.info("*** Sistema pronto para ouvir o usuário ***")

        for callback in self.state_change_callbacks.get(new_state, []):
            try:
                callback()
            except Exception as e:
                logger.error(f"Erro no callback de mudança de estado: {e}")

    def on_state_change(self, state: State, callback: Callable) -> None:
        if state in self.state_change_callbacks:
            self.state_change_callbacks[state].append(callback)

    def is_user_turn(self) -> bool:
        return self.current_state == State.USER_TURN

    def is_ai_turn(self) -> bool:
        return self.current_state == State.IA_TURN

    def is_waiting(self) -> bool:
        return self.current_state == State.WAITING

    def is_standby(self) -> bool:
        return self.current_state == State.STANDBY

    def start_new_conversation(self, standby=False) -> str:
        # Usando UUID v7 baseado em timestamp para melhor ordenação e compatibilidade
        self.conversation_id = str(uuid_v7())
        self.transcricoes = []
        self.ultima_resposta = None

        if not standby:
            self.transition_to(State.USER_TURN)
        else:
            self.transition_to(State.STANDBY)

        logger.info(f"Nova conversa iniciada com ID: {self.conversation_id}")
        return self.conversation_id

    def registrar_transcricao_usuario(self, texto: str) -> None:
        self.transcricoes.append({
            "timestamp": datetime.now().isoformat(),
            "origem": "usuario",
            "texto": texto
        })
        logger.info(f"Transcrição do usuário registrada: {texto}")

    def registrar_transcricao_ia(self, texto: str, resposta_completa: Optional[Dict] = None) -> None:
        self.transcricoes.append({
            "timestamp": datetime.now().isoformat(),
            "origem": "ia",
            "texto": texto
        })
        self.ultima_resposta = resposta_completa
        logger.info(f"Resposta da IA registrada: {texto}")

    def registrar_transcricao_sistema(self, texto: str) -> None:
        self.transcricoes.append({
            "timestamp": datetime.now().isoformat(),
            "origem": "sistema",
            "texto": texto
        })
        logger.info(f"Mensagem do sistema registrada: {texto}")

    def obter_historico_transcricoes(self) -> List[Dict]:
        return self.transcricoes

    def get_conversation_id(self) -> Optional[str]:
        return self.conversation_id

    def end_conversation(self) -> None:
        logger.info(f"Conversa {self.conversation_id} finalizada")
        self.conversation_id = None
        self.transition_to(State.STANDBY)

    # Novas funções adicionadas:
    async def wait_for_state(self, state: State):
        """Aguarda até que o estado especificado seja atingido."""
        while self.current_state != state:
            await asyncio.sleep(0.1)

    async def wait_for_state_change(self):
        """Aguarda até que ocorra uma mudança do estado atual."""
        current_state = self.current_state
        while self.current_state == current_state:
            await asyncio.sleep(0.1)
