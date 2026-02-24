import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import api_router
from app.core.config import settings
from app.core.redis_client import RedisClient
from app.worker.itinerary_worker import run_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: Consumer Group 생성 보장
    await RedisClient.ensure_consumer_group(
        settings.redis_request_stream,
        settings.redis_consumer_group,
    )

    # 워커를 백그라운드 태스크로 시작
    shutdown_event = asyncio.Event()
    worker_task = asyncio.create_task(run_worker(shutdown_event))

    yield

    # shutdown: 워커에 종료 신호 보내고 대기
    shutdown_event.set()
    try:
        await asyncio.wait_for(worker_task, timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Worker 종료 타임아웃 — 태스크 취소")
        worker_task.cancel()
    except Exception:
        logger.exception("Worker 종료 중 오류")

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
