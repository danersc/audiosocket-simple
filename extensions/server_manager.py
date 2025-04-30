import asyncio
import logging
import socket
from typing import Dict, List, Tuple, Any

# Importar handlers do audiosocket dinamicamente
from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador

logger = logging.getLogger(__name__)

class ServerManager:
    """
    Classe responsável por gerenciar os servidores socket para ramais de IA.
    Permite iniciar, parar e reiniciar servidores dinamicamente.
    """
    
    def __init__(self):
        # Dicionário para armazenar servidores ativos
        # {extension_id: {'ia_server': obj, 'retorno_server': obj, 'config': dict}}
        self.servers: Dict[int, Dict[str, Any]] = {}
        
        # Mapeamento de porta para extension_id para identificação rápida
        # {porta: extension_id}
        self.port_to_extension: Dict[int, int] = {}
        
        # Mapeamento de ramal para extension_id
        # {ramal: extension_id}
        self.extension_to_id: Dict[str, int] = {}
        
        # Mapeamento reverso de porta de retorno para porta de IA
        # {porta_retorno: porta_ia}
        self.return_to_ia_port: Dict[int, int] = {}
    
    def is_port_available(self, ip: str, port: int) -> bool:
        """
        Verifica se uma porta está disponível para uso.
        
        Args:
            ip: Endereço IP para verificar
            port: Número da porta para verificar
            
        Returns:
            bool: True se a porta estiver disponível, False caso contrário
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((ip, port))
            result = True
        except:
            result = False
        finally:
            sock.close()
        return result
    
    async def start_server(self, config: Dict[str, Any]) -> Tuple[asyncio.Server, asyncio.Server]:
        """
        Inicia servidores socket para um ramal específico.
        
        Args:
            config: Dicionário com configuração do ramal
            
        Returns:
            Tuple contendo os servidores de IA e retorno, ou levanta exceção se não for possível iniciar
        """
        extension_id = config['id']
        ramal_ia = config['ramal_ia']
        porta_ia = config['porta_ia']
        porta_retorno = config['porta_retorno']
        ip_registro = config['ip_servidor']  # IP para registro/Asterisk
        
        # Sempre usar 0.0.0.0 para binding do socket
        binding_ip = '0.0.0.0'
        
        # Verificar se as portas estão disponíveis no IP de binding
        if not self.is_port_available(binding_ip, porta_ia):
            err_msg = f"Porta {porta_ia} não está disponível para ramal IA {ramal_ia}. Ramal não será iniciado."
            logger.error(err_msg)
            raise RuntimeError(err_msg)
        
        if not self.is_port_available(binding_ip, porta_retorno):
            err_msg = f"Porta {porta_retorno} não está disponível para ramal retorno {config['ramal_retorno']}. Ramal não será iniciado."
            logger.error(err_msg)
            raise RuntimeError(err_msg)
        
        # Criar servidores assíncronos
        try:
            # Servidor para visitante (IA) - com parâmetros para melhor qualidade de áudio
            ia_server = await asyncio.start_server(
                iniciar_servidor_audiosocket_visitante,
                binding_ip,  # Use 0.0.0.0 para binding
                porta_ia,
                # Manter apenas parâmetros essenciais e alguns importantes para qualidade
                limit=1024*1024,  # 1MB buffer
                start_serving=True
            )
            
            # Servidor para morador (retorno) - com parâmetros para melhor qualidade de áudio
            retorno_server = await asyncio.start_server(
                iniciar_servidor_audiosocket_morador,
                binding_ip,  # Use 0.0.0.0 para binding
                porta_retorno,
                # Manter apenas parâmetros essenciais e alguns importantes para qualidade
                limit=1024*1024,  # 1MB buffer
                start_serving=True
            )
            
            # Criar uma cópia da configuração e adicionar detalhes de binding
            config_copy = config.copy()
            config_copy['binding_ip'] = binding_ip
            
            # Armazenar servidores e configuração sem criar tasks
            # Voltando à configuração original que funcionava
            self.servers[extension_id] = {
                'ia_server': ia_server,
                'retorno_server': retorno_server,
                'config': config_copy
            }
            
            # Atualizar mapeamentos
            self.port_to_extension[porta_ia] = extension_id
            self.port_to_extension[porta_retorno] = extension_id
            self.extension_to_id[ramal_ia] = extension_id
            self.return_to_ia_port[porta_retorno] = porta_ia
            
            logger.info(f"Iniciados servidores para ramal {ramal_ia}: "
                       f"IA: Socket em {binding_ip}:{porta_ia}, Registro para Asterisk: {ip_registro}:{porta_ia}, "
                       f"Retorno: Socket em {binding_ip}:{porta_retorno}, Registro para Asterisk: {ip_registro}:{porta_retorno}")
            
            return ia_server, retorno_server
        
        except Exception as e:
            logger.error(f"Erro ao iniciar servidores para ramal {ramal_ia}: {e}")
            raise
    
    async def stop_server(self, extension_id: int) -> bool:
        """
        Para os servidores de um ramal específico.
        
        Args:
            extension_id: ID do ramal para parar
            
        Returns:
            bool: True se os servidores foram parados com sucesso
        """
        if extension_id not in self.servers:
            logger.warning(f"Tentativa de parar servidores para ramal inexistente: {extension_id}")
            return False
        
        try:
            servers = self.servers[extension_id]
            config = servers['config']
            
            # Removendo código de cancelamento de tasks
            # para voltar à configuração original que funcionava
            
            # Fechar servidores
            servers['ia_server'].close()
            servers['retorno_server'].close()
            
            # Aguardar fechamento completo
            await servers['ia_server'].wait_closed()
            await servers['retorno_server'].wait_closed()
            
            # Remover mapeamentos
            porta_ia = config['porta_ia']
            porta_retorno = config['porta_retorno']
            ramal_ia = config['ramal_ia']
            
            if porta_ia in self.port_to_extension:
                del self.port_to_extension[porta_ia]
            
            if porta_retorno in self.port_to_extension:
                del self.port_to_extension[porta_retorno]
            
            if ramal_ia in self.extension_to_id:
                del self.extension_to_id[ramal_ia]
            
            if porta_retorno in self.return_to_ia_port:
                del self.return_to_ia_port[porta_retorno]
            
            # Remover da lista de servidores
            del self.servers[extension_id]
            
            logger.info(f"Servidores para ramal {ramal_ia} parados com sucesso")
            return True
        
        except Exception as e:
            logger.error(f"Erro ao parar servidores para ramal {extension_id}: {e}")
            return False
    
    async def start_all_servers(self, configs: List[Dict[str, Any]]) -> int:
        """
        Inicia todos os servidores com base nas configurações fornecidas.
        
        Args:
            configs: Lista de configurações de ramais
            
        Returns:
            int: Número de servidores iniciados com sucesso
        """
        success_count = 0
        tasks = []
        
        # Iniciar todos os servidores em paralelo para melhorar performance
        for config in configs:
            task = asyncio.create_task(self._safe_start_server(config))
            tasks.append(task)
        
        # Esperar que todos os servidores sejam iniciados
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Contar os servidores iniciados com sucesso
        for result in results:
            if isinstance(result, Exception):
                # Um erro ocorreu durante a inicialização
                logger.error(f"Erro ao iniciar servidor: {result}")
            elif result:
                # Servidor iniciado com sucesso
                success_count += 1
        
        return success_count
    
    async def _safe_start_server(self, config: Dict[str, Any]) -> bool:
        """
        Método auxiliar para iniciar um servidor com tratamento de exceções.
        
        Args:
            config: Configuração do ramal
            
        Returns:
            bool: True se o servidor foi iniciado com sucesso
        """
        try:
            await self.start_server(config)
            return True
        except Exception as e:
            logger.error(f"Falha ao iniciar servidor para ramal {config['ramal_ia']}: {e}")
            return False
    
    async def restart_servers(self, new_configs: List[Dict[str, Any]]) -> Tuple[int, int, int]:
        """
        Reinicia os servidores com novas configurações. 
        Para servidores que não existem mais, inicia novos e atualiza os existentes.
        
        Args:
            new_configs: Lista com novas configurações de ramais
            
        Returns:
            Tuple[int, int, int]: Contadores de (removidos, atualizados, adicionados)
        """
        removed_count = 0
        updated_count = 0
        added_count = 0
        
        # Mapear novos configs por ID para fácil acesso
        new_configs_map = {config['id']: config for config in new_configs}
        
        # Remover servidores que não estão mais nas configurações
        current_ids = set(self.servers.keys())
        new_ids = set(new_configs_map.keys())
        
        # IDs a serem removidos
        for extension_id in current_ids - new_ids:
            success = await self.stop_server(extension_id)
            if success:
                removed_count += 1
        
        # Atualizar servidores existentes ou adicionar novos
        for config in new_configs:
            extension_id = config['id']
            
            if extension_id in self.servers:
                # Verificar se configuração mudou
                old_config = self.servers[extension_id]['config']
                
                if self._config_changed(old_config, config):
                    # Se configuração mudou, reiniciar servidor
                    await self.stop_server(extension_id)
                    try:
                        await self.start_server(config)
                        updated_count += 1
                        logger.info(f"Servidor para ramal {config['ramal_ia']} atualizado com sucesso")
                    except Exception as e:
                        logger.error(f"Erro ao atualizar servidor para ramal {config['ramal_ia']}: {e}")
            else:
                # Iniciar novo servidor
                try:
                    await self.start_server(config)
                    added_count += 1
                    logger.info(f"Novo servidor para ramal {config['ramal_ia']} iniciado com sucesso")
                except Exception as e:
                    logger.error(f"Erro ao iniciar novo servidor para ramal {config['ramal_ia']}: {e}")
        
        return removed_count, updated_count, added_count
    
    def _config_changed(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> bool:
        """
        Verifica se a configuração de um ramal mudou.
        
        Args:
            old_config: Configuração antiga
            new_config: Nova configuração
            
        Returns:
            bool: True se a configuração mudou
        """
        # Campos relevantes para verificar mudanças
        keys = ['ip_servidor', 'porta_ia', 'porta_retorno', 'ramal_ia', 'ramal_retorno']
        
        for key in keys:
            if old_config.get(key) != new_config.get(key):
                return True
        
        return False
    
    def get_extension_info(self, call_id: str = None, porta: int = None, ramal: str = None) -> Dict[str, Any]:
        """
        Recupera informações de um ramal com base em call_id, porta ou número do ramal.
        
        Args:
            call_id: ID da chamada (UUID)
            porta: Número da porta
            ramal: Número do ramal
            
        Returns:
            Dict: Informações do ramal ou dicionário vazio se não encontrado
        """
        # Primeiro tenta pela porta (mais rápido)
        if porta and porta in self.port_to_extension:
            extension_id = self.port_to_extension[porta]
            if extension_id in self.servers:
                return self.servers[extension_id]['config']
        
        # Depois tenta pelo ramal
        if ramal and ramal in self.extension_to_id:
            extension_id = self.extension_to_id[ramal]
            if extension_id in self.servers:
                return self.servers[extension_id]['config']
        
        return {}
    
    def get_all_extensions(self) -> List[Dict[str, Any]]:
        """
        Retorna todas as configurações de ramais ativos.
        
        Returns:
            List[Dict]: Lista de configurações de ramais
        """
        return [server['config'] for server in self.servers.values()]
    
    def get_return_info(self, porta_ia: int) -> Dict[str, Any]:
        """
        Obtém informações de retorno com base na porta da IA.
        
        Args:
            porta_ia: Porta da IA
            
        Returns:
            Dict: Informações do retorno ou dicionário vazio se não encontrado
        """
        if porta_ia in self.port_to_extension:
            extension_id = self.port_to_extension[porta_ia]
            if extension_id in self.servers:
                return self.servers[extension_id]['config']
        
        return {}
    
    def get_ia_info_from_return(self, porta_retorno: int) -> Dict[str, Any]:
        """
        Obtém informações da IA com base na porta de retorno.
        
        Args:
            porta_retorno: Porta de retorno
            
        Returns:
            Dict: Informações da IA ou dicionário vazio se não encontrado
        """
        if porta_retorno in self.return_to_ia_port:
            porta_ia = self.return_to_ia_port[porta_retorno]
            return self.get_extension_info(porta=porta_ia)
        
        return {}