#!/usr/bin/env python3
"""
Script para testar o audiosocket_handler usando um arquivo SLIN pré-gravado.
Esse teste serve para diagnosticar problemas de reconhecimento de voz,
substituindo a entrada do microfone por um áudio conhecido.

Uso:
    python test_audiosocket_with_file.py [arquivo_slin]

Argumentos:
    arquivo_slin: Caminho para o arquivo SLIN (padrão: usa o configurado em config.json)

Importante: Execute primeiro o script record_slin_audio.py para gerar um arquivo
            de áudio SLIN para usar neste teste.
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("TestAudiosocketWithFile")

# Diretório padrão para arquivos de áudio
AUDIO_CACHE_DIR = "audio/cache"

def load_config():
    """Carrega a configuração do config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar configuração: {e}")
        return {}

def update_config_for_testing(test_audio_file):
    """
    Atualiza o config.json temporariamente para incluir a configuração de teste.
    
    Args:
        test_audio_file: Caminho para o arquivo de áudio SLIN para teste
    
    Returns:
        Boolean indicando sucesso da operação
    """
    try:
        # Carregar configuração atual
        config = load_config()
        
        # Fazer backup da configuração original
        backup_file = "config.json.bak"
        if not os.path.exists(backup_file):
            with open(backup_file, 'w') as f:
                json.dump(config, f, indent=4)
                logger.info(f"Backup da configuração salvo em {backup_file}")
        
        # Adicionar configuração de teste
        if "testing" not in config:
            config["testing"] = {}
        
        config["testing"]["enabled"] = True
        config["testing"]["test_audio_file"] = test_audio_file
        
        # Salvar configuração atualizada
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
            logger.info(f"Configuração atualizada com arquivo de teste: {test_audio_file}")
        
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar configuração: {e}")
        return False

def restore_config():
    """Restaura a configuração original do config.json"""
    backup_file = "config.json.bak"
    try:
        if os.path.exists(backup_file):
            with open(backup_file, 'r') as f:
                config = json.load(f)
            
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=4)
                logger.info("Configuração original restaurada")
            
            os.remove(backup_file)
            return True
    except Exception as e:
        logger.error(f"Erro ao restaurar configuração: {e}")
    return False

def check_file_exists(file_path):
    """Verifica se o arquivo existe e é acessível"""
    if not os.path.exists(file_path):
        logger.error(f"Arquivo não encontrado: {file_path}")
        return False
    
    # Verificar permissões
    try:
        with open(file_path, 'rb') as f:
            f.read(1)
        return True
    except Exception as e:
        logger.error(f"Erro ao acessar arquivo: {e}")
        return False

def patch_audiosocket_handler():
    """
    Aplica um patch temporário no audiosocket_handler.py para usar o arquivo de teste.
    Esta função apenas imprime instruções para o usuário, já que a modificação
    permanente é feita nas atualizações do arquivo original.
    """
    print("\n" + "="*60)
    print("INSTRUÇÕES DE MODIFICAÇÃO:")
    print("="*60)
    print("Para que o teste funcione, você precisa modificar o audiosocket_handler.py:")
    print("\n1. Carregue o arquivo de teste na configuração:")
    print("   ```python")
    print("   # Carregar configurações do config.json")
    print("   try:")
    print("       with open('config.json', 'r') as f:")
    print("           config = json.load(f)")
    print("           # ... configurações existentes ...")
    print("           ")
    print("           # Configuração para testes")
    print("           TEST_MODE = config.get('testing', {}).get('enabled', False)")
    print("           TEST_AUDIO_FILE = config.get('testing', {}).get('test_audio_file', None)")
    print("           if TEST_MODE and TEST_AUDIO_FILE:")
    print("               logger.info(f\"Modo de teste ativado com arquivo: {TEST_AUDIO_FILE}\")")
    print("   ```")
    print("\n2. No método receber_audio_visitante_azure_speech (ou receber_audio_visitante_vad),")
    print("   adicione a lógica para usar o arquivo de teste após o final da fala:")
    print("   ```python")
    print("   # Se estamos em modo de teste e temos um arquivo de teste")
    print("   if TEST_MODE and TEST_AUDIO_FILE and speech_end_detected:")
    print("       try:")
    print("           # Carregar o arquivo de teste")
    print("           test_file_path = TEST_AUDIO_FILE")
    print("           if not os.path.isabs(test_file_path):")
    print("               # Se for um nome de arquivo, procurar no diretório de cache")
    print("               test_file_path = os.path.join('audio/cache', test_file_path)")
    print("               ")
    print("           logger.info(f\"[{call_id}] Modo de teste: usando arquivo {test_file_path}\")")
    print("           with open(test_file_path, 'rb') as f:")
    print("               test_audio_data = f.read()")
    print("               ")
    print("           # Substituir o áudio capturado pelo arquivo de teste")
    print("           audio_data = test_audio_data")
    print("           logger.info(f\"[{call_id}] Áudio de teste carregado: {len(audio_data)} bytes\")")
    print("       except Exception as e:")
    print("           logger.error(f\"[{call_id}] Erro ao carregar arquivo de teste: {e}\")")
    print("   ```")
    print("\nIMPORTANTE: Estas modificações devem ser feitas no código para que o teste funcione!")
    print("="*60)

def main():
    # Configurar parser de argumentos
    parser = argparse.ArgumentParser(description="Testa o audiosocket_handler com um arquivo SLIN pré-gravado")
    parser.add_argument('audio_file', nargs='?', default=None,
                       help="Caminho para o arquivo de áudio SLIN (padrão: usa o configurado em config.json)")
    parser.add_argument('--list', action='store_true',
                       help="Lista os arquivos SLIN disponíveis no diretório de cache")
    parser.add_argument('--restore', action='store_true',
                       help="Restaura a configuração original")
    
    args = parser.parse_args()
    
    # Se solicitado, restaurar configuração e sair
    if args.restore:
        if restore_config():
            print("Configuração original restaurada com sucesso.")
        else:
            print("Falha ao restaurar configuração original.")
        return
    
    # Se solicitado, listar arquivos disponíveis e sair
    if args.list:
        if os.path.exists(AUDIO_CACHE_DIR):
            slin_files = [f for f in os.listdir(AUDIO_CACHE_DIR) if f.endswith('.slin')]
            if slin_files:
                print("\nArquivos SLIN disponíveis:")
                for i, file in enumerate(slin_files):
                    size = os.path.getsize(os.path.join(AUDIO_CACHE_DIR, file))
                    print(f"{i+1}. {file} ({size} bytes)")
                print(f"\nPara usar um arquivo específico: python {sys.argv[0]} {os.path.join(AUDIO_CACHE_DIR, slin_files[0])}")
            else:
                print(f"Nenhum arquivo SLIN encontrado em {AUDIO_CACHE_DIR}")
                print(f"Execute primeiro: python record_slin_audio.py")
        else:
            print(f"Diretório {AUDIO_CACHE_DIR} não encontrado")
        return
    
    # Obter arquivo de áudio
    test_audio_file = args.audio_file
    
    # Se nenhum arquivo foi especificado, verificar na configuração atual
    if test_audio_file is None:
        config = load_config()
        test_audio_file = config.get("testing", {}).get("test_audio_file")
        
        # Se ainda não temos um arquivo, usar o primeiro disponível no diretório cache
        if test_audio_file is None:
            if os.path.exists(AUDIO_CACHE_DIR):
                slin_files = [f for f in os.listdir(AUDIO_CACHE_DIR) if f.endswith('.slin')]
                if slin_files:
                    test_audio_file = os.path.join(AUDIO_CACHE_DIR, slin_files[0])
                    logger.info(f"Usando primeiro arquivo SLIN disponível: {test_audio_file}")
    
    # Se ainda não temos um arquivo, mostrar erro e sair
    if test_audio_file is None:
        logger.error("Nenhum arquivo de áudio especificado e nenhum encontrado no diretório de cache.")
        print("\nPor favor, execute primeiro:")
        print("python record_slin_audio.py")
        print("\nOu especifique um arquivo:")
        print(f"python {sys.argv[0]} caminho/para/arquivo.slin")
        return
    
    # Verificar se o arquivo existe
    if not check_file_exists(test_audio_file):
        logger.error(f"Arquivo de áudio não encontrado ou não acessível: {test_audio_file}")
        return
    
    # Atualizar configuração
    if update_config_for_testing(test_audio_file):
        logger.info("Configuração atualizada com sucesso.")
    else:
        logger.error("Falha ao atualizar configuração.")
        return
    
    # Exibir instruções para modificação do código
    patch_audiosocket_handler()
    
    # Exibir instruções finais
    print("\n" + "="*60)
    print("PRÓXIMOS PASSOS:")
    print("="*60)
    print("1. Execute a aplicação principal normalmente:")
    print("   python main.py")
    print("\n2. Quando terminar os testes, restaure a configuração original:")
    print(f"   python {sys.argv[0]} --restore")
    print("\n3. Para listar arquivos de áudio disponíveis:")
    print(f"   python {sys.argv[0]} --list")
    print("="*60)


if __name__ == "__main__":
    main()