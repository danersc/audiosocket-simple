#!/usr/bin/env python3
# main.py - Aplicação principal audiosocket-simple

import socket
import threading
import os
import logging
import concurrent.futures
from dotenv import load_dotenv
from state_machine import StateMachine, State
from audiosocket_handler import iniciar_servidor_audiosocket

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("audiosocket.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Máquina de estados compartilhada para a última chamada ativa
# Será usada para debug
current_state_machine = None

def main():
    """Função principal que inicia o servidor AudioSocket e a API de debug."""
    
    # Verifica variáveis de ambiente essenciais
    required_env_vars = ['AZURE_SPEECH_KEY', 'AZURE_SPEECH_REGION']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Variáveis de ambiente ausentes: {', '.join(missing_vars)}")
        logger.error("Crie um arquivo .env com essas variáveis")
        return
    
    # Preparando diretórios para arquivos estáticos e templates
    import shutil
    logger.info("Preparando diretórios para arquivos estáticos e templates...")
    
    try:
        # Garante que os diretórios de templates e static existem
        templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
        css_dir = os.path.join(static_dir, 'css')
        js_dir = os.path.join(static_dir, 'js')
        
        # Cria os diretórios
        os.makedirs(templates_dir, exist_ok=True)
        os.makedirs(static_dir, exist_ok=True)
        os.makedirs(css_dir, exist_ok=True)
        os.makedirs(js_dir, exist_ok=True)
        
        logger.info(f"Diretórios criados/verificados: {templates_dir}, {static_dir}")
    except Exception as e:
        logger.error(f"Erro ao preparar diretórios: {e}")
    
    # Inicia a API de debug em uma thread separada
    logger.info("Iniciando API de debug...")


    # Inicializa uma máquina de estados global para debug
    global current_state_machine
    current_state_machine = StateMachine()

    try:
        # Inicializa o servidor AudioSocket
        logger.info("Iniciando servidor AudioSocket...")
        host = '127.0.0.1'  # Escutar na interface de loopback
        port = 8080  # Porta configurada para o AudioSocket
        
        # Cria o socket do servidor
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(5)  # Permitir até 5 conexões pendentes
        
        # Loop para aceitar conexões
        try:
            while True:
                cliente_socket, endereco = server.accept()
                logger.info(f"Nova conexão de {endereco[0]}:{endereco[1]}")
                
                # Inicia uma nova conversa (limpa o histórico anterior)
                current_state_machine.end_conversation()
                
                # Inicia uma nova thread para lidar com a conexão
                thread_cliente = threading.Thread(
                    target=iniciar_servidor_audiosocket,
                    args=(cliente_socket, endereco, current_state_machine)
                )
                thread_cliente.daemon = True
                thread_cliente.start()
        except KeyboardInterrupt:
            logger.info("Servidor interrompido pelo usuário")
        finally:
            server.close()
            logger.info("Servidor encerrado")
    
    except Exception as e:
        logger.error(f"Erro ao iniciar o servidor: {e}")

if __name__ == "__main__":
    main()
