"""FastAPI app (M6.2). Local only, no authentication in v1 (ADR-004)."""

from finintel.api.app import create_app

__all__ = ["create_app"]
