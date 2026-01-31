from fastapi import APIRouter
from app.api.V1.routers import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/v1")
