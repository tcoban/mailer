import time
import httpx
from typing import Optional, Dict
from src.core.config import settings
from src.services.provider_interface import EmailProvider, EmailMessage, SendResult
from src.db.models import MessageStatus
from structlog import get_logger

logger = get_logger()

class MSGraphAdapter(EmailProvider):
    def __init__(self):
        self.token: Optional[str] = None
        self.token_expires_at: float = 0
        self.client = httpx.AsyncClient(timeout=15.0)

    async def _get_access_token(self) -> str:
        if self.token and time.time() < self.token_expires_at - 60:
            return self.token

        url = f"https://login.microsoftonline.com/{settings.MS_GRAPH_TENANT_ID}/oauth2/v2.0/token"
        data = {
            "client_id": settings.MS_GRAPH_CLIENT_ID,
            "client_secret": settings.MS_GRAPH_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        
        try:
            resp = await self.client.post(url, data=data)
            resp.raise_for_status()
            payload = resp.json()
            self.token = payload["access_token"]
            self.token_expires_at = time.time() + payload["expires_in"]
            return self.token
        except httpx.HTTPError as e:
            logger.error("graph_auth_failed", error=str(e))
            raise

    async def send(self, message: EmailMessage) -> SendResult:
        try:
            token = await self._get_access_token()
        except Exception as e:
            return SendResult(
                status=MessageStatus.RETRY_PENDING,
                reason=f"GRAPH_AUTH_ERROR: {str(e)}",
                retry_after=30 # Wait before retry auth
            )

        # Build Graph payload
        # Ensure 'from' is the user we are sending as, or use /users/{id}/sendMail
        # The URL in _legacy_ts was /users/{from}/sendMail
        # We need to encode the sender email in URL
        sender_email = message.from_address.email
        url = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
        
        payload = {
            "message": {
                "subject": message.subject,
                "body": {
                    "contentType": "HTML" if message.body_content_type == "text/html" else "Text",
                    "content": message.body
                },
                "toRecipients": [{"emailAddress": {"address": a.email, "name": a.name}} for a in message.to_addresses],
                "ccRecipients": [{"emailAddress": {"address": a.email, "name": a.name}} for a in (message.cc_addresses or [])],
                "bccRecipients": [{"emailAddress": {"address": a.email, "name": a.name}} for a in (message.bcc_addresses or [])],
                # Attachments would go here
            },
            "saveToSentItems": False
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            resp = await self.client.post(url, json=payload, headers=headers)
            
            provider_message_id = resp.headers.get("request-id") or resp.headers.get("client-request-id")
            retry_after_header = resp.headers.get("Retry-After")
            retry_after = int(retry_after_header) if retry_after_header and retry_after_header.isdigit() else None

            if resp.status_code == 202:
                return SendResult(
                    status=MessageStatus.SENT,
                    reason="GRAPH_ACCEPTED",
                    provider_message_id=provider_message_id
                )
            elif resp.status_code == 429:
                return SendResult(
                    status=MessageStatus.RETRY_PENDING,
                    reason="GRAPH_RATE_LIMITED",
                    retry_after=retry_after or 60,
                    raw_response={"status": 429}
                )
            elif resp.status_code >= 500:
                return SendResult(
                    status=MessageStatus.RETRY_PENDING,
                    reason=f"GRAPH_PROVIDER_5XX: {resp.status_code}",
                    retry_after=retry_after or 30,
                    raw_response={"status": resp.status_code}
                )
            else:
                # 4xx (except 429) -> FAILED
                error_body = resp.text
                return SendResult(
                    status=MessageStatus.FAILED,
                    reason=f"GRAPH_PROVIDER_4XX: {resp.status_code} {error_body[:200]}",
                    raw_response={"status": resp.status_code, "body": error_body}
                )

        except httpx.RequestError as e:
            return SendResult(
                status=MessageStatus.RETRY_PENDING,
                reason=f"GRAPH_NETWORK_ERROR: {str(e)}",
                retry_after=10
            )

    async def close(self):
        await self.client.aclose()
