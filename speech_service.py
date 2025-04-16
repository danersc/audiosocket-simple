import asyncio
from io import BytesIO

from audio_utils import converter_bytes_para_wav, converter_wav_para_slin
import azure.cognitiveservices.speech as speechsdk
import os
from pydub import AudioSegment

async def transcrever_audio_async(dados_audio_slin):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, transcrever_audio, dados_audio_slin)

async def sintetizar_fala_async(texto):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sintetizar_fala, texto)

def transcrever_audio(dados_audio_slin):
    audio_wav = converter_bytes_para_wav(dados_audio_slin, 8000)
    if not audio_wav:
        return None
    audio_segment = AudioSegment.from_file(BytesIO(audio_wav), format="wav")
    audio_segment = audio_segment.set_frame_rate(16000)
    buffer = BytesIO()
    audio_segment.export(buffer, format='wav')
    audio_wav_16k = buffer.getvalue()
    speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SPEECH_REGION'))
    speech_config.speech_recognition_language = 'pt-BR'
    audio_stream = speechsdk.audio.PushAudioInputStream()
    audio_stream.write(audio_wav_16k)
    audio_stream.close()
    audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    result = recognizer.recognize_once()
    return result.text if result.reason == speechsdk.ResultReason.RecognizedSpeech else None

def sintetizar_fala(texto):
    speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SPEECH_REGION'))
    speech_config.speech_synthesis_language = 'pt-BR'
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(texto).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return converter_wav_para_slin(result.audio_data, 8000)
    return None
