import asyncio
import logging
import os
import argparse
import sys
from dotenv import load_dotenv
from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador, set_extension_manager
from speech_service import pre_sintetizar_frases_comuns
from extensions.api_server import APIServer
from extensions.server_manager import ServerManager
from extensions.config_persistence import ConfigPersistence
from extensions.db_connector import DBConnector

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('logs', 'audiosocket.log'))
    ]
)

logger = logging.getLogger(__name__)

load_dotenv()

# Inicializar diretório de logs se não existir
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

def parse_arguments():
    """
    Analisa os argumentos de linha de comando para configurar a aplicação.
    """
    parser = argparse.ArgumentParser(description='Servidor AudioSocket para portaria inteligente')
    
    # Argumentos para portas
    parser.add_argument('--port-ia', type=int, default=8080,
                        help='Porta para o servidor de visitantes (padrão: 8080)')
    parser.add_argument('--port-retorno', type=int, default=8081,
                        help='Porta para o servidor de moradores (padrão: 8081)')
    parser.add_argument('--port-api', type=int, default=None,
                        help='Porta para o servidor API (padrão: valor de API_PORT no .env ou 8082)')
    
    # Argumentos para identificação da instância
    parser.add_argument('--ramal-ia', type=str, default='1000',
                        help='Número do ramal da IA para esta instância (padrão: 1000)')
    parser.add_argument('--ramal-retorno', type=str, default='1001',
                        help='Número do ramal de retorno para esta instância (padrão: 1001)')
    parser.add_argument('--extension-id', type=int, default=0,
                        help='ID da extensão no banco de dados (padrão: 0)')
    parser.add_argument('--condominio-id', type=int, default=0,
                        help='ID do condomínio no banco de dados (padrão: 0)')
    
    # Outros argumentos
    parser.add_argument('--log-file', type=str, default=None,
                        help='Arquivo de log específico para esta instância')
    parser.add_argument('--env-file', type=str, default=None,
                        help='Arquivo .env específico para esta instância')
    
    return parser.parse_args()

async def main():
    # Analisar argumentos de linha de comando
    args = parse_arguments()
    
    # Carregar .env específico se fornecido
    if args.env_file and os.path.exists(args.env_file):
        load_dotenv(args.env_file, override=True)
        logger.info(f"Carregadas variáveis de ambiente de {args.env_file}")
    
    # Configurar arquivo de log específico para esta instância se fornecido
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        logger.info(f"Adicionado arquivo de log específico: {args.log_file}")
    
    # Exibir informações de configuração
    logger.info(f"Iniciando AudioSocket-Simple com as seguintes configurações:")
    logger.info(f"  Porta IA (visitantes): {args.port_ia}")
    logger.info(f"  Porta Retorno (moradores): {args.port_retorno}")
    logger.info(f"  Ramal IA: {args.ramal_ia}")
    logger.info(f"  Ramal Retorno: {args.ramal_retorno}")
    logger.info(f"  Extension ID: {args.extension_id}")
    logger.info(f"  Condomínio ID: {args.condominio_id}")
    
    # Pré-sintetizar frases comuns para reduzir latência
    logger.info("Pré-sintetizando frases comuns...")
    pre_sintetizar_frases_comuns()
    
    # Configurar componentes para o servidor web
    server_manager = ServerManager()
    config_persistence = ConfigPersistence()
    
    # Passar o extension_manager para o audiosocket_handler
    set_extension_manager(server_manager)
    
    # Iniciar servidor para visitantes
    server_visitante = await asyncio.start_server(
        iniciar_servidor_audiosocket_visitante, 
        '0.0.0.0', 
        args.port_ia, 
        limit=1024*1024  # 1MB buffer
    )
    logger.info(f"Servidor AudioSocket para VISITANTES iniciado na porta {args.port_ia}")
    
    # Iniciar servidor para moradores 
    # IMPORTANTE: Este servidor deve receber conexões com o mesmo GUID
    # da sessão original do visitante para manter o contexto da conversa
    server_morador = await asyncio.start_server(
        iniciar_servidor_audiosocket_morador, 
        '0.0.0.0', 
        args.port_retorno, 
        limit=1024*1024  # 1MB buffer
    )
    logger.info(f"Servidor AudioSocket para MORADORES iniciado na porta {args.port_retorno}")
    
    # Iniciar servidor web para API - apenas se esta for a instância principal
    # ou se a porta API específica foi fornecida
    api_runner = None
    api_site = None
    
    if args.port_api or (args.extension_id == 0):
        api_port = args.port_api or int(os.getenv('API_PORT', '8082'))
        api_server = APIServer(server_manager, config_persistence)
        try:
            api_runner, api_site = await api_server.start(host='0.0.0.0', port=api_port)
            logger.info(f"Servidor API HTTP iniciado na porta {api_port}")
        except Exception as e:
            logger.warning(f"Não foi possível iniciar o servidor API na porta {api_port}: {e}")
            logger.warning("Continuando sem servidor API")
    
    logger.info(f"Sistema pronto para processar chamadas para o ramal {args.ramal_ia}")
    
    # Iniciar todos os serviços simultaneamente
    async with server_visitante, server_morador:
        await asyncio.gather(
            server_visitante.serve_forever(),
            server_morador.serve_forever()
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Programa encerrado pelo usuário")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)
