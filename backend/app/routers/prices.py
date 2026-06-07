"""Current-price endpoint for all assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_auth
from app.services.prices import PriceFetchError, fetch_current_prices

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/", dependencies=[Depends(require_auth)])
async def get_prices() -> dict:
    try:
        quotes = await fetch_current_prices()
    except PriceFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Price fetch error: {exc}",
        )

    return {quote.asset.value: quote.model_dump() for quote in quotes.values()}