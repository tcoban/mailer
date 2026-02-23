"""
Robust Circuit Breaker for provider calls.

Features:
- Sliding‐window (time‐based) failure‐rate calculation
- Three states: CLOSED → OPEN → HALF_OPEN → CLOSED
- Per-provider instances via registry
- asyncio.Lock for concurrency safety
- Configurable thresholds and timeouts
- Prometheus gauge integration (deferred import)
- Structured‐log state‐change notifications
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Dict, Optional

from structlog import get_logger

logger = get_logger()


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@unique
class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Tunable knobs for the circuit breaker."""

    # Sliding window (seconds) to track failures
    window_duration: float = 60.0

    # If failure *rate* inside the window exceeds this, open the circuit.
    # Range: 0.0 – 1.0.  0.5 = 50 % of calls failed.
    failure_rate_threshold: float = 0.5

    # Minimum number of calls in the window before the failure rate is
    # evaluated.  Avoids tripping on the first request.
    minimum_calls: int = 10

    # How long to stay OPEN before transitioning to HALF_OPEN (seconds).
    recovery_timeout: float = 60.0

    # Number of consecutive successes in HALF_OPEN needed to close again.
    half_open_max_calls: int = 3


# ---------------------------------------------------------------------------
# Outcome tracker (sliding window)
# ---------------------------------------------------------------------------

@dataclass
class _CallOutcome:
    timestamp: float
    success: bool


class _SlidingWindow:
    """Time‐based sliding window of call outcomes."""

    def __init__(self, duration: float) -> None:
        self._duration = duration
        self._outcomes: deque[_CallOutcome] = deque()

    def record(self, success: bool) -> None:
        now = time.monotonic()
        self._outcomes.append(_CallOutcome(timestamp=now, success=success))
        self._evict(now)

    def stats(self) -> tuple[int, int, int]:
        """Return (total, successes, failures) inside current window."""
        now = time.monotonic()
        self._evict(now)
        total = len(self._outcomes)
        successes = sum(1 for o in self._outcomes if o.success)
        return total, successes, total - successes

    def reset(self) -> None:
        self._outcomes.clear()

    # ── private ──
    def _evict(self, now: float) -> None:
        cutoff = now - self._duration
        while self._outcomes and self._outcomes[0].timestamp < cutoff:
            self._outcomes.popleft()


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Async‐safe circuit breaker with sliding window failure‐rate detection.

    Usage::

        cb = CircuitBreaker("msgraph")
        if not cb.allow_request():
            return SendResult(status=RETRY_PENDING, reason="CIRCUIT_OPEN")
        result = await provider.send(msg)
        cb.record_success() / cb.record_failure()
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self.name = name
        self.cfg = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._lock = asyncio.Lock()
        self._window = _SlidingWindow(self.cfg.window_duration)
        self._opened_at: float = 0.0
        self._half_open_successes: int = 0
        self._half_open_calls: int = 0

    # ── public query ──

    @property
    def state(self) -> CircuitState:
        return self._state

    async def allow_request(self) -> bool:
        """Check whether a request may proceed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self.cfg.recovery_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                    self._half_open_successes = 0
                    self._half_open_calls = 0
                    return True  # allow probe request
                return False  # still open

            # HALF_OPEN: allow limited calls (up to half_open_max_calls)
            if self._half_open_calls < self.cfg.half_open_max_calls:
                return True
            return False

    async def record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                self._half_open_calls += 1
                if self._half_open_successes >= self.cfg.half_open_max_calls:
                    self._window.reset()
                    self._transition(CircuitState.CLOSED)
                return

            self._window.record(success=True)

    async def record_failure(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half‐open → re‐open immediately
                self._half_open_calls += 1
                self._transition(CircuitState.OPEN)
                self._opened_at = time.monotonic()
                return

            self._window.record(success=False)
            self._maybe_trip()

    # ── introspection (for Prometheus / admin) ──

    def snapshot(self) -> Dict:
        total, successes, failures = self._window.stats()
        return {
            "name": self.name,
            "state": self._state.value,
            "window_total": total,
            "window_failures": failures,
            "failure_rate": failures / total if total else 0.0,
        }

    # ── private ──

    def _maybe_trip(self) -> None:
        total, _, failures = self._window.stats()
        if total < self.cfg.minimum_calls:
            return
        rate = failures / total
        if rate >= self.cfg.failure_rate_threshold:
            self._transition(CircuitState.OPEN)
            self._opened_at = time.monotonic()

    def _transition(self, new_state: CircuitState) -> None:
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        logger.warning(
            "circuit_breaker_transition",
            breaker=self.name,
            old_state=old.value,
            new_state=new_state.value,
            **self.snapshot(),
        )


# ---------------------------------------------------------------------------
# Per‐provider Registry
# ---------------------------------------------------------------------------

_registry: Dict[str, CircuitBreaker] = {}
_registry_lock = asyncio.Lock()


async def get_circuit_breaker(
    provider_name: str,
    config: Optional[CircuitBreakerConfig] = None,
) -> CircuitBreaker:
    """Retrieve or create a circuit breaker for *provider_name*."""
    async with _registry_lock:
        if provider_name not in _registry:
            _registry[provider_name] = CircuitBreaker(provider_name, config)
        return _registry[provider_name]


def get_circuit_breaker_sync(provider_name: str) -> Optional[CircuitBreaker]:
    """Non‐async accessor for metrics scraping."""
    return _registry.get(provider_name)


def all_breakers() -> Dict[str, CircuitBreaker]:
    """Return the full registry (read‐only snapshot)."""
    return dict(_registry)
