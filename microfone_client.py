#!/usr/bin/env python3
import socket, struct, threading, pyaudio, logging, time
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

KIND_ID, KIND_SLIN, KIND_HANGUP = 0x01, 0x10, 0x00

class AudioSocketClient:
    def __init__(self, host='127.0.0.1', port=8080):
        self.host, self.port = host, port
        # Gerando UUID para identificação da chamada
        self.call_id = uuid.uuid4().bytes
        self.sample_rate, self.channels, self.chunk_size = 8000, 1, 320
        self.format = pyaudio.paInt16
        self.running = False
        
        # Socket reconfigurado para melhor performance
        self.socket_buffer_size = 1024 * 16  # 16KB de buffer

    def connect(self):
        try:
            # Criar socket com tratamento de erros
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                logging.info("Socket criado com sucesso")
            except socket.error as e:
                logging.error(f"Erro ao criar socket: {e}")
                raise
            
            # Configurar buffer de socket
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.socket_buffer_size)
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.socket_buffer_size)
                
                # Configurar timeout para operações de socket
                self.socket.settimeout(5.0)  # 5 segundos de timeout para conexão inicial
                
                # Opções avançadas para TCP
                # Desabilitar algoritmo de Nagle para reduzir latência
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # Permitir reutilização de endereço local
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                
                # Em sistemas que suportam, configurar TCP keepalive
                if hasattr(socket, 'SO_KEEPALIVE'):
                    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                # Em macOS/Linux, configurar tempo de TCP keepalive se disponível
                if hasattr(socket, 'TCP_KEEPIDLE'):
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)  # 60 segundos
                
                logging.info("Socket configurado com opções avançadas")
            except Exception as e:
                logging.warning(f"Erro ao configurar opções de socket (não fatal): {e}")
            
            # Tentar estabelecer conexão com retry
            max_retries = 3
            retry_count = 0
            retry_delay = 1.0  # segundos
            
            while retry_count < max_retries:
                try:
                    logging.info(f"Tentando conectar a {self.host}:{self.port} (tentativa {retry_count+1}/{max_retries})...")
                    self.socket.connect((self.host, self.port))
                    logging.info(f"Conexão estabelecida com {self.host}:{self.port}")
                    break
                except socket.timeout:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logging.error(f"Timeout ao conectar após {max_retries} tentativas")
                        raise ConnectionError(f"Não foi possível conectar a {self.host}:{self.port} após {max_retries} tentativas")
                    logging.warning(f"Timeout ao conectar. Tentando novamente em {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Aumentar o delay exponencialmente
                except ConnectionRefusedError:
                    logging.error(f"Conexão recusada por {self.host}:{self.port}. O servidor está em execução?")
                    raise
                except Exception as e:
                    logging.error(f"Erro ao conectar: {e}")
                    raise
            
            # Ajustar timeout para operações após conexão estabelecida
            self.socket.settimeout(2.0)  # 2 segundos para operações normais
            
            # Enviar ID da chamada com retry em caso de falha
            try:
                logging.info(f"Enviando ID da chamada: {self.call_id.hex()}")
                packet = struct.pack('>B H', KIND_ID, len(self.call_id)) + self.call_id
                bytes_sent = self.socket.send(packet)
                
                if bytes_sent != len(packet):
                    logging.warning(f"Pacote ID enviado parcialmente: {bytes_sent}/{len(packet)} bytes")
                    # Tentar enviar o restante
                    remaining = packet[bytes_sent:]
                    self.socket.sendall(remaining)
                
                logging.info("ID da chamada enviado com sucesso")
            except Exception as e:
                logging.error(f"Erro ao enviar ID da chamada: {e}")
                self.socket.close()
                raise
            
            # Configurar estado e iniciar threads
            self.running = True
            logging.info("Conexão estabelecida! Iniciando transmissão de áudio...")
            
            # Iniciar threads para envio e recebimento de áudio
            try:
                self.send_thread = threading.Thread(target=self.send_audio, name="SendAudio")
                self.send_thread.daemon = True
                self.send_thread.start()
                
                self.receive_thread = threading.Thread(target=self.receive_audio, name="ReceiveAudio")
                self.receive_thread.daemon = True
                self.receive_thread.start()
                
                logging.info("Threads de áudio iniciadas com sucesso")
            except Exception as e:
                logging.error(f"Erro ao iniciar threads de áudio: {e}")
                self.running = False
                self.socket.close()
                raise
                
        except Exception as e:
            logging.error(f"Erro na conexão: {e}")
            self.running = False
            if hasattr(self, 'socket') and self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            raise

    def send_audio(self):
        try:
            # Envolva a inicialização do PyAudio em um bloco try/except
            p = pyaudio.PyAudio()
            
            # Verificar dispositivos de entrada disponíveis
            info = p.get_host_api_info_by_index(0)
            input_devices = []
            
            for i in range(info.get('deviceCount')):
                device_info = p.get_device_info_by_host_api_device_index(0, i)
                if device_info.get('maxInputChannels') > 0:
                    input_devices.append((i, device_info.get('name')))
            
            if input_devices:
                logging.info(f"Dispositivos de entrada disponíveis:")
                for idx, name in input_devices:
                    logging.info(f"  [{idx}] {name}")
                
                # Usar o primeiro dispositivo de entrada disponível
                input_device_idx = input_devices[0][0]
                logging.info(f"Usando dispositivo de entrada: [{input_device_idx}] {input_devices[0][1]}")
            else:
                input_device_idx = None
                logging.warning("Nenhum dispositivo de entrada encontrado! Verifique seu microfone.")
            
            # Configurar buffer de áudio maior com parâmetros mais seguros
            stream = p.open(format=self.format, 
                          channels=self.channels, 
                          rate=self.sample_rate, 
                          input=True, 
                          input_device_index=input_device_idx,
                          frames_per_buffer=self.chunk_size,
                          start=True)
            
            logging.info("Stream de áudio iniciado com sucesso")
            
            try:
                while self.running:
                    try:
                        # Usar exception_on_overflow=False para evitar erros em caso de sobrecarga
                        data = stream.read(self.chunk_size, exception_on_overflow=False)
                        if data and len(data) == self.chunk_size * 2:  # 2 bytes por amostra (16 bits)
                            # Garantir que o tamanho do chunk esteja correto (320 bytes)
                            # O audiosocket_handler.py espera exatamente 320 bytes para processar corretamente
                            if len(data) != 640:
                                logging.warning(f"Tamanho de chunk inesperado: {len(data)} bytes, esperado 640 bytes")
                                # Padding ou truncamento para garantir 640 bytes exatos
                                if len(data) < 640:
                                    # Adicionar padding se menor
                                    data = data + b'\x00' * (640 - len(data))
                                else:
                                    # Truncar se maior
                                    data = data[:640]
                                
                            self.socket.sendall(struct.pack('>B H', KIND_SLIN, 640) + data)
                        # Adicionar pequeno delay para evitar sobrecarga de pacotes
                        time.sleep(0.02)  # 20ms de delay entre pacotes
                    except OSError as e:
                        # Captura especificamente erros de E/S que podem ocorrer durante a leitura
                        logging.error(f"Erro de E/S durante a leitura do áudio: {e}")
                        time.sleep(0.1)  # Pequena pausa para evitar loop rápido em caso de erro
            except Exception as e:
                logging.error(f"Erro no loop de envio de áudio: {e}")
            finally:
                logging.info("Fechando stream de entrada")
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception as e:
                    logging.error(f"Erro ao fechar stream de entrada: {e}")
        except Exception as e:
            logging.error(f"Erro ao inicializar PyAudio para captura: {e}")
        finally:
            self.running = False
            try:
                p.terminate()
            except:
                pass
            logging.info("Thread de envio de áudio encerrada")

    def receive_audio(self):
        try:
            # Inicializar PyAudio de forma segura
            p = pyaudio.PyAudio()
            
            # Verificar dispositivos de saída disponíveis
            info = p.get_host_api_info_by_index(0)
            output_devices = []
            
            for i in range(info.get('deviceCount')):
                device_info = p.get_device_info_by_host_api_device_index(0, i)
                if device_info.get('maxOutputChannels') > 0:
                    output_devices.append((i, device_info.get('name')))
            
            if output_devices:
                logging.info(f"Dispositivos de saída disponíveis:")
                for idx, name in output_devices:
                    logging.info(f"  [{idx}] {name}")
                
                # Usar o primeiro dispositivo de saída disponível
                output_device_idx = output_devices[0][0]
                logging.info(f"Usando dispositivo de saída: [{output_device_idx}] {output_devices[0][1]}")
            else:
                output_device_idx = None
                logging.warning("Nenhum dispositivo de saída encontrado! Verifique sua configuração de áudio.")
            
            # Configurar buffer de áudio maior para melhor qualidade de reprodução
            # Usando try/except para capturar erros específicos de inicialização de stream
            try:
                stream = p.open(format=self.format, 
                              channels=self.channels, 
                              rate=self.sample_rate, 
                              output=True, 
                              output_device_index=output_device_idx,
                              frames_per_buffer=1024,
                              start=True)  # Começar imediatamente
                logging.info("Stream de saída de áudio iniciado com sucesso")
            except Exception as e:
                logging.error(f"Erro ao inicializar o stream de saída: {e}")
                raise  # Re-lançar para ser capturado pelo bloco try/except externo
            
            last_audio_time = 0
            audio_count = 0
            audio_buffer = []  # Buffer para acumular pacotes antes de reproduzir
            buffer_size = 3  # Número de pacotes a acumular antes de reproduzir (ajustável)
            max_buffer_size = 10  # Limite máximo para evitar atrasos muito grandes
            
            # Configurar timeout para recepção de socket para evitar bloqueio indefinido
            self.socket.settimeout(0.5)  # 500ms timeout
            
            empty_packet_count = 0
            max_empty_packets = 10  # Número máximo de pacotes vazios antes de considerar desconexão
            
            try:
                while self.running:
                    try:
                        header = self.socket.recv(3)
                        if not header or len(header) < 3: 
                            empty_packet_count += 1
                            logging.warning(f"Recebido header incompleto ({empty_packet_count}/{max_empty_packets})")
                            
                            if empty_packet_count >= max_empty_packets:
                                logging.warning("Muitos pacotes vazios recebidos, encerrando conexão...")
                                break
                                
                            # Pequena pausa para evitar loop rápido
                            time.sleep(0.1)
                            continue
                        
                        # Resetar contador de pacotes vazios
                        empty_packet_count = 0
                            
                        kind, length = header[0], struct.unpack('>H', header[1:3])[0]
                        
                        # Verificação de segurança para tamanho de pacote
                        if length > 16384:  # Limitar a 16KB por pacote
                            logging.warning(f"Tamanho de pacote suspeito: {length} bytes, ignorando")
                            continue
                        
                        # Usar timeout para evitar bloqueio na recepção de payload
                        self.socket.settimeout(0.2)  # 200ms timeout para receber payload
                        payload = self.socket.recv(length)
                        self.socket.settimeout(0.5)  # Restaurar timeout normal
                        
                        if kind == KIND_SLIN:
                            # Verificar se o payload tem o tamanho esperado
                            if len(payload) != length:
                                logging.warning(f"Payload incompleto: esperado {length}, recebido {len(payload)}")
                                continue
                                
                            # Acumular pacotes no buffer para reprodução mais suave
                            audio_buffer.append(payload)
                            
                            # Ajuste dinâmico do tamanho do buffer baseado em condições
                            # Se estivermos recebendo pacotes muito rapidamente, aumentar o buffer
                            if last_audio_time > 0:
                                time_diff = time.time() - last_audio_time
                                if time_diff < 0.01 and buffer_size < max_buffer_size:  # Pacotes chegando muito rápido
                                    buffer_size += 1
                                elif time_diff > 0.05 and buffer_size > 2:  # Pacotes chegando com atraso
                                    buffer_size -= 1
                            
                            # Quando tivermos pacotes suficientes acumulados ou buffer muito grande, reproduzir
                            if len(audio_buffer) >= buffer_size or len(audio_buffer) >= max_buffer_size:
                                try:
                                    combined_payload = b''.join(audio_buffer)
                                    stream.write(combined_payload, exception_on_underflow=False)
                                    audio_buffer = []  # Limpar buffer após reprodução
                                except Exception as e:
                                    logging.error(f"Erro ao reproduzir áudio: {e}")
                                    # Limpar buffer em caso de erro para evitar acúmulo
                                    audio_buffer = []
                            
                            audio_count += 1
                            
                            # A cada 50 pacotes de áudio, mostramos um indicador
                            if audio_count % 50 == 0:
                                current_time = time.time()
                                if last_audio_time > 0:
                                    rate = 50 / (current_time - last_audio_time)
                                    latency = len(audio_buffer) * (self.chunk_size / self.sample_rate)
                                    logging.info(f"Recebendo áudio: {rate:.1f} pacotes/s, buffer={buffer_size}, latência={latency*1000:.1f}ms")
                                last_audio_time = current_time
                        elif kind == KIND_HANGUP:
                            logging.info("Recebido sinal de encerramento (HANGUP)")
                            break
                        else:
                            logging.debug(f"Recebido pacote não-SLIN: kind={kind}, length={length}")
                    
                    except socket.timeout:
                        # Timeout na recepção - normal durante períodos sem áudio
                        # Reproduzir qualquer áudio pendente no buffer para evitar atraso
                        if audio_buffer:
                            try:
                                combined_payload = b''.join(audio_buffer)
                                stream.write(combined_payload, exception_on_underflow=False)
                                audio_buffer = []
                            except Exception as e:
                                logging.error(f"Erro ao reproduzir áudio após timeout: {e}")
                                audio_buffer = []
                    
                    except ConnectionResetError:
                        logging.error("Conexão fechada pelo servidor")
                        break
                        
                    except Exception as e:
                        logging.error(f"Erro durante processamento de pacote: {e}")
                        # Pequena pausa para evitar loop rápido em caso de erro persistente
                        time.sleep(0.1)
                
            except Exception as e:
                logging.error(f"Erro no loop principal de recebimento: {e}")
            
            finally:
                # Reproduzir qualquer áudio restante no buffer
                if audio_buffer:
                    try:
                        combined_payload = b''.join(audio_buffer)
                        stream.write(combined_payload, exception_on_underflow=False)
                    except:
                        pass
                
                # Limpar recursos de áudio
                logging.info("Fechando stream de saída")
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception as e:
                    logging.error(f"Erro ao fechar stream de saída: {e}")
        
        except Exception as e:
            logging.error(f"Erro fatal na inicialização de áudio: {e}")
        
        finally:
            # Sinalizar que a thread está encerrando
            self.running = False
            
            # Limpar recursos de PyAudio
            try:
                p.terminate()
            except Exception as e:
                logging.error(f"Erro ao terminar PyAudio: {e}")
                
            logging.info("Thread de recebimento de áudio encerrada")

    def disconnect(self):
        # Primeiro, marcar como não rodando para as threads pararem
        self.running = False
        logging.info("Iniciando processo de desconexão...")
        
        # Esperar threads encerrarem com timeout
        threads_to_wait = []
        
        if hasattr(self, 'send_thread') and self.send_thread and self.send_thread.is_alive():
            threads_to_wait.append(('send_thread', self.send_thread))
            
        if hasattr(self, 'receive_thread') and self.receive_thread and self.receive_thread.is_alive():
            threads_to_wait.append(('receive_thread', self.receive_thread))
        
        # Aguardar threads encerrarem com timeout
        if threads_to_wait:
            logging.info(f"Aguardando {len(threads_to_wait)} threads encerrarem...")
            for thread_name, thread in threads_to_wait:
                # Aguardar no máximo 3 segundos por thread
                thread.join(timeout=3.0)
                if thread.is_alive():
                    logging.warning(f"Thread {thread_name} não encerrou no tempo esperado")
                else:
                    logging.info(f"Thread {thread_name} encerrada com sucesso")
        
        # Enviar sinal de HANGUP e fechar socket
        try:
            # Verificar se o socket existe e está conectado
            if hasattr(self, 'socket') and self.socket:
                # Configurar timeout curto para operações finais
                try:
                    self.socket.settimeout(1.0)
                except:
                    pass
                
                # Enviar comando de HANGUP
                try:
                    logging.info("Enviando sinal de HANGUP...")
                    self.socket.sendall(struct.pack('>B H', KIND_HANGUP, 0))
                    logging.info("Sinal de HANGUP enviado com sucesso")
                except (OSError, BrokenPipeError, socket.timeout) as e:
                    logging.warning(f"Não foi possível enviar comando de hangup: {e}")
                except Exception as e:
                    logging.warning(f"Erro inesperado ao enviar HANGUP: {e}")
                
                # Encerrar socket
                try:
                    logging.info("Fechando socket...")
                    # Primeiro shutdown para indicar que não haverá mais dados
                    try:
                        self.socket.shutdown(socket.SHUT_RDWR)
                    except:
                        pass
                    
                    # Depois fechar o socket
                    self.socket.close()
                    logging.info("Socket fechado com sucesso")
                except Exception as e:
                    logging.warning(f"Erro ao fechar socket: {e}")
                
                # Limpar referência ao socket
                self.socket = None
                    
            logging.info("Desconexão concluída.")
        except Exception as e:
            logging.error(f"Erro durante a desconexão: {e}")
        
        # Garantir que o estado final é consistente
        self.running = False

if __name__ == "__main__":
    import argparse
    import signal
    
    # Adicionar opções de linha de comando
    parser = argparse.ArgumentParser(description='Cliente de microfone para AudioSocket')
    parser.add_argument('--host', default='127.0.0.1', help='Endereço do servidor (padrão: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8080, help='Porta do servidor (padrão: 8080)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Habilitar logs detalhados')
    parser.add_argument('--quiet', '-q', action='store_true', help='Mostrar apenas logs de erro')
    args = parser.parse_args()
    
    # Configurar nível de log com base nos argumentos
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.info("Modo verbose ativado: logs detalhados habilitados")
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    # Preparar cliente
    client = None
    
    # Handler para sinal de interrupção (Ctrl+C)
    def signal_handler(sig, frame):
        logging.info("Sinal de interrupção recebido. Encerrando...")
        if client and client.running:
            client.disconnect()
        
    # Registrar handler de sinal
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Usar os valores fornecidos pelo usuário ou os padrões
        logging.info(f"Iniciando cliente para servidor {args.host}:{args.port}")
        
        # Inicializar o cliente
        client = AudioSocketClient(host=args.host, port=args.port)
        
        # Tentar conectar ao servidor
        try:
            client.connect()
            logging.info("Conexão estabelecida. Pressione Ctrl+C para encerrar")
        except ConnectionRefusedError:
            logging.error(f"Não foi possível conectar ao servidor {args.host}:{args.port}")
            logging.error("Verifique se o servidor está em execução e a porta está correta")
            exit(1)
        except Exception as e:
            logging.error(f"Erro durante a conexão: {e}")
            exit(1)
        
        # Verificar periodicamente se o cliente ainda está rodando
        # e monitorar saúde da conexão
        monitor_interval = 5.0  # verificar a cada 5 segundos
        last_check_time = time.time()
        
        # Loop principal
        while client.running:
            time.sleep(0.1)  # Pequeno delay para não consumir CPU
            
            # Verificações periódicas
            current_time = time.time()
            if current_time - last_check_time >= monitor_interval:
                if hasattr(client, 'send_thread') and not client.send_thread.is_alive():
                    logging.error("Thread de envio de áudio encerrada inesperadamente!")
                    break
                    
                if hasattr(client, 'receive_thread') and not client.receive_thread.is_alive():
                    logging.error("Thread de recebimento de áudio encerrada inesperadamente!")
                    break
                
                last_check_time = current_time
        
    except KeyboardInterrupt:
        # Este bloco é um fallback - normalmente o signal_handler lidará com Ctrl+C
        logging.info("Interrupção detectada. Encerrando conexão...")
    except Exception as e:
        logging.error(f"Erro inesperado: {e}")
        import traceback
        logging.error(traceback.format_exc())
    finally:
        # Garantir que o cliente se desconecte adequadamente
        if client and client.running:
            try:
                client.disconnect()
            except Exception as e:
                logging.error(f"Erro ao desconectar: {e}")
        
        logging.info("Cliente encerrado. Até mais!")
        
    # Forçar a saída para garantir que não há threads bloqueando
    import os, sys
    try:
        sys.exit(0)
    except SystemExit:
        os._exit(0)
