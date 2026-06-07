"""HTTP routes for prediction CRUD, refresh, and journal rendering."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import require_auth
from app.models.prediction import (
    CHECK_IN_MARKS,
    Asset,
    Direction,
    Prediction,
)
from app.services.llm import LLMExtractionError, extract_prediction
from app.services.prices import PriceFetchError, fetch_current_price, fetch_historical_price
from app.services.storage import get_store
from app.services.verdict import compute_verdict
from app.services.journal import render_journal

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class CreatePredictionRequest(BaseModel):
    transcript: str
    language: str = "en-US"
    voice_started_at: str


class PatchPredictionRequest(BaseModel):
    asset: Asset | None = None
    direction: Direction | None = None
    target_price: float | None = None
    timeframe: str | None = None
    note: str | None = None


@router.get("/", dependencies=[Depends(require_auth)])
async def list_predictions() -> list[Prediction]:
    return get_store().list()


@router.get("/{prediction_id}", dependencies=[Depends(require_auth)])
async def get_prediction(prediction_id: str) -> Prediction:
    try:
        return get_store().get(prediction_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.post("/", dependencies=[Depends(require_auth)])
async def create_prediction(body: CreatePredictionRequest) -> Prediction:
    try:
        extracted = await extract_prediction(body.transcript, body.language)
    except LLMExtractionError:
        extracted = None

    if extracted is None:
        asset = Asset.BTC
        direction = Direction.NEUTRAL
        target_price = None
        timeframe = None
    else:
        asset = extracted.asset if extracted.asset is not None else Asset.BTC
        direction = extracted.direction if extracted.direction is not None else Direction.NEUTRAL
        target_price = extracted.target_price
        timeframe = extracted.timeframe

    try:
        entry_price, _source = await fetch_current_price(asset)
    except PriceFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Price fetch failed: {exc}",
        )

    voice_started_at = datetime.fromisoformat(body.voice_started_at)
    if voice_started_at.tzinfo is None:
        voice_started_at = voice_started_at.replace(tzinfo=timezone.utc)

    prediction = Prediction(
        id=str(uuid4()),
        voice_started_at=voice_started_at,
        confirmed_at=datetime.now(timezone.utc),
        raw_transcript=body.transcript,
        language=body.language,
        asset=asset,
        direction=direction,
        target_price=target_price,
        timeframe=timeframe,
        entry_price=entry_price,
    )
    prediction.ensure_checkins()
    get_store().save(prediction)
    return prediction


@router.patch("/{prediction_id}", dependencies=[Depends(require_auth)])
async def patch_prediction(prediction_id: str, body: PatchPredictionRequest) -> Prediction:
    try:
        prediction = get_store().get(prediction_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    updates = {}
    for field_name, value in body.model_dump(exclude_unset=True).items():
        updates[field_name] = value

    if "timeframe" in updates and updates["timeframe"] is not None:
        if updates["timeframe"] not in CHECK_IN_MARKS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"timeframe must be one of {CHECK_IN_MARKS} or null, got {updates['timeframe']!r}",
            )

    prediction = prediction.model_copy(update=updates)
    get_store().save(prediction)
    return prediction


@router.delete("/{prediction_id}", dependencies=[Depends(require_auth)])
async def delete_prediction(prediction_id: str) -> dict[str, str]:
    try:
        get_store().get(prediction_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    get_store().delete(prediction_id)
    return {"status": "deleted"}


@router.post("/{prediction_id}/refresh", dependencies=[Depends(require_auth)])
async def refresh_prediction(prediction_id: str) -> Prediction:
    try:
        prediction = get_store().get(prediction_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    now = datetime.now(timezone.utc)
    marks_due = [
        (mark, checkin)
        for mark, checkin in prediction.checkins.items()
        if checkin.price is None and checkin.due_at <= now
    ]

    async def _fetch(mark: str, checkin: object) -> tuple[str, float, str] | tuple[str, str]:
        try:
            price, source = await fetch_historical_price(prediction.asset, checkin.due_at)
            return (mark, price, source.value)
        except PriceFetchError as exc:
            return (mark, str(exc))

    results = await asyncio.gather(*[_fetch(mark, c) for mark, c in marks_due])

    updated_checkins = dict(prediction.checkins)
    for result in results:
        mark = result[0]
        if len(result) == 3:
            _, price, source_str = result
            old = updated_checkins[mark]
            updated_checkins[mark] = old.model_copy(
                update={"price": price, "fetched_at": now, "source": source_str}
            )
        else:
            _, error_str = result
            old = updated_checkins[mark]
            updated_checkins[mark] = old.model_copy(update={"fetch_error": error_str})

    prediction = prediction.model_copy(update={"checkins": updated_checkins})
    get_store().save(prediction)
    return prediction


@router.post("/refresh-all", dependencies=[Depends(require_auth)])
async def refresh_all_predictions() -> dict:
    predictions = get_store().list()
    refreshed = 0
    errors: list[dict[str, str]] = []

    for p in predictions:
        try:
            await refresh_prediction(p.id)
            refreshed += 1
        except Exception as exc:
            errors.append({"id": p.id, "error": str(exc)})

    return {"refreshed": refreshed, "errors": errors}


@router.get("/{prediction_id}/journal.md", dependencies=[Depends(require_auth)])
async def journal(prediction_id: str) -> str:
    try:
        prediction = get_store().get(prediction_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    latest_price: float | None = None
    for mark in reversed(CHECK_IN_MARKS):
        checkin = prediction.checkins.get(mark)
        if checkin is not None and checkin.price is not None:
            latest_price = checkin.price
            break

    verdict = compute_verdict(prediction, latest_price)
    md = render_journal(prediction, verdict, latest_price)

    from starlette.responses import Response

    return Response(content=md, media_type="text/markdown")