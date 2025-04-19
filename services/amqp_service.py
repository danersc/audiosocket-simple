
import pika
import json
import logging

def enviar_msg_autorizacao_morador(payload):
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()

    channel.queue_declare(queue='fila_autorizacao')

    channel.basic_publish(
        exchange='',
        routing_key='fila_autorizacao',
        body=json.dumps(payload)
    )

    logging.info(f"Mensagem AMQP enviada: {payload}")
    connection.close()
