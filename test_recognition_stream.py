#!/usr/bin/env python3
import os
import socket
import threading
import time
import wave
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk

load_dotenv()

# Configurações gerais
SAMPLE_RATE = 8000
CHANNELS = 1
DEBUG_DIR = "audio/debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

# Parser TLV AudioSocket
def read_tlv_packet(conn):
    header = conn.recv(3)
    if len(header) < 3:
        return None, None

    packet_type = header[0]
    length = int.from_bytes(header[1:3], "big")

    payload = b''
    while len(payload) < length:
        chunk = conn.recv(length - len(payload))
        if not chunk:
            return None, None
        payload += chunk

    return packet_type, payload

# Callbacks do Azure Speech SDK
class SpeechCallbacks:
    def __init__(self):
        self.recognition_results = []

    def log_event(self, event_type, data=None):
        timestamp = time.strftime('%H:%M:%S')
        print(f"[{timestamp}] {event_type}: {data}")

    def on_recognized(self, evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text
            self.log_event("RECOGNIZED", text)
            self.recognition_results.append(text)
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            self.log_event("NO_MATCH", evt.result.no_match_details)

    def register_callbacks(self, recognizer):
        recognizer.recognized.connect(self.on_recognized)
        recognizer.canceled.connect(lambda evt: self.log_event("CANCELED", evt.reason))
        recognizer.session_started.connect(lambda evt: self.log_event("SESSION_STARTED", evt.session_id))
        recognizer.session_stopped.connect(lambda evt: self.log_event("SESSION_STOPPED", evt.session_id))

# Verificação das credenciais Azure
def check_azure_credentials():
    key = os.getenv("AZURE_SPEECH_KEY")
    region = os.getenv("AZURE_SPEECH_REGION")
    if not key or not region:
        print("Configure as credenciais do Azure!")
        return False
    print(f"Azure configurado para região: {region}")
    return True

# Recebe áudio do socket e envia para Azure
def socket_audio_receiver(push_stream):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("0.0.0.0", 8080))
    server_socket.listen(1)

    print("Aguardando conexão na porta 8080...")
    conn, addr = server_socket.accept()
    print(f"Conexão recebida de: {addr}")

    audio_buffer = []
    try:
        while True:
            packet_type, payload = read_tlv_packet(conn)
            if packet_type is None:
                break

            if packet_type == 0x10:  # áudio
                audio_buffer.append(payload)
                push_stream.write(payload)

            elif packet_type == 0x01:  # UUID
                print(f"UUID recebido: {payload.hex()}")

            elif packet_type == 0x00:  # Fim da transmissão
                print("Pacote de término recebido.")
                break

    except Exception as e:
        print(f"Erro ao receber dados: {e}")
    finally:
        conn.close()
        push_stream.close()

        audio_data = b''.join(audio_buffer)
        filename = os.path.join(DEBUG_DIR, "audio_recebido_socket.wav")
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data)

        print(f"Áudio salvo em {filename}")

# Função principal
def main():
    if not check_azure_credentials():
        return

    callbacks = SpeechCallbacks()

    speech_config = speechsdk.SpeechConfig(
        subscription=os.getenv("AZURE_SPEECH_KEY"),
        region=os.getenv("AZURE_SPEECH_REGION")
    )
    speech_config.speech_recognition_language = "pt-BR"

    audio_format = speechsdk.audio.AudioStreamFormat(
        samples_per_second=SAMPLE_RATE,
        bits_per_sample=16,
        channels=CHANNELS
    )

    push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)

    recognizer = speechsdk.SpeechRecognizer(speech_config, audio_config)
    callbacks.register_callbacks(recognizer)

    recognizer.start_continuous_recognition_async()

    receiver_thread = threading.Thread(target=socket_audio_receiver, args=(push_stream,))
    receiver_thread.start()

    print("Reconhecendo áudio recebido via socket...")
    print("Pressione Ctrl+C para finalizar.")

    try:
        while receiver_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Interrompido pelo usuário.")
    finally:
        recognizer.stop_continuous_recognition_async()
        receiver_thread.join()

    print("Resultados reconhecidos:")
    for text in callbacks.recognition_results:
        print(f"-> {text}")

if __name__ == "__main__":
    main()
