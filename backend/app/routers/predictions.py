"""HTTP routes for prediction CRUD and refresh flows.

This file currently only exposes the list endpoint (Task 2). Subsequent tasks
add POST /transcribe, POST /, PATCH /{id}, DELETE /{id}, refresh, and
journal.md rendering.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.prediction import Prediction
from app.services.storage import get_store

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/")
async def list_predictions() -> list[Prediction]:
    return get_store().list()
