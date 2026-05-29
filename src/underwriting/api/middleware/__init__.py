"""FastAPI middleware for API authentication and request processing."""

from underwriting.api.middleware.auth import authenticate_api_key

__all__ = ["authenticate_api_key"]
