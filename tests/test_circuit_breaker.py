"""
Unit tests for the robust Circuit Breaker.
"""

import asyncio
import time
import pytest

from src.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    _SlidingWindow,
)


# ---------------------------------------------------------------------------
# Sliding window
# ---------------------------------------------------------------------------

class TestSlidingWindow:
    def test_record_and_stats(self):
        w = _SlidingWindow(duration=10.0)
        w.record(success=True)
        w.record(success=False)
        w.record(success=True)
        total, successes, failures = w.stats()
        assert total == 3
        assert successes == 2
        assert failures == 1

    def test_reset(self):
        w = _SlidingWindow(duration=10.0)
        w.record(success=True)
        w.record(success=False)
        w.reset()
        total, _, _ = w.stats()
        assert total == 0

    def test_empty_stats(self):
        w = _SlidingWindow(duration=10.0)
        total, successes, failures = w.stats()
        assert total == 0
        assert successes == 0
        assert failures == 0


# ---------------------------------------------------------------------------
# Circuit Breaker state machine
# ---------------------------------------------------------------------------

class TestCircuitBreakerStates:
    """Test the CLOSED → OPEN → HALF_OPEN → CLOSED cycle."""

    @pytest.fixture
    def fast_cb(self):
        """A circuit breaker with low thresholds for quick testing."""
        config = CircuitBreakerConfig(
            window_duration=60.0,
            failure_rate_threshold=0.5,
            minimum_calls=4,
            recovery_timeout=0.1,  # 100ms for fast test
            half_open_max_calls=2,
        )
        return CircuitBreaker("test_provider", config)

    @pytest.mark.asyncio
    async def test_starts_closed(self, fast_cb):
        assert fast_cb.state == CircuitState.CLOSED
        assert await fast_cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_stays_closed_under_threshold(self, fast_cb):
        """Below minimum_calls, circuit stays closed even with failures."""
        await fast_cb.record_failure()
        await fast_cb.record_failure()
        await fast_cb.record_failure()  # 3 failures, but minimum_calls is 4
        assert fast_cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_on_failure_rate(self, fast_cb):
        """When failure rate ≥ 50% with ≥ minimum_calls, circuit opens."""
        # 2 successes + 2 failures = 50% rate → should trip
        await fast_cb.record_success()
        await fast_cb.record_success()
        await fast_cb.record_failure()
        await fast_cb.record_failure()
        assert fast_cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_blocks_requests(self, fast_cb):
        # Trip the breaker
        await fast_cb.record_success()
        await fast_cb.record_success()
        await fast_cb.record_failure()
        await fast_cb.record_failure()
        assert fast_cb.state == CircuitState.OPEN
        assert await fast_cb.allow_request() is False

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, fast_cb):
        """After recovery_timeout elapses, transition OPEN → HALF_OPEN."""
        # Trip the breaker
        await fast_cb.record_success()
        await fast_cb.record_success()
        await fast_cb.record_failure()
        await fast_cb.record_failure()
        assert fast_cb.state == CircuitState.OPEN

        # Wait for recovery
        await asyncio.sleep(0.15)  # > 0.1s recovery_timeout
        allowed = await fast_cb.allow_request()
        assert allowed is True
        assert fast_cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_closes_on_success(self, fast_cb):
        """Enough successes in HALF_OPEN → CLOSED."""
        # Trip
        await fast_cb.record_success()
        await fast_cb.record_success()
        await fast_cb.record_failure()
        await fast_cb.record_failure()

        # Wait for half-open
        await asyncio.sleep(0.15)
        await fast_cb.allow_request()
        assert fast_cb.state == CircuitState.HALF_OPEN

        # Probe successes
        await fast_cb.record_success()
        await fast_cb.record_success()  # half_open_max_calls = 2
        assert fast_cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_reopens_on_failure(self, fast_cb):
        """Any failure in HALF_OPEN → OPEN again."""
        # Trip
        await fast_cb.record_success()
        await fast_cb.record_success()
        await fast_cb.record_failure()
        await fast_cb.record_failure()

        # Wait for half-open
        await asyncio.sleep(0.15)
        await fast_cb.allow_request()
        assert fast_cb.state == CircuitState.HALF_OPEN

        # Probe failure
        await fast_cb.record_failure()
        assert fast_cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_snapshot(self, fast_cb):
        snap = fast_cb.snapshot()
        assert snap["name"] == "test_provider"
        assert snap["state"] == "CLOSED"
        assert snap["window_total"] == 0
        assert snap["failure_rate"] == 0.0
