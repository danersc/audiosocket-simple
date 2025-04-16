#!/usr/bin/env python3
# microfone_client.py - Cliente que captura áudio do microfone e envia para o AudioSocket

import socket
import struct
import threading
import time
import sys
import os
import pyaudio
import argparse
import logging
import collections
from dotenv import load_dotenv
import uuid

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("microfone_client.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Definição dos tipos de mensagem do AudioSocket
KIND_HANGUP = 0x00
KIND_ID = 0x01
KIND_SILENCE = 0x02
KIND_SLIN = 0x10
KIND_ERROR = 0xff

class AudioSocketClient:
    def __init__(self, host='127.0.0.1', port=8080):
        """
        Inicializa o cliente AudioSocket.
        
        Args:
            host: Endereço do servidor AudioSocket
            port: Porta do servidor AudioSocket
        """
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.running = False
        self.call_id = uuid.uuid4().bytes  # Gera um UUID aleatório para o call_id
        self.audio_thread = None
        self.receive_thread = None
        
        # Configurações de áudio
        self.sample_rate = 8000  # Taxa de amostragem em Hz
        self.chunk_size = 320    # Tamanho do chunk em bytes (8000Hz * 20ms * 2 bytes por amostra)
        self.channels = 1        # Mono
        self.format = pyaudio.paInt16  # 16 bits por amostra
        
        # Configurações do buffer para reprodução mais suave
        self.buffer_ms = 120     # Tamanho do buffer em milissegundos (120ms = 0.12s)
        self.buffer_chunks = int(self.buffer_ms / 20)  # Quantidade de chunks para bufferizar (20ms por chunk)
        self.min_buffer_size = self.chunk_size * self.buffer_chunks  # Tamanho mínimo do buffer em bytes
    
    def connect(self):
        """Conecta ao servidor AudioSocket."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Envia mensagem KIND_ID (ID da chamada)
            call_id_msg = struct.pack('>B H', KIND_ID, len(self.call_id)) + self.call_id
            self.socket.sendall(call_id_msg)
            
            logger.info(f"Conectado ao servidor AudioSocket em {self.host}:{self.port}")
            logger.info(f"ID da chamada: {self.call_id.hex()}")
            return True
        except Exception as e:
            logger.error(f"Erro ao conectar ao servidor AudioSocket: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Desconecta do servidor AudioSocket."""
        if self.connected and self.socket:
            try:
                # Envia mensagem KIND_HANGUP
                hangup_msg = struct.pack('>B H', KIND_HANGUP, 0)
                self.socket.sendall(hangup_msg)
                
                # Fecha o socket
                self.socket.close()
                self.socket = None
                self.connected = False
                logger.info("Desconectado do servidor AudioSocket")
                return True
            except Exception as e:
                logger.error(f"Erro ao desconectar do servidor AudioSocket: {e}")
                self.socket = None
                self.connected = False
                return False
    
    def start_streaming(self):
        """Inicia a captura e transmissão de áudio."""
        if not self.connected:
            logger.error("Não conectado ao servidor AudioSocket")
            return False
        
        if self.running:
            logger.warning("Streaming já está em execução")
            return True
        
        self.running = True
        
        # Inicia thread de captura e envio de áudio
        self.audio_thread = threading.Thread(target=self._audio_capture_thread)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        # Inicia thread de recebimento de áudio
        self.receive_thread = threading.Thread(target=self._audio_receive_thread)
        self.receive_thread.daemon = True
        self.receive_thread.start()
        
        logger.info("Streaming de áudio iniciado")
        return True
    
    def stop_streaming(self):
        """Para a captura e transmissão de áudio."""
        if not self.running:
            return
        
        self.running = False
        
        # Aguarda as threads terminarem
        if self.audio_thread:
            self.audio_thread.join(timeout=2.0)
            self.audio_thread = None
        
        if self.receive_thread:
            self.receive_thread.join(timeout=2.0)
            self.receive_thread = None
        
        logger.info("Streaming de áudio finalizado")
    
    def _audio_capture_thread(self):
        """Thread de captura e envio de áudio."""
        try:
            # Inicializa o PyAudio
            audio = pyaudio.PyAudio()
            
            # Lista dispositivos de entrada disponíveis
            info = "\nDispositivos de entrada disponíveis:\n"
            for i in range(audio.get_device_count()):
                dev_info = audio.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:
                    info += f"[{i}] {dev_info['name']}\n"
            logger.info(info)
            
            # Abre o stream de áudio com o dispositivo padrão
            stream = audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size // 2  # Frames em amostras, não bytes
            )
            
            logger.info("Captura de áudio iniciada. Falando para o sistema...")
            
            # Loop de captura e envio de áudio
            while self.running and self.connected:
                try:
                    # Lê um chunk de áudio
                    audio_data = stream.read(self.chunk_size // 2, exception_on_overflow=False)
                    
                    if not audio_data:
                        continue
                    
                    # Envia o chunk para o servidor
                    if len(audio_data) > 0:
                        # Cria a mensagem KIND_SLIN
                        slin_msg = struct.pack('>B H', KIND_SLIN, len(audio_data)) + audio_data
                        
                        # Envia a mensagem
                        self.socket.sendall(slin_msg)
                except socket.error as e:
                    logger.error(f"Erro de socket ao enviar áudio: {e}")
                    self.connected = False
                    break
                except Exception as e:
                    logger.error(f"Erro ao capturar ou enviar áudio: {e}")
            
            # Fecha o stream de áudio
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            logger.info("Thread de captura de áudio finalizada")
            
        except Exception as e:
            logger.error(f"Erro fatal na thread de captura de áudio: {e}")
            self.running = False
    
    def _audio_receive_thread(self):
        """Thread de recebimento de áudio."""
        try:
            # Inicializa o PyAudio para reprodução
            audio = pyaudio.PyAudio()
            
            # Abre o stream para reprodução
            stream = audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk_size // 2
            )
            
            # Configura o socket como não bloqueante
            self.socket.setblocking(False)
            
            # Buffer para acumular fragmentos de mensagens
            network_buffer = b''
            
            # Buffer circular para suavizar a reprodução de áudio
            audio_buffer = collections.deque(maxlen=20)  # Máximo de 20 chunks
            
            # Flag para controlar o início da reprodução depois de bufferizar
            playback_started = False
            
            logger.info(f"Thread de recebimento de áudio iniciada (buffer: {self.buffer_ms}ms)")
            
            # Loop de recebimento de áudio
            while self.running and self.connected:
                try:
                    # Tenta receber dados do socket
                    data = self.socket.recv(4096)
                    
                    if not data:
                        # Conexão fechada pelo servidor
                        logger.warning("Conexão fechada pelo servidor")
                        self.connected = False
                        break
                    
                    # Adiciona os dados ao buffer
                    network_buffer += data
                    
                    # Processa mensagens completas no buffer
                    while len(network_buffer) >= 3:  # Tamanho mínimo do cabeçalho
                        # Extrai o tipo e o comprimento da mensagem
                        kind = network_buffer[0]
                        length = struct.unpack('>H', network_buffer[1:3])[0]
                        
                        # Verifica se temos a mensagem completa
                        if len(network_buffer) < 3 + length:
                            break
                        
                        # Extrai o payload
                        payload = network_buffer[3:3+length]
                        
                        # Processa a mensagem
                        if kind == KIND_SLIN:
                            # Adiciona o áudio ao buffer circular
                            audio_buffer.append(payload)
                            
                            # Verifica se o buffer inicial está completo
                            if not playback_started and len(audio_buffer) >= self.buffer_chunks:
                                logger.info(f"Buffer inicial preenchido ({len(audio_buffer)} chunks), iniciando reprodução")
                                playback_started = True
                            
                            # Reproduz o áudio do buffer se o playback já foi iniciado
                            if playback_started and audio_buffer:
                                # Reproduz o chunk mais antigo do buffer
                                chunk_to_play = audio_buffer.popleft()
                                stream.write(chunk_to_play)
                                sys.stdout.write('.')
                                sys.stdout.flush()
                        elif kind == KIND_HANGUP:
                            logger.info("Recebido sinal de desconexão do servidor")
                            self.connected = False
                            break
                        
                        # Remove a mensagem processada do buffer
                        network_buffer = network_buffer[3+length:]
                
                except BlockingIOError:
                    # Sem dados disponíveis no momento
                    
                    # Continua a reprodução do buffer mesmo sem novos dados
                    if playback_started and audio_buffer:
                        chunk_to_play = audio_buffer.popleft()
                        stream.write(chunk_to_play)
                        sys.stdout.write('-')  # Indicador diferente quando estamos consumindo do buffer
                        sys.stdout.flush()
                    
                    time.sleep(0.01)
                    continue
                except socket.error as e:
                    logger.error(f"Erro de socket ao receber áudio: {e}")
                    self.connected = False
                    break
                except Exception as e:
                    logger.error(f"Erro ao receber ou reproduzir áudio: {e}")
            
            # Reproduz o restante do buffer antes de fechar
            logger.info(f"Reproduzindo {len(audio_buffer)} chunks restantes no buffer")
            while audio_buffer:
                chunk_to_play = audio_buffer.popleft()
                stream.write(chunk_to_play)
            
            # Fecha o stream de áudio
            stream.stop_stream()
            stream.close()
            audio.terminate()
            
            logger.info("Thread de recebimento de áudio finalizada")
            
        except Exception as e:
            logger.error(f"Erro fatal na thread de recebimento de áudio: {e}")
            self.running = False

def main():
    """Função principal."""
    parser = argparse.ArgumentParser(description="Cliente AudioSocket para captura de microfone")
    parser.add_argument('--host', default='127.0.0.1', help='Endereço do servidor AudioSocket')
    parser.add_argument('--port', type=int, default=8080, help='Porta do servidor AudioSocket')
    parser.add_argument('--buffer', type=int, default=120, help='Tamanho do buffer de áudio em milissegundos (padrão: 120ms)')
    args = parser.parse_args()
    
    print("=== Cliente AudioSocket para Microfone ===")
    print(f"Conectando ao servidor em {args.host}:{args.port}...")
    
    # Cria e conecta o cliente
    client = AudioSocketClient(host=args.host, port=args.port)
    
    # Configura o tamanho do buffer de áudio
    client.buffer_ms = args.buffer
    client.buffer_chunks = max(1, int(client.buffer_ms / 20))  # No mínimo 1 chunk
    client.min_buffer_size = client.chunk_size * client.buffer_chunks
    print(f"Tamanho do buffer configurado: {client.buffer_ms}ms ({client.buffer_chunks} chunks)")
    
    
    if not client.connect():
        print("Falha ao conectar ao servidor. Verifique se o servidor está em execução.")
        return
    
    print("Conectado ao servidor!")
    print("Iniciando captura de áudio do microfone...")
    
    # Inicia o streaming de áudio
    client.start_streaming()
    
    try:
        # Mantém o programa em execução até Ctrl+C
        print("\nCapturando áudio do microfone. Pressione Ctrl+C para sair...")
        print("A captura de áudio está em andamento. Fale no microfone!")
        print("Os pontos (.) indicam áudio recebido do servidor...")
        
        while client.running and client.connected:
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    finally:
        # Limpa e desconecta
        print("Finalizando...")
        client.stop_streaming()
        client.disconnect()
        print("Conexão finalizada.")

if __name__ == "__main__":
    main()