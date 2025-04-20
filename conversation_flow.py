# conversation_flow.py

import logging
from enum import Enum, auto
from typing import Optional

from ai.crew import process_user_message_with_coordinator
from ai.tools import validar_intent_com_fuzzy

import pika
import json
import asyncio  ### PASSO 2: precisamos de asyncio

logger = logging.getLogger(__name__)

class FlowState(Enum):
    COLETANDO_DADOS = auto()
    VALIDADO = auto()
    CHAMANDO_MORADOR = auto()
    ESPERANDO_MORADOR = auto()
    FINALIZADO = auto()

class ConversationFlow:
    """
    Define o fluxo de interação entre visitante e morador, passo a passo.
    """

    def __init__(self):
        self.state = FlowState.COLETANDO_DADOS
        self.intent_data = {}
        self.is_fuzzy_valid = False
        self.voip_number_morador: Optional[str] = None

        # Para controlar tentativas de chamada
        self.tentativas_chamada = 0  ### PASSO 2

    # ---------------
    # VISITOR
    # ---------------
    def on_visitor_message(self, session_id: str, text: str, session_manager):
        logger.debug(f"[Flow] Visitor message in state={self.state}, text='{text}'")

        if self.state == FlowState.COLETANDO_DADOS:
            result = process_user_message_with_coordinator(session_id, text)
            logger.debug(f"[Flow] result IA: {result}")

            # Atualiza self.intent_data com quaisquer dados retornados
            if result and "dados" in result:
                for k, v in result["dados"].items():
                    self.intent_data[k] = v

            # Se veio alguma mensagem para o visitante, enfileira
            if result and "mensagem" in result:
                session_manager.enfileirar_visitor(session_id, result["mensagem"])

            # Se valid_for_action, tentamos fuzzy
            if result and result.get("valid_for_action"):
                fuzzy_res = validar_intent_com_fuzzy(self.intent_data)
                logger.info(f"[Flow] fuzzy= {fuzzy_res}")

                if fuzzy_res["status"] == "válido":
                    self.is_fuzzy_valid = True
                    self.voip_number_morador = fuzzy_res.get("voip_number")
                    self.state = FlowState.VALIDADO

                    # Mensagem curta ao visitante:
                    session_manager.enfileirar_visitor(
                        session_id,
                        "Ok, vamos entrar em contato com o morador. Aguarde, por favor."
                    )

                    # Avança para CHAMANDO_MORADOR
                    self.state = FlowState.CHAMANDO_MORADOR
                    self.chamar_morador(session_id, session_manager)
                else:
                    session_manager.enfileirar_visitor(
                        session_id,
                        f"Desculpe, dados inválidos: {fuzzy_res.get('reason','motivo')}. Vamos tentar novamente."
                    )

        elif self.state == FlowState.CHAMANDO_MORADOR:
            session_manager.enfileirar_visitor(
                session_id,
                "Ainda estou tentando chamar o morador, aguarde..."
            )

        elif self.state == FlowState.ESPERANDO_MORADOR:
            session_manager.enfileirar_visitor(
                session_id,
                "O morador está na linha. Aguarde a resposta."
            )

        elif self.state == FlowState.FINALIZADO:
            session_manager.enfileirar_visitor(session_id, "A chamada já foi encerrada. Obrigado.")
        else:
            session_manager.enfileirar_visitor(session_id, "Aguarde, por favor.")

    # ---------------
    # RESIDENT
    # ---------------
    def on_resident_message(self, session_id: str, text: str, session_manager):
        logger.debug(f"[Flow] Resident message in state={self.state}, text='{text}'")

        if self.state == FlowState.CHAMANDO_MORADOR:
            # Significa que o morador atendeu e começou a falar
            self.state = FlowState.ESPERANDO_MORADOR
            session_manager.enfileirar_resident(session_id, "Olá, morador! O visitante pediu acesso...")
            session_manager.enfileirar_visitor(session_id, "O morador atendeu. Aguarde a resposta.")

        elif self.state == FlowState.ESPERANDO_MORADOR:
            # Esperamos SIM ou NÃO
            lower_text = text.lower()
            if "sim" in lower_text:
                session_manager.enfileirar_visitor(session_id, "Morador autorizou sua entrada!")
                self.state = FlowState.FINALIZADO
                self._finalizar(session_id, session_manager)
            elif "não" in lower_text or "nao" in lower_text:
                session_manager.enfileirar_visitor(session_id, "Morador negou a entrada.")
                self.state = FlowState.FINALIZADO
                self._finalizar(session_id, session_manager)
            else:
                session_manager.enfileirar_resident(session_id, "Não entendi. Responda SIM ou NÃO.")

        elif self.state == FlowState.FINALIZADO:
            session_manager.enfileirar_resident(session_id, "O fluxo já foi finalizado. Obrigado.")

        elif self.state == FlowState.COLETANDO_DADOS:
            session_manager.enfileirar_resident(
                session_id,
                "Ainda estamos coletando dados do visitante. Aguarde um instante..."
            )

        else:
            # Estado VALIDADO ou outro
            session_manager.enfileirar_resident(session_id, "Ainda estou preparando a chamada, aguarde.")

    # ----------------------------------------------------
    #  CHAMAR MORADOR via AMQP
    # ----------------------------------------------------
    def chamar_morador(self, session_id: str, session_manager):
        """
        Envia a mensagem AMQP para gerar a ligação com o morador.
        E agenda a verificação da conexão em 10s.
        """
        if not self.voip_number_morador:
            logger.warning("[Flow] voip_number_morador está vazio, não posso discar.")
            return

        # Primeira tentativa ou re-tentativa
        self.tentativas_chamada += 1

        session_manager.enfileirar_visitor(
            session_id,
            f"Discando para {self.voip_number_morador}... (Tentativa {self.tentativas_chamada})"
        )

        try:
            self.enviar_clicktocall(self.voip_number_morador, session_id)
            logger.info(f"[Flow] AMQP enviado para origin={self.voip_number_morador}, tentativa={self.tentativas_chamada}")
        except Exception as e:
            logger.error(f"[Flow] Falha ao enviar AMQP: {e}")
            session_manager.enfileirar_visitor(
                session_id,
                "Não foi possível chamar o morador. Tente novamente mais tarde."
            )
            self.state = FlowState.FINALIZADO
            self._finalizar(session_id, session_manager)
            return

        ### PASSO 2: Agendar a verificação em 10s
        loop = asyncio.get_event_loop()
        loop.create_task(self.monitorar_morador_conexao(session_id, session_manager))


    async def monitorar_morador_conexao(self, session_id: str, session_manager):
        """
        Aguarda 10s para ver se o estado mudou para ESPERANDO_MORADOR.
        Se não mudou, tenta chamar de novo (até 2 tentativas).
        Se mesmo assim não mudou, finaliza.
        """
        await asyncio.sleep(10)

        # Verifica se neste meio tempo o morador atendeu (ESPERANDO_MORADOR)
        if self.state == FlowState.ESPERANDO_MORADOR:
            logger.info("[Flow] Morador conectou antes dos 10s. Não precisa retentar.")
            return  # Está tudo bem.

        # Se chegou aqui, ainda está CHAMANDO_MORADOR e não conectou.
        if self.tentativas_chamada < 2:
            # Tentar novamente
            logger.info("[Flow] Morador não conectou em 10s. Vamos tentar ligar de novo.")
            self.chamar_morador(session_id, session_manager)
        else:
            # 2 tentativas falharam
            logger.info("[Flow] Morador não conectou após duas tentativas.")
            session_manager.enfileirar_visitor(session_id,
                "Não foi possível falar com o morador. Encaminharemos para a central e encerraremos a chamada."
            )
            self.state = FlowState.FINALIZADO
            self._finalizar(session_id, session_manager)


    def enviar_clicktocall(self, morador_voip_number: str, guid: str):
        """
        Ajuste host/credentials/queue etc. conforme sua infra.
        """
        rabbit_host = 'mqdev.tecnofy.com.br'
        rabbit_user = 'fonia'
        rabbit_password = 'fonia123'
        rabbit_vhost = 'DEV'
        queue_name = 'voip1-in'

        credentials = pika.PlainCredentials(rabbit_user, rabbit_password)
        parameters = pika.ConnectionParameters(
            host=rabbit_host,
            virtual_host=rabbit_vhost,
            credentials=credentials
        )

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)

        payload = {
            "data": {
                "destiny": "IA",
                "guid": guid,
                "license": "123456789012",
                "origin": morador_voip_number
            },
            "operation": {
                "eventcode": "8001",
                "guid": "cmd-" + guid,
                "msg": "",
                "timestamp": 1740696805,
                "type": "clicktocall"
            }
        }

        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(payload)
        )
        logger.info(f"[Flow] Mensagem AMQP enviada: origin={morador_voip_number}, guid={guid}")
        connection.close()

    # ----------------------------------------------------
    # FINALIZAR (chamar end_session, etc.)
    # ----------------------------------------------------
    def _finalizar(self, session_id: str, session_manager):
        """
        Encerra a conversa e remove a sessão (se preferir).
        """
        session_manager.enfileirar_resident(session_id, "Conversa encerrada.")
        session_manager.enfileirar_visitor(session_id, "Conversa encerrada. Obrigado.")

        session_manager.end_session(session_id)
