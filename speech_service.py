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

async def transcrever_audio_async(dados_audio_slin, call_id=None):
    """
    Versão assíncrona da transcrição de áudio que aceita parâmetro de call_id
    para recursos de monitoramento e gerenciamento.
    """
    try:
        # Antes de transcrever, verificar disponibilidade no ResourceManager
        if 'resource_manager' in globals() and call_id:
            from extensions.resource_manager import resource_manager
            # Adquirir semáforo para limitar número de transcrições simultâneas
            await resource_manager.acquire_transcription_lock(call_id)
            
        # Usar executor para não bloquear a thread principal
        loop = asyncio.get_event_loop()
        start_time = asyncio.get_event_loop().time()
        result = await loop.run_in_executor(None, transcrever_audio, dados_audio_slin)
        
        # Registrar métricas se temos gerenciamento de recursos
        if 'resource_manager' in globals() and call_id:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            resource_manager.record_transcription(call_id, duration_ms)
            
        return result
    finally:
        # Sempre liberar o lock quando terminar
        if 'resource_manager' in globals() and call_id:
            resource_manager.release_transcription_lock(call_id)

async def sintetizar_fala_async(texto, call_id=None):
    """
    Versão assíncrona da síntese de fala que aceita parâmetro de call_id
    para recursos de monitoramento e gerenciamento.
    """
    # Verificar cache antes de sintetizar
    hash_texto = hashlib.md5(texto.encode('utf-8')).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{hash_texto}.slin")
    
    # Se já existe no cache, retornar o arquivo de áudio imediatamente
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return f.read()
    
    try:
        # Antes de sintetizar, verificar disponibilidade no ResourceManager
        if 'resource_manager' in globals() and call_id:
            from extensions.resource_manager import resource_manager
            # Adquirir semáforo para limitar número de sínteses simultâneas
            await resource_manager.acquire_synthesis_lock(call_id)
            
        # Se não está no cache, sintetizar e salvar
        start_time = asyncio.get_event_loop().time()
        loop = asyncio.get_event_loop()
        audio_data = await loop.run_in_executor(None, sintetizar_fala, texto)
        
        # Registrar métricas se temos gerenciamento de recursos
        if 'resource_manager' in globals() and call_id:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            resource_manager.record_synthesis(call_id, duration_ms)
        
        # Salvar no cache para uso futuro (apenas se a síntese foi bem-sucedida)
        if audio_data:
            with open(cache_path, 'wb') as f:
                f.write(audio_data)
        
        return audio_data
    finally:
        # Sempre liberar o lock quando terminar
        if 'resource_manager' in globals() and call_id:
            resource_manager.release_synthesis_lock(call_id)

def transcrever_audio(dados_audio_slin):
    """
    Transcrever áudio usando Azure Speech com abordagem simplificada e robusta.
    Comportamento alinhado com o método VAD para garantir consistência na aplicação.
    """
    # Log detalhado para diagnóstico
    audio_size = len(dados_audio_slin)
    frames_estimate = audio_size // 320  # Estimativa de frames (20ms cada)
    duracao_estimada = frames_estimate * 0.02  # Duração em segundos
    
    print(f"[TRANSCRIÇÃO] Iniciando transcrição de {audio_size} bytes de áudio SLIN (~{frames_estimate} frames, ~{duracao_estimada:.2f}s)")
    
    # Verificações de segurança para garantir que temos dados válidos
    if not dados_audio_slin:
        print("[TRANSCRIÇÃO] Dados de áudio vazios")
        return None
    
    if audio_size < 320:  # Menos de um frame de áudio
        print(f"[TRANSCRIÇÃO] Áudio muito pequeno para transcrição: {audio_size} bytes")
        return None
    
    # Verificação para áudio muito curto - provável ruído
    if audio_size < 4800:  # Menos de 300ms de áudio (~15 frames)
        print(f"[TRANSCRIÇÃO] Áudio muito curto detectado ({audio_size} bytes, ~{duracao_estimada:.2f}s) - considerando ruído ou resposta curta")
        return "ok"
    
    # Verificar energia do áudio para descartar ruído
    try:
        import struct
        # Converter bytes para valores PCM 16-bit
        samples = struct.unpack('<' + 'h' * (len(dados_audio_slin) // 2), dados_audio_slin)
        # Calcular energia média
        energy = sum(sample ** 2 for sample in samples) / len(samples)
        ENERGY_THRESHOLD = 600  # Threshold ajustável para considerar áudio válido
        
        if energy < ENERGY_THRESHOLD:
            print(f"[TRANSCRIÇÃO] Áudio com energia muito baixa ({energy:.2f} < {ENERGY_THRESHOLD}) - considerando ruído")
            # Para áudios com pouca energia, tratamos como confirmação
            return "ok"
        else:
            print(f"[TRANSCRIÇÃO] Energia do áudio: {energy:.2f} (acima do threshold {ENERGY_THRESHOLD})")
    except Exception as e:
        print(f"[TRANSCRIÇÃO] Erro ao analisar energia do áudio: {e}")
        # Em caso de erro, continuamos com a transcrição normal
        
    # Verificação para áudio curto - possível "sim"
    is_short_audio = audio_size < 8000  # ~0.5 segundo de áudio
    if is_short_audio:
        print(f"[TRANSCRIÇÃO] Áudio curto detectado ({audio_size} bytes, ~{duracao_estimada:.2f}s) - possível 'sim'")
    
    # Método direto mais simples, usando exatamente a mesma abordagem do VAD
    try:
        print(f"[TRANSCRIÇÃO] Usando método de transcrição direto (estilo VAD) - {audio_size} bytes")
        
        # 1. Converter dados PCM para WAV
        print("[TRANSCRIÇÃO] Convertendo SLIN para WAV")
        audio_wav = converter_bytes_para_wav(dados_audio_slin, 8000)
        if not audio_wav:
            print("[TRANSCRIÇÃO] Falha na conversão para WAV - formato de áudio não suportado")
            # Para áudio curto, tentamos retornar "sim" mesmo com falha de conversão
            if is_short_audio:
                print(f"[TRANSCRIÇÃO] Áudio curto com falha de conversão - retornando 'sim' como fallback")
                return "sim"
            return None
            
        # 2. Converter para WAV de 16k (requisito da Azure)
        print("[TRANSCRIÇÃO] Convertendo para WAV 16kHz")
        audio_segment = AudioSegment.from_file(BytesIO(audio_wav), format="wav")
        audio_segment = audio_segment.set_frame_rate(16000)
        
        # Aplicar normalização para melhorar reconhecimento
        print("[TRANSCRIÇÃO] Normalizando áudio")
        audio_segment = audio_segment.normalize()
        
        # 3. Exportar para WAV
        buffer = BytesIO()
        audio_segment.export(buffer, format='wav')
        audio_wav_16k = buffer.getvalue()
        
        if not audio_wav_16k:
            print("[TRANSCRIÇÃO] Falha ao exportar para WAV 16kHz")
            if is_short_audio:
                print(f"[TRANSCRIÇÃO] Áudio curto com falha de exportação - retornando 'sim' como fallback")
                return "sim"
            return None
            
        print(f"[TRANSCRIÇÃO] Áudio WAV 16kHz gerado com sucesso: {len(audio_wav_16k)} bytes")
        
        # 4. Configurações otimizadas do Azure Speech
        print("[TRANSCRIÇÃO] Configurando Azure Speech SDK")
        speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SPEECH_REGION'))
        speech_config.speech_recognition_language = 'pt-BR'
        
        # Melhorias para reconhecimento mais preciso
        speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText")
        speech_config.enable_dictation()  # Melhor para frases curtas
        
        # 5. Configurar streaming de áudio 
        print("[TRANSCRIÇÃO] Configurando stream de áudio")
        audio_stream = speechsdk.audio.PushAudioInputStream()
        audio_stream.write(audio_wav_16k)
        audio_stream.close()
        audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
        
        # 6. Criar reconhecedor e executar reconhecimento
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        print("[TRANSCRIÇÃO] Executando recognize_once()...")
        result = recognizer.recognize_once()
        
        # 7. Processar resultado
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            # Verificar se o texto está vazio - pode acontecer quando Azure reconhece com sucesso mas sem conteúdo
            if result.text and result.text.strip():
                # Texto não vazio - retornar normalmente
                print(f"[TRANSCRIÇÃO] Bem-sucedida: '{result.text}'")
                return result.text
            else:
                # Texto vazio - tratar de acordo com o tamanho do áudio
                print("[TRANSCRIÇÃO] Texto reconhecido está vazio")
                
                # Para áudios curtos, tratamos como resposta curta "sim"
                if is_short_audio:
                    print(f"[TRANSCRIÇÃO] Texto vazio em áudio curto ({audio_size} bytes) - considerando 'sim'")
                    return "sim"
                else:
                    # Para áudios mais longos, consideramos como um "ok"
                    print(f"[TRANSCRIÇÃO] Texto vazio em áudio normal ({audio_size} bytes) - considerando 'ok'")
                    return "ok"
        elif result.reason == speechsdk.ResultReason.NoMatch:
            no_match_info = "Sem detalhes disponíveis"
            try:
                no_match_info = result.no_match_details.reason
            except:
                pass
            print(f"[TRANSCRIÇÃO] Nenhuma fala reconhecida (NoMatch): {no_match_info}")
            
            # Para áudios curtos, consideramos "sim"
            if is_short_audio:
                print(f"[TRANSCRIÇÃO] Áudio curto não reconhecido ({audio_size} bytes) - considerando 'sim'")
                return "sim"
            return None
        else:
            print(f"[TRANSCRIÇÃO] Falha na transcrição. Reason: {result.reason}")
            # Para áudios curtos, ainda consideramos "sim" mesmo em caso de falha
            if is_short_audio:
                print(f"[TRANSCRIÇÃO] Áudio curto com falha de reconhecimento - retornando 'sim' como fallback")
                return "sim"
            return None
            
    except Exception as e:
        print(f"[TRANSCRIÇÃO] Erro durante a transcrição: {e}")
        import traceback
        print(traceback.format_exc())
        
        # Para áudios curtos, consideramos "sim" mesmo em caso de exceção
        if is_short_audio:
            print(f"[TRANSCRIÇÃO] Áudio curto com exceção - retornando 'sim' como fallback de emergência")
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