import asyncio
import importlib
import json

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def audit(tmp_path, monkeypatch):
    """Recarga app.audit con una llave nueva y un log temporal."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", key)
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    import app.audit
    return importlib.reload(app.audit), Fernet(key)


def test_original_is_encrypted_and_recoverable(audit):
    module, fernet = audit
    asyncio.run(module.write_audit("u1", "ssn 123-45-6789", "ssn <REDACTED: SSN>", "answered"))
    raw = module.AUDIT_LOG_PATH.read_text(encoding="utf-8")
    assert "123-45-6789" not in raw  # el original NO aparece en claro
    record = json.loads(raw)
    assert record["redacted"] == "ssn <REDACTED: SSN>"
    assert fernet.decrypt(record["original_encrypted"].encode()).decode() == "ssn 123-45-6789"


def test_concurrent_writes_do_not_interleave(audit):
    module, _ = audit

    async def scenario():
        await asyncio.gather(*[module.write_audit("u1", f"m{i}", f"m{i}", "answered") for i in range(50)])
    asyncio.run(scenario())
    lines = module.AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50 and all(json.loads(line) for line in lines)


@pytest.mark.parametrize("bad_key", ["", "   ", "no-es-una-llave-fernet"])
def test_refuses_to_start_without_valid_key(monkeypatch, bad_key):
    monkeypatch.setenv("AUDIT_ENCRYPTION_KEY", bad_key)
    import app.audit
    with pytest.raises(ValueError):
        importlib.reload(app.audit)
