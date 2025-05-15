import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class DBConnector:
    def __init__(self):
        self.conn = None
        self.db_config = {
            'dbname': os.getenv('DB_NAME', 'postgres'),
            'user': os.getenv('DB_USER', 'admincd'),
            'password': os.getenv('DB_PASSWORD', 'Isabela@2022!!'),
            'host': os.getenv('DB_HOST', 'dev-postgres-cd.postgres.database.azure.com'),
            'port': os.getenv('DB_PORT', '5432'),
        }
    
    def connect(self):
        """Estabelece conexão com o banco de dados PostgreSQL."""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            logger.info("Conexão com banco de dados PostgreSQL estabelecida com sucesso.")
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar ao banco de dados: {e}")
            return False
    
    def disconnect(self):
        """Encerra a conexão com o banco de dados."""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("Conexão com banco de dados PostgreSQL encerrada.")
    
    def get_extensions(self):
        """
        Obtém todas as configurações de ramais da IA da tabela extension_ia.
        Retorna uma lista de dicionários com as configurações.
        """
        if not self.conn:
            if not self.connect():
                logger.error("Não foi possível conectar ao banco de dados para obter extensões.")
                return []
        
        try:
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            query = """
                SELECT 
                    extension_ia_id,
                    TRIM(extension_ia_number) as extension_ia_number,
                    TRIM(extension_ia_return) as extension_ia_return,
                    TRIM(extension_ia_ip) as extension_ia_ip,
                    TRIM(extension_ia_number_port) as extension_ia_number_port,
                    condominium_id,
                    TRIM(extension_ia_return_port) as extension_ia_return_port
                FROM 
                    public.extension_ia
                ORDER BY 
                    extension_ia_id
            """
            cursor.execute(query)
            extensions = cursor.fetchall()
            
            # Converter para formato mais amigável
            result = []
            for ext in extensions:
                result.append({
                    'id': ext['extension_ia_id'],
                    'ramal_ia': ext['extension_ia_number'],
                    'ramal_retorno': ext['extension_ia_return'],
                    'ip_servidor': ext['extension_ia_ip'],
                    'porta_ia': int(ext['extension_ia_number_port']),
                    'porta_retorno': int(ext['extension_ia_return_port'] or 0),
                    'condominio_id': ext['condominium_id']
                })
            
            logger.info(f"Obtidas {len(result)} configurações de ramais do banco de dados.")
            return result
        except Exception as e:
            logger.error(f"Erro ao obter extensões do banco de dados: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
    
    def test_connection(self):
        """Testa a conexão com o banco de dados."""
        if not self.conn:
            return self.connect()
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Erro ao testar conexão com banco de dados: {e}")
            self.conn = None
            return False