from pydantic import BaseModel


class InquiryRequest(BaseModel):
    # 1. Declara los dos campos del enunciado (ProyectBaseline) con su tipo.
    #    Respeta el nombre exacto del JSON: userId, no user_id.

    userId: str
    message: str


class InquiryResponse(BaseModel):
    # 2. Por ahora: userId y el message recibido.
    #    Mas adelante message sera la respuesta de la IA.
    userId: str
    message: str
