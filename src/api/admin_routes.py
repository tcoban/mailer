"""
Admin routes for DLQ management.

Endpoints:
- GET  /admin/dlq            — list DLQ entries (paginated)
- POST /admin/dlq/{id}/replay — re‐queue a single DLQ entry back to outbox
- POST /admin/dlq/replay-all  — bulk replay all DLQ entries
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.db.session import get_db_session
from src.db.models import DeadLetterQueue, Message, Outbox, MessageStatus
from src.core.metrics import dlq_replayed_total

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DLQEntryResponse(BaseModel):
    id: UUID
    message_id: UUID
    reason: str
    failed_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DLQListResponse(BaseModel):
    items: List[DLQEntryResponse]
    total: int
    next_cursor: Optional[str] = None


class ReplayResponse(BaseModel):
    replayed: int
    message: str


# ---------------------------------------------------------------------------
# GET /admin/dlq
# ---------------------------------------------------------------------------

@router.get("/dlq", response_model=DLQListResponse)
async def list_dlq(
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """List Dead Letter Queue entries."""

    stmt = (
        select(DeadLetterQueue)
        .order_by(DeadLetterQueue.failed_at.desc())
        .limit(limit + 1)
    )

    if cursor:
        cursor_entry = await db.get(DeadLetterQueue, cursor)
        if cursor_entry:
            stmt = stmt.where(DeadLetterQueue.failed_at < cursor_entry.failed_at)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = str(items[-1].id) if has_more and items else None

    # Approximate total
    count_result = await db.execute(select(func.count()).select_from(DeadLetterQueue))
    total = count_result.scalar() or 0

    return DLQListResponse(
        items=[DLQEntryResponse.model_validate(e) for e in items],
        total=total,
        next_cursor=next_cursor,
    )


# ---------------------------------------------------------------------------
# POST /admin/dlq/{id}/replay
# ---------------------------------------------------------------------------

@router.post("/dlq/{dlq_id}/replay", response_model=ReplayResponse)
async def replay_single(
    dlq_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Re‐queue a single DLQ entry back to the outbox for retry."""

    entry = await db.get(DeadLetterQueue, dlq_id)
    if not entry:
        raise HTTPException(status_code=404, detail="DLQ entry not found")

    msg = await db.get(Message, entry.message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Reset message status
    msg.status = MessageStatus.QUEUED
    msg.status_reason = None

    # Create new outbox entry
    outbox = Outbox(message_id=msg.id, next_attempt_at=func.now(), retry_count=0)
    db.add(outbox)

    # Remove from DLQ
    await db.delete(entry)
    await db.commit()

    dlq_replayed_total.inc()
    logger.info("dlq_replay_single", message_id=str(msg.id), dlq_id=str(dlq_id))

    return ReplayResponse(replayed=1, message=f"Message {msg.id} re‐queued")


# ---------------------------------------------------------------------------
# POST /admin/dlq/replay-all
# ---------------------------------------------------------------------------

@router.post("/dlq/replay-all", response_model=ReplayResponse)
async def replay_all(
    db: AsyncSession = Depends(get_db_session),
):
    """Bulk replay: move *all* DLQ entries back to the outbox."""

    result = await db.execute(select(DeadLetterQueue))
    entries = result.scalars().all()

    if not entries:
        return ReplayResponse(replayed=0, message="DLQ is empty")

    replayed = 0
    for entry in entries:
        msg = await db.get(Message, entry.message_id)
        if not msg:
            await db.delete(entry)
            continue

        msg.status = MessageStatus.QUEUED
        msg.status_reason = None

        outbox = Outbox(message_id=msg.id, next_attempt_at=func.now(), retry_count=0)
        db.add(outbox)
        await db.delete(entry)
        replayed += 1

    await db.commit()

    dlq_replayed_total.inc(replayed)
    logger.info("dlq_replay_all", replayed=replayed)

    return ReplayResponse(replayed=replayed, message=f"{replayed} messages re‐queued from DLQ")
