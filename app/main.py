from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import api_router
from app.core.config import settings
from app.core.redis_client import RedisClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: Consumer Group 생성 보장
    await RedisClient.ensure_consumer_group(
        settings.redis_request_stream,
        settings.redis_consumer_group,
    )
    yield
    # shutdown: Redis 연결 정리
    await RedisClient.close()


app = FastAPI(
    title="PlanIt Agent API",
    description="여행 일정 추천 AI Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "UP"}
