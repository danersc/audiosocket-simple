#!/usr/bin/env python3
"""
Script para adicionar diagnóstico e melhorar o reconhecedor de fala no arquivo audiosocket_handler.py.
Esta atualização visa resolver problemas do evento recognized não ser disparado.
"""

import os
import re
import sys

def update_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Identificar e substituir os blocos do reconhecedor
    pattern = r"""    # Criar o reconhecedor com o formato de áudio explícito configurado
    recognizer = speechsdk\.SpeechRecognizer\(speech_config=speech_config, audio_config=audio_config\)
    logger\.info\(f"\[\{call_id\}\] Reconhecedor de fala iniciado com formato SLIN 8kHz"\)"""
    
    # Nova configuração com diagnóstico adicional
    replacement = """    # Diagnóstico adicional para o Azure Speech SDK
    logger.info(f"[{call_id}] Versão do Azure Speech SDK: {speechsdk.__version__}")
    
    # Verificar se a língua está configurada corretamente
    try:
        lang = speech_config.speech_recognition_language
        logger.info(f"[{call_id}] Idioma reconhecimento configurado: {lang}")
    except:
        logger.warning(f"[{call_id}] Não foi possível verificar o idioma configurado")
    
    # Adicionar parâmetros extras para melhorar experiência
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "None")
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "700")
    
    # Forçar configuração explícita de idioma
    speech_config.speech_recognition_language = "pt-BR"
    
    # Criar o reconhecedor com o formato de áudio explícito configurado
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    logger.info(f"[{call_id}] Reconhecedor de fala iniciado com formato SLIN 8kHz")"""
    
    # Aplicar substituição usando regex
    new_content = re.sub(pattern, replacement, content)
    
    # Verificar se houve alterações
    if content == new_content:
        print("Nenhuma alteração necessária no arquivo.")
        return False
    
    # Fazer backup do arquivo original
    backup_path = file_path + '.bak'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Backup do arquivo original criado em: {backup_path}")
    
    # Salvar as alterações
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Arquivo {file_path} atualizado com sucesso!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        file_path = "audiosocket_handler.py"  # Padrão
    else:
        file_path = sys.argv[1]
    
    update_file(file_path)