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
        self.app.router.add_post('/api/hangup', self.hangup_call)
    
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
    
    async def hangup_call(self, request: web.Request) -> web.Response:
        """
        Envia sinal de hangup (KIND_HANGUP, 0x00) para uma chamada ativa.
        
        URL: POST /api/hangup
        Body: {"call_id": "uuid-da-chamada", "role": "visitor|resident"}
        """
        try:
            from audiosocket_handler import session_manager
            import struct
            
            data = await request.json()
            
            if 'call_id' not in data:
                return web.json_response({
                    "status": "error",
                    "message": "call_id é obrigatório"
                }, status=400)
                
            call_id = data['call_id']
            role = data.get('role', 'visitor')  # Padrão é visitante
            
            # Validar role
            if role not in ['visitor', 'resident']:
                return web.json_response({
                    "status": "error",
                    "message": "role deve ser 'visitor' ou 'resident'"
                }, status=400)
            
            # Verificar se a sessão existe
            session = session_manager.get_session(call_id)
            if not session:
                return web.json_response({
                    "status": "error",
                    "message": f"Sessão {call_id} não encontrada"
                }, status=404)
            
            # Obter a conexão ativa da sessão através do ResourceManager
            from extensions.resource_manager import resource_manager
            
            connection = resource_manager.get_active_connection(call_id, role)
            if not connection:
                return web.json_response({
                    "status": "error",
                    "message": f"Conexão ativa não encontrada para {call_id} ({role})"
                }, status=404)
            
            # Enviar KIND_HANGUP (0x00) com payload length 0
            writer = connection.get('writer')
            if not writer:
                return web.json_response({
                    "status": "error",
                    "message": f"Writer não disponível para {call_id} ({role})"
                }, status=500)
            
            # Enviar KIND_HANGUP (0x00) com tratamento de erro
            try:
                writer.write(struct.pack('>B H', 0x00, 0))
                await writer.drain()
            except ConnectionResetError:
                logger.info(f"Conexão já foi resetada durante envio de KIND_HANGUP para {call_id} ({role}) - comportamento normal")
            except Exception as e:
                logger.error(f"Erro ao enviar KIND_HANGUP para {call_id} ({role}): {e}")
                return web.json_response({
                    "status": "error",
                    "message": f"Erro ao enviar KIND_HANGUP: {str(e)}"
                }, status=500)
            
            # Definir flag para indicar teste de hangup na sessão
            session.intent_data["test_hangup"] = True
            
            # Aguardar um momento e então encerrar a sessão completamente
            asyncio.create_task(self._cleanup_session_after_delay(call_id, session_manager))
            
            logger.info(f"KIND_HANGUP enviado com sucesso para {call_id} ({role})")
            return web.json_response({
                "status": "success",
                "message": f"KIND_HANGUP enviado com sucesso para {call_id} ({role})"
            })
            
        except Exception as e:
            logger.error(f"Erro ao enviar KIND_HANGUP: {e}", exc_info=True)
            return web.json_response({
                "status": "error",
                "message": f"Erro ao enviar KIND_HANGUP: {str(e)}"
            }, status=500)
    
    async def _cleanup_session_after_delay(self, call_id, session_manager, delay=3.0):
        """Aguarda um delay e então limpa a sessão completamente."""
        await asyncio.sleep(delay)
        session = session_manager.get_session(call_id)
        if session:
            # Sinalizar encerramento e depois forçar remoção
            session_manager.end_session(call_id)
            await asyncio.sleep(1.0)
            session_manager._complete_session_termination(call_id)
            logger.info(f"Sessão {call_id} encerrada após KIND_HANGUP")
    
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