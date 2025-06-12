"""
API v1 endpoints
"""

from fastapi import APIRouter
from .endpoints import routers

api_v1_router = APIRouter()
for router in routers:
    api_v1_router.include_router(router) 