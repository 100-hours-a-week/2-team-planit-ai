from fastapi import APIRouter
from app.api.V1.endpoint.Itinerary.Itineray import router as itinerary_router

router = APIRouter()
router.include_router(itinerary_router)
