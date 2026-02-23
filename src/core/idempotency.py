import hashlib
import json
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from src.db.models import IdempotencyKey

class IdempotencyService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.ttl = 86400  # 24 hours

    def _hash_request(self, body: Dict[str, Any]) -> str:
        # Simple JSON canonicalization
        canonical = json.dumps(body, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def check_idempotency(self, key: str, body: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[int]]:
        """
        Checks if the request has been processed.
        Returns: (is_hit, response_body, response_status)
        """
        request_hash = self._hash_request(body)
        
        # 1. Check Redis (Fast Path)
        cached = await self.redis.get(f"idempotency:{key}")
        if cached:
            data = json.loads(cached)
            if data["request_hash"] == request_hash:
                return True, data["response_body"], data["response_status"]
            else:
                # Conflict
                raise IdempotencyConflictError(key)

        # 2. Check DB (Authoritative)
        stmt = select(IdempotencyKey).where(IdempotencyKey.key == key)
        result = await self.db.execute(stmt)
        record = result.scalars().first()
        
        if record:
            if record.request_hash == request_hash:
                # Hit in DB, cache back to Redis
                response_data = {
                    "request_hash": request_hash,
                    "response_body": record.response_body,
                    "response_status": record.response_status
                }
                await self.redis.setex(f"idempotency:{key}", self.ttl, json.dumps(response_data))
                return True, record.response_body, record.response_status
            else:
                raise IdempotencyConflictError(key)

        return False, None, None

    async def save_idempotency(self, key: str, body: Dict[str, Any], response_body: Dict[str, Any], status: int):
        request_hash = self._hash_request(body)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl)
        
        # Save to DB
        record = IdempotencyKey(
            key=key,
            request_hash=request_hash,
            response_body=response_body,
            response_status=status,
            expires_at=expires_at
        )
        self.db.add(record)
        # We assume caller commits

        # Save to Redis
        data = {
            "request_hash": request_hash,
            "response_body": response_body,
            "response_status": status
        }
        await self.redis.setex(f"idempotency:{key}", self.ttl, json.dumps(data))

class IdempotencyConflictError(Exception):
    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Idempotency conflict for key {key}")
