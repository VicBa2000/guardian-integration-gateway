import asyncio
import os
import random

LATENCY_SECONDS = 2.0  # el "setTimeout de 2 segundos" del enunciado


class MockAIError(Exception):
    """El servicio de IA simulado fallo."""


def _read_failure_rate() -> float:
    # Misma politica que RESIDUAL_PII_MODE: vacia = default, invalida = no arranca.
    raw = (os.getenv("MOCK_AI_FAILURE_RATE") or "").strip() or "0"
    rate = float(raw)  # "abc" ya lanza ValueError por si solo
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"MOCK_AI_FAILURE_RATE debe estar entre 0 y 1, llego {raw!r}")
    return rate


FAILURE_RATE = _read_failure_rate()


async def call_mock_ai(prompt: str) -> str:
    """Simula un LLM externo: tarda LATENCY_SECONDS y falla con prob. FAILURE_RATE."""
    await asyncio.sleep(LATENCY_SECONDS)  # no bloquea el event loop
    if random.random() < FAILURE_RATE:
        raise MockAIError("Mock AI no disponible")
    return f"Generated Answer for: {prompt}"
