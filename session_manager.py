# session_manager.py

import asyncio
import logging
from typing import Dict, Optional, List
from uuid import uuid4

# Mantenha seu import do crew se quiser, mas não vamos chamar direto aqui
# from ai.crew import process_user_message_with_coordinator

from conversation_flow import ConversationFlow

logger = logging.getLogger(__name__)


class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id

        self.visitor_state = "USER_TURN"
        self.resident_state = "STANDBY"

        self.history: List[str] = []

        # Filas de mensagens
        self.visitor_queue: asyncio.Queue = asyncio.Queue()
        self.resident_queue: asyncio.Queue = asyncio.Queue()

        self.intent_data = {}

        # Aqui criamos uma instância do Flow para cada sessão
        self.flow = ConversationFlow()


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, SessionData] = {}

    def create_session(self, session_id: Optional[str] = None) -> SessionData:
        if not session_id:
            session_id = str(uuid4())

        if session_id not in self.sessions:
            self.sessions[session_id] = SessionData(session_id)
            logger.info(f"[SessionManager] Criada nova sessão: {session_id}")
        return self.sessions[session_id]

    def get_session(self, session_id: str) -> Optional[SessionData]:
        return self.sessions.get(session_id)

    # Métodos p/ enfileirar msgs (chamados no flow)
    def enfileirar_visitor(self, session_id: str, mensagem: str):
        session = self.get_session(session_id)
        if session:
            session.visitor_queue.put_nowait(mensagem)

    def enfileirar_resident(self, session_id: str, mensagem: str):
        session = self.get_session(session_id)
        if session:
            session.resident_queue.put_nowait(mensagem)

    def get_message_for_visitor(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        if not session:
            return None
        if session.visitor_queue.empty():
            return None
        return session.visitor_queue.get_nowait()

    def get_message_for_resident(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        if not session:
            return None
        if session.resident_queue.empty():
            return None
        return session.resident_queue.get_nowait()

    # -------------------------------------------------------------
    # Novo process_visitor_text + process_resident_text
    # -------------------------------------------------------------
    def process_visitor_text(self, session_id: str, text: str):
        """
        Agora chamamos o Flow para lidar com a msg do visitante.
        """
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)

        # logs + history
        logger.info(f"[Session {session_id}] Visitor disse: {text}")
        session.history.append(f"[Visitor] {text}")

        # repassar p/ on_visitor_message
        session.flow.on_visitor_message(session_id, text, self)

    def process_resident_text(self, session_id: str, text: str):
        """
        Agora chamamos o Flow para lidar com a msg do morador.
        """
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)

        logger.info(f"[Session {session_id}] Resident disse: {text}")
        session.history.append(f"[Resident] {text}")

        session.flow.on_resident_message(session_id, text, self)

    def end_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"[SessionManager] Sessão {session_id} finalizada e removida.")
