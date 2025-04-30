#!/usr/bin/env python
# main_dynamic.py

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/audiosocket.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Inicializar diretório de logs se não existir
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)

async def main():
    """
    Função principal que inicializa o sistema de ramais dinâmicos e mantém
    os servidores rodando.
    """
    try:
        # Importar setup_system e configurar todo o sistema
        from setup_system import setup_extensions
        components = await setup_extensions()
        
        # Extrair os componentes retornados
        extension_manager = components['extension_manager']
        
        # Log de status inicial
        extensions = extension_manager.server_manager.get_all_extensions()
        logger.info(f"Sistema iniciado com {len(extensions)} ramais configurados")
        
        for ext in extensions:
            logger.info(f"Ramal ativo: {ext['ramal_ia']} (porta {ext['porta_ia']}) -> {ext['ramal_retorno']} (porta {ext['porta_retorno']})")
        
        logger.info(f"Sistema de ramais dinâmicos iniciado. API disponível na porta {os.getenv('API_PORT', '8082')}")
        
        # Importar handlers específicos e outros módulos necessários
        from audiosocket_handler import iniciar_servidor_audiosocket_visitante, iniciar_servidor_audiosocket_morador
        import socket
        
        # Verificar se algum dos servidores já está usando a porta 8101
        port_already_used = False
        for ext in extensions:
            if ext['porta_ia'] == 8101:
                port_already_used = True
                logger.info(f"Porta 8101 já está em uso pelo ramal {ext['ramal_ia']}")
                break
        
        if not port_already_used:
            # Verificar com socket se a porta está disponível
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(('0.0.0.0', 8101))
                sock.close()
                # Porta está disponível, podemos iniciar o servidor de emergência
                logger.info("Iniciando servidor de emergência na porta 8101")
                emergency_server = await asyncio.start_server(
                    iniciar_servidor_audiosocket_visitante, '0.0.0.0', 8101
                )
                logger.info("Servidor de emergência iniciado na porta 8101 (bypass)")
                
                # Usar serve_forever para manter o servidor ativo como em main.py
                await emergency_server.serve_forever()
            except OSError:
                logger.info("Porta 8101 já está em uso, não será iniciado servidor de emergência")
                sock.close()
        
        # Como não conseguimos iniciar o servidor, vamos manter o loop principal
        while True:
            await asyncio.sleep(60)  # Verificar a cada minuto
        
        # NOTA: O código abaixo nunca será executado devido ao serve_forever acima
        # que é bloqueante. Mantemos por referência caso seja necessário implementar
        # verificações periódicas de outra forma.
        
        # Verificar por atualizações no banco de dados (opcional)
        if os.getenv('AUTO_REFRESH', 'false').lower() == 'true':
            logger.info("Executando atualização automática de ramais...")
            
            try:
                removed, updated, added = await extension_manager.refresh_configurations()
                
                if removed > 0 or updated > 0 or added > 0:
                    logger.info(f"Atualização automática: {removed} removidos, {updated} atualizados, {added} adicionados")
                else:
                    logger.info("Nenhuma alteração detectada na configuração de ramais")
            except Exception as e:
                logger.error(f"Erro durante atualização automática: {e}")
        
        # Verificar status dos sockets a cada hora
        try:
            active_servers = len(extension_manager.server_manager.servers)
            logger.info(f"Status periódico: {active_servers} servidores ativos")
            
            # Exibir informações sobre cada servidor
            for ext_id, server_data in extension_manager.server_manager.servers.items():
                config = server_data.get('config', {})
                ramal = config.get('ramal_ia', 'desconhecido')
                porta = config.get('porta_ia', 0)
                logger.info(f"Servidor {ext_id} (ramal {ramal}): porta {porta} ativo")
                
        except Exception as e:
            logger.error(f"Erro ao verificar status dos servidores: {e}")
    
    except KeyboardInterrupt:
        logger.info("Interrupção do teclado detectada, encerrando...")
    
    except Exception as e:
        logger.critical(f"Erro fatal durante execução: {e}", exc_info=True)
        return 1
    
    finally:
        # Tenta encerrar os servidores graciosamente
        try:
            if 'extension_manager' in locals():
                logger.info("Encerrando extension_manager...")
                await extension_manager.shutdown()
        except Exception as shutdown_err:
            logger.error(f"Erro durante encerramento: {shutdown_err}")
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Programa interrompido pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro fatal: {e}", exc_info=True)
        sys.exit(1)