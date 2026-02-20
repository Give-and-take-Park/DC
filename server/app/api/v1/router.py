from fastapi import APIRouter
from app.api.v1.endpoints import data, dashboard

api_router = APIRouter()

api_router.include_router(data.router, prefix="/data", tags=["data"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
