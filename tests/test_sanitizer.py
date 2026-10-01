import time

import pytest
from pydantic import ValidationError

from app.sanitizer import find_residual_pii, redact_residual, sanitize
from app.schemas import MAX_MESSAGE_LENGTH, InquiryRequest

E, C, S = "<REDACTED: EMAIL>", "<REDACTED: CREDIT_CARD>", "<REDACTED: SSN>"


# Red 1 debe redactar (atrapa falsos negativos = fugas)
@pytest.mark.parametrize("raw, expected", [
    ("mail juan.perez+test@mail.example.com", f"mail {E}"),
    ("tarjeta 4111111111111111", f"tarjeta {C}"),
    ("tarjeta 4111 1111 1111 1111", f"tarjeta {C}"),
    ("tarjeta 4111-1111-1111-1111", f"tarjeta {C}"),
    ("ssn 123-45-6789, 123 45 6789, 123456789", f"ssn {S}, {S}, {S}"),
    ("ssn 123456789abc", f"ssn {S}abc"),
    ("a@example.com 4111111111111111 123-45-6789", f"{E} {C} {S}"),
])
def test_sanitize_redacts(raw, expected):
    assert sanitize(raw) == expected


# Red 1 NO debe tocar (atrapa falsos positivos = redactar de mas)
@pytest.mark.parametrize("raw", [
    "orden 1234567890", "tel 5512345678", "ssn 123-45-67890", "hola, sin datos",
])
def test_sanitize_leaves_clean_text(raw):
    assert sanitize(raw) == raw


# Red 2 atrapa lo que la red 1 dejo pasar
@pytest.mark.parametrize("raw", ["ssn 0123-45-6789", "ssn 123.45.6789", "juan@empresa"])
def test_residual_catches_near_pii(raw):
    clean = sanitize(raw)
    assert find_residual_pii(clean)
    assert "<REDACTED: SUSPECTED_PII>" in redact_residual(clean)


# ReDoS: entradas hostiles largas deben procesarse en tiempo lineal. Antes del
# fix, 40k caracteres tardaban segundos (backtracking O(n^2)).
@pytest.mark.parametrize("raw", ["a@" + "a." * 50_000, "a" * 100_000, "1 " * 50_000],
                         ids=["email-dots", "no-at", "spaced-digits"])
def test_hostile_input_is_fast(raw):
    start = time.perf_counter()
    redact_residual(sanitize(raw))
    assert time.perf_counter() - start < 0.5


def test_message_over_limit_is_rejected():
    with pytest.raises(ValidationError):
        InquiryRequest(userId="u1", message="x" * (MAX_MESSAGE_LENGTH + 1))
