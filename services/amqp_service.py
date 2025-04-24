
import pika
import json
import logging
import time

def enviar_msg_autorizacao_morador(payload):
    """
    Envia uma mensagem para a fila de autorização via AMQP.
    
    Esta função é chamada quando um morador autoriza ou nega a entrada
    de um visitante e precisa comunicar essa decisão ao sistema de controle
    de acesso físico.
    """
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()

        channel.queue_declare(queue='fila_autorizacao')

        # Adicionar timestamp para rastreabilidade
        payload['timestamp'] = int(time.time())
        
        channel.basic_publish(
            exchange='',
            routing_key='fila_autorizacao',
            body=json.dumps(payload)
        )

        logging.info(f"Mensagem AMQP enviada para fila_autorizacao: {payload}")
        connection.close()
        return True
    except Exception as e:
        logging.error(f"Erro ao enviar mensagem AMQP: {e}")
        return False
