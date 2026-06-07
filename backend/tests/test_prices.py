"""Tests for the price fetching service (Binance + Bybit + cache)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.models.prediction import Asset, PriceSource
from app.services.prices import (
    SYMBOL_MAP,
    KlineCache,
    PriceFetchError,
    PriceQuote,
    close_http_client,
    fetch_binance_kline,
    fetch_binance_ticker,
    fetch_bybit_kline,
    fetch_bybit_ticker,
    fetch_current_price,
    fetch_current_prices,
    fetch_historical_price,
    get_http_client,
    get_kline_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_kline_cache() -> None:
    """Each test starts with an empty cache."""
    get_kline_cache().clear()


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Avoid env leakage between tests."""
    get_settings.cache_clear()


@pytest.fixture
def binance_url() -> str:
    return get_settings().binance_base_url


@pytest.fixture
def bybit_url() -> str:
    return get_settings().bybit_base_url


# ---------------------------------------------------------------------------
# Symbol map
# ---------------------------------------------------------------------------


def test_symbol_map_complete() -> None:
    for asset in Asset:
        assert asset in SYMBOL_MAP
        assert SYMBOL_MAP[asset].endswith("USDT")
    assert SYMBOL_MAP[Asset.BTC] == "BTCUSDT"
    assert SYMBOL_MAP[Asset.ETH] == "ETHUSDT"
    assert SYMBOL_MAP[Asset.SOL] == "SOLUSDT"
    assert SYMBOL_MAP[Asset.BNB] == "BNBUSDT"


# ---------------------------------------------------------------------------
# Kline cache
# ---------------------------------------------------------------------------


def test_kline_cache_set_get() -> None:
    cache = KlineCache(ttl_seconds=60)
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    cache.set(Asset.BTC, due_at, 67500.0, PriceSource.BINANCE)
    assert cache.get(Asset.BTC, due_at) == (67500.0, PriceSource.BINANCE)


def test_kline_cache_ttl_expiry() -> None:
    cache = KlineCache(ttl_seconds=0)
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    cache.set(Asset.BTC, due_at, 67500.0, PriceSource.BINANCE)
    time.sleep(0.05)
    assert cache.get(Asset.BTC, due_at) is None


def test_kline_cache_bucketing() -> None:
    cache = KlineCache(ttl_seconds=60)
    t1 = datetime(2026, 6, 7, 10, 0, 30, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 7, 10, 0, 45, tzinfo=timezone.utc)
    cache.set(Asset.BTC, t1, 67500.0, PriceSource.BINANCE)
    assert cache.get(Asset.BTC, t2) == (67500.0, PriceSource.BINANCE)


def test_kline_cache_different_assets_dont_collide() -> None:
    cache = KlineCache(ttl_seconds=60)
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    cache.set(Asset.BTC, due_at, 67500.0, PriceSource.BINANCE)
    cache.set(Asset.ETH, due_at, 3500.0, PriceSource.BINANCE)
    assert cache.get(Asset.BTC, due_at) == (67500.0, PriceSource.BINANCE)
    assert cache.get(Asset.ETH, due_at) == (3500.0, PriceSource.BINANCE)


def test_kline_cache_clear() -> None:
    cache = KlineCache(ttl_seconds=60)
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    cache.set(Asset.BTC, due_at, 67500.0, PriceSource.BINANCE)
    cache.clear()
    assert cache.get(Asset.BTC, due_at) is None


# ---------------------------------------------------------------------------
# Parsing + fetch (Binance kline)
# ---------------------------------------------------------------------------


async def test_parse_binance_kline(binance_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(
                200,
                json=[
                    [
                        123,
                        "67000.00",
                        "67500",
                        "68000",
                        "67500",
                        "100",
                        456,
                        "100",
                        10,
                        "50",
                        "50",
                    ]
                ],
            )
        )
        price = await fetch_binance_kline(
            Asset.BTC, datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
        )
    assert price == 67500.0


async def test_invalid_binance_response_raises(binance_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(200, json={"unexpected": "shape"})
        )
        with pytest.raises(PriceFetchError):
            await fetch_binance_kline(
                Asset.BTC, datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
            )


async def test_binance_kline_non_200_raises(binance_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(429, text="rate limited")
        )
        with pytest.raises(PriceFetchError):
            await fetch_binance_kline(
                Asset.BTC, datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
            )


# ---------------------------------------------------------------------------
# Parsing + fetch (Bybit kline)
# ---------------------------------------------------------------------------


async def test_parse_bybit_kline(bybit_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{bybit_url}/v5/market/kline").mock(
            return_value=httpx.Response(
                200,
                json={
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "list": [
                            [
                                "123",
                                "67000.00",
                                "67500",
                                "68000",
                                "67500",
                                "100",
                                "100",
                            ]
                        ]
                    },
                },
            )
        )
        price = await fetch_bybit_kline(
            Asset.BTC, datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
        )
    assert price == 67500.0


async def test_bybit_kline_retcode_nonzero_raises(bybit_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{bybit_url}/v5/market/kline").mock(
            return_value=httpx.Response(
                200, json={"retCode": 10001, "retMsg": "bad params", "result": {}}
            )
        )
        with pytest.raises(PriceFetchError):
            await fetch_bybit_kline(
                Asset.BTC, datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
            )


# ---------------------------------------------------------------------------
# Parsing + fetch (Binance ticker)
# ---------------------------------------------------------------------------


async def test_parse_binance_ticker(binance_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/ticker/price").mock(
            return_value=httpx.Response(200, json={"symbol": "BTCUSDT", "price": "67500.50"})
        )
        price = await fetch_binance_ticker(Asset.BTC)
    assert price == 67500.5


# ---------------------------------------------------------------------------
# Parsing + fetch (Bybit ticker)
# ---------------------------------------------------------------------------


async def test_parse_bybit_ticker(bybit_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{bybit_url}/v5/market/tickers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "list": [{"symbol": "BTCUSDT", "lastPrice": "67500.50"}]
                    },
                },
            )
        )
        price = await fetch_bybit_ticker(Asset.BTC)
    assert price == 67500.5


# ---------------------------------------------------------------------------
# fetch_historical_price orchestration
# ---------------------------------------------------------------------------


async def test_historical_binance_success(binance_url: str) -> None:
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    with respx.mock(assert_all_called=False) as mock:
        binance_route = mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(
                200,
                json=[[123, "67000", "67500", "68000", "67500", "100", 456]],
            )
        )
        bybit_route = mock.get(f"{bybit_url}/v5/market/kline").mock(
            return_value=httpx.Response(200, json={"retCode": 0, "result": {"list": []}})
        )
        price, source = await fetch_historical_price(Asset.BTC, due_at)
    assert price == 67500.0
    assert source == PriceSource.BINANCE
    assert binance_route.called
    assert not bybit_route.called


async def test_historical_binance_fails_falls_to_bybit(binance_url: str, bybit_url: str) -> None:
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(500, text="boom")
        )
        mock.get(f"{bybit_url}/v5/market/kline").mock(
            return_value=httpx.Response(
                200,
                json={
                    "retCode": 0,
                    "result": {
                        "list": [
                            ["123", "67000", "67500", "68000", "67500", "100", "100"]
                        ]
                    },
                },
            )
        )
        price, source = await fetch_historical_price(Asset.BTC, due_at)
    assert price == 67500.0
    assert source == PriceSource.BYBIT


async def test_historical_both_fail_raises(binance_url: str, bybit_url: str) -> None:
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(500, text="boom")
        )
        mock.get(f"{bybit_url}/v5/market/kline").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(PriceFetchError):
            await fetch_historical_price(Asset.BTC, due_at)


async def test_historical_cache_hit(binance_url: str) -> None:
    """Second call within TTL uses the cache — the API is hit only once."""
    due_at = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    with respx.mock(assert_all_called=False) as mock:
        binance_route = mock.get(f"{binance_url}/api/v3/klines").mock(
            return_value=httpx.Response(
                200,
                json=[[123, "67000", "67500", "68000", "67500", "100", 456]],
            )
        )
        bybit_route = mock.get(f"{bybit_url}/v5/market/kline").mock(
            return_value=httpx.Response(200, json={"retCode": 0, "result": {"list": []}})
        )
        first = await fetch_historical_price(Asset.BTC, due_at)
        second = await fetch_historical_price(Asset.BTC, due_at)
    assert first == second
    assert first[1] == PriceSource.BINANCE
    assert binance_route.call_count == 1
    assert not bybit_route.called


# ---------------------------------------------------------------------------
# fetch_current_price / fetch_current_prices
# ---------------------------------------------------------------------------


async def test_current_price_binance_success(binance_url: str) -> None:
    with respx.mock(assert_all_called=False) as mock:
        binance_route = mock.get(f"{binance_url}/api/v3/ticker/price").mock(
            return_value=httpx.Response(200, json={"symbol": "BTCUSDT", "price": "67500"})
        )
        bybit_route = mock.get(f"{bybit_url}/v5/market/tickers").mock(
            return_value=httpx.Response(200, json={"retCode": 0, "result": {"list": []}})
        )
        price, source = await fetch_current_price(Asset.BTC)
    assert price == 67500.0
    assert source == PriceSource.BINANCE
    assert binance_route.called
    assert not bybit_route.called


async def test_current_price_binance_fails_falls_to_bybit(binance_url: str, bybit_url: str) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/ticker/price").mock(
            return_value=httpx.Response(500, text="boom")
        )
        mock.get(f"{bybit_url}/v5/market/tickers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "retCode": 0,
                    "result": {"list": [{"symbol": "BTCUSDT", "lastPrice": "67500"}]},
                },
            )
        )
        price, source = await fetch_current_price(Asset.BTC)
    assert price == 67500.0
    assert source == PriceSource.BYBIT


async def test_current_prices_parallel(binance_url: str) -> None:
    symbol_prices = {
        "BTCUSDT": "67500",
        "ETHUSDT": "3500",
        "SOLUSDT": "150",
        "BNBUSDT": "600",
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{binance_url}/api/v3/ticker/price").mock(
            side_effect=lambda req: httpx.Response(
                200, json={"symbol": req.url.params["symbol"], "price": symbol_prices[req.url.params["symbol"]]}
            )
        )
        result = await fetch_current_prices()
    assert set(result.keys()) == set(Asset)
    for asset, symbol in SYMBOL_MAP.items():
        quote = result[asset]
        assert isinstance(quote, PriceQuote)
        assert quote.asset == asset
        assert quote.price == float(symbol_prices[symbol])
        assert quote.source == PriceSource.BINANCE
        assert quote.fetched_at.tzinfo is not None


# ---------------------------------------------------------------------------
# HTTP client singleton + User-Agent
# ---------------------------------------------------------------------------


def test_http_client_has_user_agent() -> None:
    client = get_http_client()
    assert "User-Agent" in client.headers
    assert client.headers["User-Agent"].startswith("SesliTahmin/")


async def test_http_client_used_in_calls(binance_url: str) -> None:
    """Sanity check that the shared client is the one actually issuing requests."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{binance_url}/api/v3/ticker/price").mock(
            return_value=httpx.Response(200, json={"symbol": "BTCUSDT", "price": "1"})
        )
        await fetch_binance_ticker(Asset.BTC)
    client = get_http_client()
    assert not client.is_closed


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def test_close_http_client_is_idempotent() -> None:
    client = get_http_client()
    assert not client.is_closed
    await close_http_client()
    await close_http_client()
    # And we can still build a new one afterwards
    new_client = get_http_client()
    assert not new_client.is_closed
    await close_http_client()
