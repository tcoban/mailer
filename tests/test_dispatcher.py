import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from src.worker.dispatcher import Dispatcher
from src.db.models import Outbox, Message, MessageStatus
from src.services.provider_interface import SendResult

@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session

@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    return provider

@pytest.mark.asyncio
async def test_dispatcher_process_batch_empty(mock_session, mock_provider):
    dispatcher = Dispatcher(provider=mock_provider)
    
    # Mock result with no entries
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result
    
    processed = await dispatcher._process_batch(mock_session)
    assert processed == 0

@pytest.mark.asyncio
async def test_dispatcher_process_message_sent(mock_session, mock_provider):
    dispatcher = Dispatcher(provider=mock_provider)
    
    msg_id = uuid4()
    outbox = Outbox(message_id=msg_id, retry_count=0)
    msg = Message(id=msg_id, status=MessageStatus.QUEUED, subject="Test")
    
    mock_session.get.return_value = msg
    mock_provider.send.return_value = SendResult(
        status=MessageStatus.SENT, 
        provider_message_id="p-123"
    )
    
    # Mock circuit breaker to allow request
    with patch("src.worker.dispatcher.get_circuit_breaker") as mock_get_cb:
        mock_cb = AsyncMock()
        mock_cb.allow_request.return_value = True
        mock_cb.snapshot.return_value = {"failure_rate": 0.0}
        mock_get_cb.return_value = mock_cb
        
        await dispatcher._process_message(mock_session, outbox)
    
    assert msg.status == MessageStatus.SENT
    assert mock_session.delete.called # Outbox should be deleted
    assert dispatcher.batch_size == 11 # Adaptive throttling increase (if below limit)

@pytest.mark.asyncio
async def test_dispatcher_throttling_on_429(mock_session, mock_provider):
    dispatcher = Dispatcher(provider=mock_provider)
    dispatcher.batch_size = 10
    
    msg_id = uuid4()
    outbox = Outbox(message_id=msg_id, retry_count=0)
    msg = Message(id=msg_id, status=MessageStatus.QUEUED)
    
    mock_session.get.return_value = msg
    mock_provider.send.return_value = SendResult(
        status=MessageStatus.RETRY_PENDING,
        reason="GRAPH_RATE_LIMITED"
    )
    
    with patch("src.worker.dispatcher.get_circuit_breaker") as mock_get_cb:
        mock_cb = AsyncMock()
        mock_cb.allow_request.return_value = True
        mock_cb.snapshot.return_value = {"failure_rate": 0.0}
        mock_get_cb.return_value = mock_cb
        
        await dispatcher._process_message(mock_session, outbox)
    
    assert dispatcher.batch_size == 5 # Reduced by half
    assert dispatcher.poll_interval == 2.0 # Doubled
