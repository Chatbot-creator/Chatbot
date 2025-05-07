from fastapi import APIRouter
from .users.routes import router as users_router
from .properties.routes import router as properties_router
from .chatbot.router import router as chatbot_router

router = APIRouter()

# Include routers from different app modules
router.include_router(users_router, prefix="/users", tags=["users"])
router.include_router(properties_router, prefix="/properties", tags=["properties"])
router.include_router(chatbot_router)  # Note: chatbot router already has prefix defined 