"""End-to-end tests for API endpoints: auth, predictions, ASR, prices, journal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.models.prediction import Asset, Checkin, Direction, PriceSource, Prediction
from app.services.llm import ExtractedPrediction
from app.services.prices import PriceQuote
from app.services.storage import get_store


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch, tmp_path):
    """Reset all lru_caches and point storage at tmp_path."""
    get_settings.cache_clear()
    get_store.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    yield
    get_store.cache_clear()
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path):
    """Async test client with no auth token set."""
    get_settings.cache_clear()
    get_store.cache_clear()

    async def _make():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    return _make


def _pred(
    *,
    voice_started_at: datetime | None = None,
    asset: Asset = Asset.BTC,
    direction: Direction = Direction.UP,
    entry_price: float = 67500.0,
    target_price: float | None = 70000.0,
    timeframe: str | None = "1d",
) -> Prediction:
    vs = voice_started_at or datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    p = Prediction(
        id="11111111-1111-1111-1111-111111111111",
        voice_started_at=vs,
        confirmed_at=vs + timedelta(seconds=8),
        raw_transcript="I think Bitcoin will pump to 70k by tomorrow",
        asset=asset,
        direction=direction,
        target_price=target_price,
        timeframe=timeframe,
        entry_price=entry_price,
    )
    p.ensure_checkins()
    return p


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


async def test_auth_disabled_when_token_empty(tmp_path):
    """No auth required when AUTH_TOKEN is empty."""
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/")

    assert resp.status_code == 200


async def test_auth_required_with_token(monkeypatch, tmp_path):
    """Missing Bearer header returns 401 when AUTH_TOKEN is set."""
    get_settings.cache_clear()
    get_store.cache_clear()
    monkeypatch.setenv("AUTH_TOKEN", "secret123")
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/")

    assert resp.status_code == 401


async def test_auth_success(monkeypatch, tmp_path):
    """Correct Bearer token passes auth."""
    get_settings.cache_clear()
    get_store.cache_clear()
    monkeypatch.setenv("AUTH_TOKEN", "secret123")
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/", headers={"Authorization": "Bearer secret123"})

    assert resp.status_code == 200


async def test_auth_wrong_token(monkeypatch, tmp_path):
    """Wrong Bearer token returns 401."""
    get_settings.cache_clear()
    get_store.cache_clear()
    monkeypatch.setenv("AUTH_TOKEN", "secret123")
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/", headers={"Authorization": "Bearer wrong"})

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Prediction endpoint tests
# ---------------------------------------------------------------------------


async def test_list_predictions_empty(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_predictions_returns_saved(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()
    p = _pred()
    store.save(p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == p.id


async def test_get_prediction_by_id(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()
    p = _pred()
    store.save(p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/predictions/{p.id}")

    assert resp.status_code == 200
    assert resp.json()["id"] == p.id


async def test_get_prediction_404(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/predictions/nonexistent")

    assert resp.status_code == 404


async def test_create_prediction_happy_path(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    extracted = ExtractedPrediction(
        asset=Asset.BTC,
        direction=Direction.UP,
        target_price=70000.0,
        timeframe="1d",
    )

    with (
        patch("app.routers.predictions.extract_prediction", new_callable=AsyncMock, return_value=extracted),
        patch("app.routers.predictions.fetch_current_price", new_callable=AsyncMock, return_value=(67500.0, PriceSource.BINANCE)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/predictions/",
                json={
                    "transcript": "BTC going to 70k",
                    "language": "en-US",
                    "voice_started_at": "2026-06-07T14:30:00Z",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["asset"] == "BTC"
    assert data["direction"] == "up"
    assert data["target_price"] == 70000.0
    assert data["entry_price"] == 67500.0
    assert data["timeframe"] == "1d"
    assert len(data["checkins"]) == 8


async def test_create_prediction_extraction_failure_uses_defaults(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    extracted = ExtractedPrediction(
        asset=None,
        direction=None,
        target_price=None,
        timeframe=None,
    )

    with (
        patch("app.routers.predictions.extract_prediction", new_callable=AsyncMock, return_value=extracted),
        patch("app.routers.predictions.fetch_current_price", new_callable=AsyncMock, return_value=(50000.0, PriceSource.BYBIT)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/predictions/",
                json={
                    "transcript": "mumble mumble",
                    "language": "en-US",
                    "voice_started_at": "2026-06-07T14:30:00Z",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["asset"] == "BTC"
    assert data["direction"] == "neutral"
    assert data["entry_price"] == 50000.0


async def test_create_prediction_price_fetch_failure_returns_502(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    from app.services.prices import PriceFetchError

    extracted = ExtractedPrediction(asset=Asset.BTC, direction=Direction.UP)

    with (
        patch("app.routers.predictions.extract_prediction", new_callable=AsyncMock, return_value=extracted),
        patch("app.routers.predictions.fetch_current_price", new_callable=AsyncMock, side_effect=PriceFetchError("boom")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/predictions/",
                json={
                    "transcript": "BTC up",
                    "language": "en-US",
                    "voice_started_at": "2026-06-07T14:30:00Z",
                },
            )

    assert resp.status_code == 502


async def test_patch_prediction_updates_fields(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()
    p = _pred()
    store.save(p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/predictions/{p.id}",
            json={"direction": "down", "note": "changed my mind"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["direction"] == "down"
    assert data["note"] == "changed my mind"


async def test_patch_prediction_invalid_timeframe(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()
    p = _pred()
    store.save(p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/predictions/{p.id}",
            json={"timeframe": "invalid"},
        )

    assert resp.status_code == 400


async def test_delete_prediction(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()
    p = _pred()
    store.save(p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete(f"/api/predictions/{p.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_delete_prediction_404(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/api/predictions/nonexistent")

    assert resp.status_code == 404


async def test_refresh_backfills_due_marks(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()

    voice_time = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)
    p = _pred(voice_started_at=voice_time)
    p.ensure_checkins()
    store.save(p)

    with patch(
        "app.routers.predictions.fetch_historical_price",
        new_callable=AsyncMock,
        return_value=(68000.0, PriceSource.BINANCE),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/predictions/{p.id}/refresh")

    assert resp.status_code == 200
    data = resp.json()
    checkins = data["checkins"]
    due_marks = [k for k, v in checkins.items() if v["price"] is not None]
    assert len(due_marks) > 0


async def test_refresh_uses_due_at_not_created_at(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()

    voice_time = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    p = _pred(voice_started_at=voice_time)
    p.ensure_checkins()
    store.save(p)

    call_args_list = []

    async def _mock_fetch(asset, due_at):
        call_args_list.append((asset, due_at))
        return (68000.0, PriceSource.BINANCE)

    with patch(
        "app.routers.predictions.fetch_historical_price",
        new_callable=AsyncMock,
        side_effect=_mock_fetch,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(f"/api/predictions/{p.id}/refresh")

    for _asset, due_at in call_args_list:
        assert due_at.tzinfo is not None


async def test_refresh_records_source_and_fetched_at(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()

    voice_time = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)
    p = _pred(voice_started_at=voice_time)
    p.ensure_checkins()
    store.save(p)

    with patch(
        "app.routers.predictions.fetch_historical_price",
        new_callable=AsyncMock,
        return_value=(68000.0, PriceSource.BINANCE),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/predictions/{p.id}/refresh")

    data = resp.json()
    any_checkin = None
    for k, v in data["checkins"].items():
        if v["price"] is not None:
            any_checkin = v
            break
    assert any_checkin is not None
    assert any_checkin["source"] == "binance"
    assert any_checkin["fetched_at"] is not None


async def test_refresh_records_fetch_error_on_both_failure(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()

    from app.services.prices import PriceFetchError

    voice_time = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)
    p = _pred(voice_started_at=voice_time)
    p.ensure_checkins()
    store.save(p)

    with patch(
        "app.routers.predictions.fetch_historical_price",
        new_callable=AsyncMock,
        side_effect=PriceFetchError("both exchanges down"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/predictions/{p.id}/refresh")

    data = resp.json()
    error_marks = [k for k, v in data["checkins"].items() if v.get("fetch_error")]
    assert len(error_marks) > 0


async def test_refresh_all_returns_summary(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()

    voice_time = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)
    p1 = Prediction(
        id="aaa11111-1111-1111-1111-111111111111",
        voice_started_at=voice_time,
        confirmed_at=voice_time + timedelta(seconds=8),
        raw_transcript="BTC up",
        asset=Asset.BTC,
        direction=Direction.UP,
        entry_price=67500.0,
    )
    p1.ensure_checkins()
    store.save(p1)

    with patch(
        "app.routers.predictions.fetch_historical_price",
        new_callable=AsyncMock,
        return_value=(68000.0, PriceSource.BINANCE),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/predictions/refresh-all")

    assert resp.status_code == 200
    data = resp.json()
    assert "refreshed" in data
    assert isinstance(data["errors"], list)


# ---------------------------------------------------------------------------
# Journal / ASR / Prices tests
# ---------------------------------------------------------------------------


async def test_journal_endpoint_returns_markdown(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()
    store = get_store()

    voice_time = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)
    p = _pred(voice_started_at=voice_time)
    p.checkins["15min"] = Checkin(
        mark="15min",
        due_at=voice_time + timedelta(minutes=15),
        price=68000.0,
        fetched_at=datetime.now(timezone.utc),
        source=PriceSource.BINANCE,
    )
    store.save(p)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/predictions/{p.id}/journal.md")

    assert resp.status_code == 200
    assert "text/markdown" in resp.headers.get("content-type", "")
    assert "BTC" in resp.text


async def test_transcribe_endpoint_returns_transcript(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    from app.services.asr import ASRResult

    mock_result = ASRResult(transcript="hello world", language="en", duration_seconds=3.5)

    with patch("app.routers.asr_router.transcribe_audio", new_callable=AsyncMock, return_value=mock_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/predictions/transcribe",
                files={"file": ("audio.webm", b"fake-bytes", "audio/webm")},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["transcript"] == "hello world"
    assert data["language"] == "en"


async def test_prices_endpoint_returns_dict(tmp_path):
    get_settings.cache_clear()
    get_store.cache_clear()

    now = datetime.now(timezone.utc)
    mock_prices = {
        asset: PriceQuote(
            asset=asset,
            price=float(i * 10000),
            source=PriceSource.BINANCE,
            fetched_at=now,
        )
        for i, asset in enumerate(Asset)
    }

    with patch("app.routers.prices.fetch_current_prices", new_callable=AsyncMock, return_value=mock_prices):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/prices/")

    assert resp.status_code == 200
    data = resp.json()
    assert "BTC" in data