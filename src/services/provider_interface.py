from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from src.db.models import MessageStatus

@dataclass
class SendResult:
    status: MessageStatus
    reason: str
    provider_message_id: Optional[str] = None
    retry_after: Optional[int] = None  # Seconds
    raw_response: Optional[Dict[str, Any]] = None

@dataclass
class EmailAddress:
    email: str
    name: Optional[str] = None

@dataclass
class EmailMessage:
    subject: str
    body: str
    from_address: EmailAddress
    to_addresses: List[EmailAddress]
    cc_addresses: Optional[List[EmailAddress]] = None
    bcc_addresses: Optional[List[EmailAddress]] = None
    body_content_type: str = "text/html"

class EmailProvider(ABC):
    """
    Abstract interface for email providers (e.g., MS Graph, SMTP, SES).
    """
    
    @abstractmethod
    async def send(self, message: EmailMessage) -> SendResult:
        """
        Sends an email message via the provider.
        Must handle provider-specific errors and return a standardized SendResult.
        """
        pass
