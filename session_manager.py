import asyncio
import logging
from typing import Dict, Optional, List
from uuid import uuid4

# Importe a função que processa a mensagem do usuário usando a Crew:
# Ajuste o caminho conforme o nome e local do seu arquivo de IA.
from ai.crew import process_user_message_with_coordinator

logger = logging.getLogger(__name__)


class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id

        # Estados (simples) de cada lado:
        self.visitor_state = "USER_TURN"
        self.resident_state = "STANDBY"

        # Histórico textual (por debug, se quiser)
        self.history: List[str] = []

        # Fila de mensagens pendentes para cada lado
        self.visitor_queue: asyncio.Queue = asyncio.Queue()
        self.resident_queue: asyncio.Queue = asyncio.Queue()

        # Onde armazenamos dados extraídos pela IA (intent, interlocutor_name, etc.)
        self.intent_data = {}


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

    # -------------------------------------------------------------
    # Métodos para pegar mensagens pendentes (necessários
    # no audiosocket_handler.py)
    # -------------------------------------------------------------
    def get_message_for_visitor(self, session_id: str) -> Optional[str]:
        """
        Retorna a próxima mensagem pendente ao VISITANTE, ou None se não houver.
        Chamado periodicamente pelo audiosocket_handler para enviar ao usuário.
        """
        session = self.get_session(session_id)
        if not session:
            return None
        if session.visitor_queue.empty():
            return None
        return session.visitor_queue.get_nowait()

    def get_message_for_resident(self, session_id: str) -> Optional[str]:
        """
        Retorna a próxima mensagem pendente ao MORADOR, ou None se não houver.
        Chamado periodicamente pelo audiosocket_handler para enviar ao usuário.
        """
        session = self.get_session(session_id)
        if not session:
            return None
        if session.resident_queue.empty():
            return None
        return session.resident_queue.get_nowait()

    # -------------------------------------------------------------
    # VISITOR: Processar texto e chamar IA
    # -------------------------------------------------------------
    def process_visitor_text(self, session_id: str, text: str):
        """
        Recebe o texto do visitante e chama a IA (Crew) para obter a resposta.
        Em seguida, enfileira a(s) resposta(s) para o visitante ou morador, se houver.
        """
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)

        logger.info(f"[Session {session_id}] Visitor disse: {text}")
        session.history.append(f"[Visitor] {text}")

        try:
            # Chama a IA (Crew):
            #   Exemplo de retorno:
            #   {
            #     "mensagem": "Texto da resposta da IA",
            #     "dados": {...},
            #     "valid_for_action": False,
            #     "set_call_status": "USER_TURN"
            #   }
            result = process_user_message_with_coordinator(session_id, text)
            logger.debug(f"[Session {session_id}] Resposta IA: {result}")

            if result:
                # 1) Enfileira a mensagem principal para o visitante
                msg = result.get("mensagem")
                if msg:
                    session.visitor_queue.put_nowait(msg)

                # 2) Atualiza partial intent
                if "dados" in result:
                    session.intent_data.update(result["dados"])

                # 3) Se valid_for_action for True, podemos enviar msg ao morador
                #    (depende da sua lógica)
                if result.get("valid_for_action"):
                    session.resident_queue.put_nowait("O visitante concluiu a intenção. Pode autorizar?")

                # 4) Se "set_call_status" existe, mudar o visitor_state
                new_status = result.get("set_call_status")
                if new_status:
                    session.visitor_state = new_status

        except Exception as e:
            logger.error(f"Erro ao chamar IA (visitor): {e}")
            session.visitor_queue.put_nowait("Ocorreu um erro ao processar sua mensagem. Tente novamente.")


    # -------------------------------------------------------------
    # RESIDENT: Processar texto e (opcionalmente) chamar IA
    # -------------------------------------------------------------
    def process_resident_text(self, session_id: str, text: str):
        """
        Recebe o texto do morador.
        Pode ou não chamar a IA, dependendo da sua lógica.
        Exemplo: se 'sim' => autoriza; se 'não' => nega.
        """
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)

        logger.info(f"[Session {session_id}] Resident disse: {text}")
        session.history.append(f"[Resident] {text}")

        # Exemplo simples interpretando "sim" ou "não"
        if "sim" in text.lower():
            session.visitor_queue.put_nowait("O morador autorizou sua entrada.")
            session.resident_state = "IA_TURN"
        elif "não" in text.lower() or "nao" in text.lower():
            session.visitor_queue.put_nowait("O morador negou a entrada.")
            session.resident_state = "IA_TURN"
        else:
            # Se quiser, chamar a IA aqui também. Ex.:
            #   result = process_user_message_with_coordinator(session_id, text)
            #   ...
            # Ou algo manual simples:
            response = f"Morador, não entendi (você disse: {text}). Responda sim ou não."
            session.resident_queue.put_nowait(response)
