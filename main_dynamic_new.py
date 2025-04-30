#!/usr/bin/env python
# main_dynamic_new.py
# Versão reescrita do main_dynamic.py para usar asyncio.create_task como em main.py

import asyncio
import logging
import os
import sys
import json
from dotenv import load_dotenv
from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador

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

# Configurações globais
DEFAULT_BUFFER_SIZE = 1024 * 1024  # 1MB buffer
API_PORT = int(os.getenv('API_PORT', '8082'))

async def iniciar_api_server():
    """
    Inicia o servidor API em uma porta separada para gerenciamento.
    """
    # Importar módulos necessários dentro da função para evitar dependências cíclicas
    from extensions.extension_manager import ExtensionManager
    from extensions.db_connector import DBConnector
    from extensions.config_persistence import ConfigPersistence
    
    # Criar os componentes necessários
    db_connector = DBConnector()
    config_persistence = ConfigPersistence()
    
    # Inicializar o extension_manager com os componentes
    extension_manager = ExtensionManager()
    extension_manager.db_connector = db_connector
    extension_manager.config_persistence = config_persistence
    
    # Inicializar o API server
    api_runner, api_site = await extension_manager.api_server.start(port=API_PORT)
    logger.info(f"API REST iniciada na porta {API_PORT}")
    
    # Configurar atualização automática se necessário
    auto_refresh = os.getenv('AUTO_REFRESH', 'false').lower() == 'true'
    if auto_refresh:
        logger.info("Configurada atualização automática de ramais")
        # A atualização automática será gerenciada por outro mecanismo
    
    return api_runner, api_site, extension_manager

async def carregar_ramais():
    """
    Carrega configurações de ramais do banco de dados.
    Se falhar, tenta carregar do arquivo local.
    """
    # Primeiro tenta carregar do banco de dados
    try:
        # Importar o DBConnector
        from extensions.db_connector import DBConnector
        
        db_connector = DBConnector()
        if db_connector.connect():
            logger.info("Conexão com banco de dados estabelecida com sucesso")
            extensions = db_connector.get_extensions()
            
            if extensions:
                logger.info(f"Carregados {len(extensions)} ramais do banco de dados")
                
                # Salvar em arquivo local para uso futuro
                try:
                    from extensions.config_persistence import ConfigPersistence
                    config_persistence = ConfigPersistence()
                    config_persistence.save_configs(extensions)
                    logger.info(f"Configurações salvas no arquivo local")
                except Exception as save_err:
                    logger.warning(f"Erro ao salvar configurações localmente: {save_err}")
                
                # Desconectar do banco
                db_connector.disconnect()
                return extensions
            else:
                logger.warning("Nenhum ramal encontrado no banco de dados")
        else:
            logger.warning("Não foi possível conectar ao banco de dados")
    except Exception as e:
        logger.error(f"Erro ao carregar configurações do banco de dados: {e}")
    
    # Se falhar com o banco, tenta do arquivo local
    logger.info("Tentando carregar configurações do arquivo local...")
    config_path = "./data/ramais_config.json"
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
            ramais = data.get('ramais', [])
            logger.info(f"Carregados {len(ramais)} ramais do arquivo local")
            return ramais
    except Exception as e:
        logger.error(f"Erro ao carregar configurações de ramais do arquivo local: {e}")
        return []

async def verificar_atualizacoes_periodicas(extension_manager, interval_seconds):
    """
    Verifica periodicamente por atualizações no banco de dados.
    
    Args:
        extension_manager: Instância do ExtensionManager
        interval_seconds: Intervalo entre verificações em segundos
    """
    while True:
        await asyncio.sleep(interval_seconds)
        
        try:
            logger.info("Verificando atualizações no banco de dados...")
            
            # Tentar atualizar configurações
            db_connector = extension_manager.db_connector
            if db_connector.connect():
                db_extensions = db_connector.get_extensions()
                
                if db_extensions:
                    # Comparar com configurações atuais
                    current_extensions = extension_manager.server_manager.get_all_extensions()
                    current_ids = {ext.get('id') for ext in current_extensions}
                    db_ids = {ext.get('id') for ext in db_extensions}
                    
                    # Identificar mudanças
                    to_add = db_ids - current_ids
                    to_remove = current_ids - db_ids
                    to_update = {ext_id for ext_id in current_ids & db_ids 
                               if any(current['id'] == ext_id and db['id'] == ext_id and 
                                      extension_manager.server_manager._config_changed(current, db) 
                                      for current in current_extensions for db in db_extensions)}
                    
                    changes_count = len(to_add) + len(to_remove) + len(to_update)
                    if changes_count > 0:
                        logger.info(f"Detectadas {changes_count} alterações: "
                                   f"{len(to_add)} adições, {len(to_remove)} remoções, {len(to_update)} atualizações")
                        
                        # TODO: Implementar mecanismo para aplicar as alterações
                    else:
                        logger.info("Nenhuma alteração detectada")
                
                db_connector.disconnect()
        
        except Exception as e:
            logger.error(f"Erro ao verificar atualizações: {e}")

async def iniciar_db_listener(extension_manager):
    """
    Inicia o listener de notificações do banco de dados.
    
    Args:
        extension_manager: Instância do ExtensionManager
    """
    # Importar módulos necessários
    from extensions.db_connector import DBConnector
    import json
    import psycopg2
    import psycopg2.extensions
    import select
    import time
    
    db_config = {
        'dbname': os.getenv('DB_NAME', 'postgres'),
        'user': os.getenv('DB_USER', 'admincd'),
        'password': os.getenv('DB_PASSWORD', 'Isabela@2022!!'),
        'host': os.getenv('DB_HOST', 'dev-postgres-cd.postgres.database.azure.com'),
        'port': os.getenv('DB_PORT', '5432'),
    }
    
    channel = "change_record_extension_ia"
    
    while True:
        conn = None
        try:
            # Conectar ao banco de dados
            conn = psycopg2.connect(**db_config)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            
            cursor = conn.cursor()
            cursor.execute(f"LISTEN {channel};")
            logger.info(f"Listener conectado ao canal '{channel}'")
            
            # Loop de escuta
            while True:
                if select.select([conn], [], [], 5) == ([conn], [], []):
                    conn.poll()
                    
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        try:
                            payload = json.loads(notify.payload)
                            logger.info(f"Notificação recebida: {payload['action']} na extensão")
                            
                            # Processar a notificação
                            action = payload.get('action', '').upper()
                            data = payload.get('data', {})
                            
                            # Atualizar configurações com base na notificação
                            if action == 'INSERT':
                                # TODO: Implementar adição de novo ramal
                                logger.info(f"Nova extensão detectada: {data.get('extension_ia_number')}")
                            elif action == 'UPDATE':
                                # TODO: Implementar atualização de ramal
                                logger.info(f"Atualização de extensão: {data.get('extension_ia_id')}")
                            elif action == 'DELETE':
                                # TODO: Implementar remoção de ramal
                                logger.info(f"Remoção de extensão: {data.get('extension_ia_id')}")
                            
                        except json.JSONDecodeError:
                            logger.error(f"Payload inválido recebido: {notify.payload}")
                        except Exception as e:
                            logger.error(f"Erro ao processar notificação: {e}")
                
                await asyncio.sleep(0.1)  # Pequeno delay para evitar uso intensivo de CPU
                
        except Exception as e:
            logger.error(f"Erro no listener de notificações: {e}")
            if conn:
                try:
                    conn.close()
                except:
                    pass
            
            # Esperar um pouco antes de tentar reconectar
            await asyncio.sleep(5)

async def main():
    """
    Função principal que inicializa o sistema de ramais dinâmicos,
    seguindo o padrão de inicialização do main.py para melhor performance.
    """
    try:
        # Pré-sintetizar frases comuns para cache
        from speech_service import pre_sintetizar_frases_comuns
        logger.info("Pré-sintetizando frases comuns...")
        pre_sintetizar_frases_comuns()
        
        # Iniciar API server em uma task separada
        api_task = asyncio.create_task(iniciar_api_server())
        api_runner, api_site, extension_manager = await api_task
        
        # Registrar extension_manager no audiosocket_handler
        from audiosocket_handler import set_extension_manager
        set_extension_manager(extension_manager)
        
        # Carregar configurações de ramais
        ramais = await carregar_ramais()
        if not ramais:
            logger.warning("Nenhum ramal configurado. Usando configuração padrão.")
            ramais = [{
                'id': 0,
                'ramal_ia': '1000',
                'ramal_retorno': '1001',
                'ip_servidor': '0.0.0.0',
                'porta_ia': 8080,
                'porta_retorno': 8081,
                'condominio_id': 0
            }]
        
        logger.info(f"Carregados {len(ramais)} ramais configurados")
        
        # Iniciar todos os servidores e criar tasks para serve_forever
        server_tasks = []
        servers = []
        
        for ramal in ramais:
            try:
                # Extrair configurações
                porta_ia = ramal['porta_ia']
                porta_retorno = ramal['porta_retorno']
                binding_ip = '0.0.0.0'  # Sempre usar 0.0.0.0 para binding
                
                # Iniciar servidor para visitante (IA)
                server_ia = await asyncio.start_server(
                    iniciar_servidor_audiosocket_visitante,
                    binding_ip,
                    porta_ia,
                    limit=DEFAULT_BUFFER_SIZE
                )
                
                # Iniciar servidor para morador (retorno)
                server_retorno = await asyncio.start_server(
                    iniciar_servidor_audiosocket_morador,
                    binding_ip,
                    porta_retorno,
                    limit=DEFAULT_BUFFER_SIZE
                )
                
                # Adicionar à lista de servidores para context manager
                servers.append(server_ia)
                servers.append(server_retorno)
                
                # Criar tasks para serve_forever (crucial para performance)
                ia_task = asyncio.create_task(server_ia.serve_forever())
                retorno_task = asyncio.create_task(server_retorno.serve_forever())
                server_tasks.extend([ia_task, retorno_task])
                
                logger.info(f"Iniciado ramal {ramal['ramal_ia']} nas portas {porta_ia}/{porta_retorno}")
            
            except OSError as e:
                if "address already in use" in str(e).lower():
                    logger.error(f"Porta {e.args[1].split(':')[-1].strip()} já está em uso. Ramal {ramal['ramal_ia']} não iniciado.")
                else:
                    logger.error(f"Erro ao iniciar ramal {ramal['ramal_ia']}: {e}")
            except Exception as e:
                logger.error(f"Erro ao iniciar ramal {ramal['ramal_ia']}: {e}")
        
        if not server_tasks:
            logger.critical("Nenhum servidor foi iniciado. Encerrando.")
            return 1
        
        logger.info(f"Sistema de ramais dinâmicos iniciado com {len(server_tasks)//2} ramais ativos")
        
        # Iniciar task de atualização periódica se AUTO_REFRESH estiver habilitado
        # auto_refresh = os.getenv('AUTO_REFRESH', 'false').lower() == 'true'
        # if auto_refresh:
        #     refresh_interval = int(os.getenv('REFRESH_INTERVAL_SECONDS', '3600'))  # Default 1 hora
        #     refresh_task = asyncio.create_task(
        #         verificar_atualizacoes_periodicas(extension_manager, refresh_interval)
        #     )
        #     server_tasks.append(refresh_task)
        #     logger.info(f"Iniciada verificação periódica de atualizações a cada {refresh_interval} segundos")
        #
        # Adicionar task para o listener de notificações do banco
        try:
            notification_task = asyncio.create_task(
                iniciar_db_listener(extension_manager)
            )
            server_tasks.append(notification_task)
            logger.info("Iniciado listener de notificações do banco de dados")
        except Exception as e:
            logger.error(f"Não foi possível iniciar o listener de notificações: {e}")
        
        # Manter servidores rodando até interrupção
        try:
            # Aguardar indefinidamente
            await asyncio.gather(*server_tasks)
        except asyncio.CancelledError:
            logger.info("Tasks canceladas. Encerrando servidores...")
    
    except KeyboardInterrupt:
        logger.info("Interrupção do teclado detectada, encerrando...")
    
    except Exception as e:
        logger.critical(f"Erro fatal durante execução: {e}", exc_info=True)
        return 1
    
    finally:
        # Tenta encerrar graciosamente
        try:
            # Cancelar todas as tasks
            for task in server_tasks:
                if not task.done():
                    task.cancel()
            
            # Encerrar API
            if 'api_runner' in locals():
                await api_runner.cleanup()
            
            # Encerrar extension_manager
            if 'extension_manager' in locals():
                await extension_manager.shutdown()
        except Exception as shutdown_err:
            logger.error(f"Erro durante encerramento: {shutdown_err}")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Programa interrompido pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)
