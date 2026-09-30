import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

# Llave secreta SOLO desde el entorno. Sin llave valida la app no arranca: no
# hay opcion segura (guardar el original en claro, o no guardarlo).
_key = (os.getenv("AUDIT_ENCRYPTION_KEY") or "").strip()
if not _key:
    raise ValueError(
        "Falta AUDIT_ENCRYPTION_KEY. Genera una con: python -c "
        '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
    )
_fernet = Fernet(_key)  # formato invalido -> ValueError aqui, al arrancar

AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH") or "data/audit_log.jsonl")
_lock = asyncio.Lock()


def _append(line: str) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def write_audit(user_id: str, original: str, redacted: str,
                      outcome: str, residual_pii_count: int = 0) -> None:
    """Agrega un registro JSONL: original CIFRADO, redactado en plano."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "userId": user_id,
        "original_encrypted": _fernet.encrypt(original.encode()).decode(),
        "redacted": redacted,
        "outcome": outcome,  # answered | blocked | service_busy
        "residual_pii_count": residual_pii_count,  # solo el conteo, nunca valores
    }
    async with _lock:  # una escritura a la vez: las lineas no se mezclan
        await asyncio.to_thread(_append, json.dumps(record, ensure_ascii=False))
