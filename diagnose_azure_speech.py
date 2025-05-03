#!/usr/bin/env python3
"""
Diagnóstico do Azure Speech SDK - Identifica possíveis problemas com a configuração.

Este script verifica:
1. Se as credenciais estão configuradas corretamente
2. Se o formato de áudio está sendo passado corretamente
3. Se o evento recognized está sendo disparado
4. Se há conectividade com a Azure

Útil para depurar problemas de reconhecimento de fala.
"""

import os
import time
import azure.cognitiveservices.speech as speechsdk
import asyncio

def diagnose_azure_speech():
    print("\n=== Diagnóstico do Azure Speech ===\n")
    
    # Verificar versão do SDK
    print(f"Versão do Azure Speech SDK: {speechsdk.__version__}")
    
    # Verificar credenciais
    azure_key = os.getenv('AZURE_SPEECH_KEY')
    azure_region = os.getenv('AZURE_SPEECH_REGION')
    
    if not azure_key:
        print("ERRO: AZURE_SPEECH_KEY não está definida no ambiente")
        print("Defina com: export AZURE_SPEECH_KEY=sua-chave")
        return False
    else:
        print("✓ AZURE_SPEECH_KEY configurada")
        
    if not azure_region:
        print("ERRO: AZURE_SPEECH_REGION não está definida no ambiente")
        print("Defina com: export AZURE_SPEECH_REGION=sua-regiao")
        return False
    else:
        print(f"✓ AZURE_SPEECH_REGION configurada: {azure_region}")
    
    print("\n--- Configuração básica ---")
    
    # Configuração básica
    speech_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
    speech_config.speech_recognition_language = "pt-BR"
    
    # Formatar o stream para 8kHz (SLIN)
    print("Configurando stream de áudio para 8kHz 16-bit mono (SLIN)...")
    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=8000,
        bits_per_sample=16,
        channels=1
    )
    
    # Criar o stream e o reconhecedor
    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    
    # Verificar propriedades disponíveis
    print("\n--- Propriedades disponíveis ---")
    important_props = [
        "Speech_SegmentationSilenceTimeoutMs",
        "SpeechServiceConnection_InitialSilenceTimeoutMs",
        "SpeechServiceConnection_EndSilenceTimeoutMs",
        "SpeechServiceConnection_RecoLanguage"
    ]
    
    for prop in important_props:
        full_prop = f"speechsdk.PropertyId.{prop}"
        if hasattr(speechsdk.PropertyId, prop):
            print(f"✓ {prop} disponível")
            try:
                val = speech_config.get_property(getattr(speechsdk.PropertyId, prop))
                print(f"  Valor atual: {val}")
            except:
                print("  Valor não disponível")
        else:
            print(f"✗ {prop} NÃO disponível")
    
    # Verificar eventos disponíveis
    print("\n--- Testando reconhecimento ---")
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    # Variáveis para monitorar eventos
    done_event = asyncio.Event()
    recognition_results = []
    
    # Definir callbacks para monitorar
    def on_recognized(evt):
        print(f"Evento RECOGNIZED disparado! Razão: {evt.result.reason}")
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            print(f"Texto reconhecido: '{evt.result.text}'")
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            print(f"NoMatch: {evt.result.no_match_details if hasattr(evt.result, 'no_match_details') else 'N/A'}")
        recognition_results.append(("recognized", evt.result.reason))
    
    def on_recognizing(evt):
        print(f"Evento RECOGNIZING disparado: '{evt.result.text}'")
        recognition_results.append(("recognizing", evt.result.text))
    
    def on_speech_start_detected(evt):
        print(f"Início de fala detectado!")
        recognition_results.append(("speech_start", time.time()))
    
    def on_speech_end_detected(evt):
        print(f"Fim de fala detectado!")
        recognition_results.append(("speech_end", time.time()))
    
    def on_canceled(evt):
        print(f"Reconhecimento cancelado! Razão: {evt.reason}")
        if evt.reason == speechsdk.CancellationReason.Error:
            print(f"Erro: {evt.error_details}")
        recognition_results.append(("canceled", evt.reason))
        done_event.set()
    
    def on_session_stopped(evt):
        print(f"Sessão encerrada: {evt.session_id}")
        recognition_results.append(("session_stopped", evt.session_id))
        done_event.set()
    
    # Conectar callbacks
    recognizer.recognized.connect(on_recognized)
    recognizer.recognizing.connect(on_recognizing)
    recognizer.speech_start_detected.connect(on_speech_start_detected)
    recognizer.speech_end_detected.connect(on_speech_end_detected)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(on_session_stopped)
    
    print("\nTeste de reconhecimento com áudio de teste (8kHz)...")
    recognizer.start_continuous_recognition_async()
    
    # Simular envio de áudio - criamos um sinal de áudio sintético com uma onda senoidal
    import math
    import struct
    
    # Gerar onda senoidal de 1kHz em um buffer PCM 16-bit a 8kHz
    freq = 1000  # 1kHz
    duration_s = 2.0  # 2 segundos
    sample_rate = 8000
    num_samples = int(duration_s * sample_rate)
    
    print(f"Gerando áudio de teste: {duration_s}s de tom de {freq}Hz...")
    
    # Gerar e enviar o áudio
    for i in range(num_samples):
        t = i / sample_rate  # tempo em segundos
        amplitude = 32000.0  # próximo do máximo para 16-bit signed (-32768 a 32767)
        sample = int(amplitude * math.sin(2 * math.pi * freq * t))
        sample_bytes = struct.pack("<h", sample)  # PCM 16-bit little endian
        push_stream.write(sample_bytes)
        
        # Enviar em pequenos chunks com pausas para simular streaming
        if i % 400 == 0:  # cada 50ms de áudio
            time.sleep(0.01)  # pequena pausa
    
    print("Áudio de teste enviado! Aguardando resultado...")
    
    # Fechar o stream para indicar fim do áudio
    push_stream.close()
    
    # Aguardar por até 10 segundos pelo resultado
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Se já estamos em um event loop (comum em contexto async)
            future = asyncio.run_coroutine_threadsafe(wait_for_done(done_event), loop)
            future.result(10)  # timeout de 10s
        else:
            # Se não estamos em um event loop
            loop.run_until_complete(asyncio.wait_for(done_event.wait(), 10))
    except asyncio.TimeoutError:
        print("TIMEOUT! Não recebemos resposta em 10 segundos.")
    finally:
        recognizer.stop_continuous_recognition_async()
    
    # Analisar resultados
    print("\n--- Resultado do Diagnóstico ---")
    if not recognition_results:
        print("❌ PROBLEMA CRÍTICO: Nenhum evento de reconhecimento foi disparado!")
    else:
        print(f"✓ {len(recognition_results)} eventos disparados")
        
        for event_type, data in recognition_results:
            print(f"  - {event_type}: {data}")
        
        # Verificar se o recognized foi disparado
        recognized = any(event_type == "recognized" for event_type, _ in recognition_results)
        if recognized:
            print("✓ Evento RECOGNIZED foi disparado pelo Azure Speech")
        else:
            print("❌ PROBLEMA: Evento RECOGNIZED não foi disparado!")
            print("   Isso pode indicar problema com o formato de áudio ou conectividade.")
    
    print("\n--- Recomendações ---")
    if not recognized:
        print("1. Verifique se as credenciais do Azure estão corretas e ativas")
        print("2. Certifique-se de que o formato de áudio está configurado para 8kHz 16-bit mono")
        print("3. Verifique a conectividade com o serviço Azure Speech")
        print("4. Tente usar um arquivo de áudio conhecido para testar (em vez de áudio gerado)")
    else:
        print("O diagnóstico básico não identificou problemas críticos.")
    
    print("\nDiagnóstico concluído!")

async def wait_for_done(event):
    await event.wait()

if __name__ == "__main__":
    # Verificar se estamos em asyncio
    try:
        asyncio.get_running_loop()
        is_async = True
    except RuntimeError:
        is_async = False
    
    if is_async:
        print("Executando em contexto assíncrono...")
        asyncio.create_task(diagnose_azure_speech())
    else:
        diagnose_azure_speech()