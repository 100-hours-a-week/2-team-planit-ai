from fastapi import APIRouter
from app.api.V1.endpoint.Itinerary.Itineray import router as itinerary_router
from app.api.V1.endpoint.Chatbot.Chatbot import router as chatbot_router

router = APIRouter()
router.include_router(itinerary_router)
router.include_router(chatbot_router)
