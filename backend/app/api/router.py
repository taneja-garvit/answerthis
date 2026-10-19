from fastapi import APIRouter

from app.api.routes import claims, demo, drafts, exports, health, projects, reviews

health_router = health.router

api_router = APIRouter(prefix="/api")
for module in (projects, drafts, claims, reviews, exports, demo):
    api_router.include_router(module.router)
