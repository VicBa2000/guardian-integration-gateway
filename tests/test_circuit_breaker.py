import asyncio
import time

import pytest

from app.circuit_breaker import CircuitBreaker, CircuitOpenError

calls = {"n": 0}  # cuantas veces se llamo realmente al "servicio"


async def ok():
    calls["n"] += 1
    await asyncio.sleep(0.05)
    return "ok"


async def fail():
    calls["n"] += 1
    await asyncio.sleep(0.05)
    raise RuntimeError("caido")


async def slow():
    await asyncio.sleep(10)


async def run(cb, func):
    """Devuelve el resultado o el nombre de la excepcion."""
    try:
        return await cb.call(func)
    except Exception as e:
        return type(e).__name__


def test_opens_after_3_consecutive_failures_and_fails_fast():
    async def scenario():
        cb = CircuitBreaker()
        for _ in range(3):
            await run(cb, fail)
        calls["n"], t = 0, time.perf_counter()
        assert await run(cb, ok) == "CircuitOpenError"
        assert time.perf_counter() - t < 0.01  # sin esperar
        assert calls["n"] == 0                 # ni siquiera llamo al servicio
    asyncio.run(scenario())


def test_success_resets_consecutive_counter():
    async def scenario():
        cb = CircuitBreaker()
        for f in (fail, fail, ok, fail, fail):
            await run(cb, f)
        assert cb.state == "closed" and cb.failures == 2
    asyncio.run(scenario())


def test_timeout_counts_as_failure():
    async def scenario():
        cb = CircuitBreaker(call_timeout=0.05)
        for _ in range(3):
            assert await run(cb, slow) == "TimeoutError"
        assert cb.state == "open"
    asyncio.run(scenario())


@pytest.mark.parametrize("trial, expected_state", [(fail, "open"), (ok, "closed")])
def test_half_open_trial_decides(trial, expected_state):
    async def scenario():
        cb = CircuitBreaker(reset_timeout=0.1)
        for _ in range(3):
            await run(cb, fail)
        await asyncio.sleep(0.15)
        await run(cb, trial)
        assert cb.state == expected_state
    asyncio.run(scenario())


def test_half_open_lets_only_one_trial_through():
    async def scenario():
        cb = CircuitBreaker(reset_timeout=0.1)
        for _ in range(3):
            await run(cb, fail)
        await asyncio.sleep(0.15)
        calls["n"] = 0
        results = await asyncio.gather(*[run(cb, ok) for _ in range(5)])
        assert calls["n"] == 1
        assert sorted(results) == ["CircuitOpenError"] * 4 + ["ok"]
    asyncio.run(scenario())
