# Reglas de Desarrollo — The Guardian Integration Gateway

## Contexto del proyecto
Proyecto de entrevista tecnica para un puesto de backend. El enunciado
completo (fuente de verdad) esta en `ProyectBaseline`. Limite de tiempo:
4-6 horas. El uso de un asistente de IA (Claude, Cursor, ChatGPT, Gemini)
es obligatorio: el evaluador quiere ver como se orquesta la IA para
resolver logica de seguridad, asi que las decisiones importantes deben
quedar razonadas y trazables (ver regla 3).

**Objetivo**: un middleware seguro con un endpoint `POST /secure-inquiry`
que recibe `{ userId: string, message: string }` y ejecuta:
1. **Sanitizacion**: reemplaza emails, tarjetas de credito y SSNs
   (formato SSN o 9 digitos) del `message` por `<REDACTED: TYPE>`.
2. **Llamada mock a IA**: simula un servicio externo con una espera de
   2 segundos que devuelve un "Generated Answer".
3. **Audit log**: guarda el mensaje original **cifrado** y el mensaje
   redactado en texto plano en una base de datos mock (archivo JSON).
4. **Circuit breaker**: si la llamada mock falla 3 veces seguidas, la API
   responde de inmediato con el fallback `"Service Busy"` sin esperar el
   timeout.

**Stack**: Python/FastAPI o Node.js/Express (a elegir; una vez elegido,
registrarlo aqui y no cambiarlo — ver regla 5).
- Stack elegido: **Python + FastAPI** (servidor: uvicorn)

**Entregables**:
- Codigo en un repositorio de GitHub.
- `Dockerfile` y/o `docker-compose.yml` funcionando.
- Video del entorno local mostrando el proyecto funcionando, subido al repo.

## Reglas obligatorias

### 1. Fuente de verdad
- Los requisitos son los de `ProyectBaseline`. No inventar requisitos
  extra ni reinterpretar los existentes; si algo es ambiguo (ej. formato
  exacto de la respuesta, que cuenta como "fallo" de la llamada mock,
  cuando se resetea el circuit breaker), preguntar al usuario y registrar
  la decision en `cambios.txt`.
- No inventar comportamiento de librerias externas (cifrado, frameworks,
  etc.). Usar solo APIs documentadas de la version instalada; si hay duda,
  verificar en la documentacion oficial antes de escribir codigo.

### 2. Analizar antes de modificar
- Antes de tocar un archivo existente, entender que hace y por que existe.
- Seguridad de datos: el mensaje original **nunca** debe persistirse, ni
  loguearse, ni devolverse en texto plano. Cualquier cambio que toque el
  flujo del mensaje original debe revisarse contra esta regla — una fuga
  del original es un bug critico, no un detalle menor.
- Las claves de cifrado se leen de variables de entorno / config, nunca
  hardcodeadas ni commiteadas.
- El componente modificado debe mantener el mismo resultado funcional que
  el original, salvo que el cambio pedido sea explicitamente otra cosa.

### 3. Bitacora de cambios (cambios.txt)
- Un `cambios.txt` en la raiz del proyecto.
- Despues de cada unidad de trabajo aprobada: archivo tocado, descripcion
  breve, y a que parte del flujo afecta (sanitizer, mock IA, audit log,
  circuit breaker, Docker/infra).
- Registrar tambien las decisiones de diseno tomadas (y por que): sirve
  como evidencia de la orquestacion de IA que pide la entrevista.
- Al retomar trabajo despues de un `/clear`, leer primero este `CLAUDE.md`
  y despues `cambios.txt`.

### 4. Manejo de contexto
- Si el contexto esta cerca de llenarse, avisar al usuario y pedir `/clear`
  antes de seguir.
- Al retomar: releer este archivo, `ProyectBaseline` y `cambios.txt` para
  saber donde se quedo.

### 5. Calidad de codigo
- No agregar features, refactors o abstracciones no pedidas.
- No generar codigo generico o alucinado (ver regla 1).
- Mantener consistencia con el stack elegido — no cambiarlo a mitad de
  camino sin discutirlo.
- El sanitizer y el circuit breaker son la logica central evaluada: deben
  tener tests que cubran los casos borde (varios PII en un mismo mensaje,
  tarjetas con espacios/guiones, SSN con y sin guiones, falsos positivos
  obvios, apertura del breaker tras 3 fallos consecutivos).

### 6. Checklist de "terminado"
El proyecto no se considera terminado hasta que:
- `POST /secure-inquiry` cumple los 4 puntos del enunciado de punta a punta.
- Los tests del sanitizer y del circuit breaker pasan.
- La app levanta con Docker (`docker compose up` o `docker build` + `run`)
  desde un clon limpio del repo.
- Hay un README con instrucciones para correrlo y probar el endpoint.
- El video de demostracion esta grabado y subido al repo junto con el codigo.

### 7. Archivos de referencia
- Enunciado del proyecto: `ProyectBaseline`
- Reglas de desarrollo: `CLAUDE.md` (este archivo)
- Bitacora de cambios y decisiones: `cambios.txt`
