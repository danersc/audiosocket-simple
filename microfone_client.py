#!/usr/bin/env python3
import socket, struct, threading, pyaudio, logging, uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

KIND_ID, KIND_SLIN, KIND_HANGUP = 0x01, 0x10, 0x00

class AudioSocketClient:
    def __init__(self, host='18.231.197.181', port=8080):
        self.host, self.port = host, port
        self.call_id = uuid.uuid4().bytes
        self.sample_rate, self.channels, self.chunk_size = 8000, 1, 320
        self.format = pyaudio.paInt16
        self.running = False

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.socket.sendall(struct.pack('>B H', KIND_ID, len(self.call_id)) + self.call_id)
        logging.info("Conectado ao servidor.")
        self.running = True
        threading.Thread(target=self.send_audio).start()
        threading.Thread(target=self.receive_audio).start()

    def send_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=self.format, channels=self.channels, rate=self.sample_rate, input=True, frames_per_buffer=self.chunk_size//2)
        try:
            while self.running:
                data = stream.read(self.chunk_size//2, exception_on_overflow=False)
                self.socket.sendall(struct.pack('>B H', KIND_SLIN, len(data)) + data)
        except Exception as e:
            logging.error(f"Erro no envio de áudio: {e}")
            self.running = False
        stream.stop_stream()
        stream.close()
        p.terminate()

    def receive_audio(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=self.format, channels=self.channels, rate=self.sample_rate, output=True)
        try:
            while self.running:
                header = self.socket.recv(3)
                if not header: break
                kind, length = header[0], struct.unpack('>H', header[1:3])[0]
                payload = self.socket.recv(length)
                if kind == KIND_SLIN:
                    stream.write(payload)
        except Exception as e:
            logging.error(f"Erro no recebimento de áudio: {e}")
            self.running = False
        stream.stop_stream()
        stream.close()
        p.terminate()

    def disconnect(self):
        self.running = False
        self.socket.sendall(struct.pack('>B H', KIND_HANGUP, 0))
        self.socket.close()
        logging.info("Desconectado do servidor.")

if __name__ == "__main__":
    client = AudioSocketClient()
    try:
        client.connect()
        while client.running: pass
    except KeyboardInterrupt:
        client.disconnect()
