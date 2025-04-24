import asyncio
import os
import hashlib
from io import BytesIO

from audio_utils import converter_bytes_para_wav, converter_wav_para_slin
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment

# Diretório de cache para síntese de voz
CACHE_DIR = 'audio/cache'
os.makedirs(CACHE_DIR, exist_ok=True)

async def transcrever_audio_async(dados_audio_slin):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, transcrever_audio, dados_audio_slin)

async def sintetizar_fala_async(texto):
    # Verificar cache antes de sintetizar
    hash_texto = hashlib.md5(texto.encode('utf-8')).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{hash_texto}.slin")
    
    # Se já existe no cache, retornar o arquivo de áudio
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return f.read()
    
    # Se não está no cache, sintetizar e salvar
    loop = asyncio.get_event_loop()
    audio_data = await loop.run_in_executor(None, sintetizar_fala, texto)
    
    # Salvar no cache para uso futuro (apenas se a síntese foi bem-sucedida)
    if audio_data:
        with open(cache_path, 'wb') as f:
            f.write(audio_data)
    
    return audio_data

def transcrever_audio(dados_audio_slin):
    audio_wav = converter_bytes_para_wav(dados_audio_slin, 8000)
    if not audio_wav:
        return None
    
    # Converter para WAV de 16k (requisito da Azure)
    audio_segment = AudioSegment.from_file(BytesIO(audio_wav), format="wav")
    audio_segment = audio_segment.set_frame_rate(16000)
    
    # Normalizar áudio para melhorar chances de reconhecer palavras curtas
    audio_segment = audio_segment.normalize() 
    
    buffer = BytesIO()
    audio_segment.export(buffer, format='wav')
    audio_wav_16k = buffer.getvalue()
    
    # Configuração do serviço de fala
    speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SPEECH_REGION'))
    speech_config.speech_recognition_language = 'pt-BR'
    
    # Melhorar reconhecimento de palavras curtas como "Sim"
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText")
    
    audio_stream = speechsdk.audio.PushAudioInputStream()
    audio_stream.write(audio_wav_16k)
    audio_stream.close()
    audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    # Tentar reconhecer o áudio
    result = recognizer.recognize_once()
    
    # Quando o residente diz "Sim", às vezes é muito baixo ou curto para ser reconhecido
    # Verificamos os detalhes para otimizar
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text
    elif result.reason == speechsdk.ResultReason.NoMatch:
        # Para áudios curtos com NoMatch, consideramos que pode ser "sim" não reconhecido
        # Tamanho típico de um "sim" rápido é entre 1000-6000 bytes
        if len(dados_audio_slin) < 6000:
            print(f"Detecção de resposta curta não reconhecida ({len(dados_audio_slin)} bytes) - assumindo 'sim'")
            return "sim"
    
    return None

def sintetizar_fala(texto):
    speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SPEECH_REGION'))
    speech_config.speech_synthesis_language = 'pt-BR'
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(texto).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return converter_wav_para_slin(result.audio_data, 8000)
    return None

# Pré-carregar frases comuns
def pre_sintetizar_frases_comuns():
    """Pré-sintetiza frases comuns para o cache."""
    frases_comuns = [
        "Olá, seja bem-vindo! Em que posso ajudar?",
        "Por favor, me informe o seu nome",
        "Por favor, me informe para qual apartamento e o nome do morador",
        "Obrigado, aguarde um instante",
        "Ok, vamos entrar em contato com o morador. Aguarde, por favor.",
        "Desculpe, não consegui entender. Pode repetir por favor?",
        "Olá, morador! Você está em ligação com a portaria inteligente."
    ]
    
    for frase in frases_comuns:
        hash_texto = hashlib.md5(frase.encode('utf-8')).hexdigest()
        cache_path = os.path.join(CACHE_DIR, f"{hash_texto}.slin")
        
        # Só sintetiza se não existir no cache
        if not os.path.exists(cache_path):
            audio_data = sintetizar_fala(frase)
            if audio_data:
                with open(cache_path, 'wb') as f:
                    f.write(audio_data)
                print(f"Sintetizado e cacheado: '{frase}'")

# Pré-sintetizar frases na inicialização (descomente para habilitar)
# pre_sintetizar_frases_comuns()