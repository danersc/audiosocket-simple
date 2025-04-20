# conversation_flow.py

import logging
from enum import Enum, auto
from typing import Optional

from ai.crew import process_user_message_with_coordinator
from ai.tools import validar_intent_com_fuzzy

import pika
import json

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

    def on_visitor_message(self, session_id: str, text: str, session_manager):
        logger.debug(f"[Flow] Visitor message in state={self.state}, text='{text}'")

        if self.state == FlowState.COLETANDO_DADOS:
            result = process_user_message_with_coordinator(session_id, text)
            logger.debug(f"[Flow] result IA: {result}")

            if result and "dados" in result:
                for k, v in result["dados"].items():
                    self.intent_data[k] = v

            if result and "mensagem" in result:
                session_manager.enfileirar_visitor(session_id, result["mensagem"])

            # Se valid_for_action, rodar fuzzy
            if result and result.get("valid_for_action"):
                fuzzy_res = validar_intent_com_fuzzy(self.intent_data)
                logger.info(f"[Flow] fuzzy= {fuzzy_res}")

                if fuzzy_res["status"] == "válido":
                    self.is_fuzzy_valid = True
                    self.voip_number_morador = fuzzy_res.get("voip_number")
                    # -> Mudar para VALIDADO
                    self.state = FlowState.VALIDADO

                    session_manager.enfileirar_visitor(
                        session_id,
                        "Obrigado, temos todos os dados. Vou chamar o morador agora..."
                    )

                    # Aqui imediatamente passamos para CHAMANDO_MORADOR
                    self.state = FlowState.CHAMANDO_MORADOR
                    self.chamar_morador(session_id, session_manager)

                else:
                    # Rejeitado
                    session_manager.enfileirar_visitor(
                        session_id,
                        f"Desculpe, dados inválidos: {fuzzy_res.get('reason','motivo')}."
                    )

        elif self.state == FlowState.CHAMANDO_MORADOR:
            session_manager.enfileirar_visitor(session_id, "Já estou chamando o morador, aguarde...")

        elif self.state == FlowState.ESPERANDO_MORADOR:
            session_manager.enfileirar_visitor(session_id, "O morador está na linha. Aguarde a resposta.")

        elif self.state == FlowState.FINALIZADO:
            session_manager.enfileirar_visitor(session_id, "Fluxo encerrado. Obrigado.")
        else:
            # DEFAULT para qualquer outro estado
            session_manager.enfileirar_visitor(session_id, "Aguarde, por favor.")

    def on_resident_message(self, session_id: str, text: str, session_manager):
        logger.debug(f"[Flow] Resident message in state={self.state}, text='{text}'")

        if self.state == FlowState.CHAMANDO_MORADOR:
            # Morador atendeu
            self.state = FlowState.ESPERANDO_MORADOR
            session_manager.enfileirar_resident(session_id, "Olá, vou te passar as informações do visitante...")
            session_manager.enfileirar_visitor(session_id, "O morador atendeu. Aguarde a resposta.")

        elif self.state == FlowState.ESPERANDO_MORADOR:
            # Morador diz sim/não...
            if "sim" in text.lower():
                session_manager.enfileirar_visitor(session_id, "Morador autorizou sua entrada!")
                self.state = FlowState.FINALIZADO
            elif "nao" in text.lower() or "não" in text.lower():
                session_manager.enfileirar_visitor(session_id, "Morador negou sua entrada.")
                self.state = FlowState.FINALIZADO
            else:
                session_manager.enfileirar_resident(session_id, "Não entendi. Responda SIM ou NÃO.")

        elif self.state == FlowState.FINALIZADO:
            session_manager.enfileirar_resident(session_id, "O fluxo já foi finalizado. Obrigado.")
        else:
            # Se o morador falar em COLETANDO_DADOS ou VALIDADO,
            # pode ignorar ou mandar msg
            session_manager.enfileirar_resident(session_id, "Aguarde, não iniciamos sua etapa ainda.")

    # ----------------------------------------------------
    #  CHAMAR MORADOR via AMQP
    # ----------------------------------------------------
    def chamar_morador(self, session_id: str, session_manager):
        """
        Envia a mensagem AMQP para gerar a ligação com o morador.
        """
        if not self.voip_number_morador:
            logger.warning("[Flow] voip_number_morador está vazio, não posso discar.")
            return

        # Enfileira para o VISITANTE uma msg de status
        session_manager.enfileirar_visitor(
            session_id,
            f"Discando para {self.voip_number_morador}..."
        )

        try:
            self.enviar_clicktocall(self.voip_number_morador, session_id)
            logger.info(f"[Flow] AMQP enviado para origin={self.voip_number_morador}")
        except Exception as e:
            logger.error(f"[Flow] Falha ao enviar AMQP: {e}")
            # Decidimos se encerramos ou tentamos algo. Por hora, avisa
            session_manager.enfileirar_visitor(
                session_id,
                "Não foi possível chamar o morador. Tente novamente mais tarde."
            )
            self.state = FlowState.FINALIZADO

    def enviar_clicktocall(self, morador_voip_number: str, guid: str):
        """
        Envia de fato a mensagem AMQP com base no seu exemplo.
        Ajuste host/credentials/queue etc. conforme sua infra.
        """
        # Exemplo de credenciais
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

        # Montar payload
        # Usamos "origin" = morador_voip_number
        # O "guid" iremos usar session_id (você pode criar outro se quiser)
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
