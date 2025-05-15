import logging
import os
import asyncio
from typing import Dict, List, Any, Optional, Tuple

from .db_connector import DBConnector
from .config_persistence import ConfigPersistence
from .server_manager import ServerManager
from .api_server import APIServer
from .db_listener import PostgresListener

logger = logging.getLogger(__name__)

class ExtensionManager:
    """
    Classe principal que gerencia todo o sistema de extensões da IA.
    Coordena a conexão com banco de dados, persistência local e gerenciamento de servidores.
    """
    
    def __init__(self):
        self.db_connector = DBConnector()
        self.config_persistence = ConfigPersistence()
        self.server_manager = ServerManager()
        self.api_server = APIServer(
            self.server_manager,
            self.config_persistence,
            self.db_connector
        )
        self.db_listener = PostgresListener(self.handle_db_notification)
        self.is_running = False
        self.api_runner = None
        self.api_site = None
    
    async def handle_db_notification(self, payload: Dict[str, Any]):
        """
        Processa notificações recebidas do banco de dados e realiza as ações necessárias.
        
        Args:
            payload: Dicionário contendo os dados da notificação
        """
        try:
            action = payload.get('action', '').upper()  # Converter para maiúsculo para padronização
            data = payload.get('data', {})
            
            logger.info(f"Processando notificação: {action} para extensão")
            
            if action == 'INSERT':
                # Nova extensão foi adicionada
                logger.info(f"Nova extensão detectada: {data.get('extension_ia_number')}")
                
                # Converter para o formato usado pelo ServerManager
                config = {
                    'id': data.get('extension_ia_id'),
                    'ramal_ia': data.get('extension_ia_number', '').strip(),
                    'ramal_retorno': data.get('extension_ia_return', '').strip(),
                    'ip_servidor': data.get('extension_ia_ip', '').strip(),
                    'porta_ia': int(data.get('extension_ia_number_port', 0)),
                    'porta_retorno': int(data.get('extension_ia_return_port', 0)),
                    'condominio_id': data.get('condominium_id', 0)
                }
                
                # Iniciar novo servidor para esta extensão
                try:
                    await self.server_manager.start_server(config)
                    logger.info(f"Servidor para nova extensão {config['ramal_ia']} iniciado com sucesso")
                    
                    # Atualizar configurações locais
                    configs = self.config_persistence.load_configs()
                    configs.append(config)
                    self.config_persistence.save_configs(configs)
                except Exception as e:
                    logger.error(f"Erro ao iniciar servidor para nova extensão: {e}")
                    # Porta pode estar em uso ou outro erro, não adicionamos o ramal
                
            elif action == 'UPDATE':
                # Extensão foi atualizada
                extension_id = data.get('extension_ia_id')
                logger.info(f"Atualização de extensão detectada: ID {extension_id}")
                
                # Converter para o formato usado pelo ServerManager
                config = {
                    'id': extension_id,
                    'ramal_ia': data.get('extension_ia_number', '').strip(),
                    'ramal_retorno': data.get('extension_ia_return', '').strip(),
                    'ip_servidor': data.get('extension_ia_ip', '').strip(),
                    'porta_ia': int(data.get('extension_ia_number_port', 0)),
                    'porta_retorno': int(data.get('extension_ia_return_port', 0)),
                    'condominio_id': data.get('condominium_id', 0)
                }
                
                # Verificar se já temos esta extensão
                if extension_id in self.server_manager.servers:
                    # Parar o servidor atual
                    await self.server_manager.stop_server(extension_id)
                    
                    try:
                        # Iniciar com a nova configuração
                        await self.server_manager.start_server(config)
                        logger.info(f"Servidor para extensão {config['ramal_ia']} reiniciado com nova configuração")
                        
                        # Atualizar configurações locais
                        configs = self.config_persistence.load_configs()
                        for i, existing_config in enumerate(configs):
                            if existing_config.get('id') == extension_id:
                                configs[i] = config
                                break
                        self.config_persistence.save_configs(configs)
                    except Exception as e:
                        logger.error(f"Erro ao reiniciar servidor para extensão ID {extension_id}: {e}")
                        logger.warning(f"A extensão ID {extension_id} foi removida devido à falha na atualização")
                        
                        # Remover das configurações locais já que não conseguimos subir o socket
                        configs = self.config_persistence.load_configs()
                        configs = [c for c in configs if c.get('id') != extension_id]
                        self.config_persistence.save_configs(configs)
                else:
                    # Extensão não existe, tratar como INSERT
                    try:
                        await self.server_manager.start_server(config)
                        logger.info(f"Servidor para extensão atualizada {config['ramal_ia']} iniciado")
                        
                        # Atualizar configurações locais
                        configs = self.config_persistence.load_configs()
                        configs.append(config)
                        self.config_persistence.save_configs(configs)
                    except Exception as e:
                        logger.error(f"Erro ao iniciar servidor para extensão atualizada ID {extension_id}: {e}")
                        # Não persistimos a configuração se falhar ao iniciar o servidor
                
            elif action == 'DELETE':
                # Extensão foi removida
                extension_id = data.get('extension_ia_id')
                logger.info(f"Remoção de extensão detectada: ID {extension_id}")
                
                # Verificar se temos esta extensão
                if extension_id in self.server_manager.servers:
                    # Parar o servidor
                    await self.server_manager.stop_server(extension_id)
                    logger.info(f"Servidor para extensão ID {extension_id} removido com sucesso")
                    
                    # Atualizar configurações locais
                    configs = self.config_persistence.load_configs()
                    configs = [c for c in configs if c.get('id') != extension_id]
                    self.config_persistence.save_configs(configs)
                else:
                    logger.warning(f"Tentativa de remover extensão ID {extension_id} que não está ativa")
            
            else:
                logger.warning(f"Ação desconhecida recebida: {action}")
        
        except Exception as e:
            logger.error(f"Erro ao processar notificação do banco de dados: {e}")

    async def initialize(self, api_port: int = 8082) -> bool:
        """
        Inicializa o sistema de extensões.
        
        Args:
            api_port: Porta para o servidor API
            
        Returns:
            bool: True se inicializado com sucesso
        """
        try:
            # Carregar configurações (do banco ou local)
            configs = self._load_configurations()
            
            if not configs:
                logger.warning("Nenhuma configuração de extensão encontrada. Usando configuração padrão.")
                # Configuração padrão para compatibilidade
                configs = [{
                    'id': 0,
                    'ramal_ia': '1000',
                    'ramal_retorno': '1001',
                    'ip_servidor': '0.0.0.0',
                    'porta_ia': 8080,
                    'porta_retorno': 8081,
                    'condominio_id': 0
                }]
            
            # Iniciar servidores para cada ramal
            success_count = await self.server_manager.start_all_servers(configs)
            
            logger.info(f"Iniciados {success_count} de {len(configs)} servidores de ramais")
            
            # Iniciar servidor API
            self.api_runner, self.api_site = await self.api_server.start(port=api_port)
            
            # Iniciar o listener de banco de dados
            await self.db_listener.start()
            logger.info("Listener de banco de dados para notificações de ramais iniciado")
            
            self.is_running = True
            return True
        
        except Exception as e:
            logger.error(f"Erro ao inicializar sistema de extensões: {e}")
            return False
    
    def _load_configurations(self) -> List[Dict[str, Any]]:
        """
        Carrega configurações de ramais do banco de dados ou arquivo local.
        
        Returns:
            List[Dict]: Lista de configurações de ramais
        """
        # Tentar do banco de dados primeiro
        if self.db_connector.connect():
            configs = self.db_connector.get_extensions()
            
            # Se obteve configurações do banco, salvar localmente
            if configs:
                self.config_persistence.save_configs(configs)
                return configs
        
        # Se não conseguiu do banco, tentar do arquivo local
        logger.info("Não foi possível obter configurações do banco, tentando arquivo local")
        return self.config_persistence.load_configs()
    
    async def refresh_configurations(self) -> Tuple[int, int, int]:
        """
        Atualiza as configurações de ramais a partir do banco de dados.
        
        Returns:
            Tuple[int, int, int]: Contadores de (removidos, atualizados, adicionados)
        """
        if self.db_connector.connect():
            configs = self.db_connector.get_extensions()
            
            if configs:
                # Persistir configurações localmente
                self.config_persistence.save_configs(configs)
                
                # Atualizar servidores
                return await self.server_manager.restart_servers(configs)
        
        return 0, 0, 0
    
    async def shutdown(self) -> bool:
        """
        Encerra todos os servidores e limpa recursos.
        
        Returns:
            bool: True se encerrado com sucesso
        """
        try:
            # Parar o listener do banco de dados
            await self.db_listener.stop()
            logger.info("Listener de banco de dados encerrado")
            
            # Parar todos os servidores
            for extension_id in list(self.server_manager.servers.keys()):
                await self.server_manager.stop_server(extension_id)
            
            # Encerrar servidor API
            if self.api_runner:
                await self.api_runner.cleanup()
            
            # Encerrar conexão com banco
            self.db_connector.disconnect()
            
            self.is_running = False
            return True
        
        except Exception as e:
            logger.error(f"Erro ao encerrar sistema de extensões: {e}")
            return False
    
    def get_extension_info(self, call_id=None, porta=None, ramal=None) -> Dict[str, Any]:
        """
        Obtém informações de um ramal com base em call_id, porta ou número do ramal.
        
        Args:
            call_id: ID da chamada (UUID)
            porta: Número da porta
            ramal: Número do ramal
            
        Returns:
            Dict: Informações do ramal ou dicionário vazio se não encontrado
        """
        return self.server_manager.get_extension_info(call_id, porta, ramal)
    
    def get_all_extensions(self) -> List[Dict[str, Any]]:
        """
        Retorna todas as configurações de ramais ativos.
        
        Returns:
            List[Dict]: Lista de configurações de ramais
        """
        return self.server_manager.get_all_extensions()