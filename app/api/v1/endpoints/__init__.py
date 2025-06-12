"""
API v1 endpoint modules
"""

from .auth import router as auth_router
from .upload import router as upload_router

routers = [auth_router, upload_router] 