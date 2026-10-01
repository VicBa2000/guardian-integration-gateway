# The Guardian Integration Gateway

> 🇲🇽 Español · [🇺🇸 English version](#english-version)

Un middleware en FastAPI que protege los datos personales antes de que lleguen a un LLM.
Cada mensaje pasa por un sanitizador que quita emails, tarjetas y números de seguro social;
solo el texto limpio se envía a la IA. El mensaje original queda guardado **cifrado** en una
bitácora de auditoría, y si el servicio de IA se cae, un circuit breaker responde de
inmediato en lugar de dejar al cliente esperando.

```
POST /secure-inquiry  { "userId": "...", "message": "..." }
        │
        ▼
 1. Sanitizador ── 1er filtro: EMAIL / CREDIT_CARD / SSN  →  <REDACTED: TYPE>
        │          2º filtro: busca lo que "parece" dato sensible y se escapó
        │                     → lo tapa (default) o rechaza la petición (422)
        ▼
 2. Circuit breaker ──► IA simulada (tarda 2 s) ──► "Generated Answer"
        │   si falla 3 veces seguidas, responde "Service Busy" al instante
        ▼
 3. Auditoría (JSON Lines): mensaje original cifrado + mensaje limpio legible
```

## Demo

Video del proyecto corriendo en local: [demo/guardian-demo.mp4](demo/guardian-demo.mp4)

## Cómo levantarlo

Necesitas Docker. Primero crea tu archivo de configuración y genera la llave de cifrado:

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Pega la llave que te imprime en `AUDIT_ENCRYPTION_KEY` dentro de `.env` y levanta el servicio:

```bash
docker compose up -d --build
```

Listo. Puedes probarlo desde **http://localhost:8000/docs** o con curl:

```bash
curl -X POST http://localhost:8000/secure-inquiry \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","message":"mi ssn es 123-45-6789, tarjeta 4111 1111 1111 1111, mail ana@example.com"}'
```

```json
{"userId":"u1","message":"Generated Answer for: mi ssn es <REDACTED: SSN>, tarjeta <REDACTED: CREDIT_CARD>, mail <REDACTED: EMAIL>"}
```

La bitácora se guarda en `./data/audit_log.jsonl` de tu máquina. Como es un volumen de
Docker, no se pierde aunque bajes el contenedor con `docker compose down`.

> **Importante:** guarda una copia de `.env` junto con `data/`. Si pierdes la llave, no hay
> forma de volver a leer los mensajes originales.

## Configuración

Todo se configura con variables en `.env`:

| Variable | Si no la defines | Para qué sirve |
|---|---|---|
| `AUDIT_ENCRYPTION_KEY` | La app **no arranca** | Llave con la que se cifra el mensaje original. |
| `AUDIT_LOG_PATH` | `data/audit_log.jsonl` | Ruta de la bitácora. |
| `RESIDUAL_PII_MODE` | `redact` | Qué hacer cuando el segundo filtro encuentra algo sospechoso: `redact` lo tapa con `<REDACTED: SUSPECTED_PII>` y sigue; `block` rechaza la petición con `422` y nunca llama a la IA. |
| `MOCK_AI_FAILURE_RATE` | `0` | Qué tan seguido falla la IA simulada, de `0` (nunca) a `1` (siempre). Útil para ver el circuit breaker en acción. |

Si una variable trae un valor que no existe (por ejemplo `RESIDUAL_PII_MODE=blok`), la app
se niega a arrancar y te dice por qué. Preferimos eso a que corra en silencio con un modo
que no es el que pediste.

## Para probar cada caso

**Ver el circuit breaker.** Pon `MOCK_AI_FAILURE_RATE=1` en `.env`, reinicia con
`docker compose up -d --force-recreate` y manda la misma petición cinco veces:

```
1. 503 {"message":"Service Busy"}  ~2.0 s   ┐ intenta llamar a la IA, espera y falla
2. 503 {"message":"Service Busy"}  ~2.0 s   │
3. 503 {"message":"Service Busy"}  ~2.0 s   ┘ tercer fallo seguido: el circuito se abre
4. 503 {"message":"Service Busy"}  ~0.01 s  ┐ ya ni intenta: responde al instante
5. 503 {"message":"Service Busy"}  ~0.01 s  ┘
```

Pasados 30 segundos, el breaker deja pasar **una sola** petición de prueba. Si la IA
responde bien, el circuito se cierra y todo vuelve a la normalidad; si vuelve a fallar, el
circuito se queda abierto otros 30 segundos.

**Ver el segundo filtro.** Manda `{"userId":"u1","message":"ssn 0123-45-6789"}`. Ese número
no tiene el formato exacto de un SSN, así que el primer filtro lo deja pasar, pero el segundo
lo detecta como sospechoso. Con la configuración por defecto se tapa; en modo `block`
recibes un `422`. En ningún caso la respuesta de error repite el dato detectado.

**Leer un mensaje original de la bitácora** (solo para investigar un incidente; necesitas
la llave):

```bash
docker compose exec gateway python -c "
import json, os; from cryptography.fernet import Fernet
f = Fernet(os.environ['AUDIT_ENCRYPTION_KEY'])
for line in open('data/audit_log.jsonl'):
    r = json.loads(line); print(r['outcome'], '|', f.decrypt(r['original_encrypted'].encode()).decode())
"
```

## Correrlo sin Docker y ejecutar las pruebas

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v            # 25 pruebas
uvicorn app.main:app --reload  # necesita AUDIT_ENCRYPTION_KEY en el entorno
```

| Archivo | Qué verifica |
|---|---|
| `test_sanitizer.py` | Que los datos sensibles se tapen, que el texto normal (teléfonos, números de pedido) **no** se toque, y que el segundo filtro atrape lo que se le escapa al primero |
| `test_circuit_breaker.py` | Que se abra tras 3 fallos seguidos y responda sin llamar a la IA; que un éxito reinicie la cuenta; que un timeout cuente como fallo; que después de enfriarse deje pasar una sola prueba |
| `test_audit.py` | Que el mensaje original nunca quede legible en el archivo y que se pueda descifrar con la llave; que 50 escrituras simultáneas no se mezclen; que sin llave válida la app no arranque |

## Decisiones de diseño

- **Dos filtros en lugar de uno.** Ningún regex es perfecto, así que después del filtro
  preciso corre un segundo filtro más amplio sobre el texto ya limpio. Si algo se parece a
  un dato sensible, no llega a la IA. Ante la duda, se tapa.
- **Lookarounds `(?<!\d)` / `(?!\d)` en lugar de `\b`.** Con `\b`, un SSN pegado a letras
  (`123456789abc`) se escapaba, porque para el regex no hay "borde" entre un dígito y una
  letra. Los lookarounds solo exigen que no haya otro dígito pegado.
- **Las tarjetas se reconocen por grupos de cuatro.** La primera versión aceptaba un
  separador entre cualquier par de dígitos y, como el regex siempre intenta abarcar lo más
  posible, se "comía" los primeros dígitos de un SSN que venía después. Resultado: en
  `4111111111111111 123-45-6789` quedaba expuesto `-45-6789`. Lo descubrió una prueba con
  varios datos en el mismo mensaje, que ahora se quedó como prueba de regresión.
- **El dato detectado nunca se repite hacia afuera.** Ni en la respuesta, ni en mensajes de
  error, ni en logs, ni en la parte legible de la bitácora. Solo se guarda cuántos
  sospechosos hubo (`residual_pii_count`).
- **"Service Busy" responde con 503**, no con 200, y mantiene la misma forma que una
  respuesta normal. Solo los fallos de la IA se convierten en "Service Busy"; si el error
  es un bug nuestro, sale como 500 para que no pase desapercibido.
- **La bitácora es JSON Lines** (un registro por línea). Cada petición solo agrega una
  línea al final, en vez de reescribir todo el archivo. La escritura corre en otro hilo con
  un candado, para no frenar al servidor y para que dos registros no se encimen. Se
  registran todas las respuestas: exitosas, bloqueadas y fallidas.
- **Cifrado con Fernet.** Además de cifrar, firma cada registro: si alguien altera aunque
  sea un carácter, ya no se puede descifrar.
- **Docker:** las dependencias se instalan antes de copiar el código (así se aprovecha la
  caché), el proceso no corre como root, `.env` nunca entra a la imagen y se usa un solo
  worker a propósito (ver abajo).

El razonamiento detrás de cada decisión, y los errores que fuimos encontrando, están
documentados en [`cambios.txt`](cambios.txt).

## Limitaciones conocidas

- **Un regex no entiende contexto.** No detecta nombres, direcciones ni datos escritos con
  palabras ("uno dos tres..."). Para eso haría falta un modelo de reconocimiento de
  entidades.
- **El circuit breaker vive en memoria.** Si el contenedor se reinicia, empieza de cero; y
  si hubiera varios workers o réplicas, cada uno tendría el suyo. Compartirlo requeriría
  guardar su estado afuera, por ejemplo en Redis. Por eso el contenedor corre con un solo
  worker.
- **Tarjetas con agrupación distinta a 4-4-4-x** (como American Express, 4-6-5) no las
  reconoce el primer filtro; las atrapa el segundo como sospechosas.
- **Todavía no hay rotación de llave.** Si cambias `AUDIT_ENCRYPTION_KEY`, los registros
  anteriores quedan ilegibles. Para rotarla habría que descifrar cada registro con la llave
  vieja y volver a cifrarlo con la nueva (Fernet ya trae `MultiFernet(...).rotate()` para
  eso), y solo entonces desechar la vieja.
- `pytest` se instala también en la imagen de producción; separarlo en un
  `requirements-dev.txt` la haría más ligera.

## Estructura

```
app/
  main.py             el endpoint: sanitiza → llama a la IA con el breaker → audita
  schemas.py          modelos de entrada y salida (Pydantic)
  sanitizer.py        primer filtro (datos con tipo) y segundo filtro (sospechosos)
  mock_ai.py          IA simulada: tarda 2 s y puede fallar a propósito
  circuit_breaker.py  el circuit breaker (cerrado / abierto / en prueba)
  audit.py            bitácora cifrada en JSON Lines
tests/                25 pruebas con pytest
Dockerfile, docker-compose.yml, .env.example
cambios.txt           bitácora de cambios y decisiones del desarrollo
```

---

## English version

A secure FastAPI middleware that sits between users and an (external) LLM. It strips PII
from every message before it can leave the service, keeps an encrypted audit trail, and
protects itself from a failing upstream with a circuit breaker.

```
POST /secure-inquiry  { "userId": "...", "message": "..." }
        │
        ▼
 1. Sanitizer ── net 1: EMAIL / CREDIT_CARD / SSN  →  <REDACTED: TYPE>
        │        net 2: residual detector (near-PII) → redact (default) or block (422)
        ▼
 2. Circuit breaker ──► Mock AI (2 s)  ──►  "Generated Answer"
        │   3 consecutive failures → open → instant 503 "Service Busy"
        ▼
 3. Audit log (JSON Lines): original ENCRYPTED (Fernet) + redacted in plain text
```

### Demo

Local run walkthrough: [demo/guardian-demo.mp4](demo/guardian-demo.mp4)

### Quick start (Docker)

```bash
cp .env.example .env
# Generate the encryption key and paste it into AUDIT_ENCRYPTION_KEY in .env:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up -d --build
```

Open **http://localhost:8000/docs** (Swagger UI) or use curl:

```bash
curl -X POST http://localhost:8000/secure-inquiry \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","message":"my ssn is 123-45-6789, card 4111 1111 1111 1111, mail ana@example.com"}'
```

```json
{"userId":"u1","message":"Generated Answer for: my ssn is <REDACTED: SSN>, card <REDACTED: CREDIT_CARD>, mail <REDACTED: EMAIL>"}
```

The audit trail is written to `./data/audit_log.jsonl` on the host (a mounted volume,
so it survives `docker compose down`).

> **Back up `.env` together with `data/`.** Without the key, the encrypted originals
> cannot be recovered.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `AUDIT_ENCRYPTION_KEY` | — (**required**) | Fernet key used to encrypt the original message. Missing/invalid → the app refuses to start. |
| `AUDIT_LOG_PATH` | `data/audit_log.jsonl` | Where the audit log is written. |
| `RESIDUAL_PII_MODE` | `redact` | What to do with suspected PII that net 1 did not recognize: `redact` → `<REDACTED: SUSPECTED_PII>` and continue; `block` → `422`, the LLM is never called. |
| `MOCK_AI_FAILURE_RATE` | `0` | Probability (0–1) that the mock AI fails. Set to `1` to watch the breaker open. |

Invalid values (e.g. `RESIDUAL_PII_MODE=blok`) make the app **fail at startup** instead of
silently falling back to another mode. Empty values use the default.

### Demo scenarios

**Circuit breaker.** Set `MOCK_AI_FAILURE_RATE=1` in `.env`, then
`docker compose up -d --force-recreate` and send the same request 5 times:

```
1. 503 {"message":"Service Busy"}  ~2.0 s   ┐ calls the AI, waits, fails
2. 503 {"message":"Service Busy"}  ~2.0 s   │
3. 503 {"message":"Service Busy"}  ~2.0 s   ┘ 3rd consecutive failure → circuit OPEN
4. 503 {"message":"Service Busy"}  ~0.01 s  ┐ instant: the AI is not even called
5. 503 {"message":"Service Busy"}  ~0.01 s  ┘
```

After 30 s the breaker goes **half-open** and lets exactly **one** trial call through:
success closes it, failure re-opens it.

**Residual PII.** `{"userId":"u1","message":"ssn 0123-45-6789"}` is not a valid SSN
format (net 1 ignores it), but net 2 flags it: redacted as `<REDACTED: SUSPECTED_PII>`
(default) or rejected with `422` in `block` mode. The `422` body never includes the
detected value.

**Reading an original from the audit log** (investigation only, needs the key):

```bash
docker compose exec gateway python -c "
import json, os; from cryptography.fernet import Fernet
f = Fernet(os.environ['AUDIT_ENCRYPTION_KEY'])
for line in open('data/audit_log.jsonl'):
    r = json.loads(line); print(r['outcome'], '|', f.decrypt(r['original_encrypted'].encode()).decode())
"
```

### Running locally & tests

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v          # 25 tests
uvicorn app.main:app --reload  # needs AUDIT_ENCRYPTION_KEY in the environment
```

| Test file | What it proves |
|---|---|
| `test_sanitizer.py` | PII is redacted (false negatives), clean text is untouched (false positives), net 2 catches near-PII |
| `test_circuit_breaker.py` | Opens after 3 consecutive failures and fails fast without calling the service; a success resets the counter; timeouts count; half-open lets a single trial through |
| `test_audit.py` | The original never appears in clear text and decrypts with the key; 50 concurrent writes → 50 valid lines; no valid key → refuses to start |

### Design decisions

- **Two detection nets (defense in depth, fail-closed).** Precise patterns first; then a
  loose residual detector over the *already redacted* text. Anything suspicious never
  reaches the LLM.
- **Lookarounds `(?<!\d)` / `(?!\d)` instead of `\b`.** `\b` does not separate a digit
  from a letter, so `123456789abc` leaked. Lookarounds only forbid *adjacent digits*.
- **Card pattern by groups** (`(?:\d{4}[ -]?){3}\d{1,7}`). The first version allowed a
  separator between any two digits and, being greedy, swallowed digits of a neighboring
  SSN (`4111111111111111 123-45-6789` leaked `-45-6789`). Found by a mixed-PII test, now a
  regression test.
- **Detected PII is never echoed** in responses, error messages, logs or the plain-text
  audit field — only a count (`residual_pii_count`).
- **Circuit breaker fallback is `503`**, with the same body shape as a normal response.
  Only expected upstream failures map to "Service Busy"; our own bugs surface as `500`.
- **Audit log as JSON Lines**, appended via `asyncio.to_thread` + `asyncio.Lock`: no
  event-loop blocking, no interleaved lines, no full-file rewrites. Every outcome is
  audited (`answered`, `blocked`, `service_busy`).
- **Fernet** (AES + HMAC) authenticates the ciphertext: a tampered record fails to decrypt.
- **Docker:** dependencies layer before code (cache), non-root user, `.env` never baked
  into the image, single worker on purpose (see limitations).

The full decision log, including the reasoning behind each choice and the bugs found along
the way, is in [`cambios.txt`](cambios.txt).

### Known limitations

- **Regex-based detection** cannot catch names, addresses or PII spelled out in words
  ("one two three…"). That would require NER / an ML classifier.
- **Circuit breaker state is in-process memory:** it resets on restart, and with multiple
  workers or replicas each has its own breaker. A shared breaker would need external state
  (e.g. Redis). The container runs a single worker for this reason.
- **Card formats outside 4-4-4-x grouping** (e.g. Amex 4-6-5) are not recognized by net 1;
  they are caught by net 2 as suspected PII instead.
- **No key rotation yet.** Changing `AUDIT_ENCRYPTION_KEY` makes older records
  unreadable. Rotation would re-encrypt them with Fernet's `MultiFernet([new, old]).rotate()`
  and only then discard the old key.
- `pytest` ships in the runtime image; splitting a `requirements-dev.txt` would slim it.

### Project structure

```
app/
  main.py             endpoint + wiring (sanitize → breaker/mock AI → audit)
  schemas.py          request/response models (Pydantic)
  sanitizer.py        net 1 (typed PII) + net 2 (residual detector)
  mock_ai.py          simulated external AI (2 s latency, configurable failures)
  circuit_breaker.py  closed / open / half-open breaker
  audit.py            encrypted JSON Lines audit log
tests/                25 tests (pytest)
Dockerfile, docker-compose.yml, .env.example
cambios.txt           decision & change log
```
