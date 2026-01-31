from fastapi import FastAPI

from app.api.routes import api_router

app = FastAPI(
    title="PlanIt Agent API",
    description="여행 일정 추천 AI Agent API",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "UP"}