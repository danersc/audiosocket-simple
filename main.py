import asyncio
import logging
import os
from dotenv import load_dotenv
from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador, set_extension_manager
from speech_service import pre_sintetizar_frases_comuns
from extensions.api_server import APIServer
from extensions.server_manager import ServerManager
from extensions.config_persistence import ConfigPersistence
from extensions.db_connector import DBConnector

logging.basicConfig(level=logging.INFO)

load_dotenv()

# Inicializar diretório de logs se não existir
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

async def main():
    # Pré-sintetizar frases comuns para reduzir latência
    logging.info("Pré-sintetizando frases comuns...")
    pre_sintetizar_frases_comuns()
    
    # Configurar componentes para o servidor web
    server_manager = ServerManager()
    config_persistence = ConfigPersistence()
    
    # Configurar com modo de compatibilidade se não conseguir conectar ao DB
    try:
        db_connector = DBConnector()
        # Testar a conexão para verificar se está funcionando
        if not db_connector.test_connection():
            raise Exception("Teste de conexão falhou")
        logging.info("Conexão com banco de dados estabelecida com sucesso")
    except Exception as e:
        logging.warning(f"Não foi possível conectar ao banco de dados: {e}")
        logging.warning("Utilizando modo de compatibilidade com MockDBConnector")
        from extensions.mock_db_connector import MockDBConnector
        db_connector = MockDBConnector()
    
    # Passar o extension_manager para o audiosocket_handler
    set_extension_manager(server_manager)
    
    # Iniciar servidor para visitantes
    server_visitante = await asyncio.start_server(iniciar_servidor_audiosocket_visitante, '0.0.0.0', 8080)
    logging.info("Servidor AudioSocket para VISITANTES iniciado na porta 8080")
    
    # Iniciar servidor para moradores 
    # IMPORTANTE: Este servidor deve receber conexões com o mesmo GUID
    # da sessão original do visitante para manter o contexto da conversa
    server_morador = await asyncio.start_server(iniciar_servidor_audiosocket_morador, '0.0.0.0', 8081)
    logging.info("Servidor AudioSocket para MORADORES iniciado na porta 8081")
    
    # Iniciar servidor web na porta 8082 para API
    api_server = APIServer(server_manager, config_persistence, db_connector)
    api_port = int(os.getenv('API_PORT', '8082'))
    api_runner, api_site = await api_server.start(host='0.0.0.0', port=api_port)
    logging.info(f"Servidor API HTTP iniciado na porta {api_port}")
    
    logging.info("Sistema pronto para processar chamadas de visitantes e moradores")

    # Iniciar todos os serviços simultaneamente
    async with server_visitante, server_morador:
        await asyncio.gather(
            server_visitante.serve_forever(),
            server_morador.serve_forever()
        )

if __name__ == "__main__":
    asyncio.run(main())
