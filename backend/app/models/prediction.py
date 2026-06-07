"""Pydantic data models for voice predictions."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Asset(StrEnum):
    BTC = "BTC"
    ETH = "ETH"
    SOL = "SOL"
    BNB = "BNB"


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class PriceSource(StrEnum):
    BINANCE = "binance"
    BYBIT = "bybit"


CHECK_IN_MARKS: list[str] = ["15min", "45min", "1h", "6h", "12h", "1d", "3d", "1w"]

CHECK_IN_DURATIONS: dict[str, timedelta] = {
    "15min": timedelta(minutes=15),
    "45min": timedelta(minutes=45),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(days=7),
}


class Checkin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mark: str
    due_at: datetime
    price: float | None = None
    fetched_at: datetime | None = None
    source: PriceSource | None = None
    fetch_error: str | None = None


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    voice_started_at: datetime
    created_at: datetime | None = None
    confirmed_at: datetime
    raw_transcript: str
    audio_path: str | None = None
    language: str = "en-US"
    asset: Asset
    direction: Direction
    target_price: float | None = None
    timeframe: str | None = None
    entry_price: float
    note: str | None = None
    checkins: dict[str, Checkin] = Field(default_factory=dict)

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, v: str | None) -> str | None:
        if v is not None and v not in CHECK_IN_MARKS:
            raise ValueError(
                f"timeframe must be one of {CHECK_IN_MARKS} or None, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _mirror_created_at(self) -> Prediction:
        # created_at always mirrors voice_started_at (UTC). User-provided values
        # are overwritten to keep the invariant from the spec.
        self.created_at = self.voice_started_at
        return self

    def due_at_for(self, mark: str) -> datetime:
        return self.voice_started_at + CHECK_IN_DURATIONS[mark]

    def ensure_checkins(self) -> None:
        for mark in CHECK_IN_MARKS:
            if mark not in self.checkins:
                self.checkins[mark] = Checkin(
                    mark=mark, due_at=self.due_at_for(mark)
                )
