"""HTTP plumbing tests: TokenBucket refill timing (no real sleeps) and
BaseClient retry behavior against a mocked transport.

Async code under test is driven via asyncio.run() from plain `def test_*`
functions, not `async def test_*` -- pytest-asyncio is not a project
dependency (see pyproject.toml), so an `async def test_*` would never
actually execute its body under plain pytest.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest

from kalshi_mt.api.http import BaseClient, TokenBucket


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def test_token_bucket_refills_over_fake_time():
    clock = _FakeClock()

    async def _run():
        with patch("time.monotonic", clock.now):
            bucket = TokenBucket(rate=2.0, burst=2)
            await bucket.acquire()  # 2 -> 1
            await bucket.acquire()  # 1 -> 0
            assert bucket._tokens < 1.0

            async def fake_sleep(seconds: float) -> None:
                clock.advance(seconds)

            with patch("asyncio.sleep", fake_sleep):
                await bucket.acquire()  # must wait for refill; fake clock advances instead of a real sleep
            assert bucket._tokens < 1.0  # consumed again right after refill

    asyncio.run(_run())


def test_token_bucket_does_not_exceed_burst_capacity():
    clock = _FakeClock()

    async def _run():
        with patch("time.monotonic", clock.now):
            bucket = TokenBucket(rate=100.0, burst=3)
            clock.advance(1000.0)  # a huge elapsed gap should still cap at burst, not overflow
            await bucket.acquire()
            assert bucket._tokens <= 2.0  # capacity(3) - 1 just consumed

    asyncio.run(_run())


def _sequenced_handler(sequence):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = calls["n"]
        calls["n"] += 1
        status, body = sequence[min(i, len(sequence) - 1)]
        return httpx.Response(status, json=body)

    return handler, calls


def _client_with_mock_transport(handler) -> BaseClient:
    bucket = TokenBucket(rate=1000.0, burst=1000)  # high capacity: acquire() never sleeps here
    client = BaseClient("https://example.test", bucket)
    client._client = httpx.AsyncClient(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    )
    return client


async def _instant_sleep(seconds: float) -> None:
    return None


def test_base_client_retries_on_429_then_succeeds():
    handler, calls = _sequenced_handler([(429, {}), (429, {}), (200, {"ok": True})])

    async def _run():
        client = _client_with_mock_transport(handler)
        with patch("asyncio.sleep", _instant_sleep):
            result = await client.get_json("/x")
        assert result == {"ok": True}
        assert calls["n"] == 3
        await client.aclose()

    asyncio.run(_run())


def test_base_client_does_not_retry_on_404():
    handler, calls = _sequenced_handler([(404, {"error": "not found"})])

    async def _run():
        client = _client_with_mock_transport(handler)
        with patch("asyncio.sleep", _instant_sleep), pytest.raises(httpx.HTTPStatusError):
            await client.get_json("/x")
        assert calls["n"] == 1
        await client.aclose()

    asyncio.run(_run())


def test_base_client_exhausts_after_the_configured_attempts():
    """Asserts against the configured budget rather than a literal, so raising
    it for a real reason (2026-07-31: five attempts collapsed into 16 seconds
    and lost a collector to a post-resume DNS gap) does not look like a
    regression here."""
    from kalshi_mt.api.http import _RETRY_ATTEMPTS

    handler, calls = _sequenced_handler([(500, {"error": "boom"})])

    async def _run():
        client = _client_with_mock_transport(handler)
        with patch("asyncio.sleep", _instant_sleep), pytest.raises(httpx.HTTPStatusError):
            await client.get_json("/x")
        assert calls["n"] == _RETRY_ATTEMPTS
        await client.aclose()

    asyncio.run(_run())


def test_dns_failure_is_retryable():
    """`getaddrinfo failed` killed a collector relaunched seconds after the host
    resumed from sleep. It arrives as httpx.ConnectError, a TransportError."""
    import httpx

    from kalshi_mt.api.http import _is_retryable

    assert _is_retryable(httpx.ConnectError("[Errno 11001] getaddrinfo failed"))


def test_retry_budget_outlasts_a_post_resume_network_gap():
    """The policy was never wrong about WHAT to retry -- it gave up too fast.
    wait_random_exponential draws from [0, 2^n], so five attempts collapsed into
    16 seconds while DNS was still coming back. The floor is what fixes it."""
    from kalshi_mt.api.http import _RETRY_ATTEMPTS, _RETRY_WAIT

    class _State:
        def __init__(self, n):
            self.attempt_number = n
            self.outcome = None
            self.idle_for = 0.0
            self.seconds_since_start = 0.0

    waits = [_RETRY_WAIT(_State(n)) for n in range(1, _RETRY_ATTEMPTS)]
    assert all(w >= 2.0 for w in waits), f"a wait with no floor defeats the point: {waits}"
    # Enough total patience to cover a network stack coming back after resume.
    assert sum(waits) >= 120.0, f"total retry window too short: {sum(waits):.1f}s"


def test_retry_budget_stays_bounded():
    """A genuinely dead endpoint must still fail rather than retry forever."""
    from kalshi_mt.api.http import _RETRY_ATTEMPTS

    assert _RETRY_ATTEMPTS <= 10
