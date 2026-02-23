from cryptography.fernet import Fernet
from src.core.config import settings

# Initialize Fernet with the key from settings
# We do this at module level so it's ready to use
# Ensure PII_ENCRYPTION_KEY is a valid base64 encoded 32-byte key
_fernet = Fernet(settings.PII_ENCRYPTION_KEY)

def encrypt_pii(data: str) -> str:
    """Encrypts a string containing PII."""
    if not data:
        return data
    return _fernet.encrypt(data.encode()).decode()

def decrypt_pii(token: str) -> str:
    """Decrypts a PII token back to the original string."""
    if not token:
        return token
    return _fernet.decrypt(token.encode()).decode()
