"""Tests for the prediction data models and PredictionStore."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.main import app
from app.models.prediction import (
    CHECK_IN_DURATIONS,
    CHECK_IN_MARKS,
    Asset,
    Checkin,
    Direction,
    Prediction,
    PriceSource,
)
from app.services.storage import PredictionStore, get_store

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_prediction(
    *,
    voice_started_at: datetime | None = None,
    entry_price: float = 67500.0,
    target_price: float | None = 70000.0,
    timeframe: str | None = "1d",
    asset: Asset = Asset.BTC,
    direction: Direction = Direction.UP,
    note: str | None = None,
    audio_path: str | None = None,
    confirmed_at: datetime | None = None,
) -> Prediction:
    voice_started_at = voice_started_at or datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    confirmed_at = confirmed_at or (voice_started_at + timedelta(seconds=8))
    return Prediction(
        id="11111111-1111-1111-1111-111111111111",
        voice_started_at=voice_started_at,
        confirmed_at=confirmed_at,
        raw_transcript="I think Bitcoin will pump to 70k by tomorrow",
        audio_path=audio_path,
        language="en-US",
        asset=asset,
        direction=direction,
        target_price=target_price,
        timeframe=timeframe,
        entry_price=entry_price,
        note=note,
    )


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------


def test_ensure_checkins_initializes_all_marks():
    p = _make_prediction()
    assert p.checkins == {}
    p.ensure_checkins()
    assert set(p.checkins.keys()) == set(CHECK_IN_MARKS)
    assert len(p.checkins) == 8
    for mark, checkin in p.checkins.items():
        assert isinstance(checkin, Checkin)
        assert checkin.mark == mark
        assert checkin.price is None
        assert checkin.fetched_at is None
        assert checkin.source is None
        assert checkin.due_at == p.voice_started_at + CHECK_IN_DURATIONS[mark]


def test_due_at_for_correct_offset():
    voice = datetime(2026, 6, 7, 10, 0, tzinfo=timezone.utc)
    p = _make_prediction(voice_started_at=voice)
    assert p.due_at_for("15min") == voice + timedelta(minutes=15)
    assert p.due_at_for("45min") == voice + timedelta(minutes=45)
    assert p.due_at_for("1h") == voice + timedelta(hours=1)
    assert p.due_at_for("6h") == voice + timedelta(hours=6)
    assert p.due_at_for("12h") == voice + timedelta(hours=12)
    assert p.due_at_for("1d") == voice + timedelta(days=1)
    assert p.due_at_for("3d") == voice + timedelta(days=3)
    assert p.due_at_for("1w") == voice + timedelta(days=7)


def test_invalid_timeframe_rejected():
    with pytest.raises(ValidationError):
        _make_prediction(timeframe="invalid")


def test_created_at_mirrors_voice_started_at():
    voice = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    p = _make_prediction(voice_started_at=voice)
    assert p.created_at == voice


def test_asset_enum_values():
    assert Asset.BTC.value == "BTC"
    assert Asset.ETH.value == "ETH"
    assert Asset.SOL.value == "SOL"
    assert Asset.BNB.value == "BNB"


def test_direction_enum_values():
    assert Direction.UP.value == "up"
    assert Direction.DOWN.value == "down"
    assert Direction.NEUTRAL.value == "neutral"


def test_price_source_enum_values():
    assert PriceSource.BINANCE.value == "binance"
    assert PriceSource.BYBIT.value == "bybit"


def test_check_in_marks_constant_complete():
    expected = {"15min", "45min", "1h", "6h", "12h", "1d", "3d", "1w"}
    assert set(CHECK_IN_MARKS) == expected
    assert set(CHECK_IN_DURATIONS.keys()) == expected


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------


def test_save_and_get_roundtrip(tmp_path: Path):
    store = PredictionStore(tmp_path)
    p = _make_prediction()
    store.save(p)

    loaded = store.get(p.id)
    assert loaded.id == p.id
    assert loaded.voice_started_at == p.voice_started_at
    assert loaded.confirmed_at == p.confirmed_at
    assert loaded.raw_transcript == p.raw_transcript
    assert loaded.asset == p.asset
    assert loaded.direction == p.direction
    assert loaded.target_price == p.target_price
    assert loaded.entry_price == p.entry_price
    assert loaded.timeframe == p.timeframe


def test_list_newest_first(tmp_path: Path):
    store = PredictionStore(tmp_path)
    base = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    p_old = _make_prediction(voice_started_at=base)
    p_mid = Prediction(
        **{
            **p_old.model_dump(),
            "id": "22222222-2222-2222-2222-222222222222",
            "voice_started_at": base + timedelta(hours=1),
        }
    )
    p_new = Prediction(
        **{
            **p_old.model_dump(),
            "id": "33333333-3333-3333-3333-333333333333",
            "voice_started_at": base + timedelta(hours=2),
        }
    )

    store.save(p_old)
    store.save(p_mid)
    store.save(p_new)

    listed = store.list()
    assert [p.id for p in listed] == [p_new.id, p_mid.id, p_old.id]


def test_delete_removes_file_and_audio(tmp_path: Path):
    store = PredictionStore(tmp_path)
    audio = tmp_path / "audio" / "recording.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"fake-audio-bytes")
    # Use absolute path that lives inside tmp_path so the store considers it
    # eligible for cleanup.
    p = _make_prediction(audio_path=str(audio))
    store.save(p)

    assert (store.predictions_dir / f"{p.id}.json").exists()
    assert audio.exists()

    store.delete(p.id)

    assert not (store.predictions_dir / f"{p.id}.json").exists()
    assert not audio.exists()


def test_get_missing_raises_keyerror(tmp_path: Path):
    store = PredictionStore(tmp_path)
    with pytest.raises(KeyError):
        store.get("nonexistent-id")


def test_save_is_atomic(tmp_path: Path):
    store = PredictionStore(tmp_path)
    p = _make_prediction()
    store.save(p)

    path = store.predictions_dir / f"{p.id}.json"
    assert path.exists()
    # The file must be valid JSON
    raw = path.read_text()
    data = json.loads(raw)
    assert data["id"] == p.id


def test_singleton_store_shares_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Reset lru_caches for this test
    get_settings.cache_clear()
    get_store.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store1 = get_store()
    store2 = get_store()
    assert store1 is store2
    assert store1.data_dir == tmp_path
    get_store.cache_clear()
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Integration endpoint test
# ---------------------------------------------------------------------------


def test_storage_endpoint_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """GET /api/predictions/ returns [] when no predictions are stored."""
    get_settings.cache_clear()
    get_store.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    async def run() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/predictions/")

        assert response.status_code == 200
        assert response.json() == []

    asyncio.run(run())

    get_store.cache_clear()
    get_settings.cache_clear()
