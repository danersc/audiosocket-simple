from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# =======================
# 🧠 MODELO DE INTENÇÃO
# =======================

class IntentType(str, Enum):
    VISITA = "visita"
    ENTREGA = "entrega"
    DESCONHECIDO = "desconhecido"

class IntentData(BaseModel):
    intent_type: IntentType = Field(..., description="Tipo de intenção identificada")
    interlocutor_name: str = Field("", description="Nome da pessoa no portão")
    apartment_number: str = Field("", description="Número do apartamento de destino")
    resident_name: str = Field("", description="Nome do morador/destinatário")

class FullIntentResponse(BaseModel):
    mensagem: str
    dados: IntentData
    valid_for_action: bool
    set_call_status: Optional[str] = "USER_TURN"
