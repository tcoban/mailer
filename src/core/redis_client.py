from typing import AsyncGenerator
import redis.asyncio as redis
from src.core.config import settings

async def get_redis_client() -> AsyncGenerator[redis.Redis, None]:
    client = redis.from_url(str(settings.REDIS_URI), encoding="utf-8", decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
