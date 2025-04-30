#!/usr/bin/env python
# setup_system.py

import asyncio
import logging
import sys
import os
from dotenv import load_dotenv
from speech_service import pre_sintetizar_frases_comuns
from extensions.extension_manager import ExtensionManager
from extensions.server_manager import ServerManager
from extensions.db_connector import DBConnector
from extensions.config_persistence import ConfigPersistence
from extensions.api_server import APIServer
from audiosocket_handler import set_extension_manager
from session_manager import SessionManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/audiosocket.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Inicializar diretório de logs se não existir
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

async def setup_extensions():
    """
    Configura todo o sistema de ramais dinâmicos sem iniciar os servidores.
    Retorna os objetos necessários para inicialização em outro módulo.
    """
    # Inicializar todos os componentes
    db_connector = DBConnector()
    config_persistence = ConfigPersistence()
    server_manager = ServerManager()
    extension_manager = ExtensionManager()
    
    # Teste de conexão com banco de dados
    if db_connector.connect():
        logger.info("Conexão com banco de dados estabelecida")
    else:
        logger.warning("Falha ao conectar com banco de dados, usando configurações locais")
    
    # Inicializar extension_manager
    await extension_manager.initialize(api_port=int(os.getenv('API_PORT', '8082')))
    
    # Configurar o extension_manager no audiosocket_handler global
    set_extension_manager(extension_manager)
    
    # Criar uma nova instância de SessionManager que use o extension_manager
    session_manager = SessionManager(extension_manager)
    
    # Configurar audiosocket_handler para usar o novo session_manager
    import audiosocket_handler
    audiosocket_handler.session_manager = session_manager
    
    # Pré-sintetizar frases comuns para cache
    logger.info("Pré-sintetizando frases comuns...")
    pre_sintetizar_frases_comuns()
    
    return {
        'extension_manager': extension_manager,
        'session_manager': session_manager,
        'db_connector': db_connector,
        'server_manager': server_manager,
        'config_persistence': config_persistence
    }

if __name__ == "__main__":
    try:
        print("Este script não deve ser executado diretamente.")
        print("Ele é importado pelo main_dynamic.py para configurar o sistema.")
        print("Execute 'python main_dynamic.py' para iniciar o sistema.")
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)