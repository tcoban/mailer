import hashlib
import hmac
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Request, BackgroundTasks, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from structlog import get_logger

from src.db.session import get_db_session
from src.db.models import Message, Outbox, ProviderEvent, MessageStatus
from src.schemas.message import MessageCreate, MessageResponse, MessageListResponse
from src.schemas.webhook import GraphChangeNotification, WebhookPayload
from src.core.idempotency import IdempotencyService, IdempotencyConflictError
from src.core.redis_client import get_redis_client
from src.core.security import encrypt_pii
from src.core.config import settings
from src.domain.lifecycle import can_transition

router = APIRouter()
logger = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_hmac_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for generic webhook providers."""
    if not secret:
        return True  # Signature verification disabled if no secret configured
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_idempotency_service(
    db: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis_client),
) -> IdempotencyService:
    return IdempotencyService(db, redis)


# ---------------------------------------------------------------------------
# POST /messages
# ---------------------------------------------------------------------------

@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    message_in: MessageCreate,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    db: AsyncSession = Depends(get_db_session),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
):
    """
    Enqueue a message for delivery.
    Requires Idempotency-Key header.
    """

    # Check Idempotency
    try:
        body_dict = message_in.model_dump(mode="json")
        is_hit, cached_response, cached_status = await idempotency.check_idempotency(
            idempotency_key, body_dict
        )

        if is_hit:
            logger.info("idempotency_hit", key=idempotency_key)
            return JSONResponse(
                content=cached_response,
                status_code=cached_status,
                headers={"Idempotency-Replayed": "true"},
            )

    except IdempotencyConflictError:
        logger.warning("idempotency_conflict", key=idempotency_key)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "type": "https://docs.mailer.example/errors/idempotency-conflict",
                "title": "Idempotency conflict",
                "status": 409,
                "detail": "Idempotency-Key already used with different payload",
                "instance": str(request.url),
            },
        )

    # Encrypt Body
    encrypted_body = encrypt_pii(message_in.body)

    # Create Message
    db_message = Message(
        subject=message_in.subject,
        from_address=message_in.from_address,
        to_addresses=[r.email for r in message_in.to],
        cc_addresses=[r.email for r in message_in.cc] if message_in.cc else None,
        bcc_addresses=[r.email for r in message_in.bcc] if message_in.bcc else None,
        encrypted_body=encrypted_body,
        body_content_type=message_in.body_content_type,
        campaign_id=message_in.campaign_id,
        tags=message_in.tags,
        metadata_fields=message_in.metadata,
        scheduled_at=message_in.scheduled_at,
        status=MessageStatus.QUEUED,
    )

    db.add(db_message)
    await db.flush()  # get ID

    # Outbox entry – schedule for future or now
    next_attempt = message_in.scheduled_at if message_in.scheduled_at else func.now()
    outbox_entry = Outbox(message_id=db_message.id, next_attempt_at=next_attempt)
    db.add(outbox_entry)

    # Build response & persist idempotency
    response_obj = MessageResponse.model_validate(db_message)
    response_dict = response_obj.model_dump(mode="json")

    await idempotency.save_idempotency(
        key=idempotency_key,
        body=body_dict,
        response_body=response_dict,
        status=201,
    )

    await db.commit()
    logger.info("message_enqueued", message_id=str(db_message.id))
    return response_obj


# ---------------------------------------------------------------------------
# GET /messages  (cursor pagination)
# ---------------------------------------------------------------------------

@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    cursor: Optional[str] = Query(None, description="Opaque cursor (message UUID) for keyset pagination"),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[MessageStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db_session),
):
    """List messages with cursor-based (keyset) pagination."""

    stmt = select(Message).order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)

    if status_filter:
        stmt = stmt.where(Message.status == status_filter)

    if cursor:
        # Cursor is the UUID of the last item seen – fetch items created before it
        cursor_msg = await db.get(Message, cursor)
        if cursor_msg:
            stmt = stmt.where(
                (Message.created_at < cursor_msg.created_at)
                | (
                    (Message.created_at == cursor_msg.created_at)
                    & (Message.id < cursor_msg.id)
                )
            )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = str(items[-1].id) if has_more and items else None

    return MessageListResponse(
        items=[MessageResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        total=len(items),
    )


# ---------------------------------------------------------------------------
# DELETE /messages/{id}  – Cancellation
# ---------------------------------------------------------------------------

@router.delete("/messages/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_message(
    id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Cancel a queued or retry-pending message.
    """
    msg = await db.get(Message, id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    if not can_transition(msg.status, MessageStatus.CANCELLED):
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel message in status {msg.status}"
        )

    # Remove from outbox if exists
    stmt = delete(Outbox).where(Outbox.message_id == id)
    await db.execute(stmt)

    msg.status = MessageStatus.CANCELLED
    msg.status_reason = "Cancelled by user"
    
    await db.commit()
    logger.info("message_cancelled", message_id=str(id))



# ---------------------------------------------------------------------------
# POST /webhooks/{provider}  – Webhook Receiver
# ---------------------------------------------------------------------------

@router.post("/webhooks/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Receives webhooks from email providers.

    - **graph**: MS Graph change notifications (supports validationToken handshake).
    - **generic**: HMAC-SHA256 signed payloads from SendGrid, Mailgun, etc.
    """

    # ── MS Graph validation-token handshake ──
    if provider == "graph":
        validation_token = request.query_params.get("validationToken")
        if validation_token:
            logger.info("graph_webhook_validation", token=validation_token[:8] + "…")
            return PlainTextResponse(content=validation_token, media_type="text/plain")

    # ── Read raw body for signature verification ──
    raw_body = await request.body()

    # ── HMAC signature verification (generic providers) ──
    if provider != "graph":
        sig_header = request.headers.get("X-Webhook-Signature", "")
        if not _verify_hmac_signature(raw_body, sig_header, settings.WEBHOOK_SIGNING_SECRET):
            logger.warning("webhook_signature_invalid", provider=provider)
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # ── Graph: validate clientState ──
    if provider == "graph" and settings.WEBHOOK_SIGNING_SECRET:
        try:
            payload = GraphChangeNotification.model_validate_json(raw_body)
            for item in payload.value:
                if item.client_state != settings.WEBHOOK_SIGNING_SECRET:
                    logger.warning("graph_webhook_client_state_mismatch", provider=provider)
                    raise HTTPException(status_code=403, detail="Invalid clientState")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Graph notification payload")

    # ── Audit log: persist raw event ──
    event = ProviderEvent(
        provider=provider,
        event_type="webhook",
        payload={"raw": raw_body.decode("utf-8", errors="replace")},
    )
    db.add(event)

    # ── Process payload ──
    try:
        if provider == "graph":
            await _process_graph_webhook(payload, db)
        else:
            generic = WebhookPayload.model_validate_json(raw_body)
            await _process_generic_webhook(generic, db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("webhook_processing_error", provider=provider, error=str(exc))
        # Still commit the audit log even if processing fails
        await db.commit()
        raise HTTPException(status_code=422, detail=f"Webhook processing error: {exc}")

    await db.commit()
    return {"status": "accepted"}


# ---------------------------------------------------------------------------
# Webhook processors
# ---------------------------------------------------------------------------

async def _process_graph_webhook(notification: GraphChangeNotification, db: AsyncSession):
    """Process MS Graph change notifications and update message statuses."""
    for item in notification.value:
        # Try to extract our message ID from the resource path or resourceData
        # Graph subscriptions for mail typically have resource like
        # "users/{id}/messages/{messageId}"
        # We map the provider's message ID to our internal one via provider_message_id
        resource_id = item.resource_data.id if item.resource_data else None
        if not resource_id:
            logger.debug("graph_webhook_no_resource_id", resource=item.resource)
            continue

        # Lookup by provider_message_id
        stmt = select(Message).where(Message.provider_message_id == resource_id)
        result = await db.execute(stmt)
        msg = result.scalars().first()

        if not msg:
            logger.debug("graph_webhook_unknown_message", provider_message_id=resource_id)
            continue

        # Determine new status from changeType
        new_status = _map_graph_event_to_status(item.change_type)
        if new_status and can_transition(msg.status, new_status):
            msg.status = new_status
            logger.info(
                "webhook_status_update",
                message_id=str(msg.id),
                old_status=msg.status,
                new_status=new_status.value,
            )


async def _process_generic_webhook(payload: WebhookPayload, db: AsyncSession):
    """Process generic webhook payload from providers like SendGrid/Mailgun."""
    if not payload.provider_message_id:
        logger.debug("generic_webhook_no_provider_id")
        return

    stmt = select(Message).where(Message.provider_message_id == payload.provider_message_id)
    result = await db.execute(stmt)
    msg = result.scalars().first()

    if not msg:
        logger.debug("generic_webhook_unknown_message", provider_message_id=payload.provider_message_id)
        return

    new_status = _map_generic_event_to_status(payload.event_type)
    if new_status and can_transition(msg.status, new_status):
        msg.status = new_status
        logger.info(
            "webhook_status_update",
            message_id=str(msg.id),
            new_status=new_status.value,
        )


def _map_graph_event_to_status(change_type: str) -> Optional[MessageStatus]:
    """Map Graph changeType to our MessageStatus."""
    mapping = {
        "delivered": MessageStatus.DELIVERED,
        "bounced": MessageStatus.BOUNCED,
        "failed": MessageStatus.FAILED,
    }
    return mapping.get(change_type.lower())


def _map_generic_event_to_status(event_type: str) -> Optional[MessageStatus]:
    """Map generic provider event types to MessageStatus."""
    mapping = {
        "delivered": MessageStatus.DELIVERED,
        "bounced": MessageStatus.BOUNCED,
        "bounce": MessageStatus.BOUNCED,
        "dropped": MessageStatus.FAILED,
        "failed": MessageStatus.FAILED,
        "deferred": MessageStatus.RETRY_PENDING,
    }
    return mapping.get(event_type.lower())
