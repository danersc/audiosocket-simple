# conversation_flow.py

import logging
import time
from enum import Enum, auto
from typing import Optional

from ai.crew import process_user_message_with_coordinator
from ai.tools import validar_intent_com_fuzzy

import pika
import json
import asyncio

logger = logging.getLogger(__name__)

class FlowState(Enum):
    COLETANDO_DADOS = auto()
    VALIDADO = auto()
    CHAMANDO_MORADOR = auto()
    CALLING_IN_PROGRESS = auto()  # Estado para processos de chamada em andamento (sem notificar o visitante)
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
        self.tentativas_chamada = 0
        self.max_tentativas = 2
        self.call_timeout_seconds = 10  # Tempo para aguardar antes de tentar novamente
        self.calling_task = None  # Referência para a tarefa assíncrona de chamada

    # ---------------
    # VISITOR
    # ---------------
    def on_visitor_message(self, session_id: str, text: str, session_manager):
        logger.debug(f"[Flow] Visitor message in state={self.state}, text='{text}'")

        if self.state == FlowState.COLETANDO_DADOS:
            try:
                # Adicionar timeout para prevenção de bloqueio
                result = process_user_message_with_coordinator(session_id, text)
                logger.debug(f"[Flow] result IA: {result}")
                
                # Verificar se o resultado é None ou está vazio
                if result is None:
                    logger.error(f"[Flow] IA retornou resultado None para '{text}'")
                    session_manager.enfileirar_visitor(
                        session_id,
                        "Desculpe, tive um problema ao processar sua mensagem. Por favor, repita ou informe novamente seus dados."
                    )
                    return
                
                # Se a chamada ao morador está em progresso, não processamos novas entradas do visitante
                if self.state in [FlowState.CALLING_IN_PROGRESS, FlowState.ESPERANDO_MORADOR]:
                    logger.info(f"[Flow] Ignorando entrada do visitante durante estado {self.state}")
                    return
                
                # Atualiza self.intent_data com quaisquer dados retornados
                if "dados" in result:
                    for k, v in result["dados"].items():
                        self.intent_data[k] = v
                else:
                    logger.warning(f"[Flow] Resultado sem campo 'dados': {result}")
                    
                # Log de segurança para entender o estado atual
                logger.info(f"[Flow] Dados acumulados: {self.intent_data}")

                # Se veio alguma mensagem para o visitante, enfileira
                if "mensagem" in result:
                    session_manager.enfileirar_visitor(session_id, result["mensagem"])
                else:
                    # Mensagem de fallback caso não tenha mensagem no resultado
                    session_manager.enfileirar_visitor(
                        session_id,
                        "Por favor, continue informando os dados necessários."
                    )

                # Se valid_for_action, tentamos fuzzy
                if result.get("valid_for_action"):
                    # Verificação de segurança nos dados antes da validação fuzzy
                    apt = self.intent_data.get("apartment_number", "").strip()
                    resident = self.intent_data.get("resident_name", "").strip()
                    
                    # Log detalhado para cada etapa
                    logger.info(f"[Flow] Preparando para validação fuzzy com: apt={apt}, resident={resident}, data={self.intent_data}")
                    
                    if not apt or not resident:
                        logger.warning(f"[Flow] Dados incompletos antes do fuzzy: apt={apt}, resident={resident}")
                        session_manager.enfileirar_visitor(
                            session_id,
                            "Preciso do número do apartamento e nome do morador para continuar."
                        )
                        return
                    
                    # Verificação extra para depuração
                    logger.info(f"[Flow] Iniciando validação fuzzy com intent_data: {self.intent_data}")
                    
                    # Executa a validação fuzzy
                    fuzzy_res = validar_intent_com_fuzzy(self.intent_data)
                    logger.info(f"[Flow] Resultado do fuzzy: {fuzzy_res}")

                    if fuzzy_res["status"] == "válido":
                        self.is_fuzzy_valid = True
                        self.voip_number_morador = fuzzy_res.get("voip_number")
                        
                        # Atualizar o intent_data com o nome correto do apartamento/morador
                        if "apartment_number" in fuzzy_res:
                            self.intent_data["apartment_number"] = fuzzy_res["apartment_number"]
                        if "match_name" in fuzzy_res:
                            self.intent_data["resident_name"] = fuzzy_res["match_name"]
                            
                        self.state = FlowState.VALIDADO

                        # Mensagem única ao visitante (sem informar detalhes das tentativas)
                        session_manager.enfileirar_visitor(
                            session_id,
                            "Aguarde enquanto entramos em contato com o morador..."
                        )

                        # Avança para CHAMANDO_MORADOR e inicia o processo de chamada
                        self.state = FlowState.CHAMANDO_MORADOR
                        # Iniciar o processo de chamada como uma task assíncrona
                        loop = asyncio.get_event_loop()
                        self.calling_task = loop.create_task(self.iniciar_processo_chamada(session_id, session_manager))
                    else:
                        # Mensagem com mais detalhes sobre o motivo da falha
                        if "best_match" in fuzzy_res and fuzzy_res.get("best_score", 0) > 50:
                            session_manager.enfileirar_visitor(
                                session_id,
                                f"Encontrei um morador similar ({fuzzy_res['best_match']}), mas preciso que confirme o apartamento e nome corretos."
                            )
                        else:
                            session_manager.enfileirar_visitor(
                                session_id,
                                f"Desculpe, dados inválidos: {fuzzy_res.get('reason','motivo')}. Vamos tentar novamente."
                            )
            except Exception as e:
                # Tratamento de erro global para evitar travar o fluxo
                logger.error(f"[Flow] Erro no processamento: {str(e)}")
                session_manager.enfileirar_visitor(
                    session_id,
                    "Desculpe, ocorreu um erro ao processar sua solicitação. Por favor, tente novamente."
                )

        elif self.state == FlowState.CHAMANDO_MORADOR or self.state == FlowState.CALLING_IN_PROGRESS:
            # Não atualizamos o visitante durante o processo de chamada
            # apenas log para debug
            logger.debug(f"[Flow] Visitante tentou interagir durante processo de chamada em state={self.state}")

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

        # Detectar conexão de áudio do morador (trigger especial do socket)
        is_connection_trigger = text == "AUDIO_CONNECTION_ESTABLISHED"
        
        if (self.state == FlowState.CHAMANDO_MORADOR or self.state == FlowState.CALLING_IN_PROGRESS) and (is_connection_trigger or text):
            # Mensagem especial para log quando é o gatilho de conexão
            if is_connection_trigger:
                logger.info(f"[Flow] Detectada conexão de áudio do morador para session_id={session_id}")
            else:
                logger.info(f"[Flow] Morador atendeu e começou a falar: '{text}'")
                
            # Em qualquer caso, mudar para o estado de espera de resposta
            self.state = FlowState.ESPERANDO_MORADOR
            logger.info(f"[Flow] Morador atendeu chamada para sessão {session_id}. Mudando para estado ESPERANDO_MORADOR")
            
            # Verificar se temos os dados necessários para continuar
            visitor_name = self.intent_data.get("interlocutor_name", "")
            intent_type = self.intent_data.get("intent_type", "")
            apt = self.intent_data.get("apartment_number", "")
            
            if not visitor_name or not intent_type or not apt:
                logger.warning(f"[Flow] Dados incompletos ao atender morador: visitor={visitor_name}, intent={intent_type}, apt={apt}")
                visitor_name = visitor_name or "Um visitante"
                intent_type = intent_type or "acesso"
                apt = apt or "[não identificado]"
            
            # Mensagem detalhada para o morador com o contexto da visita
            intent_desc = {
                "entrega": "uma entrega",
                "visita": "uma visita",
                "servico": "um serviço",
            }.get(intent_type, "um acesso")
            
            # Mensagem de saudação com pausa para evitar que a chamada caia imediatamente
            initial_greeting = f"Olá, morador do apartamento {apt}. Um momento por favor..."
            session_manager.enfileirar_resident(session_id, initial_greeting)
            
            # Aguardar 1 segundo antes de enviar a próxima mensagem
            # Isso será processado assincronamente por enviar_mensagens_morador
            
            # Mensagem principal com os detalhes da visita
            resident_msg = (f"{visitor_name} está na portaria solicitando {intent_desc}. "
                           f"Você autoriza a entrada? Responda SIM ou NÃO.")
            session_manager.enfileirar_resident(session_id, resident_msg)
            
            # Notificar o visitante que o morador atendeu
            session_manager.enfileirar_visitor(session_id, "O morador atendeu. Aguarde enquanto verificamos sua autorização...")

        elif self.state == FlowState.ESPERANDO_MORADOR:
            # Processamento da resposta do morador
            lower_text = text.lower()
            visitor_name = self.intent_data.get("interlocutor_name", "Visitante")
            
            # Verificar se contém pergunta antes de checar sim/não
            if "quem" in lower_text or "?" in lower_text:
                # Morador está pedindo mais informações
                intent_type = self.intent_data.get("intent_type", "")
                apt = self.intent_data.get("apartment_number", "")
                
                # Mensagem detalhada sobre o visitante
                additional_info = f"{visitor_name} está na portaria para {intent_type}. "
                if intent_type == "entrega":
                    additional_info += "É uma entrega para seu apartamento."
                elif intent_type == "visita":
                    additional_info += "É uma visita pessoal."
                
                # Aguarda decisão após fornecer mais informações
                session_manager.enfileirar_resident(
                    session_id,
                    f"{additional_info} Por favor, responda SIM para autorizar ou NÃO para negar."
                )
                
            # Lista expandida de termos de aprovação
            elif any(word in lower_text for word in ["sim", "autorizo", "pode entrar", "autorizado", "deixa entrar", "libera", "ok", "claro", "positivo", "tá", "ta", "bom"]):
                # Morador autorizou
                logger.info(f"[Flow] Morador AUTORIZOU a entrada com resposta: '{text}'")
                
                session_manager.enfileirar_resident(
                    session_id, 
                    f"Obrigado! {visitor_name} será informado que a entrada foi autorizada."
                )
                session_manager.enfileirar_visitor(
                    session_id, 
                    f"Ótima notícia! O morador autorizou sua entrada."
                )
                
                # Salvar resultado da autorização na sessão
                self.intent_data["authorization_result"] = "authorized"
                
                # Atualizar o state e iniciar encerramento
                self.state = FlowState.FINALIZADO
                self._finalizar(session_id, session_manager)
                
            # Lista expandida de termos de negação    
            elif any(word in lower_text for word in ["não", "nao", "nego", "negativa", "negado", "bloqueado", "barrado", "recusado", "nunca"]):
                # Morador negou
                logger.info(f"[Flow] Morador NEGOU a entrada com resposta: '{text}'")
                
                session_manager.enfileirar_resident(
                    session_id, 
                    f"Entendido. {visitor_name} será informado que a entrada não foi autorizada."
                )
                session_manager.enfileirar_visitor(
                    session_id, 
                    "Infelizmente o morador não autorizou sua entrada neste momento."
                )
                
                # Salvar resultado da autorização na sessão
                self.intent_data["authorization_result"] = "denied"
                
                # Atualizar o state e iniciar encerramento
                self.state = FlowState.FINALIZADO
                self._finalizar(session_id, session_manager)
                
            else:
                # Resposta não reconhecida
                session_manager.enfileirar_resident(
                    session_id, 
                    "Desculpe, não consegui entender sua resposta. Por favor, responda SIM para autorizar a entrada ou NÃO para negar."
                )

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
    #  PROCESSO DE CHAMADA AO MORADOR (ASSÍNCRONO)
    # ----------------------------------------------------
    async def iniciar_processo_chamada(self, session_id: str, session_manager):
        """
        Gerencia o processo completo de chamada ao morador de forma assíncrona,
        sem notificar o visitante sobre cada etapa.
        """
        # Log detalhado para diagnóstico
        logger.info(f"[Flow] Iniciando processo de chamada para morador: voip={self.voip_number_morador}, session_id={session_id}")
        logger.info(f"[Flow] Dados do intent: {self.intent_data}")
        
        if not self.voip_number_morador:
            logger.warning("[Flow] voip_number_morador está vazio, não posso discar.")
            session_manager.enfileirar_visitor(
                session_id,
                "Não foi possível entrar em contato com o morador. Tente novamente mais tarde."
            )
            self.state = FlowState.FINALIZADO
            self._finalizar(session_id, session_manager)
            return

        # Mudamos para o estado de processamento em andamento
        self.state = FlowState.CALLING_IN_PROGRESS
        
        # Realizar tentativas de chamada sem notificar o visitante
        while self.tentativas_chamada < self.max_tentativas:
            self.tentativas_chamada += 1
            logger.info(f"[Flow] Tentativa {self.tentativas_chamada} de chamar o morador {self.voip_number_morador}")
            
            try:
                # Enviar comando para fazer a ligação
                logger.info(f"[Flow] Enviando clicktocall para {self.voip_number_morador} na tentativa {self.tentativas_chamada}")
                
                success = self.enviar_clicktocall(self.voip_number_morador, session_id)
                
                if not success:
                    logger.error(f"[Flow] Falha ao enviar clicktocall na tentativa {self.tentativas_chamada}")
                    # Se falhou no envio e é a última tentativa, sair do loop
                    if self.tentativas_chamada >= self.max_tentativas:
                        break
                    
                    # Extra logging para diagnóstico
                    logger.error(f"[Flow] Dados para clicktocall que falharam: voip={self.voip_number_morador}, intent={self.intent_data}")
                    continue  # Tenta novamente na próxima iteração
                
                logger.info(f"[Flow] AMQP enviado com sucesso para origin={self.voip_number_morador}, tentativa={self.tentativas_chamada}")

                # Aguarda o timeout para ver se o morador atende
                for _ in range(self.call_timeout_seconds):
                    await asyncio.sleep(1)  # Verifica a cada 1 segundo
                    # Se o morador atendeu neste meio tempo, o estado terá mudado
                    if self.state == FlowState.ESPERANDO_MORADOR:
                        logger.info(f"[Flow] Morador atendeu na tentativa {self.tentativas_chamada}")
                        return  # Processo concluído com sucesso
                
                # Se chegou aqui, o timeout foi atingido e o morador não atendeu
                logger.info(f"[Flow] Timeout de {self.call_timeout_seconds}s atingido na tentativa {self.tentativas_chamada}")
                
            except Exception as e:
                logger.error(f"[Flow] Erro inesperado ao processar chamada: {e}")
                if self.tentativas_chamada >= self.max_tentativas:
                    break  # Sai do loop após a última tentativa falhar
            
            # Aguarda um breve período entre tentativas
            if self.tentativas_chamada < self.max_tentativas:
                await asyncio.sleep(1)  # Pequeno intervalo entre tentativas
        
        # Se todas as tentativas falharam, notifica o visitante
        logger.info(f"[Flow] Todas as {self.max_tentativas} tentativas de contato com o morador falharam")
        session_manager.enfileirar_visitor(
            session_id,
            "Não foi possível contatar o morador no momento. Por favor, tente novamente mais tarde."
        )
        
        # Finaliza o processo
        self.state = FlowState.FINALIZADO
        self._finalizar(session_id, session_manager)


    def enviar_clicktocall(self, morador_voip_number: str, guid: str):
        """
        Envia solicitação de chamada para o morador via AMQP, garantindo
        que o mesmo GUID da sessão original seja utilizado como identificador.
        """
        rabbit_host = 'mqdev.tecnofy.com.br'
        rabbit_user = 'fonia'
        rabbit_password = 'fonia123'
        rabbit_vhost = 'voip'
        queue_name = 'api-to-voip1'

        # Verificação de segurança - GUID não pode estar vazio
        if not guid or len(guid) < 8:
            logger.error(f"[Flow] GUID inválido para clicktocall: '{guid}'")
            return False

        # Verificação de segurança - número do morador não pode estar vazio
        if not morador_voip_number:
            logger.error(f"[Flow] Número do morador inválido: '{morador_voip_number}'")
            return False

        try:
            credentials = pika.PlainCredentials(rabbit_user, rabbit_password)
            parameters = pika.ConnectionParameters(
                host=rabbit_host,
                virtual_host=rabbit_vhost,
                credentials=credentials
            )

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)

            # Timestamp atual para o evento
            current_timestamp = int(time.time())

            # IMPORTANTE: Garantir que o mesmo GUID da sessão seja usado
            # na chamada para o morador, para que os contextos se conectem
            payload = {
                "data": {
                    "destiny": "IA",
                    "guid": guid,  # GUID da sessão original
                    "license": "123456789012",
                    "origin": morador_voip_number
                },
                "operation": {
                    "eventcode": "8001",
                    "guid": "cmd-" + guid,
                    "msg": "",
                    "timestamp": current_timestamp,
                    "type": "clicktocall"
                }
            }

            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(payload)
            )
            
            logger.info(f"[Flow] Mensagem AMQP enviada: origin={morador_voip_number}, guid={guid}, timestamp={current_timestamp}")
            connection.close()
            return True
            
        except Exception as e:
            logger.error(f"[Flow] Erro ao enviar AMQP clicktocall: {e}")
            return False

    # ----------------------------------------------------
    # FINALIZAR (chamar end_session, etc.)
    # ----------------------------------------------------
    def _finalizar(self, session_id: str, session_manager):
        """
        Prepara o encerramento controlado da conversa e das conexões.
        
        1. Envia mensagens finais a ambos os participantes
        2. Aciona o mecanismo de encerramento controlado
        3. O session_manager sinaliza que as conexões devem ser encerradas
        4. As tasks assíncronas de audiosocket detectam o sinal e encerram graciosamente
        """
        logger.info(f"[Flow] Iniciando encerramento controlado da sessão {session_id}")
        
        # Mensagens para os participantes
        if self.state in [FlowState.CHAMANDO_MORADOR, FlowState.CALLING_IN_PROGRESS, FlowState.ESPERANDO_MORADOR]:
            # Se o morador estava envolvido, avisar ambos
            session_manager.enfileirar_resident(
                session_id, 
                "A conversa foi finalizada. Obrigado pela sua resposta."
            )
            
            # O texto para o visitante depende do contexto
            if "sim" in session_id.lower() or "autorizo" in session_id.lower():
                session_manager.enfileirar_visitor(
                    session_id,
                    "Sua entrada foi autorizada pelo morador. Finalizando a chamada."
                )
            elif "não" in session_id.lower() or "nao" in session_id.lower():
                session_manager.enfileirar_visitor(
                    session_id,
                    "Sua entrada não foi autorizada pelo morador. Finalizando a chamada."
                )
            else:
                session_manager.enfileirar_visitor(
                    session_id,
                    "A chamada com o morador foi finalizada. Obrigado por utilizar nosso sistema."
                )
        else:
            # Caso padrão (apenas visitante)
            session_manager.enfileirar_visitor(
                session_id,
                "Conversa finalizada. Obrigado por utilizar nosso sistema."
            )
        
        # Sinalizar para as tarefas de AudioSocket que devem encerrar as conexões
        session_manager.end_session(session_id)
