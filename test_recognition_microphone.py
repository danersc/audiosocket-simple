#!/usr/bin/env python3
"""
Script para testar o reconhecimento de voz local com o Azure Speech SDK.
Captura áudio do microfone e tenta transcrever usando a mesma estrutura de callbacks
que a aplicação principal.

Uso:
    python test_recognition_microphone.py

Requisitos:
    - Azure Speech SDK
    - PyAudio
    - Credenciais Azure configuradas nas variáveis de ambiente:
        - AZURE_SPEECH_KEY
        - AZURE_SPEECH_REGION
"""

import os
import time
import asyncio
import pyaudio
import azure.cognitiveservices.speech as speechsdk
import threading
import wave
import struct
from dotenv import load_dotenv

load_dotenv()

# Configurações de áudio
SAMPLE_RATE = 16000  # Usando 16kHz (padrão para reconhecimento de voz de alta qualidade)
CHANNELS = 1  # Mono
FORMAT = pyaudio.paInt16  # 16-bit
CHUNK_SIZE = 1600  # 100ms de áudio por chunk

# Para salvar áudio para análise
RECORD_SECONDS = 30  # Tempo máximo de gravação
OUTPUT_FILENAME = "audio_capturado.wav"
DEBUG_DIR = "audio/debug"

class SpeechCallbacks:
    """Classe para gerenciar callbacks do Azure Speech SDK similar à implementação principal."""
    
    def __init__(self):
        # Estado interno
        self.collecting_audio = False
        self.audio_buffer = []
        self.speech_detected = False
        self.speech_start_time = None
        
        # Para diagnóstico
        self.chunks_received = 0
        self.chunks_collected = 0
        self.recognition_results = []
        self.recognition_timestamps = []
        
        # Sinalizador para indicar quando a fala foi reconhecida
        self.recognized_event = threading.Event()
        
        # Para salvar áudio capturado
        os.makedirs(DEBUG_DIR, exist_ok=True)
        
        # Para log de eventos
        self.event_log = []
        
    def log_event(self, event_type, data=None):
        """Adiciona um evento ao log com timestamp."""
        timestamp = time.time()
        self.event_log.append({
            'timestamp': timestamp,
            'event': event_type,
            'data': data
        })
        
        # Também mostra no console
        print(f"[{time.strftime('%H:%M:%S', time.localtime(timestamp))}] {event_type}: {data}")
    
    def on_recognized(self, evt):
        """Callback quando a fala é reconhecida completamente."""
        self.log_event("RECOGNIZED", f"Reason: {evt.result.reason}")
        
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self.log_event("TEXT_RECOGNIZED", text)
            
            # Guardar resultado e timestamp
            self.recognition_results.append(text)
            self.recognition_timestamps.append(time.time())
            
            # Sinalizar que recebemos um resultado
            self.recognized_event.set()
            
            # Salvar áudio para análise
            if self.audio_buffer:
                try:
                    audio_data = b"".join(self.audio_buffer)
                    filename = f"{DEBUG_DIR}/recognized_audio_{len(self.recognition_results)}.wav"
                    self.save_audio_to_wav(audio_data, filename)
                    self.log_event("AUDIO_SAVED", filename)
                except Exception as e:
                    self.log_event("ERROR_SAVING_AUDIO", str(e))
        
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            self.log_event("NO_MATCH", 
                           evt.result.no_match_details if hasattr(evt.result, 'no_match_details') else "Sem detalhes")
            
            # Mesmo com NoMatch, salvamos o áudio para análise
            if self.audio_buffer:
                try:
                    audio_data = b"".join(self.audio_buffer)
                    filename = f"{DEBUG_DIR}/nomatch_audio_{int(time.time())}.wav"
                    self.save_audio_to_wav(audio_data, filename)
                    self.log_event("NOMATCH_AUDIO_SAVED", filename)
                except Exception as e:
                    self.log_event("ERROR_SAVING_AUDIO", str(e))
        
        # Limpar buffer para o próximo reconhecimento
        self.audio_buffer = []
        self.collecting_audio = False
        self.speech_detected = False
    
    def on_speech_start_detected(self, evt):
        """Callback quando o início da fala é detectado."""
        self.log_event("SPEECH_START_DETECTED", "")
        
        # Iniciar coleta
        self.collecting_audio = True
        self.speech_detected = True
        self.speech_start_time = time.time()
        
        # Limpar buffer para nova fala
        self.audio_buffer = []
    
    def on_speech_end_detected(self, evt):
        """Callback quando o fim da fala é detectado."""
        # Calcular duração se possível
        duration_ms = 0
        if self.speech_start_time:
            duration_ms = (time.time() - self.speech_start_time) * 1000
            
        self.log_event("SPEECH_END_DETECTED", f"Duração: {duration_ms:.1f}ms")
        
        # Marcar fim da coleta
        self.collecting_audio = False
    
    def on_recognizing(self, evt):
        """Callback para resultados parciais de reconhecimento."""
        if evt.result and evt.result.text:
            self.log_event("RECOGNIZING", evt.result.text)
    
    def on_session_started(self, evt):
        """Callback quando a sessão de reconhecimento é iniciada."""
        self.log_event("SESSION_STARTED", evt.session_id)
    
    def on_session_stopped(self, evt):
        """Callback quando a sessão de reconhecimento é encerrada."""
        self.log_event("SESSION_STOPPED", evt.session_id)
    
    def on_canceled(self, evt):
        """Callback quando o reconhecimento é cancelado."""
        self.log_event("CANCELED", f"Reason: {evt.reason}")
        if evt.reason == speechsdk.CancellationReason.Error:
            self.log_event("ERROR", evt.error_details)
    
    def add_audio_chunk(self, chunk):
        """Adiciona um chunk de áudio ao buffer."""
        # Incrementar estatísticas
        self.chunks_received += 1
        
        # Se não há áudio, ignorar
        if not chunk or len(chunk) == 0:
            return False
        
        # Sempre coletar se fala foi detectada
        if self.speech_detected:
            self.collecting_audio = True
        
        # Se estamos coletando, adicionar ao buffer
        if self.collecting_audio:
            self.audio_buffer.append(chunk)
            self.chunks_collected += 1
            return True
        
        return False
    
    def register_callbacks(self, recognizer):
        """Registra todos os callbacks com o recognizer."""
        recognizer.recognized.connect(self.on_recognized)
        recognizer.speech_start_detected.connect(self.on_speech_start_detected)
        recognizer.speech_end_detected.connect(self.on_speech_end_detected)
        recognizer.recognizing.connect(self.on_recognizing)
        recognizer.session_started.connect(self.on_session_started)
        recognizer.session_stopped.connect(self.on_session_stopped)
        recognizer.canceled.connect(self.on_canceled)
        
        self.log_event("CALLBACKS_REGISTERED", "")
    
    def save_audio_to_wav(self, audio_data, filename):
        """Salva dados de áudio PCM em um arquivo WAV."""
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data)

def check_azure_credentials():
    """Verifica se as credenciais do Azure Speech estão configuradas."""
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    
    if not key or not region:
        print("\n" + "="*60)
        print("ERRO: Credenciais do Azure Speech não configuradas!")
        print("Por favor, defina as seguintes variáveis de ambiente:")
        print("  export AZURE_SPEECH_KEY=sua-chave")
        print("  export AZURE_SPEECH_REGION=sua-regiao")
        print("="*60 + "\n")
        return False
    
    print(f"Azure Speech configurado para região: {region}")
    return True

def main():
    # Verificar credenciais
    if not check_azure_credentials():
        return
    
    # Inicializar callback handler
    callbacks = SpeechCallbacks()
    
    # Configurar Azure Speech
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = "pt-BR"
    
    # Criar configuração de áudio para microfone
    audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
    
    # Criar reconhecedor
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    
    # Registrar callbacks
    callbacks.register_callbacks(recognizer)
    
    print("\n" + "="*60)
    print("Teste de Reconhecimento de Voz com Microfone")
    print("="*60)
    print(f"SDK Version: {speechsdk.__version__}")
    print(f"Idioma: {speech_config.speech_recognition_language}")
    print(f"Modo: Reconhecimento contínuo com microfone")
    print("="*60)
    print("\nFale algo no microfone...")
    print("- Pressione Ctrl+C para encerrar o teste")
    print("- Serão salvos arquivos WAV com o áudio reconhecido")
    print("="*60 + "\n")
    
    # Iniciar reconhecimento contínuo
    recognizer.start_continuous_recognition_async()
    
    # Também vamos salvar todo o áudio da sessão para análise posterior
    p = pyaudio.PyAudio()
    all_audio_chunks = []
    
    # Abrir stream do microfone para captura manual
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE)
    
    # Loop principal para captura e processamento
    try:
        for i in range(0, int(SAMPLE_RATE / CHUNK_SIZE * RECORD_SECONDS)):
            # Capturar áudio do microfone
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            all_audio_chunks.append(data)
            
            # Adicionar ao buffer para reconhecimento (apenas para debug)
            callbacks.add_audio_chunk(data)
            
            # Verificar se tivemos um reconhecimento e mostrar status
            if callbacks.recognized_event.is_set():
                print(f"\nReconhecimento ocorreu! Texto: \"{callbacks.recognition_results[-1]}\"")
                print(f"Áudio salvo em: {DEBUG_DIR}/recognized_audio_{len(callbacks.recognition_results)}.wav")
                print("\nContinue falando... (Ctrl+C para sair)")
                
                # Resetar para o próximo reconhecimento
                callbacks.recognized_event.clear()
            
            # Pequena pausa para evitar uso intenso da CPU
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário!")
    finally:
        # Salvar todo o áudio capturado
        print("\nFinalizando e salvando áudio completo...")
        all_audio = b"".join(all_audio_chunks)
        
        with wave.open(OUTPUT_FILENAME, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(all_audio)
        
        # Parar reconhecimento e liberar recursos
        recognizer.stop_continuous_recognition_async()
        stream.stop_stream()
        stream.close()
        p.terminate()
    
    # Mostrar estatísticas finais
    print("\n" + "="*60)
    print("Estatísticas Finais")
    print("="*60)
    print(f"Total de eventos de reconhecimento: {len(callbacks.recognition_results)}")
    print(f"Chunks de áudio processados: {callbacks.chunks_received}")
    print(f"Chunks coletados durante fala: {callbacks.chunks_collected}")
    print(f"Áudio completo salvo em: {OUTPUT_FILENAME}")
    print("="*60 + "\n")
    
    # Mostrar todos os textos reconhecidos
    if callbacks.recognition_results:
        print("Textos reconhecidos:")
        for i, (text, timestamp) in enumerate(zip(callbacks.recognition_results, 
                                                 callbacks.recognition_timestamps)):
            time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
            print(f"{i+1}. [{time_str}] {text}")
    else:
        print("Nenhum texto foi reconhecido durante o teste.")
    
    print("\nTeste concluído!")

if __name__ == "__main__":
    main()
