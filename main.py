import asyncio
import logging
from dotenv import load_dotenv
from state_machine import StateMachine
from audiosocket_handler import iniciar_servidor_audiosocket

load_dotenv()
logging.basicConfig(level=logging.INFO)

async def handle_client(reader, writer):
    state_machine = StateMachine()
    state_machine.start_new_conversation()

    # Lendo a mensagem inicial KIND_ID (esperado pelo cliente)
    try:
        header = await reader.readexactly(3)
        kind = header[0]
        length = int.from_bytes(header[1:3], "big")
        call_id = await reader.readexactly(length)

        if kind != 0x01:  # KIND_ID
            logging.error("Mensagem inicial não é KIND_ID. Fechando conexão.")
            writer.close()
            await writer.wait_closed()
            return

        logging.info(f"Recebido Call ID: {call_id.hex()}")

        # Agora iniciar o servidor audio socket normalmente
        await iniciar_servidor_audiosocket(reader, writer, state_machine)

    except asyncio.IncompleteReadError:
        logging.error("Cliente desconectado inesperadamente.")
    except Exception as e:
        logging.error(f"Erro inesperado: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_client, '127.0.0.1', 8080)
    logging.info("Servidor AudioSocket rodando em 127.0.0.1:8080")
    async with server:
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            logging.info("Servidor está sendo encerrado.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Servidor encerrado manualmente.")
