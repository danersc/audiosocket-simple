import azure.cognitiveservices.speech as speechsdk
import os

# Adicionar credenciais temporárias para teste
os.environ['AZURE_SPEECH_KEY'] = 'dummy-key-for-testing'
os.environ['AZURE_SPEECH_REGION'] = 'westus'

# Verificar se a propriedade "Speech_VoiceDetectionSensitivity" existe
# (esta é a propriedade que está causando o erro)
print("Verificando se a propriedade problemática existe:")
props_with_voice_detection = [prop for prop in dir(speechsdk.PropertyId) if 'VoiceDetection' in prop]
if props_with_voice_detection:
    print(f"Propriedades com 'VoiceDetection' no nome: {props_with_voice_detection}")
else:
    print("Nenhuma propriedade com 'VoiceDetection' no nome foi encontrada")

print("Verificando as propriedades disponíveis no Azure Speech SDK:")
print("Versão do SDK:", speechsdk.__version__)
print("\nPropertyId disponíveis relacionadas a 'Speech_':")
speech_props = [prop for prop in dir(speechsdk.PropertyId) if 'Speech_' in prop]
for prop in speech_props:
    print(f"  - {prop}")

print("\nVerificando se as credenciais Azure estão configuradas:")
azure_key = os.getenv('AZURE_SPEECH_KEY')
azure_region = os.getenv('AZURE_SPEECH_REGION')

if azure_key and azure_region:
    print(f"  - AZURE_SPEECH_KEY: Configurado (não exibido por segurança)")
    print(f"  - AZURE_SPEECH_REGION: {azure_region}")
    
    # Tenta criar uma configuração básica para testar
    try:
        speech_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
        print("\nCriação de SpeechConfig bem-sucedida.")
        
        # Testa configurar propriedades básicas
        try:
            speech_config.speech_recognition_language = 'pt-BR'
            print("Configuração de idioma bem-sucedida.")
            
            # Testa configurar propriedades relacionadas às que estavam causando erro
            try:
                speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "800")
                print("Configuração de SegmentationSilenceTimeoutMs bem-sucedida.")
            except Exception as e:
                print(f"Erro ao configurar SegmentationSilenceTimeoutMs: {e}")
                
            # Testa métodos de configuração que podem estar faltando
            print("\nTestando métodos que podem não existir:")
            
            if hasattr(speech_config, 'enable_audio_logging'):
                print("  - enable_audio_logging: Existe")
                speech_config.enable_audio_logging()
            else:
                print("  - enable_audio_logging: NÃO existe")
                
            if hasattr(speech_config, 'enable_dictation'):
                print("  - enable_dictation: Existe")
                speech_config.enable_dictation()
            else:
                print("  - enable_dictation: NÃO existe")
                
            if hasattr(speechsdk, 'ProfanityOption'):
                print("  - ProfanityOption: Existe")
                speech_config.set_profanity(speechsdk.ProfanityOption.Raw)
            else:
                print("  - ProfanityOption: NÃO existe")
                
        except Exception as e:
            print(f"Erro ao configurar propriedades: {e}")
    except Exception as e:
        print(f"Erro ao criar SpeechConfig: {e}")
else:
    print("Credenciais Azure não configuradas:")
    if not azure_key:
        print("  - AZURE_SPEECH_KEY não está definido")
    if not azure_region:
        print("  - AZURE_SPEECH_REGION não está definido")