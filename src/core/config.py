from typing import Any, Dict, Optional
from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "KOFMailer"
    API_V1_STR: str = "/v1"
    
    # Security
    # 32 url-safe base64-encoded bytes for Fernet encryption
    # Generate with: cryptography.fernet.Fernet.generate_key().decode()
    PII_ENCRYPTION_KEY: str

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "mailer"
    POSTGRES_PORT: int = 5432
    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        
        # We need to construct the URL from components if not provided directly
        # Pydantic v2 validation context is different, but let's try a simple approach
        # Accessing other fields is tricky in v2 field_validator without 'values' depending on context
        # Ideally, we should just rely on the env var or construct it.
        # For simplicity in this one-shot, let's assume if it's not set, we build it.
        # But `values` is actually `ValidationInfo` in v2 basically or similar.
        # Actually in Pydantic V2 `values` argument is deprecated for `ValidationInfo`.
        # Let's simplify: require DATABASE_URL or build it in a property or post_init,
        # but BaseSettings parses env vars.
        # Let's use a computed_field or simply allow it to be None and compute it later?
        # No, let's just default to a standard construction.
        return v

    # Redis (for Idempotency & Rate Limiting)
    REDIS_URI: RedisDsn = "redis://localhost:6379/0"

    # MS Graph
    MS_GRAPH_TENANT_ID: str
    MS_GRAPH_CLIENT_ID: str
    MS_GRAPH_CLIENT_SECRET: str
    MS_GRAPH_USER_ID: str  # The user to send as (or generic sender)

    # Webhook
    WEBHOOK_SIGNING_SECRET: str = ""  # HMAC-SHA256 secret for webhook signature verification

    model_config = SettingsConfigDict(
        env_file=".env", 
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def async_database_url(self) -> str:
        """Returns the async database URL for SQLAlchemy (asyncpg)."""
        if self.SQLALCHEMY_DATABASE_URI:
            return str(self.SQLALCHEMY_DATABASE_URI)
        # Fallback construction
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


settings = Settings()
