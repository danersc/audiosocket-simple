
import asyncio
import logging
from dotenv import load_dotenv
from state_machine import StateMachine
from audiosocket_handler import (
    iniciar_servidor_audiosocket_visitante,
    iniciar_servidor_audiosocket_morador
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

async def handle_client_visitante(reader, writer):
    state_machine = StateMachine()
    state_machine.start_new_conversation()

    try:
        header = await reader.readexactly(3)
        kind = header[0]
        length = int.from_bytes(header[1:3], "big")
        call_id = await reader.readexactly(length)

        if kind != 0x01:
            logging.error("Mensagem inicial inválida.")
            writer.close()
            await writer.wait_closed()
            return

        logging.info(f"[VISITANTE] Recebido Call ID: {call_id.hex()}")

        await iniciar_servidor_audiosocket_visitante(reader, writer, state_machine, call_id.hex())

    except Exception as e:
        logging.error(f"[VISITANTE] Erro: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def handle_client_morador(reader, writer):
    state_machine = StateMachine()

    try:
        header = await reader.readexactly(3)
        kind = header[0]
        length = int.from_bytes(header[1:3], "big")
        call_id = await reader.readexactly(length)

        if kind != 0x01:
            logging.error("Mensagem inicial inválida.")
            writer.close()
            await writer.wait_closed()
            return

        logging.info(f"[MORADOR] Recebido Call ID: {call_id.hex()}")

        await iniciar_servidor_audiosocket_morador(reader, writer, state_machine, call_id.hex())

    except Exception as e:
        logging.error(f"[MORADOR] Erro: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    server_visitante = await asyncio.start_server(handle_client_visitante, '127.0.0.1', 8080)
    server_morador = await asyncio.start_server(handle_client_morador, '127.0.0.1', 8081)

    logging.info("AudioSocket VISITANTE rodando em 127.0.0.1:8080")
    logging.info("AudioSocket MORADOR rodando em 127.0.0.1:8081")

    async with server_visitante, server_morador:
        await asyncio.gather(
            server_visitante.serve_forever(),
            server_morador.serve_forever()
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Servidores encerrados manualmente.")
