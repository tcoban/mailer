"""
Tests for the Webhook Receiver.

- Unit tests for event mapping functions (pure logic)
- Unit tests for HMAC signature verification
"""

import hashlib
import hmac
import pytest

from src.api.routes import (
    _map_graph_event_to_status,
    _map_generic_event_to_status,
    _verify_hmac_signature,
)
from src.db.models import MessageStatus


class TestHMACSignatureVerification:
    """Test the _verify_hmac_signature helper."""

    def test_valid_signature(self):
        body = b'{"event": "delivered"}'
        secret = "my-secret-key"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_hmac_signature(body, sig, secret) is True

    def test_invalid_signature(self):
        body = b'{"event": "delivered"}'
        secret = "my-secret-key"
        assert _verify_hmac_signature(body, "wrong-signature", secret) is False

    def test_empty_secret_skips_check(self):
        """If no secret is configured, verification is disabled."""
        body = b'{"event": "delivered"}'
        assert _verify_hmac_signature(body, "", "") is True
        assert _verify_hmac_signature(body, "anything", "") is True

    def test_tampered_body_detected(self):
        body = b'{"event": "delivered"}'
        secret = "my-secret-key"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        tampered = b'{"event": "bounced"}'
        assert _verify_hmac_signature(tampered, sig, secret) is False


class TestGraphEventMapping:
    """Test Graph changeType → MessageStatus mapping."""

    def test_delivered(self):
        assert _map_graph_event_to_status("delivered") == MessageStatus.DELIVERED

    def test_bounced(self):
        assert _map_graph_event_to_status("bounced") == MessageStatus.BOUNCED

    def test_failed(self):
        assert _map_graph_event_to_status("failed") == MessageStatus.FAILED

    def test_case_insensitive(self):
        assert _map_graph_event_to_status("DELIVERED") == MessageStatus.DELIVERED
        assert _map_graph_event_to_status("Bounced") == MessageStatus.BOUNCED

    def test_unknown_returns_none(self):
        assert _map_graph_event_to_status("unknown_event") is None
        assert _map_graph_event_to_status("sent") is None


class TestGenericEventMapping:
    """Test generic provider event → MessageStatus mapping."""

    def test_delivered(self):
        assert _map_generic_event_to_status("delivered") == MessageStatus.DELIVERED

    def test_bounced_variants(self):
        assert _map_generic_event_to_status("bounced") == MessageStatus.BOUNCED
        assert _map_generic_event_to_status("bounce") == MessageStatus.BOUNCED

    def test_failed_variants(self):
        assert _map_generic_event_to_status("dropped") == MessageStatus.FAILED
        assert _map_generic_event_to_status("failed") == MessageStatus.FAILED

    def test_deferred(self):
        assert _map_generic_event_to_status("deferred") == MessageStatus.RETRY_PENDING

    def test_unknown_returns_none(self):
        assert _map_generic_event_to_status("nope") is None
        assert _map_generic_event_to_status("open") is None
