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
import socket
import re

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

    def __init__(self, extension_manager=None):
        self.state = FlowState.COLETANDO_DADOS
        self.intent_data = {}
        self.is_fuzzy_valid = False
        self.voip_number_morador: Optional[str] = None
        self.extension_manager = extension_manager

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
                        
                        # Processar o voip_number para garantir um formato correto
                        if isinstance(self.voip_number_morador, str) and self.voip_number_morador.startswith("sip:"):
                            # Extrair apenas a parte numérica se estiver no formato sip:XXX@dominio
                            sip_match = re.match(r'sip:(\d+)@', self.voip_number_morador)
                            if sip_match:
                                original_number = self.voip_number_morador
                                self.voip_number_morador = sip_match.group(1)
                                logger.info(f"[Flow] Convertido número SIP URI '{original_number}' para '{self.voip_number_morador}'")
                        
                        # Garantir que o voip_number é uma string
                        if not isinstance(self.voip_number_morador, str):
                            self.voip_number_morador = str(self.voip_number_morador)
                            logger.info(f"[Flow] Convertido voip_number para string: {self.voip_number_morador}")
                        
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
                        
                        # Usar uma estratégia diferente: executar a coroutine em uma thread separada
                        import threading
                        
                        def run_async_call():
                            """Função auxiliar para executar a coroutine em uma thread separada"""
                            try:
                                logger.info(f"[Flow] Iniciando thread para executar iniciar_processo_chamada")
                                # asyncio.run() vai criar um novo event loop e executar a coroutine nele
                                asyncio.run(self.iniciar_processo_chamada(session_id, session_manager))
                                logger.info(f"[Flow] Thread de chamada concluída com sucesso")
                            except Exception as e:
                                logger.error(f"[Flow] Erro em thread de chamada: {e}", exc_info=True)
                        
                        # Iniciar a thread
                        logger.info(f"[Flow] Criando thread para iniciar_processo_chamada com session_id={session_id}")
                        call_thread = threading.Thread(target=run_async_call)
                        call_thread.daemon = True  # Thread em segundo plano
                        call_thread.start()
                        
                        # Armazenar referência
                        self.calling_task = call_thread
                        
                        # Log para confirmar
                        logger.info(f"[Flow] Thread para iniciar_processo_chamada iniciada")
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
                
            # Lista mais precisa e controlada de termos de aprovação - removida a opção de string vazia
            elif any(word in lower_text for word in ["sim", "autorizo", "pode entrar", "autorizado", "deixa entrar", "libera", "ok", "claro", "positivo"]) or text.strip().lower() == "sim" or text.strip().lower() == "s":
                # Morador autorizou
                logger.info(f"[Flow] Morador AUTORIZOU a entrada com resposta: '{text}'")
                
                # Intent type para mensagem personalizada
                intent_type = self.intent_data.get("intent_type", "")
                intent_msg = ""
                if intent_type == "entrega":
                    intent_msg = "entrega"
                elif intent_type == "visita":
                    intent_msg = "visita"
                else:
                    intent_msg = "entrada"
                
                # Mensagens personalizadas para o tipo de intent
                session_manager.enfileirar_resident(
                    session_id, 
                    f"Obrigado! {visitor_name} será informado que a {intent_msg} foi autorizada."
                )
                session_manager.enfileirar_visitor(
                    session_id, 
                    f"Ótima notícia! O morador autorizou sua {intent_msg}."
                )
                
                # Salvar resultado da autorização na sessão
                self.intent_data["authorization_result"] = "authorized"
                
                # Registrar log especial para sinalizar finalização
                logger.info(f"[Flow] Autorização CONCLUÍDA - alterando estado para FINALIZADO")
                
                # Atualizar o state e iniciar encerramento de forma controlada
                self.state = FlowState.FINALIZADO
                
                # Código para enviar mensagem AMQP para o sistema físico de autorização
                # Desabilitado temporariamente para uso futuro
                """
                from services.amqp_service import enviar_msg_autorizacao_morador
                
                # Criação do payload adequado
                payload = {
                    "call_id": session_id,
                    "action": "authorize",
                    "apartment": self.intent_data.get("apartment_number", ""),
                    "resident": self.intent_data.get("resident_name", ""),
                    "visitor": self.intent_data.get("interlocutor_name", ""),
                    "intent_type": self.intent_data.get("intent_type", "entrada"),
                    "authorization_result": "authorized"
                }
                
                # Envia assíncronamente para não bloquear o fluxo
                logger.info(f"[Flow] Enviando notificação de AUTORIZAÇÃO para sistema físico: {payload}")
                try:
                    success = enviar_msg_autorizacao_morador(payload)
                    if success:
                        logger.info(f"[Flow] Notificação enviada com sucesso para sistema físico")
                    else:
                        logger.error(f"[Flow] Falha ao enviar notificação para sistema físico")
                except Exception as e:
                    logger.error(f"[Flow] Erro ao notificar sistema físico: {str(e)}")
                """
                
                # Log para desenvolvimento
                logger.info(f"[Flow] Módulo AMQP para notificação de portaria desabilitado - uso futuro")
                
                # Finalmente, iniciar processo de finalização controlada
                self._finalizar(session_id, session_manager)
                
            # Lista expandida de termos de negação    
            elif any(word in lower_text for word in ["não", "nao", "nego", "negativa", "negado", "bloqueado", "barrado", "recusado", "nunca"]):
                # Morador negou
                logger.info(f"[Flow] Morador NEGOU a entrada com resposta: '{text}'")
                
                # Intent type para mensagem personalizada
                intent_type = self.intent_data.get("intent_type", "")
                intent_msg = ""
                if intent_type == "entrega":
                    intent_msg = "entrega"
                elif intent_type == "visita":
                    intent_msg = "visita"
                else:
                    intent_msg = "entrada"
                
                session_manager.enfileirar_resident(
                    session_id, 
                    f"Entendido. {visitor_name} será informado que a {intent_msg} não foi autorizada."
                )
                session_manager.enfileirar_visitor(
                    session_id, 
                    f"Infelizmente o morador não autorizou sua {intent_msg} neste momento."
                )
                
                # Salvar resultado da autorização na sessão
                self.intent_data["authorization_result"] = "denied"
                
                # Registrar log especial para sinalizar finalização
                logger.info(f"[Flow] Negação CONCLUÍDA - alterando estado para FINALIZADO")
                
                # Atualizar o state e iniciar encerramento de forma controlada
                self.state = FlowState.FINALIZADO
                
                # Código para enviar mensagem AMQP para o sistema físico de negação
                # Desabilitado temporariamente para uso futuro
                """
                from services.amqp_service import enviar_msg_autorizacao_morador
                
                # Criação do payload adequado
                payload = {
                    "call_id": session_id,
                    "action": "deny",
                    "apartment": self.intent_data.get("apartment_number", ""),
                    "resident": self.intent_data.get("resident_name", ""),
                    "visitor": self.intent_data.get("interlocutor_name", ""),
                    "intent_type": self.intent_data.get("intent_type", "entrada"),
                    "authorization_result": "denied"
                }
                
                # Envia assíncronamente para não bloquear o fluxo
                logger.info(f"[Flow] Enviando notificação de NEGAÇÃO para sistema físico: {payload}")
                try:
                    success = enviar_msg_autorizacao_morador(payload)
                    if success:
                        logger.info(f"[Flow] Notificação enviada com sucesso para sistema físico")
                    else:
                        logger.error(f"[Flow] Falha ao enviar notificação para sistema físico")
                except Exception as e:
                    logger.error(f"[Flow] Erro ao notificar sistema físico: {str(e)}")
                """
                
                # Log para desenvolvimento
                logger.info(f"[Flow] Módulo AMQP para notificação de portaria desabilitado - uso futuro")
                
                # Finalmente, iniciar processo de finalização controlada
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
        
        # Garantir que temos um loop de eventos válido nesta thread
        try:
            # Para verificação apenas
            current_loop = asyncio.get_running_loop()
            logger.info(f"[Flow] Usando loop de eventos existente: {current_loop}")
        except RuntimeError:
            # Isso não deveria acontecer se a coroutine foi iniciada corretamente,
            # mas adicionamos um tratamento especial por precaução
            logger.warning(f"[Flow] Não há loop de eventos na thread atual para iniciar_processo_chamada")
            # Vamos criar um novo event loop, mas isso geralmente não é necessário e pode indicar um erro de design
            asyncio.set_event_loop(asyncio.new_event_loop())
        
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

        # Melhor logging para diagnóstico
        logger.info(f"[Flow] AMQP Config: host={rabbit_host}, vhost={rabbit_vhost}, queue={queue_name}")
        logger.info(f"[Flow] AMQP: Iniciando processo de clicktocall para morador={morador_voip_number}, guid={guid}")

        # Verificação de segurança - GUID não pode estar vazio
        if not guid or len(guid) < 8:
            logger.error(f"[Flow] GUID inválido para clicktocall: '{guid}'")
            return False

        # Verificação de segurança - número do morador não pode estar vazio
        if not morador_voip_number:
            logger.error(f"[Flow] Número do morador inválido: '{morador_voip_number}'")
            return False

        try:
            # Se temos um extension_manager, tentamos obter o ramal de retorno correto
            ramal_retorno = morador_voip_number
            if self.extension_manager:
                logger.info(f"[Flow] AMQP: Tentando obter ramal dinâmico com extension_manager para guid={guid}")
                ext_info = self.extension_manager.get_extension_info(call_id=guid)
                if ext_info:
                    ramal_retorno = ext_info.get('ramal_retorno', morador_voip_number)
                    logger.info(f"[Flow] AMQP: Usando ramal de retorno dinâmico: {ramal_retorno} para sessão {guid}")
                else:
                    logger.warning(f"[Flow] AMQP: Usando ramal de retorno padrão: {morador_voip_number}, pois não encontrei configuração dinâmica")
            else:
                logger.warning(f"[Flow] AMQP: Extension manager não disponível, usando ramal padrão: {morador_voip_number}")

            # Configuração da conexão com parâmetros aprimorados
            logger.info(f"[Flow] AMQP: Criando credenciais para conexão...")
            credentials = pika.PlainCredentials(rabbit_user, rabbit_password)
            parameters = pika.ConnectionParameters(
                host=rabbit_host,
                virtual_host=rabbit_vhost,
                credentials=credentials,
                connection_attempts=2,  # Tentar conectar 2 vezes
                retry_delay=1,          # 1 segundo entre tentativas
                socket_timeout=5        # 5 segundos de timeout
            )

            logger.info(f"[Flow] AMQP: Tentando conexão com {rabbit_host}...")
            connection = pika.BlockingConnection(parameters)
            logger.info(f"[Flow] AMQP: Conexão estabelecida com sucesso!")
            
            channel = connection.channel()
            logger.info(f"[Flow] AMQP: Canal criado, declarando fila {queue_name}...")
            
            channel.queue_declare(queue=queue_name, durable=True)
            logger.info(f"[Flow] AMQP: Fila declarada com sucesso!")

            # Timestamp atual para o evento
            current_timestamp = int(time.time())

            # IMPORTANTE: Garantir que o mesmo GUID da sessão seja usado
            # na chamada para o morador, para que os contextos se conectem
            payload = {
                "data": {
                    "destiny": "IA",
                    "guid": guid,  # GUID da sessão original
                    "license": "123456789012",
                    "origin": ramal_retorno  # Usando o ramal dinâmico ou o padrão
                },
                "operation": {
                    "eventcode": "8001",
                    "guid": "cmd-" + guid,
                    "msg": "",
                    "timestamp": current_timestamp,
                    "type": "clicktocall"
                }
            }

            payload_json = json.dumps(payload)
            logger.info(f"[Flow] AMQP: Enviando payload: {payload_json}")

            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=payload_json
            )
            
            logger.info(f"[Flow] AMQP: Mensagem enviada com sucesso: origin={ramal_retorno}, guid={guid}, timestamp={current_timestamp}")
            connection.close()
            logger.info(f"[Flow] AMQP: Conexão fechada com sucesso!")
            return True
            
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"[Flow] AMQP: Erro de conexão ao servidor RabbitMQ: {e}")
            logger.error(f"[Flow] AMQP: Detalhes da conexão: host={rabbit_host}, vhost={rabbit_vhost}, user={rabbit_user}")
            return False
        except pika.exceptions.ChannelError as e:
            logger.error(f"[Flow] AMQP: Erro no canal RabbitMQ (possivelmente a fila não existe): {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"[Flow] AMQP: Erro ao serializar payload JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"[Flow] AMQP: Erro inesperado ao enviar clicktocall: {e}", exc_info=True)
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
        
        # Carregar intenções
        authorization_result = self.intent_data.get("authorization_result", "")
        intent_type = self.intent_data.get("intent_type", "entrada")
        logger.info(f"[Flow] Finalizando com authorization_result={authorization_result}, intent_type={intent_type}")
            
        # Mensagens para os participantes
        if self.state in [FlowState.CHAMANDO_MORADOR, FlowState.CALLING_IN_PROGRESS, FlowState.ESPERANDO_MORADOR, FlowState.FINALIZADO]:
            # Se o morador estava envolvido, avisar ambos
            session_manager.enfileirar_resident(
                session_id, 
                "A conversa foi finalizada. Obrigado pela sua resposta."
            )
            
            # O texto para o visitante depende do resultado da autorização
            authorization_result = self.intent_data.get("authorization_result", "")
            intent_type = self.intent_data.get("intent_type", "entrada")
            
            # Verificar se é o caso de teste para o KIND_HANGUP
            is_test_hangup = self.intent_data.get("test_hangup", False)
            
            if is_test_hangup:
                # Definir flag específica para teste de hangup
                session = session_manager.get_session(session_id)
                if session:
                    session.intent_data["test_hangup"] = True
                    logger.info(f"[Flow] Flag de teste KIND_HANGUP ativada para sessão {session_id}")
                
                # Usar mensagem de finalização específica para teste
                session_manager.enfileirar_visitor(
                    session_id,
                    "A chamada com o morador foi finalizada. Obrigado por utilizar nosso sistema."
                )
            elif authorization_result == "authorized":
                if intent_type == "entrega":
                    session_manager.enfileirar_visitor(
                        session_id,
                        "Sua entrega foi autorizada pelo morador. Finalizando a chamada."
                    )
                elif intent_type == "visita":
                    session_manager.enfileirar_visitor(
                        session_id, 
                        "Sua visita foi autorizada pelo morador. Finalizando a chamada."
                    )
                else:
                    session_manager.enfileirar_visitor(
                        session_id,
                        "Sua entrada foi autorizada pelo morador. Finalizando a chamada."
                    )
            elif authorization_result == "denied":
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
        
        # Utilizar encerramento ativo KIND_HANGUP após um delay para permitir que todas as mensagens
        # sejam enviadas e ouvidas
        self._schedule_active_hangup(session_id, session_manager)
        logger.info(f"[Flow] Finalização programada com encerramento ativo KIND_HANGUP para sessão {session_id}")

    def _schedule_active_hangup(self, session_id: str, session_manager, delay=5.0):
        """
        Agenda o envio de KIND_HANGUP ativo após um delay para encerrar a chamada.
        O delay permite que todas as mensagens de áudio sejam reproduzidas primeiro.
        
        Args:
            session_id: ID da sessão
            session_manager: Gerenciador de sessões
            delay: Tempo em segundos para aguardar antes de enviar KIND_HANGUP (padrão: 5s)
        """
        import asyncio
        
        async def send_hangup_after_delay():
            # Aguardar o delay para permitir que as mensagens sejam enviadas
            await asyncio.sleep(delay)
            
            # Verificar se a sessão ainda existe
            session = session_manager.get_session(session_id)
            if not session:
                logger.info(f"[Flow] Sessão {session_id} já foi encerrada antes do KIND_HANGUP")
                return
                
            try:
                # Importar ResourceManager para acessar conexões ativas
                from extensions.resource_manager import resource_manager
                import struct
                
                # Enviar KIND_HANGUP para o visitante
                visitor_conn = resource_manager.get_active_connection(session_id, "visitor")
                if visitor_conn and 'writer' in visitor_conn:
                    try:
                        logger.info(f"[Flow] Enviando KIND_HANGUP ativo para visitante na sessão {session_id}")
                        visitor_conn['writer'].write(struct.pack('>B H', 0x00, 0))
                        await visitor_conn['writer'].drain()
                    except ConnectionResetError:
                        logger.info(f"[Flow] Conexão do visitante já foi resetada durante envio de KIND_HANGUP - comportamento normal")
                    except Exception as e:
                        logger.warning(f"[Flow] Erro ao enviar KIND_HANGUP para visitante: {e}")
                else:
                    logger.warning(f"[Flow] Conexão do visitante não encontrada para enviar KIND_HANGUP na sessão {session_id}")
                
                # Enviar KIND_HANGUP para o morador (se existir conexão)
                resident_conn = resource_manager.get_active_connection(session_id, "resident")
                if resident_conn and 'writer' in resident_conn:
                    try:
                        logger.info(f"[Flow] Enviando KIND_HANGUP ativo para morador na sessão {session_id}")
                        resident_conn['writer'].write(struct.pack('>B H', 0x00, 0))
                        await resident_conn['writer'].drain()
                    except ConnectionResetError:
                        logger.info(f"[Flow] Conexão do morador já foi resetada durante envio de KIND_HANGUP - comportamento normal")
                    except Exception as e:
                        logger.warning(f"[Flow] Erro ao enviar KIND_HANGUP para morador: {e}")
                
                # Após enviar os KIND_HANGUP, aguardar um pouco e finalizar a sessão completamente
                await asyncio.sleep(1.0)
                session_manager.end_session(session_id)
                
                # Uma limpeza final após mais um pequeno delay
                await asyncio.sleep(1.0)
                if session_manager.get_session(session_id):
                    logger.info(f"[Flow] Forçando limpeza final da sessão {session_id}")
                    session_manager._complete_session_termination(session_id)
                    
            except Exception as e:
                logger.error(f"[Flow] Erro ao enviar KIND_HANGUP ativo: {e}", exc_info=True)
                
                # Em caso de erro, tentar finalizar a sessão do modo tradicional
                session_manager.end_session(session_id)
        
        # Usar a mesma estratégia com thread separada
        import threading
        
        def run_async_hangup():
            """Função auxiliar para executar o hangup em uma thread separada"""
            try:
                logger.info(f"[Flow] Iniciando thread para executar hangup para session_id={session_id}")
                # asyncio.run() vai criar um novo event loop e executar a coroutine nele
                asyncio.run(send_hangup_after_delay())
                logger.info(f"[Flow] Thread de hangup concluída com sucesso")
            except Exception as e:
                logger.error(f"[Flow] Erro em thread de hangup: {e}", exc_info=True)
        
        # Iniciar a thread
        logger.info(f"[Flow] Criando thread para hangup com session_id={session_id}")
        hangup_thread = threading.Thread(target=run_async_hangup)
        hangup_thread.daemon = True  # Thread em segundo plano
        hangup_thread.start()
        
        # Não aguardamos a conclusão da tarefa para não bloquear o fluxo
        logger.info(f"[Flow] Thread para hangup iniciada")
