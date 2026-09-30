import asyncio
import time


class CircuitOpenError(Exception):
    """Circuito abierto: se rechaza al instante, sin llamar al servicio."""


class CircuitBreaker:
    def __init__(self, failure_threshold=3, reset_timeout=30.0, call_timeout=5.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.call_timeout = call_timeout
        self.state = "closed"  # closed | open | half_open
        self.failures = 0      # fallos CONSECUTIVOS
        self.opened_at = 0.0
        self._trial_in_flight = False  # half_open deja pasar UNA sola prueba

    async def call(self, func, *args):
        if self.state == "open":
            if time.monotonic() - self.opened_at < self.reset_timeout:
                raise CircuitOpenError()  # falla rapido: ni siquiera llama a func
            self.state = "half_open"      # ya enfrio: toca probar
        is_trial = self.state == "half_open"
        if is_trial:
            if self._trial_in_flight:
                raise CircuitOpenError()  # ya hay una prueba en curso
            self._trial_in_flight = True
        try:
            result = await asyncio.wait_for(func(*args), self.call_timeout)
        except Exception:
            self.failures += 1
            if is_trial or self.failures >= self.failure_threshold:
                self.state, self.opened_at = "open", time.monotonic()
            raise
        finally:
            if is_trial:
                self._trial_in_flight = False
        self.state, self.failures = "closed", 0  # exito: reinicia el contador
        return result
