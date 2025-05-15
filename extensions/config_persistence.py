import json
import os
import logging

logger = logging.getLogger(__name__)

class ConfigPersistence:
    """
    Classe responsável por persistir configurações de ramais localmente,
    permitindo que o sistema reinicie com as mesmas configurações mesmo
    sem acesso ao banco de dados.
    """
    
    def __init__(self, config_path="./data/ramais_config.json"):
        self.config_path = config_path
        # Garante que o diretório existe
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
    
    def save_configs(self, configs):
        """
        Salva as configurações de ramais em um arquivo JSON local.
        
        Args:
            configs (list): Lista de dicionários com configurações de ramais
        """
        try:
            with open(self.config_path, 'w') as f:
                json.dump({'ramais': configs}, f, indent=2)
            logger.info(f"Configurações de {len(configs)} ramais salvas em {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar configurações localmente: {e}")
            return False
    
    def load_configs(self):
        """
        Carrega configurações de ramais a partir do arquivo JSON local.
        
        Returns:
            list: Lista de dicionários com configurações de ramais
        """
        if not os.path.exists(self.config_path):
            logger.warning(f"Arquivo de configuração {self.config_path} não encontrado.")
            return []
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
                configs = data.get('ramais', [])
                logger.info(f"Carregadas {len(configs)} configurações de ramais do arquivo local")
                return configs
        except Exception as e:
            logger.error(f"Erro ao carregar configurações locais: {e}")
            return []