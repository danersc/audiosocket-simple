import asyncio
import json
import logging
import psycopg2
import psycopg2.extensions
import select
from typing import Callable, Dict, Any
from dotenv import load_dotenv
import os

load_dotenv()
logger = logging.getLogger(__name__)

class PostgresListener:
    """
    Classe que implementa um listener assíncrono para notificações do PostgreSQL.
    Usa asyncio para não bloquear a aplicação principal.
    """
    
    def __init__(self, callback: Callable[[dict], None], channel: str = "change_record_extension_ia"):
        """
        Inicializa o listener do PostgreSQL.
        
        Args:
            callback: Função que será chamada quando uma notificação for recebida
            channel: Canal do PostgreSQL para escutar notificações
        """
        self.callback = callback
        self.channel = channel
        self.conn = None
        self.running = False
        self.task = None
        self.db_config = {
            'dbname': os.getenv('DB_NAME', 'postgres'),
            'user': os.getenv('DB_USER', 'admincd'),
            'password': os.getenv('DB_PASSWORD', 'Isabela@2022!!'),
            'host': os.getenv('DB_HOST', 'dev-postgres-cd.postgres.database.azure.com'),
            'port': os.getenv('DB_PORT', '5432'),
        }
    
    async def connect(self) -> bool:
        """
        Estabelece conexão com o banco de dados PostgreSQL.
        
        Returns:
            bool: True se a conexão foi estabelecida com sucesso
        """
        try:
            # Use psycopg2 diretamente, já que não tem versão assíncrona nativa
            self.conn = psycopg2.connect(**self.db_config)
            self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            
            # Registrar no canal
            cursor = self.conn.cursor()
            cursor.execute(f"LISTEN {self.channel};")
            cursor.close()
            
            logger.info(f"Listener conectado ao banco de dados e escutando no canal '{self.channel}'")
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar listener ao banco de dados: {e}")
            return False
    
    async def listen(self):
        """
        Inicia o loop de escuta de notificações de forma não-bloqueante.
        """
        if not self.conn:
            success = await self.connect()
            if not success:
                logger.error("Não foi possível iniciar o listener devido a falha na conexão")
                return
        
        self.running = True
        logger.info(f"Listener iniciado no canal '{self.channel}'")
        
        while self.running:
            try:
                # Verifica se há notificações disponíveis, com timeout para não bloquear
                if select.select([self.conn], [], [], 1) == ([self.conn], [], []):
                    self.conn.poll()
                    
                    # Processa todas as notificações pendentes
                    while self.conn.notifies:
                        notify = self.conn.notifies.pop(0)
                        try:
                            payload = json.loads(notify.payload)
                            logger.info(f"Notificação recebida: {payload['action']} na extensão")
                            logger.debug(f"Payload completo: {payload}")
                            
                            # Chama o callback com os dados recebidos
                            await self.callback(payload)
                        except json.JSONDecodeError:
                            logger.error(f"Payload inválido recebido: {notify.payload}")
                        except Exception as e:
                            logger.error(f"Erro ao processar notificação: {e}", exc_info=True)
                
                # Dá chance para outras tarefas assíncronas executarem
                await asyncio.sleep(0.1)
                
            except psycopg2.OperationalError:
                logger.error("Conexão com o banco de dados perdida. Tentando reconectar...")
                self.conn.close()
                self.conn = None
                
                # Tenta reconectar
                await asyncio.sleep(5)  # Espera 5 segundos antes de tentar novamente
                success = await self.connect()
                if not success:
                    logger.error("Falha ao reconectar. Tentando novamente em 10 segundos...")
                    await asyncio.sleep(10)
            
            except Exception as e:
                logger.error(f"Erro no loop do listener: {e}")
                await asyncio.sleep(5)  # Pequena pausa para evitar loop de erro intensivo
    
    async def start(self):
        """
        Inicia o listener em uma tarefa assíncrona separada.
        """
        if self.task is not None:
            logger.warning("Listener já está em execução")
            return
        
        # Inicia o listener como uma tarefa assíncrona
        self.task = asyncio.create_task(self.listen())
        logger.info("Tarefa de listener iniciada")
        
    async def stop(self):
        """
        Para o listener e libera os recursos.
        """
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        
        if self.conn:
            self.conn.close()
            self.conn = None
        
        logger.info("Listener encerrado")