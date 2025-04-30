import logging
import json
from aiohttp import web
import asyncio
from typing import Dict, Any

from .server_manager import ServerManager
from .config_persistence import ConfigPersistence
from .db_connector import DBConnector

logger = logging.getLogger(__name__)

class APIServer:
    """
    Servidor HTTP simples para gerenciar os ramais de IA remotamente.
    Fornece endpoints para status, atualização de configurações, etc.
    """
    
    def __init__(self, server_manager: ServerManager, config_persistence: ConfigPersistence, db_connector: DBConnector):
        self.server_manager = server_manager
        self.config_persistence = config_persistence
        self.db_connector = db_connector
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """Configura as rotas da API."""
        self.app.router.add_get('/api/status', self.get_status)
        self.app.router.add_post('/api/refresh', self.refresh_config)
        self.app.router.add_get('/api/extensions', self.get_extensions)
        self.app.router.add_post('/api/restart', self.restart_extension)
    
    async def get_status(self, request: web.Request) -> web.Response:
        """
        Retorna o status de todos os servidores de ramais ativos.
        
        URL: GET /api/status
        """
        extensions = []
        
        for extension_id, server_data in self.server_manager.servers.items():
            config = server_data['config']
            extensions.append({
                "id": extension_id,
                "ramal_ia": config['ramal_ia'],
                "ramal_retorno": config['ramal_retorno'],
                "ip": config['ip_servidor'],
                "porta_ia": config['porta_ia'],
                "porta_retorno": config['porta_retorno'],
                "condominio_id": config['condominio_id'],
                "status": "ativo"
            })
        
        return web.json_response({
            "status": "success",
            "total_extensions": len(extensions),
            "extensions": extensions
        })
    
    async def refresh_config(self, request: web.Request) -> web.Response:
        """
        Atualiza as configurações de ramais a partir do banco de dados.
        
        URL: POST /api/refresh
        """
        try:
            # Obter novas configurações do banco
            db_configs = self.db_connector.get_extensions()
            
            if not db_configs:
                return web.json_response({
                    "status": "error",
                    "message": "Não foi possível obter configurações do banco de dados"
                }, status=500)
            
            # Atualizar servidores com novas configurações
            removed, updated, added = await self.server_manager.restart_servers(db_configs)
            
            # Persistir configurações localmente
            self.config_persistence.save_configs(db_configs)
            
            return web.json_response({
                "status": "success",
                "message": "Configurações atualizadas com sucesso",
                "stats": {
                    "removed": removed,
                    "updated": updated,
                    "added": added,
                    "total_active": len(self.server_manager.servers)
                }
            })
        
        except Exception as e:
            logger.error(f"Erro ao atualizar configurações: {e}")
            return web.json_response({
                "status": "error",
                "message": f"Erro ao atualizar configurações: {str(e)}"
            }, status=500)
    
    async def get_extensions(self, request: web.Request) -> web.Response:
        """
        Retorna todas as configurações de ramais do banco de dados.
        
        URL: GET /api/extensions
        """
        try:
            db_configs = self.db_connector.get_extensions()
            return web.json_response({
                "status": "success",
                "total": len(db_configs),
                "extensions": db_configs
            })
        except Exception as e:
            logger.error(f"Erro ao obter extensões: {e}")
            return web.json_response({
                "status": "error",
                "message": f"Erro ao obter extensões: {str(e)}"
            }, status=500)
    
    async def restart_extension(self, request: web.Request) -> web.Response:
        """
        Reinicia um ramal específico.
        
        URL: POST /api/restart
        Body: {"extension_id": 123} ou {"ramal": "1001"}
        """
        try:
            data = await request.json()
            
            if 'extension_id' in data:
                extension_id = int(data['extension_id'])
                if extension_id in self.server_manager.servers:
                    config = self.server_manager.servers[extension_id]['config']
                    await self.server_manager.stop_server(extension_id)
                    await self.server_manager.start_server(config)
                    return web.json_response({
                        "status": "success",
                        "message": f"Ramal ID {extension_id} reiniciado com sucesso"
                    })
                else:
                    return web.json_response({
                        "status": "error",
                        "message": f"Ramal ID {extension_id} não encontrado"
                    }, status=404)
            
            elif 'ramal' in data:
                ramal = data['ramal']
                if ramal in self.server_manager.extension_to_id:
                    extension_id = self.server_manager.extension_to_id[ramal]
                    config = self.server_manager.servers[extension_id]['config']
                    await self.server_manager.stop_server(extension_id)
                    await self.server_manager.start_server(config)
                    return web.json_response({
                        "status": "success",
                        "message": f"Ramal {ramal} reiniciado com sucesso"
                    })
                else:
                    return web.json_response({
                        "status": "error",
                        "message": f"Ramal {ramal} não encontrado"
                    }, status=404)
            
            else:
                return web.json_response({
                    "status": "error",
                    "message": "É necessário fornecer extension_id ou ramal"
                }, status=400)
        
        except Exception as e:
            logger.error(f"Erro ao reiniciar ramal: {e}")
            return web.json_response({
                "status": "error",
                "message": f"Erro ao reiniciar ramal: {str(e)}"
            }, status=500)
    
    async def start(self, host: str = '0.0.0.0', port: int = 8082):
        """
        Inicia o servidor API.
        
        Args:
            host: Endereço IP para bindar o servidor
            port: Porta para o servidor API
        """
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        logger.info(f"Servidor API iniciado em http://{host}:{port}")
        
        return runner, site