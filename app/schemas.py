from pydantic import BaseModel, Field

# Tope de entrada: acota el CPU de las regex por peticion (defensa ReDoS).
# Mas largo -> 422 antes de que corra el sanitizer.
MAX_MESSAGE_LENGTH = 5000


class InquiryRequest(BaseModel):
    # 1. Declara los dos campos del enunciado (ProyectBaseline) con su tipo.
    #    Respeta el nombre exacto del JSON: userId, no user_id.

    userId: str
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)


class InquiryResponse(BaseModel):
    # 2. Por ahora: userId y el message recibido.
    #    Mas adelante message sera la respuesta de la IA.
    userId: str
    message: str
