#!/usr/bin/env python3
"""
Script para gravar um áudio no formato SLIN (Signed Linear) para diagnóstico.
Este script grava um áudio do microfone e o salva no formato SLIN para ser usado
como referência em testes de diagnóstico.

Uso:
    python record_slin_audio.py [nome_arquivo] [duracao_segundos]

Argumentos:
    nome_arquivo: Nome do arquivo de saída (padrão: test_audio.slin)
    duracao_segundos: Duração da gravação em segundos (padrão: 10)

Requisitos:
    - PyAudio
    - PySLIN
"""

import os
import sys
import time
import pyaudio
import wave
import hashlib
import argparse
from pathlib import Path

# Configurações de áudio
SAMPLE_RATE = 8000  # SLIN é 8kHz por padrão
CHANNELS = 1        # Mono
FORMAT = pyaudio.paInt16  # 16-bit
CHUNK_SIZE = 320    # 40ms de áudio por chunk (mesmo valor usado no audiosocket_handler)

# Diretório padrão para salvar os arquivos
AUDIO_CACHE_DIR = "audio/cache"


def md5_hash(data):
    """Gera um hash MD5 dos dados binários do áudio."""
    return hashlib.md5(data).hexdigest()


def record_audio(duration_seconds=10, progress_callback=None):
    """
    Grava áudio do microfone por um período de tempo especificado.
    
    Args:
        duration_seconds: Duração da gravação em segundos
        progress_callback: Função para reportar progresso
        
    Returns:
        Dados de áudio brutos (PCM) no formato SLIN
    """
    # Inicializar PyAudio
    p = pyaudio.PyAudio()
    
    # Mostrar informações sobre o dispositivo de entrada padrão
    device_info = p.get_default_input_device_info()
    print(f"Dispositivo de entrada: {device_info['name']}")
    
    # Abrir stream para captura
    stream = p.open(format=FORMAT,
                   channels=CHANNELS,
                   rate=SAMPLE_RATE,
                   input=True,
                   frames_per_buffer=CHUNK_SIZE)
    
    print(f"\nIniciando gravação de {duration_seconds} segundos...")
    print("Fale algo no microfone...")
    
    # Calcular número de iterações baseado no chunk_size e duração
    n_chunks = int(SAMPLE_RATE / CHUNK_SIZE * duration_seconds)
    
    # Lista para armazenar os chunks de áudio
    audio_chunks = []
    
    # Loop de gravação
    for i in range(n_chunks):
        # Atualizar progresso
        if i % 10 == 0:  # A cada 10 chunks (cerca de 400ms)
            progress = (i / n_chunks) * 100
            print(f"\rProgresso: {progress:.1f}%", end="")
            if progress_callback:
                progress_callback(progress)
                
        # Ler um chunk de áudio
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        audio_chunks.append(data)
    
    print("\rProgresso: 100.0%")
    print("\nGravação concluída!")
    
    # Fechar e liberar recursos
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    # Juntar todos os chunks em um único buffer
    return b"".join(audio_chunks)


def save_slin_file(audio_data, output_filename):
    """
    Salva dados de áudio diretamente no formato SLIN.
    
    Args:
        audio_data: Bytes de áudio no formato PCM
        output_filename: Nome do arquivo de saída
    """
    # Garantir que o diretório exista
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    
    # Salvar o arquivo SLIN (que é basicamente PCM raw)
    with open(output_filename, 'wb') as f:
        f.write(audio_data)
    
    print(f"Arquivo SLIN salvo: {output_filename}")
    print(f"Tamanho: {len(audio_data)} bytes")
    
    # Gerar um hash do arquivo para referência
    audio_hash = md5_hash(audio_data)
    print(f"Hash MD5: {audio_hash}")
    
    return audio_hash


def save_wav_file(audio_data, output_filename):
    """
    Salva uma cópia do áudio no formato WAV para referência.
    Útil para ouvir o áudio gravado com um player padrão.
    
    Args:
        audio_data: Bytes de áudio no formato PCM
        output_filename: Nome do arquivo de saída
    """
    # Criar arquivo WAV para referência (mais fácil de ouvir)
    wav_filename = output_filename.replace('.slin', '.wav')
    
    with wave.open(wav_filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)
    
    print(f"Arquivo WAV de referência salvo: {wav_filename}")


def main():
    # Configurar parser de argumentos
    parser = argparse.ArgumentParser(description="Grava áudio no formato SLIN para diagnóstico")
    parser.add_argument('output_file', nargs='?', default="test_audio.slin", 
                        help="Nome do arquivo de saída (padrão: test_audio.slin)")
    parser.add_argument('duration', nargs='?', type=int, default=10,
                        help="Duração da gravação em segundos (padrão: 10)")
    parser.add_argument('--cache', action='store_true',
                        help="Salvar no diretório de cache com nome baseado no hash")
    
    args = parser.parse_args()
    
    # Gravar o áudio
    audio_data = record_audio(args.duration)
    
    # Determinar nome do arquivo de saída
    if args.cache:
        # Gerar hash do áudio
        audio_hash = md5_hash(audio_data)
        # Criar nome de arquivo baseado no hash
        output_filename = os.path.join(AUDIO_CACHE_DIR, f"{audio_hash}.slin")
    else:
        # Usar nome fornecido pelo usuário
        output_filename = args.output_file
        # Se for um caminho relativo, converter para o diretório atual
        if not os.path.isabs(output_filename):
            output_filename = os.path.join(os.getcwd(), output_filename)
    
    # Garantir que o diretório de saída exista
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)
    
    # Salvar o arquivo SLIN
    audio_hash = save_slin_file(audio_data, output_filename)
    
    # Salvar uma cópia em WAV para referência
    save_wav_file(audio_data, output_filename)
    
    # Mostrar instruções de uso
    print("\n" + "="*60)
    print("INSTRUÇÕES DE USO:")
    print("="*60)
    print(f"1. Para usar este áudio nos testes, adicione essa linha ao config.json:")
    print(f'   "test_audio_file": "{os.path.basename(output_filename)}"')
    print("2. Execute a aplicação principal normalmente")
    print("3. Para mudar o arquivo de teste, modifique a configuração ou:")
    print(f"   Grave outro áudio: python {sys.argv[0]} outro_nome.slin")
    print("="*60)
    
    return audio_hash


if __name__ == "__main__":
    main()