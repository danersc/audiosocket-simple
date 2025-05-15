import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class MockDBConnector:
    """
    Implementação de substituição para DBConnector quando o banco de dados não está disponível.
    Fornece as mesmas interfaces mas usa valores fixos ou configuração local.
    """
    
    def __init__(self):
        logger.info("Inicializando MockDBConnector para modo de compatibilidade")
        self.local_config = []
        
    def connect(self):
        """Simula conexão bem-sucedida."""
        logger.info("Simulando conexão bem-sucedida no modo de compatibilidade")
        return True
        
    def disconnect(self):
        """Simula desconexão."""
        logger.info("Simulando desconexão no modo de compatibilidade")
        
    def get_extensions(self) -> List[Dict[str, Any]]:
        """
        Retorna configurações de ramais padrão para modo de compatibilidade.
        Tenta carregar de ramais_config.json se disponível.
        
        Returns:
            List[Dict]: Lista de configurações de ramais
        """
        # Primeiro tenta carregar da configuração local
        try:
            from extensions.config_persistence import ConfigPersistence
            config_persistence = ConfigPersistence()
            saved_configs = config_persistence.load_configs()
            if saved_configs:
                logger.info(f"Usando {len(saved_configs)} configurações de ramais do arquivo local")
                self.local_config = saved_configs
                return saved_configs
        except Exception as e:
            logger.warning(f"Erro ao carregar configurações locais: {e}")
        
        # Se não tem configurações salvas, retorna configuração padrão
        # para compatibilidade com versões anteriores
        default_config = [
            {
                'id': 1,
                'ramal_ia': '1001',
                'ramal_retorno': '1002',
                'ip_servidor': '0.0.0.0',
                'porta_ia': 8080,
                'porta_retorno': 8081,
                'condominio_id': 1
            }
        ]
        
        logger.info("Usando configuração padrão para modo de compatibilidade")
        return default_config
        
    def test_connection(self):
        """Simula teste de conexão bem-sucedido."""
        return True