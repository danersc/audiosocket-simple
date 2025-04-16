#!/usr/bin/env python3
# speech_service.py - Serviços de transcrição e síntese de voz

import os
import logging
import azure.cognitiveservices.speech as speechsdk
from io import BytesIO
from pydub import AudioSegment
from audio_utils import converter_bytes_para_wav, converter_wav_para_slin

logger = logging.getLogger(__name__)

def transcrever_audio(dados_audio_slin):
    """
    Transcreve áudio do formato SLIN utilizando Azure Speech Services.
    
    Args:
        dados_audio_slin: Bytes de áudio no formato SLIN
        
    Returns:
        Texto transcrito ou None em caso de erro
    """
    try:
        # Converter SLIN para WAV bytes a 8000 Hz
        audio_wav = converter_bytes_para_wav(dados_audio_slin, sample_rate=8000)
        if not audio_wav:
            return None

        # Resamplear o áudio para 16000 Hz (requerido pelo Azure)
        audio_segment = AudioSegment.from_file(BytesIO(audio_wav), format="wav")
        audio_segment = audio_segment.set_frame_rate(16000)

        # Exportar o áudio resampleado para bytes
        buffer = BytesIO()
        audio_segment.export(buffer, format='wav')
        audio_wav_16k = buffer.getvalue()

        # Configurar o serviço do Azure Speech
        speech_key = os.getenv('AZURE_SPEECH_KEY')
        service_region = os.getenv('AZURE_SPEECH_REGION')

        if not speech_key or not service_region:
            logger.error("AZURE_SPEECH_KEY e AZURE_SPEECH_REGION não estão definidas")
            return None

        # Configurar o reconhecimento de fala
        audio_stream = speechsdk.audio.PushAudioInputStream()
        audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
        speech_config.speech_recognition_language = 'pt-BR'

        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        # Enviar o áudio para o recognizer
        audio_stream.write(audio_wav_16k)
        audio_stream.close()

        # Realizar a transcrição
        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcricao = result.text
            logger.info(f"Transcrição: {transcricao}")
            return transcricao
        else:
            logger.warning(f"Erro na transcrição: {result.reason}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao transcrever áudio: {e}")
        return None

def sintetizar_fala(texto):
    """
    Sintetiza texto em fala utilizando Azure Speech Services.
    
    Args:
        texto: Texto a ser sintetizado
        
    Returns:
        Bytes de áudio no formato SLIN ou None em caso de erro
    """
    try:
        speech_key = os.getenv('AZURE_SPEECH_KEY')
        service_region = os.getenv('AZURE_SPEECH_REGION')

        if not speech_key or not service_region:
            logger.error("AZURE_SPEECH_KEY e AZURE_SPEECH_REGION não estão definidas")
            return None

        # Configurar o serviço do Azure Speech
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
        speech_config.speech_synthesis_language = 'pt-BR'
        speech_config.speech_synthesis_voice_name = 'pt-BR-ThalitaNeural'

        # Define o formato de saída como PCM 8 kHz, 16 bits, mono
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff8Khz16BitMonoPcm
        )

        # Criar o sintetizador
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

        # Sintetizar o texto em fala
        result = synthesizer.speak_text_async(texto).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            # Obter os dados de áudio sintetizado
            audio_data = result.audio_data

            # Converter os dados de áudio WAV para SLIN
            dados_slin = converter_wav_para_slin(audio_data, sample_rate=8000)
            return dados_slin
        else:
            logger.warning(f"Erro na síntese de fala: {result.reason}")
            return None
            
    except Exception as e:
        logger.error(f"Erro ao sintetizar fala: {e}")
        return None
