#!/usr/bin/env python3
"""
Script para modificar o audiosocket_handler.py para dar suporte ao modo de teste.

Este script faz as modificações necessárias no audiosocket_handler.py para
suportar o teste com um arquivo de áudio SLIN pré-gravado. As modificações são:

1. Adicionar código para carregar a configuração de teste
2. Adicionar código para usar o arquivo de teste após a detecção de fala

Uso:
    python modify_audiosocket_handler.py

Este script deve ser executado após configurar o modo de teste com o script
test_audiosocket_with_file.py.
"""

import os
import re
import sys
import logging
import shutil
import argparse

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("ModifyAudiosocketHandler")

def backup_file(file_path):
    """Cria uma cópia de backup do arquivo se ainda não existir."""
    backup_path = f"{file_path}.bak"
    if not os.path.exists(backup_path):
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup criado: {backup_path}")
        return True
    logger.info(f"Backup já existe: {backup_path}")
    return False

def restore_backup(file_path):
    """Restaura o arquivo original a partir do backup."""
    backup_path = f"{file_path}.bak"
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, file_path)
        logger.info(f"Arquivo restaurado a partir do backup: {file_path}")
        return True
    logger.error(f"Backup não encontrado: {backup_path}")
    return False

def add_test_config_code(file_content):
    """
    Adiciona o código para carregar a configuração de teste.
    
    Procura o trecho onde são carregadas as configurações do config.json
    e adiciona as linhas para carregar as configurações de teste.
    """
    # Padrão para encontrar o final do bloco de carregamento de configurações
    config_pattern = r"(try:.*?with open\('config\.json', 'r'\) as f:.*?VOICE_DETECTION_TYPE = VoiceDetectionType.*?$)"
    
    # Código a ser adicionado
    test_config_code = """
        # Configuração para testes
        TEST_MODE = config.get('testing', {}).get('enabled', False)
        TEST_AUDIO_FILE = config.get('testing', {}).get('test_audio_file', None)
        if TEST_MODE and TEST_AUDIO_FILE:
            logger.info(f"Modo de teste ativado com arquivo: {TEST_AUDIO_FILE}")
    """
    
    # Procurar o padrão e substituir com o código adicional
    pattern = re.compile(config_pattern, re.DOTALL | re.MULTILINE)
    match = pattern.search(file_content)
    
    if match:
        # Adicionar o código após o bloco existente, mantendo a indentação
        new_content = file_content[:match.end()] + test_config_code + file_content[match.end():]
        logger.info("Código de configuração de teste adicionado com sucesso")
        return new_content
    else:
        logger.error("Não foi possível encontrar o local para adicionar a configuração de teste")
        return file_content

def add_test_file_usage_vad(file_content):
    """
    Adiciona o código para usar o arquivo de teste no modo VAD.
    
    Procura o código que encerra a detecção de fala no método receber_audio_visitante_vad
    e adiciona o código para carregar e usar o arquivo de teste.
    """
    # Padrão para encontrar o local onde a fala é processada
    pattern = r"(speech_duration = \(asyncio\.get_event_loop\(\)\.time\(\) - speech_start\) \* 1000.*?audio_data = b\"\"\.join\(frames\).*?frames\.clear\(\))"
    
    # Código a ser adicionado
    test_file_code = """
                            # Se estamos em modo de teste e temos um arquivo de teste
                            if 'TEST_MODE' in globals() and TEST_MODE and TEST_AUDIO_FILE:
                                try:
                                    # Carregar o arquivo de teste
                                    test_file_path = TEST_AUDIO_FILE
                                    if not os.path.isabs(test_file_path):
                                        # Se for um nome de arquivo, procurar no diretório de cache
                                        test_file_path = os.path.join('audio/cache', test_file_path)
                                        
                                    logger.info(f"[{call_id}] Modo de teste: usando arquivo {test_file_path}")
                                    with open(test_file_path, 'rb') as f:
                                        test_audio_data = f.read()
                                        
                                    # Substituir o áudio capturado pelo arquivo de teste
                                    audio_data = test_audio_data
                                    logger.info(f"[{call_id}] Áudio de teste carregado: {len(audio_data)} bytes")
                                    
                                    # Log para o call_logger
                                    call_logger.log_event("TEST_AUDIO_LOADED", {
                                        "file": test_file_path,
                                        "size": len(audio_data)
                                    })
                                except Exception as e:
                                    logger.error(f"[{call_id}] Erro ao carregar arquivo de teste: {e}")
                                    call_logger.log_error("TEST_AUDIO_LOAD_FAILED", 
                                                        f"Erro ao carregar arquivo de teste", 
                                                        {"error": str(e)})
    """
    
    # Procurar o padrão e substituir com o código adicional
    pattern = re.compile(pattern, re.DOTALL | re.MULTILINE)
    match = pattern.search(file_content)
    
    if match:
        # Adicionar o código após o bloco existente, mantendo a indentação
        new_content = file_content[:match.end()] + test_file_code + file_content[match.end():]
        logger.info("Código de uso de arquivo de teste adicionado com sucesso para o modo VAD")
        return new_content
    else:
        logger.error("Não foi possível encontrar o local para adicionar o código de teste no modo VAD")
        return file_content

def add_test_file_usage_azure(file_content):
    """
    Adiciona o código para usar o arquivo de teste no modo Azure Speech.
    
    Procura o código no método on_speech_end_detected do Azure Speech e
    adiciona o código para carregar e usar o arquivo de teste.
    """
    # Padrão para encontrar o local no método on_speech_end_detected
    pattern = r"(def on_speech_end_detected\(self, evt\):.*?self\.collecting_audio = False)"
    
    # Código a ser adicionado
    test_file_code = """
        # Se estamos em modo de teste e temos um arquivo de teste
        if 'TEST_MODE' in globals() and TEST_MODE and TEST_AUDIO_FILE:
            try:
                # Carregar o arquivo de teste
                test_file_path = TEST_AUDIO_FILE
                if not os.path.isabs(test_file_path):
                    # Se for um nome de arquivo, procurar no diretório de cache
                    test_file_path = os.path.join('audio/cache', test_file_path)
                    
                logger.info(f"[{self.call_id}] Modo de teste Azure: usando arquivo {test_file_path}")
                with open(test_file_path, 'rb') as f:
                    test_audio_data = f.read()
                    
                # Substituir o áudio capturado pelo arquivo de teste
                # Devido à implementação do Azure Speech, vamos substituir apenas o áudio adicional
                # após o que já foi coletado
                self.audio_buffer.append(test_audio_data)
                logger.info(f"[{self.call_id}] Áudio de teste carregado (Azure): {len(test_audio_data)} bytes")
                
                # Log para o call_logger
                if self.call_logger:
                    self.call_logger.log_event("TEST_AUDIO_LOADED_AZURE", {
                        "file": test_file_path,
                        "size": len(test_audio_data)
                    })
            except Exception as e:
                logger.error(f"[{self.call_id}] Erro ao carregar arquivo de teste (Azure): {e}")
                if self.call_logger:
                    self.call_logger.log_error("TEST_AUDIO_LOAD_FAILED_AZURE", 
                                            f"Erro ao carregar arquivo de teste", 
                                            {"error": str(e)})
    """
    
    # Verificar se o código já não existe para evitar duplicatas
    if "TEST_MODE in globals() and TEST_MODE and TEST_AUDIO_FILE" in file_content:
        logger.info("Código de teste já existe no arquivo")
        return file_content
    
    # Procurar o padrão e substituir com o código adicional
    pattern = re.compile(pattern, re.DOTALL | re.MULTILINE)
    match = pattern.search(file_content)
    
    if match:
        # Adicionar o código após o bloco existente, mantendo a indentação
        end_pos = match.end()
        indentation = re.search(r"(\s+)self\.collecting_audio = False", match.group(0)).group(1)
        # Ajustar a indentação do código a ser inserido
        formatted_code = test_file_code.replace("\n        ", f"\n{indentation}")
        
        new_content = file_content[:end_pos] + formatted_code + file_content[end_pos:]
        logger.info("Código de uso de arquivo de teste adicionado com sucesso para o modo Azure Speech")
        return new_content
    else:
        logger.error("Não foi possível encontrar o local para adicionar o código de teste no modo Azure Speech")
        return file_content

def modify_audiosocket_handler():
    """
    Função principal que modifica o arquivo audiosocket_handler.py para suportar o modo de teste.
    """
    file_path = "audiosocket_handler.py"
    
    if not os.path.exists(file_path):
        logger.error(f"Arquivo {file_path} não encontrado")
        return False
    
    # Fazer backup do arquivo original
    backup_file(file_path)
    
    # Ler o conteúdo do arquivo
    with open(file_path, 'r') as f:
        file_content = f.read()
    
    # Verificar se o código de teste já existe
    if "TEST_MODE = config.get('testing', {}).get('enabled', False)" in file_content:
        logger.info("Configuração de teste já existe no arquivo")
    else:
        # Adicionar código para carregar a configuração de teste
        file_content = add_test_config_code(file_content)
    
    # Adicionar código para usar o arquivo de teste no modo VAD
    file_content = add_test_file_usage_vad(file_content)
    
    # Adicionar código para usar o arquivo de teste no modo Azure Speech
    if "SpeechCallbacks" in file_content:
        file_content = add_test_file_usage_azure(file_content)
    
    # Salvar o arquivo modificado
    with open(file_path, 'w') as f:
        f.write(file_content)
    
    logger.info(f"Arquivo {file_path} modificado com sucesso")
    return True

def main():
    parser = argparse.ArgumentParser(description="Modifica o audiosocket_handler.py para suportar o modo de teste")
    parser.add_argument('--restore', action='store_true',
                       help="Restaura o arquivo original a partir do backup")
    
    args = parser.parse_args()
    
    if args.restore:
        if restore_backup("audiosocket_handler.py"):
            print("Arquivo original restaurado com sucesso.")
        else:
            print("Falha ao restaurar arquivo original.")
        return
    
    if modify_audiosocket_handler():
        print("\n" + "="*60)
        print("AUDIOSOCKET_HANDLER.PY MODIFICADO COM SUCESSO")
        print("="*60)
        print("\nO arquivo foi modificado para suportar o modo de teste.")
        print("Agora você pode executar a aplicação normalmente:")
        print("  python main.py")
        print("\nPara restaurar o arquivo original após os testes:")
        print(f"  python {sys.argv[0]} --restore")
        print("="*60)
    else:
        print("Falha ao modificar o arquivo.")

if __name__ == "__main__":
    main()