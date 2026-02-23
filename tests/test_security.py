"""
Unit tests for PII encryption/decryption.
"""

import pytest
from cryptography.fernet import Fernet


class TestEncryptDecrypt:
    """Test encrypt_pii / decrypt_pii round trips."""

    def test_roundtrip_basic(self):
        from src.core.security import encrypt_pii, decrypt_pii

        plaintext = "Hello, this is PII data!"
        encrypted = encrypt_pii(plaintext)
        assert encrypted != plaintext  # Not stored in clear
        decrypted = decrypt_pii(encrypted)
        assert decrypted == plaintext

    def test_roundtrip_html_body(self):
        from src.core.security import encrypt_pii, decrypt_pii

        html = "<html><body><h1>Private Info</h1><p>SSN: 123-45-6789</p></body></html>"
        encrypted = encrypt_pii(html)
        assert "123-45-6789" not in encrypted
        assert decrypt_pii(encrypted) == html

    def test_roundtrip_unicode(self):
        from src.core.security import encrypt_pii, decrypt_pii

        text = "Ünïcödé tëxt with émojis 🔐🛡️"
        assert decrypt_pii(encrypt_pii(text)) == text

    def test_empty_string_passthrough(self):
        from src.core.security import encrypt_pii, decrypt_pii

        assert encrypt_pii("") == ""
        assert decrypt_pii("") == ""

    def test_none_like_empty(self):
        """None/empty should be handled gracefully."""
        from src.core.security import encrypt_pii, decrypt_pii

        assert encrypt_pii("") == ""
        assert decrypt_pii("") == ""

    def test_different_encryptions_differ(self):
        """Fernet uses a random IV, so encrypting the same text twice should produce different ciphertexts."""
        from src.core.security import encrypt_pii

        text = "same plaintext"
        enc1 = encrypt_pii(text)
        enc2 = encrypt_pii(text)
        assert enc1 != enc2  # Different IVs

    def test_invalid_token_raises(self):
        from src.core.security import decrypt_pii

        with pytest.raises(Exception):
            decrypt_pii("not-a-valid-fernet-token")
