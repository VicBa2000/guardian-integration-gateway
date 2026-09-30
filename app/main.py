import os
from functools import partial

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.audit import write_audit
from app.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.mock_ai import MockAIError, call_mock_ai
from app.sanitizer import find_residual_pii, redact_residual, sanitize
from app.schemas import InquiryRequest, InquiryResponse

# Se lee y valida UNA vez al arrancar: un valor invalido tumba el arranque
# en vez de caer en silencio a otro modo (fail fast).
_VALID_MODES = {"redact", "block"}
# Vacia o solo espacios = "no configurada" -> default. Un typo SI falla.
RESIDUAL_PII_MODE = (os.getenv("RESIDUAL_PII_MODE") or "").strip().lower() or "redact"
if RESIDUAL_PII_MODE not in _VALID_MODES:
    raise ValueError(
        f"RESIDUAL_PII_MODE invalido: {RESIDUAL_PII_MODE!r}. "
        f"Usa uno de: {', '.join(sorted(_VALID_MODES))}"
    )

app = FastAPI(title="Guardian Integration Gateway")

# A nivel de modulo: UN breaker que recuerda los fallos entre peticiones.
# (Es por proceso: con varios workers/replicas cada uno tiene el suyo.)
breaker = CircuitBreaker(failure_threshold=3, reset_timeout=30.0, call_timeout=5.0)
FALLBACK_MESSAGE = "Service Busy"


@app.post("/secure-inquiry", response_model=InquiryResponse)
async def secure_inquiry(payload: InquiryRequest) -> InquiryResponse:
    clean = sanitize(payload.message)
    residual = len(find_residual_pii(clean))
    if residual:
        # Lo que se audita en plano NUNCA lleva sospechosos, ni siquiera si se bloquea.
        clean = redact_residual(clean)
    audit = partial(write_audit, payload.userId, payload.message, clean,
                    residual_pii_count=residual)

    if residual and RESIDUAL_PII_MODE == "block":
        await audit(outcome="blocked")
        # Mensaje generico: NUNCA incluir lo detectado (es PII en claro).
        raise HTTPException(422, "El mensaje contiene posibles datos sensibles no reconocidos.")

    try:
        # Al LLM solo le llega el texto ya limpio, nunca payload.message.
        answer = await breaker.call(call_mock_ai, clean)
    except (CircuitOpenError, MockAIError, TimeoutError):
        await audit(outcome="service_busy")
        return JSONResponse(
            status_code=503,
            content={"userId": payload.userId, "message": FALLBACK_MESSAGE},
        )
    await audit(outcome="answered")
    return InquiryResponse(userId=payload.userId, message=answer)
