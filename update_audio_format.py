#!/usr/bin/env python3
"""
Script para atualizar o formato de áudio nas funções de recebimento de áudio do visitante e morador.
Isso garante que o formato seja configurado corretamente para o Azure Speech reconhecer o SLIN 8kHz.

Este script encontra e substitui os trechos relevantes em audiosocket_handler.py de forma automática,
garantindo que as configurações de formato de áudio e segmentação estejam otimizadas para o Azure Speech.

ATENÇÃO: Este script é para ser executado apenas uma vez. Faça um backup do arquivo original antes.
"""

import re
import sys

def update_audio_format(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Padrão para encontrar a configuração do stream de áudio
    pattern = r"""    # Criar o stream de áudio \(PCM 16-bit a 8kHz\)
    push_stream = speechsdk\.audio\.PushAudioInputStream\(
        stream_format=speechsdk\.audio\.AudioStreamFormat\(
            samples_per_second=8000, 
            bits_per_sample=16,
            channels=1
        \)
    \)
    audio_config = speechsdk\.audio\.AudioConfig\(stream=push_stream\)"""
    
    # Nova configuração com formato explícito
    replacement = """    # Criar o stream de áudio (PCM 16-bit a 8kHz) - SLIN formato
    # Configuração explícita e completa para garantir que o Azure Speech entenda corretamente o formato
    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=8000,  # Crucialmente importante: 8kHz para SLIN
        bits_per_sample=16,       # 16-bit PCM
        channels=1                # mono
    )
    
    # Log detalhado do formato para debug
    logger.info(f"[{call_id}] Configurando formato de áudio: 8kHz, 16-bit, mono (SLIN)")
    
    # Criar o stream com o formato explícito
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)"""
    
    # Procurar e substituir todas as ocorrências
    new_content = re.sub(pattern, replacement, content)
    
    # Padrão para encontrar a criação do reconhecedor
    recognizer_pattern = r"""    # Criar o reconhecedor
    recognizer = speechsdk\.SpeechRecognizer\(speech_config=speech_config, audio_config=audio_config\)"""
    
    # Nova configuração com segmentação manual
    recognizer_replacement = """    # Adicionar parâmetros extras de segmentação
    if hasattr(speechsdk.PropertyId, "Speech_SegmentationStrategy"):
        # Configurar estratégia de segmentação manual para melhor controle
        speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationStrategy, "ManualOnly")
        logger.info(f"[{call_id}] Estratégia de segmentação configurada para: ManualOnly")
    
    # Criar o reconhecedor com o formato de áudio explícito configurado
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    logger.info(f"[{call_id}] Reconhecedor de fala iniciado com formato SLIN 8kHz")"""
    
    # Procurar e substituir todas as ocorrências
    new_content = re.sub(recognizer_pattern, recognizer_replacement, new_content)
    
    # Verificar se houve alterações
    if content == new_content:
        print("Nenhuma alteração necessária no arquivo.")
        return False
    
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
    
    update_audio_format(file_path)