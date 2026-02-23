"""
Shared pytest fixtures for KOFMailer tests.

Environment variables are loaded from .env by Settings() at module-import time,
so monkeypatch won't help.  We rely on the .env file having valid values.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db():
    """Async mock of SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


@pytest.fixture
def mock_redis():
    """Async mock of Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)  # Default: cache miss
    redis.setex = AsyncMock()
    redis.aclose = AsyncMock()
    return redis
