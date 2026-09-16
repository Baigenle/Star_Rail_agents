from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    catalog,
    chat,
    custom_characters,
    health,
    memories,
    planning,
    profile,
    teams,
    activities,
    stories,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(custom_characters.router, tags=["custom-characters"])
api_router.include_router(teams.router, tags=["teams"])
api_router.include_router(memories.router, prefix="/profile", tags=["memory"])
api_router.include_router(planning.router, tags=["planning"])
api_router.include_router(activities.router, tags=["activities"])
api_router.include_router(stories.router, tags=["stories"])
