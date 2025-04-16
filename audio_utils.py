#!/usr/bin/env python3
# audio_utils.py - Utilitários para manipulação de áudio

from pydub import AudioSegment
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

def converter_bytes_para_wav(dados_slin, sample_rate=8000):
    """
    Converte bytes no formato SLIN para WAV.
    
    Args:
        dados_slin: Bytes de áudio no formato SLIN
        sample_rate: Taxa de amostragem (padrão: 8000 Hz)
        
    Returns:
        Bytes WAV do áudio convertido
    """
    try:
        audio_segment = AudioSegment(
            data=bytes(dados_slin),
            sample_width=2,  # 16 bits = 2 bytes
            frame_rate=sample_rate,
            channels=1
        )
        buffer = BytesIO()
        audio_segment.export(buffer, format='wav')
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Erro ao converter bytes para WAV: {e}")
        return None

def converter_wav_para_slin(dados_wav, sample_rate=8000):
    """
    Converte bytes WAV para o formato SLIN.
    
    Args:
        dados_wav: Bytes de áudio no formato WAV
        sample_rate: Taxa de amostragem desejada (padrão: 8000 Hz)
        
    Returns:
        Bytes SLIN do áudio convertido
    """
    try:
        audio_segment = AudioSegment.from_file(BytesIO(dados_wav), format="wav")
        audio_segment = audio_segment.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
        return audio_segment.raw_data
    except Exception as e:
        logger.error(f"Erro ao converter WAV para SLIN: {e}")
        return None