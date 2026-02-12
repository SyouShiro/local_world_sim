from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base model with ORM support enabled."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ErrorResponse(APIModel):
    """Standard error response payload."""

    code: str
    message: str
