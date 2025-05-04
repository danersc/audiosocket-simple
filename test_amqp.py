#!/usr/bin/env python3
import pika
import logging
import time
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_rabbitmq_connection():
    """
    Testa a conexão com o servidor RabbitMQ.
    """
    rabbit_host = 'mqdev.tecnofy.com.br'
    rabbit_user = 'fonia'
    rabbit_password = 'fonia123'
    rabbit_vhost = 'voip'
    queue_name = 'api-to-voip1'
    
    logger.info(f"Testando conexão com: host={rabbit_host}, vhost={rabbit_vhost}, user={rabbit_user}")
    
    try:
        # Configurar parâmetros de conexão
        credentials = pika.PlainCredentials(rabbit_user, rabbit_password)
        parameters = pika.ConnectionParameters(
            host=rabbit_host,
            virtual_host=rabbit_vhost,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=2,
            socket_timeout=10,
            blocked_connection_timeout=5
        )
        
        # Tentar estabelecer conexão
        logger.info(f"Tentando conectar a {rabbit_host}...")
        connection = pika.BlockingConnection(parameters)
        logger.info("Conexão estabelecida com sucesso!")
        
        # Criar canal
        logger.info("Criando canal...")
        channel = connection.channel()
        logger.info("Canal criado com sucesso!")
        
        # Declarar fila (com verificação)
        logger.info(f"Declarando fila '{queue_name}'...")
        queue_result = channel.queue_declare(queue=queue_name, durable=True)
        logger.info(f"Fila declarada - mensagens atuais: {queue_result.method.message_count}")
        
        # Testar envio de mensagem
        logger.info("Preparando mensagem de teste...")
        test_payload = {
            "data": {
                "destiny": "IA",
                "guid": "test-guid-12345",
                "license": "123456789012",
                "origin": "1003030"
            },
            "operation": {
                "eventcode": "8001",
                "guid": "cmd-test-guid-12345",
                "msg": "TESTE - IGNORE",
                "timestamp": int(time.time()),
                "type": "clicktocall"
            }
        }
        
        # Serializar payload
        import json
        payload_json = json.dumps(test_payload)
        logger.info(f"Payload serializado com sucesso: {payload_json[:100]}...")
        
        # Enviar mensagem
        logger.info(f"Enviando mensagem para fila '{queue_name}'...")
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=payload_json,
            properties=pika.BasicProperties(
                delivery_mode=2,  # torna a mensagem persistente
                content_type='application/json'
            )
        )
        logger.info("Mensagem enviada com sucesso!")
        
        # Fechar conexão
        logger.info("Fechando canal e conexão...")
        channel.close()
        connection.close()
        logger.info("Conexão fechada com sucesso!")
        
        return True
        
    except pika.exceptions.AMQPConnectionError as e:
        logger.error(f"Erro de conexão ao servidor RabbitMQ: {e}")
        return False
    except pika.exceptions.ChannelError as e:
        logger.error(f"Erro no canal RabbitMQ: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado: {e}")
        return False

if __name__ == "__main__":
    print("Iniciando teste de conexão AMQP...")
    success = test_rabbitmq_connection()
    if success:
        print("✅ Teste concluído com sucesso!")
        sys.exit(0)
    else:
        print("❌ Teste falhou - verifique os logs para detalhes.")
        sys.exit(1)