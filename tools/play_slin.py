#!/usr/bin/env python3
"""
Ferramenta para reproduzir arquivos .slin salvos para debug.
Converte de SLIN (PCM 16-bit 8kHz mono) para WAV para verificação.

Uso:
    python tools/play_slin.py audio/debug/arquivo.slin

Ou converte todos os arquivos de um diretório:
    python tools/play_slin.py audio/debug/
"""

import os
import sys
import wave
import struct
import subprocess
from pathlib import Path

def convert_slin_to_wav(slin_file, wav_file=None):
    """Converte um arquivo SLIN para WAV para poder ser reproduzido."""
    if wav_file is None:
        wav_file = os.path.splitext(slin_file)[0] + '.wav'
    
    with open(slin_file, 'rb') as f:
        slin_data = f.read()
    
    # Criar arquivo WAV
    with wave.open(wav_file, 'wb') as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(8000)  # 8kHz
        wav.writeframes(slin_data)
    
    print(f"Convertido: {slin_file} -> {wav_file}")
    return wav_file

def play_wav(wav_file):
    """Tenta reproduzir o arquivo WAV usando o player disponível no sistema."""
    try:
        if sys.platform == 'darwin':  # macOS
            subprocess.run(['afplay', wav_file], check=True)
        elif sys.platform == 'linux':
            subprocess.run(['aplay', wav_file], check=True)
        elif sys.platform == 'win32':  # Windows
            subprocess.run(['start', wav_file], check=True, shell=True)
        else:
            print(f"Não foi possível reproduzir automaticamente. Abra o arquivo: {wav_file}")
    except Exception as e:
        print(f"Erro ao reproduzir: {e}")
        print(f"Você pode abrir o arquivo manualmente: {wav_file}")

def analyze_slin(slin_file):
    """Analisa um arquivo SLIN e mostra informações sobre ele."""
    with open(slin_file, 'rb') as f:
        slin_data = f.read()
    
    num_samples = len(slin_data) // 2  # 2 bytes por amostra (16-bit)
    duration_ms = (num_samples / 8000) * 1000  # 8000 Hz
    
    # Calcular valor RMS do áudio (indica volume/energia)
    if num_samples > 0:
        samples = struct.unpack(f"<{num_samples}h", slin_data)
        rms = (sum(s*s for s in samples) / num_samples) ** 0.5
    else:
        rms = 0
    
    # Verificar se o áudio contém silêncio ou ruído
    silent_threshold = 100  # Valor arbitrário para considerar silêncio
    if rms < silent_threshold:
        status = "SILÊNCIO"
    else:
        status = "CONTÉM ÁUDIO"
    
    print(f"Análise: {slin_file}")
    print(f"  - Tamanho: {len(slin_data):,} bytes")
    print(f"  - Duração: {duration_ms:.1f}ms (~{duration_ms/1000:.1f}s)")
    print(f"  - Amostras: {num_samples:,}")
    print(f"  - RMS: {rms:.1f} ({status})")
    
    return {
        'file': slin_file,
        'size_bytes': len(slin_data),
        'duration_ms': duration_ms,
        'samples': num_samples,
        'rms': rms,
        'status': status
    }

def process_file(slin_file):
    """Processa um único arquivo SLIN."""
    if not os.path.exists(slin_file):
        print(f"Arquivo não encontrado: {slin_file}")
        return
    
    analysis = analyze_slin(slin_file)
    
    # Converter para WAV se contém áudio
    if analysis['status'] == "CONTÉM ÁUDIO":
        wav_file = convert_slin_to_wav(slin_file)
        
        # Perguntar se quer reproduzir
        choice = input("Reproduzir o áudio? (s/n): ").lower()
        if choice == 's':
            play_wav(wav_file)
    else:
        print("Arquivo contém apenas silêncio, não vale a pena reproduzir.")

def process_directory(directory):
    """Processa todos os arquivos SLIN em um diretório."""
    directory = Path(directory)
    slin_files = list(directory.glob('*.slin'))
    
    if not slin_files:
        print(f"Nenhum arquivo .slin encontrado em: {directory}")
        return
    
    print(f"Encontrados {len(slin_files)} arquivos .slin em: {directory}\n")
    
    # Analisar todos os arquivos
    analyses = []
    for file in slin_files:
        analyses.append(analyze_slin(str(file)))
        print("")  # Linha em branco para separar
    
    # Mostrar informações ordenadas por tamanho
    print("\nArquivos ordenados por tamanho:")
    for i, analysis in enumerate(sorted(analyses, key=lambda x: x['size_bytes'], reverse=True), 1):
        print(f"{i}. {os.path.basename(analysis['file'])} - {analysis['duration_ms']:.1f}ms - {analysis['status']}")
    
    # Perguntar qual arquivo converter
    choice = input("\nDigite o número do arquivo para converter e reproduzir (0 para sair): ")
    try:
        choice = int(choice)
        if choice > 0 and choice <= len(analyses):
            selected = sorted(analyses, key=lambda x: x['size_bytes'], reverse=True)[choice-1]
            wav_file = convert_slin_to_wav(selected['file'])
            play_wav(wav_file)
    except ValueError:
        print("Escolha inválida.")

def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <arquivo.slin ou diretório>")
        return
    
    path = sys.argv[1]
    
    if os.path.isfile(path) and path.endswith('.slin'):
        process_file(path)
    elif os.path.isdir(path):
        process_directory(path)
    else:
        print(f"Caminho inválido ou não é um arquivo .slin: {path}")

if __name__ == "__main__":
    main()