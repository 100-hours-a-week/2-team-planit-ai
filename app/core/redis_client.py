"""
Redis 연결 싱글턴 및 Stream 유틸리티

Redis Streams Consumer Group 기반 메시지 큐를 위한 연결 관리 모듈.
"""
import redis.asyncio as redis

from app.core.config import settings


class RedisClient:
    """Redis 연결 및 Stream 유틸리티"""

    _instance: redis.Redis | None = None

    @classmethod
    async def get_instance(cls) -> redis.Redis:
        if cls._instance is None:
            cls._instance = redis.from_url(
                settings.redis_url, decode_responses=True
            )
        return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.close()
            cls._instance = None

    @classmethod
    async def ensure_consumer_group(cls, stream: str, group: str):
        """Consumer Group이 없으면 생성 (멱등)"""
        r = await cls.get_instance()
        try:
            await r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
