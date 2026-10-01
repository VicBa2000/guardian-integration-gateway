import re

# Se aplican en este orden. La tarjeta va antes que el SSN para que un patron
# corto nunca "muerda" un pedazo de un numero largo.
PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # usuario@dominio.tld -> juan.perez+test@mail.example.com
    # (?<!...) en vez de \b: solo empieza al inicio de una racha de caracteres
    # validos. Con \b cada posicion reintentaba todo -> O(n^2) (ReDoS).
    ("EMAIL", re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # 3 grupos de 4 + ultimo grupo de 1-7 (13-19 digitos). Separador solo ENTRE
    # grupos, nunca despues del ultimo: asi no se "come" digitos vecinos.
    # -> 4111111111111111, 4111 1111 1111 1111, 4111-1111-1111-1111
    ("CREDIT_CARD", re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{1,7}(?!\d)")),
    # bloques 3-2-4, separador opcional -> 123-45-6789, 123 45 6789, 123456789
    # (?<!\d) / (?!\d): sin digitos pegados, pero si detecta "123456789abc"
    ("SSN", re.compile(r"(?<!\d)\d{3}[ -]?\d{2}[ -]?\d{4}(?!\d)")),
]


def sanitize(text: str) -> str:
    """Reemplaza cada PII de `text` por <REDACTED: TYPE>."""
    for pii_type, pattern in PII_PATTERNS:
        text = pattern.sub(f"<REDACTED: {pii_type}>", text)
    return text


# Red 2 (detector residual): patrones SUELTOS que corren sobre el texto YA
# redactado. No saben el tipo, solo avisan "esto parece PII".
RESIDUAL_PATTERNS: list[re.Pattern[str]] = [
    # 9+ digitos con cualquier separador en medio -> 0123-45-6789, 123.45.6789
    re.compile(r"(?<!\d)\d(?:[\s._/-]*\d){8,}(?!\d)"),
    # cualquier token con @ -> juan@empresa, a@b. (?<!\S): solo desde el inicio
    # del token; mismo resultado que \S+@\S+ pero lineal (sin ReDoS).
    re.compile(r"(?<!\S)\S+@\S+"),
]
SUSPECTED_TAG = "<REDACTED: SUSPECTED_PII>"


def find_residual_pii(text: str) -> list[str]:
    """Devuelve los fragmentos sospechosos que la red 1 no redacto.

    OJO: el resultado ES PII en claro. Usalo solo en memoria (decidir, contar);
    nunca en respuestas, logs ni en el audit en texto plano.
    """
    found: list[str] = []
    for pattern in RESIDUAL_PATTERNS:
        found.extend(pattern.findall(text))
    return found


def redact_residual(text: str) -> str:
    """Modo B (default): reemplaza cada sospechoso por SUSPECTED_TAG."""
    for pattern in RESIDUAL_PATTERNS:
        text = pattern.sub(SUSPECTED_TAG, text)
    return text
