"""Pydantic schemas for incoming webhook payloads."""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    """Generic webhook envelope used for providers like SendGrid, Mailgun, etc."""
    event_type: str = Field(..., description="e.g. 'delivered', 'bounced', 'dropped'")
    message_id: Optional[str] = Field(None, description="Our internal message ID if echoed back")
    provider_message_id: Optional[str] = Field(None, description="Provider's own message reference")
    timestamp: Optional[datetime] = None
    raw: Optional[Dict[str, Any]] = None


# MS Graph Change Notification shapes
# https://learn.microsoft.com/en-us/graph/webhooks

class GraphResourceData(BaseModel):
    """The resourceData portion of a Graph change notification."""
    id: Optional[str] = Field(None, alias="id")
    odata_type: Optional[str] = Field(None, alias="@odata.type")
    odata_id: Optional[str] = Field(None, alias="@odata.id")
    odata_etag: Optional[str] = Field(None, alias="@odata.etag")

    model_config = {"populate_by_name": True}


class GraphChangeNotificationItem(BaseModel):
    """A single change notification from MS Graph subscription."""
    subscription_id: Optional[str] = Field(None, alias="subscriptionId")
    subscription_expiration: Optional[str] = Field(None, alias="subscriptionExpirationDateTime")
    change_type: str = Field(..., alias="changeType")
    resource: str = Field(...)
    resource_data: Optional[GraphResourceData] = Field(None, alias="resourceData")
    client_state: Optional[str] = Field(None, alias="clientState")
    tenant_id: Optional[str] = Field(None, alias="tenantId")

    model_config = {"populate_by_name": True}


class GraphChangeNotification(BaseModel):
    """Top-level MS Graph webhook payload containing multiple notifications."""
    value: List[GraphChangeNotificationItem]


# Event type mapping: provider event string → our internal event types
GRAPH_EVENT_MAP = {
    "updated": "status_changed",
    "created": "created",
    "deleted": "deleted",
}

# Delivery status keywords from Graph that map to our status model
GRAPH_STATUS_MAP = {
    "delivered": "DELIVERED",
    "bounced": "BOUNCED",
    "failed": "FAILED",
}
