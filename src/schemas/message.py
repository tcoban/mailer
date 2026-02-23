from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from src.db.models import MessageStatus

class Recipient(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class MessageCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    body: str
    from_address: EmailStr
    to: List[Recipient]
    cc: Optional[List[Recipient]] = None
    bcc: Optional[List[Recipient]] = None
    body_content_type: str = "text/html"
    campaign_id: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None

class MessageResponse(BaseModel):
    id: UUID
    status: MessageStatus
    created_at: datetime
    scheduled_at: Optional[datetime] = None
    provider_message_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class MessageListResponse(BaseModel):
    items: List[MessageResponse]
    next_cursor: Optional[str] = None
    total: int
