from fastapi import APIRouter
from app.api.v1.endpoints import measurements, instruments, dashboard, auth, optical

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(measurements.router, prefix="/measurements", tags=["measurements"])
api_router.include_router(instruments.router, prefix="/instruments", tags=["instruments"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(optical.router, prefix="/optical", tags=["optical"])
