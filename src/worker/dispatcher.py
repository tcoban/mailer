"""
Outbox Dispatcher – processes queued messages using SKIP LOCKED.

Integrates:
- Circuit breaker (per-provider sliding-window)
- DLQ insertion on max retries
- Prometheus metrics
"""

import asyncio
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.db.session import async_session_maker
from src.db.models import Outbox, Message, MessageStatus, DeadLetterQueue
from src.services.provider_interface import EmailProvider, EmailMessage, EmailAddress
from src.adapters.graph_adapter import MSGraphAdapter
from src.core.security import decrypt_pii
from src.domain.lifecycle import can_transition, InvalidTransitionError
from src.core.circuit_breaker import get_circuit_breaker, CircuitState
from src.core.metrics import (
    messages_sent_total,
    messages_failed_total,
    messages_retried_total,
    dispatch_batch_duration_seconds,
    dispatch_batch_size,
    dlq_entries_total,
    circuit_breaker_state,
    circuit_breaker_failure_rate,
)

logger = get_logger()

# Constants
MAX_RETRIES = 5
BASE_BACKOFF = 30  # seconds
BATCH_SIZE = 10

# Circuit state → numeric for Prometheus gauge
_CB_STATE_MAP = {
    CircuitState.CLOSED: 0,
    CircuitState.OPEN: 1,
    CircuitState.HALF_OPEN: 2,
}


class Dispatcher:
    def __init__(self, provider: Optional[EmailProvider] = None, provider_name: str = "msgraph"):
        self.provider = provider or MSGraphAdapter()
        self.provider_name = provider_name
        self.running = False

    async def run_loop(self):
        """Main loop that polls for messages."""
        self.running = True
        logger.info("dispatcher_started")
        while self.running:
            processed = 0
            try:
                async with async_session_maker() as session:
                    processed = await self._process_batch(session)
            except Exception as e:
                logger.error("dispatcher_loop_error", error=str(e), traceback=traceback.format_exc())
                await asyncio.sleep(5)

            if processed == 0:
                await asyncio.sleep(1.0)

    async def _process_batch(self, session: AsyncSession) -> int:
        """Fetch and process a batch of messages using SKIP LOCKED."""
        now = datetime.now(timezone.utc)
        start = time.perf_counter()

        stmt = (
            select(Outbox)
            .where(Outbox.next_attempt_at <= now)
            .order_by(Outbox.next_attempt_at.asc())
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )

        result = await session.execute(stmt)
        outbox_entries = result.scalars().all()

        if not outbox_entries:
            return 0

        dispatch_batch_size.observe(len(outbox_entries))

        tasks = [self._process_message(session, entry) for entry in outbox_entries]
        await asyncio.gather(*tasks)
        await session.commit()

        elapsed = time.perf_counter() - start
        dispatch_batch_duration_seconds.observe(elapsed)

        return len(outbox_entries)

    async def _process_message(self, session: AsyncSession, outbox: Outbox):
        msg = await session.get(Message, outbox.message_id)
        if not msg:
            logger.error("outbox_orphan", message_id=outbox.message_id)
            await session.delete(outbox)
            return

        # ---------- Circuit Breaker check ----------
        cb = await get_circuit_breaker(self.provider_name)

        # Export circuit state metric
        circuit_breaker_state.labels(provider=self.provider_name).set(
            _CB_STATE_MAP.get(cb.state, 0)
        )
        snap = cb.snapshot()
        circuit_breaker_failure_rate.labels(provider=self.provider_name).set(
            snap["failure_rate"]
        )

        if not await cb.allow_request():
            # Circuit is OPEN – reschedule without calling provider
            outbox.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=BASE_BACKOFF)
            outbox.last_attempt_at = datetime.now(timezone.utc)
            logger.warning("circuit_open_skipped", message_id=str(msg.id), provider=self.provider_name)
            messages_retried_total.labels(provider=self.provider_name).inc()
            return

        # ---------- Prepare & Send ----------
        body = decrypt_pii(msg.encrypted_body)
        email_msg = EmailMessage(
            subject=msg.subject,
            body=body,
            from_address=EmailAddress(email=msg.from_address),
            to_addresses=[EmailAddress(email=e) for e in msg.to_addresses],
            cc_addresses=[EmailAddress(email=e) for e in (msg.cc_addresses or [])],
            bcc_addresses=[EmailAddress(email=e) for e in (msg.bcc_addresses or [])],
            body_content_type=msg.body_content_type,
        )

        send_result = await self.provider.send(email_msg)

        # ---------- Handle Result ----------
        if send_result.status == MessageStatus.SENT:
            await cb.record_success()
            msg.status = MessageStatus.SENT
            msg.status_reason = None
            msg.provider_message_id = send_result.provider_message_id
            msg.sent_at = datetime.now(timezone.utc)
            await session.delete(outbox)
            messages_sent_total.labels(provider=self.provider_name).inc()
            logger.info("message_sent", message_id=str(msg.id))

        elif send_result.status == MessageStatus.RETRY_PENDING:
            await cb.record_failure()
            outbox.retry_count += 1

            if outbox.retry_count >= MAX_RETRIES:
                # Move to DLQ
                msg.status = MessageStatus.FAILED
                msg.status_reason = "Max retries exceeded: " + (send_result.reason or "")

                dlq_entry = DeadLetterQueue(
                    message_id=msg.id,
                    reason=msg.status_reason,
                    payload_snapshot={
                        "subject": msg.subject,
                        "to": msg.to_addresses,
                        "retry_count": outbox.retry_count,
                        "last_error": send_result.reason,
                    },
                )
                session.add(dlq_entry)
                await session.delete(outbox)

                messages_failed_total.labels(reason="max_retries").inc()
                dlq_entries_total.inc()
                logger.error("message_failed_to_dlq", message_id=str(msg.id))
            else:
                retry_after = send_result.retry_after or (BASE_BACKOFF * (2 ** (outbox.retry_count - 1)))
                outbox.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
                outbox.last_attempt_at = datetime.now(timezone.utc)
                msg.status_reason = send_result.reason
                if can_transition(msg.status, MessageStatus.RETRY_PENDING):
                    msg.status = MessageStatus.RETRY_PENDING
                messages_retried_total.labels(provider=self.provider_name).inc()
                logger.info("message_retry_scheduled", message_id=str(msg.id), retry_after=retry_after)

        elif send_result.status == MessageStatus.FAILED:
            await cb.record_failure()
            msg.status = MessageStatus.FAILED
            msg.status_reason = send_result.reason

            dlq_entry = DeadLetterQueue(
                message_id=msg.id,
                reason=send_result.reason or "Permanent failure",
                payload_snapshot={
                    "subject": msg.subject,
                    "to": msg.to_addresses,
                    "retry_count": outbox.retry_count,
                    "last_error": send_result.reason,
                },
            )
            session.add(dlq_entry)
            await session.delete(outbox)

            messages_failed_total.labels(reason="permanent").inc()
            dlq_entries_total.inc()
            logger.error("message_failed_permanent", message_id=str(msg.id), reason=send_result.reason)
