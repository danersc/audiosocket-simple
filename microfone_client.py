#!/usr/bin/env python3
import socket, struct, threading, pyaudio, logging, time
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

KIND_ID, KIND_SLIN, KIND_HANGUP = 0x01, 0x10, 0x00

class AudioSocketClient:
    def __init__(self, host='127.0.0.1', port=8080):  # Mudando para localhost
        self.host, self.port = host, port
        # Gerando UUID para identificação da chamada
        self.call_id = uuid.uuid4().bytes
        self.sample_rate, self.channels, self.chunk_size = 8000, 1, 320
        self.format = pyaudio.paInt16
        self.running = False
        
        # Socket reconfigurado para melhor performance
        self.socket_buffer_size = 1024 * 16  # 16KB de buffer

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Configurar buffer de socket
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.socket_buffer_size)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.socket_buffer_size)
        
        # Configurar timeout para operações de socket
        self.socket.settimeout(2.0)  # 2 segundos de timeout
        
        # Opções avançadas para TCP
        # Desabilitar algoritmo de Nagle para reduzir latência
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        logging.info(f"Tentando conectar a {self.host}:{self.port}...")
        self.socket.connect((self.host, self.port))
        
        # Remover timeout após conexão estabelecida
        self.socket.settimeout(None)
        
        # Enviar ID da chamada
        logging.info(f"Enviando ID da chamada: {self.call_id.hex()}")
        self.socket.sendall(struct.pack('>B H', KIND_ID, len(self.call_id)) + self.call_id)
        
        logging.info("Conectado ao servidor! Iniciando transmissão de áudio...")
        self.running = True
        
        # Iniciar threads para envio e recebimento de áudio
        self.send_thread = threading.Thread(target=self.send_audio, name="SendAudio")
        self.send_thread.daemon = True
        self.send_thread.start()
        
        self.receive_thread = threading.Thread(target=self.receive_audio, name="ReceiveAudio")
        self.receive_thread.daemon = True
        self.receive_thread.start()

    def send_audio(self):
        p = pyaudio.PyAudio()
        # Configurar buffer de áudio maior
        stream = p.open(format=self.format, channels=self.channels, rate=self.sample_rate, 
                       input=True, frames_per_buffer=self.chunk_size//2)
        try:
            while self.running:
                data = stream.read(self.chunk_size//2, exception_on_overflow=False)
                self.socket.sendall(struct.pack('>B H', KIND_SLIN, len(data)) + data)
                # Adicionar pequeno delay para evitar sobrecarga de pacotes
                time.sleep(0.02)  # 20ms de delay entre pacotes
        except Exception as e:
            logging.error(f"Erro no envio de áudio: {e}")
            self.running = False
        stream.stop_stream()
        stream.close()
        p.terminate()

    def receive_audio(self):
        p = pyaudio.PyAudio()
        # Configurar buffer de áudio maior para melhor qualidade de reprodução
        stream = p.open(format=self.format, channels=self.channels, rate=self.sample_rate, 
                       output=True, frames_per_buffer=1024, 
                       # Adicionar parâmetros para melhorar a qualidade do áudio
                       output_device_index=None,  # Usar dispositivo padrão
                       start=True)  # Começar imediatamente
        last_audio_time = 0
        audio_count = 0
        audio_buffer = []  # Buffer para acumular pacotes antes de reproduzir
        
        try:
            while self.running:
                header = self.socket.recv(3)
                if not header: 
                    logging.warning("Recebido header vazio, encerrando conexão...")
                    break
                    
                kind, length = header[0], struct.unpack('>H', header[1:3])[0]
                payload = self.socket.recv(length)
                
                if kind == KIND_SLIN:
                    # Acumular pacotes no buffer para reprodução mais suave
                    audio_buffer.append(payload)
                    
                    # Quando tivermos alguns pacotes acumulados, reproduzir tudo de uma vez
                    if len(audio_buffer) >= 2:  # Ajuste este valor conforme necessário
                        combined_payload = b''.join(audio_buffer)
                        stream.write(combined_payload)
                        audio_buffer = []  # Limpar buffer após reprodução
                    
                    audio_count += 1
                    
                    # A cada 50 pacotes de áudio, mostramos um indicador
                    if audio_count % 50 == 0:
                        current_time = time.time()
                        if last_audio_time > 0:
                            rate = 50 / (current_time - last_audio_time)
                            logging.info(f"Recebendo áudio: {rate:.1f} pacotes/s")
                        last_audio_time = current_time
                else:
                    logging.debug(f"Recebido pacote não-SLIN: kind={kind}, length={length}")
                    
        except ConnectionResetError:
            logging.error("Conexão fechada pelo servidor")
            self.running = False
        except Exception as e:
            logging.error(f"Erro no recebimento de áudio: {e}")
            self.running = False
            
        logging.info("Thread de recebimento encerrada")
        stream.stop_stream()
        stream.close()
        p.terminate()

    def disconnect(self):
        self.running = False
        try:
            # Verificar se o socket está conectado antes de tentar enviar dados
            if hasattr(self, 'socket') and self.socket:
                try:
                    self.socket.sendall(struct.pack('>B H', KIND_HANGUP, 0))
                except (OSError, BrokenPipeError) as e:
                    logging.warning(f"Não foi possível enviar comando de hangup: {e}")
                
                try:
                    self.socket.close()
                except Exception as e:
                    logging.warning(f"Erro ao fechar socket: {e}")
                    
            logging.info("Desconectado do servidor.")
        except Exception as e:
            logging.error(f"Erro durante a desconexão: {e}")

if __name__ == "__main__":
    import argparse
    
    # Adicionar opções de linha de comando
    parser = argparse.ArgumentParser(description='Cliente de microfone para AudioSocket')
    parser.add_argument('--host', default='127.0.0.1', help='Endereço do servidor (padrão: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8080, help='Porta do servidor (padrão: 8101)')
    args = parser.parse_args()
    
    # Usar os valores fornecidos pelo usuário ou os padrões
    logging.info(f"Conectando ao servidor {args.host}:{args.port}")
    client = AudioSocketClient(host=args.host, port=args.port)
    
    try:
        client.connect()
        logging.info("Pressione Ctrl+C para encerrar")
        
        # Loop para manter o programa em execução
        while client.running:
            import time
            time.sleep(0.1)  # Pequeno delay para não consumir CPU
            
    except KeyboardInterrupt:
        logging.info("Encerrando conexão...")
    except ConnectionRefusedError:
        logging.error(f"Não foi possível conectar ao servidor {args.host}:{args.port}")
        logging.error("Verifique se o servidor está em execução")
    except Exception as e:
        logging.error(f"Erro: {e}")
    finally:
        if client.running:
            client.disconnect()
