from fastapi import APIRouter
from app.api.v1.endpoints import measurements, instruments, dashboard, auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(measurements.router, prefix="/measurements", tags=["measurements"])
api_router.include_router(instruments.router, prefix="/instruments", tags=["instruments"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
