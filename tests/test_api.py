from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

# Mock dependencies before importing main to avoid DB connection attempts
with patch("src.db.session.async_session_maker"), \
     patch("src.worker.dispatcher.Dispatcher"):
    from src.main import app
    from src.db.models import Message, Outbox, MessageStatus

client = TestClient(app)

@pytest.fixture
def mock_db():
    session = AsyncMock(spec=AsyncSession)
    return session

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get.return_value = None # Cache miss
    return redis

@pytest.mark.asyncio
async def test_create_message_success(mock_db, mock_redis):
    # Override dependencies
    from src.db.session import get_db_session
    from src.core.redis_client import get_redis_client
    
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_redis_client] = lambda: mock_redis

    payload = {
        "subject": "Hello World",
        "body": "<h1>Hi</h1>",
        "from_address": "sender@example.com",
        "to": [{"email": "recipient@example.com", "name": "Recipient"}],
        "body_content_type": "text/html"
    }
    
    headers = {
        "Idempotency-Key": "12345678-1234-1234-1234-1234567890ab"
    }

    # Setup mock_db side effects if needed (add/flush/commit)
    # AsyncMock handles awaitables automatically
    
    response = client.post("/v1/messages", json=payload, headers=headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["subject"] == "Hello World"
    assert data["status"] == "QUEUED"
    assert "id" in data
    
    # Verify DB interactions
    assert mock_db.add.call_count >= 2 # Message + Outbox
    assert mock_db.commit.called
    
    # Verify Redis interaction (Idempotency save)
    # get_redis_client returns a generator, but dependency override handles the value if lambda returns directly
    # In FastApi, async generator dependencies are context managed.
    # Our override is a simple lambda.
    # Check setex call
    assert mock_redis.setex.called

@pytest.mark.asyncio
async def test_create_message_idempotency_conflict(mock_db, mock_redis):
    # Simulate Redis hit with DIFFERENT payload hash
    import json
    cached_response = {
        "request_hash": "different_hash",
        "response_body": {"id": "old_id", "status": "QUEUED"},
        "response_status": 201
    }
    mock_redis.get.return_value = json.dumps(cached_response)
    
    payload = {
        "subject": "New Subject",
        "body": "Hi",
        "from_address": "s@ex.com",
        "to": [{"email": "r@ex.com", "name": "R"}]
    }
    headers = {"Idempotency-Key": "same-key"}
    
    response = client.post("/v1/messages", json=payload, headers=headers)
    assert response.status_code == 409
    assert "Idempotency conflict" in response.json()["title"]

@pytest.mark.asyncio
async def test_cancel_message_success(mock_db):
    from src.db.session import get_db_session
    from src.db.models import Message, MessageStatus
    
    app.dependency_overrides[get_db_session] = lambda: mock_db
    
    msg_id = uuid4()
    mock_msg = MagicMock(spec=Message)
    mock_msg.id = msg_id
    mock_msg.status = MessageStatus.QUEUED
    
    mock_db.get.return_value = mock_msg
    
    response = client.delete(f"/v1/messages/{msg_id}")
    assert response.status_code == 204
    assert mock_msg.status == MessageStatus.CANCELLED
    assert mock_db.execute.called # For delete(Outbox)
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_cancel_message_not_found(mock_db):
    from src.db.session import get_db_session
    app.dependency_overrides[get_db_session] = lambda: mock_db
    mock_db.get.return_value = None
    
    response = client.delete(f"/v1/messages/{uuid4()}")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_cancel_message_invalid_status(mock_db):
    from src.db.session import get_db_session
    from src.db.models import Message, MessageStatus
    
    app.dependency_overrides[get_db_session] = lambda: mock_db
    
    msg_id = uuid4()
    mock_msg = MagicMock(spec=Message)
    mock_msg.id = msg_id
    mock_msg.status = MessageStatus.SENT # Cannot cancel if SENT
    
    mock_db.get.return_value = mock_msg
    
    response = client.delete(f"/v1/messages/{msg_id}")
    assert response.status_code == 400
    assert "Cannot cancel message in status" in response.json()["detail"]

