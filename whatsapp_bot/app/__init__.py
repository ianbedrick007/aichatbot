"""
WhatsApp Bot Router Module

This module provides WhatsApp webhook handling for FastAPI.
Import the router and include it in your main FastAPI app.
"""
from .config import configure_logging
from .views import router

__all__ = ["router", "configure_logging"]
