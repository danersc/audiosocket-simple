"""
Gerador de UUIDs v7 para o sistema de portaria digital.

Implementação baseada na especificação RFC: https://datatracker.ietf.org/doc/draft-ietf-uuidrev-rfc4122bis/
"""

import time
import uuid
import random

def uuid7():
    """
    Gera um UUID v7 baseado em timestamp.
    
    UUID v7 usa os primeiros 48 bits para um timestamp de milissegundos,
    segmento de 12 bits para sequência e 62 bits aleatórios.
    
    Returns:
        UUID: Um objeto UUID v7
    """
    # Obtém o timestamp em milissegundos (48 bits, mais significativos)
    timestamp_ms = int(time.time() * 1000)
    timestamp_bytes = timestamp_ms.to_bytes(6, byteorder='big')
    
    # Gera 10 bytes aleatórios (80 bits para sequência e aleatoriedade)
    random_bytes = random.randbytes(10)
    
    # Combina os bytes
    uuid_bytes = timestamp_bytes + random_bytes
    
    # Define a versão 7 nos bits apropriados (bits 48-51)
    uuid_bytes = bytearray(uuid_bytes)
    uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x70  # Versão 7
    uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80  # Variante
    
    # Cria o UUID a partir dos bytes
    return uuid.UUID(bytes=bytes(uuid_bytes))

def uuid7str():
    """
    Retorna o UUID v7 como string.
    """
    return str(uuid7())