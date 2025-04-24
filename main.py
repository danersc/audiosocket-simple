import asyncio
import logging
import os
from dotenv import load_dotenv
from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador
from speech_service import pre_sintetizar_frases_comuns

logging.basicConfig(level=logging.INFO)

load_dotenv()

# Inicializar diretório de logs se não existir
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

async def main():
    # Pré-sintetizar frases comuns para reduzir latência
    logging.info("Pré-sintetizando frases comuns...")
    pre_sintetizar_frases_comuns()
    
    server_visitante = await asyncio.start_server(iniciar_servidor_audiosocket_visitante, '0.0.0.0', 8080)
    server_morador = await asyncio.start_server(iniciar_servidor_audiosocket_morador, '0.0.0.0', 8081)

    logging.info("Servidor visitante: 0.0.0.0:8080")
    logging.info("Servidor morador:   0.0.0.0:8081")

    async with server_visitante, server_morador:
        await asyncio.gather(
            server_visitante.serve_forever(),
            server_morador.serve_forever()
        )

if __name__ == "__main__":
    asyncio.run(main())
