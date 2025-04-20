import asyncio
import logging
from dotenv import load_dotenv
from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador
logging.basicConfig(level=logging.INFO)

load_dotenv()

async def main():
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
