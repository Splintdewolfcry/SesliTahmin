"""Price fetching service for Binance and Bybit.

This module owns:
- The shared ``httpx.AsyncClient`` (lazy singleton, closed at app shutdown)
- An in-memory kline cache keyed by ``(asset, due_at // 60s)``
- Low-level fetchers for Binance and Bybit (kline + ticker)
- Higher-level orchestrators with cache + fallback semantics
- The ``PriceQuote`` model used by callers when reporting current prices

Scope: pure data-layer code. No FastAPI dependency. The lifespan handler in
``app.main`` is responsible for closing the shared HTTP client on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.models.prediction import Asset, PriceSource

logger = logging.getLogger(__name__)


class PriceFetchError(Exception):
    """Raised when a price cannot be obtained from any available source."""


SYMBOL_MAP: dict[Asset, str] = {
    Asset.BTC: "BTCUSDT",
    Asset.ETH: "ETHUSDT",
    Asset.SOL: "SOLUSDT",
    Asset.BNB: "BNBUSDT",
}


class PriceQuote(BaseModel):
    """A current-price snapshot for a single asset."""

    asset: Asset
    price: float
    source: PriceSource
    fetched_at: datetime


# ---------------------------------------------------------------------------
# Kline cache
# ---------------------------------------------------------------------------


class KlineCache:
    """In-memory cache for historical (kline) close prices.

    Buckets: ``(asset, floor(due_at.timestamp() / 60))`` — so two calls that
    land in the same UTC minute share an entry. This deliberately coalesces
    redundant refresh clicks without making the cache so coarse that a stale
    1-minute candle is served indefinitely.

    TTL: configurable per instance, default supplied by ``get_settings()``.

    Thread-safety: a single ``threading.Lock`` guards all operations. This is
    a per-process cache; running multiple uvicorn workers means each worker
    has its own cache, which is fine for a single-user app. If/when that
    changes, switch to a shared backend (Redis, etc.).
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[tuple[Asset, int], tuple[float, PriceSource, datetime]] = {}

    @staticmethod
    def _bucket_for(due_at: datetime) -> int:
        ts = due_at.timestamp()
        return int(ts // 60)

    def get(self, asset: Asset, due_at: datetime) -> tuple[float, PriceSource] | None:
        key = (asset, self._bucket_for(due_at))
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            price, source, stored_at = entry
            if (datetime.now(timezone.utc) - stored_at).total_seconds() > self._ttl_seconds:
                return None
            return price, source

    def set(
        self,
        asset: Asset,
        due_at: datetime,
        price: float,
        source: PriceSource,
    ) -> None:
        key = (asset, self._bucket_for(due_at))
        with self._lock:
            self._entries[key] = (price, source, datetime.now(timezone.utc))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_kline_cache_singleton: KlineCache | None = None
_kline_cache_lock = threading.Lock()


def get_kline_cache() -> KlineCache:
    """Lazily build the process-wide ``KlineCache`` from settings."""
    global _kline_cache_singleton
    if _kline_cache_singleton is None:
        with _kline_cache_lock:
            if _kline_cache_singleton is None:
                _kline_cache_singleton = KlineCache(get_settings().kline_cache_ttl_seconds)
    return _kline_cache_singleton


# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------


_USER_AGENT = "SesliTahmin/0.1 (+https://github.com/seslitahmin)"

_http_client_singleton: httpx.AsyncClient | None = None
_http_client_lock = threading.Lock()


def get_http_client() -> httpx.AsyncClient:
    """Return a process-wide ``httpx.AsyncClient`` (created on first use)."""
    global _http_client_singleton
    if _http_client_singleton is None or _http_client_singleton.is_closed:
        with _http_client_lock:
            if _http_client_singleton is None or _http_client_singleton.is_closed:
                _http_client_singleton = httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    headers={"User-Agent": _USER_AGENT},
                )
    return _http_client_singleton


async def close_http_client() -> None:
    """Close the shared HTTP client. Safe to call multiple times."""
    global _http_client_singleton
    if _http_client_singleton is not None and not _http_client_singleton.is_closed:
        await _http_client_singleton.aclose()
    _http_client_singleton = None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_binance_kline(payload: Any) -> float:
    if not isinstance(payload, list) or not payload:
        raise PriceFetchError(f"Binance kline: expected non-empty list, got {type(payload).__name__}")
    first = payload[0]
    if not isinstance(first, list) or len(first) < 5:
        raise PriceFetchError(
            f"Binance kline: candle must have >=5 fields, got {len(first) if isinstance(first, list) else type(first).__name__}"
        )
    try:
        return float(first[4])
    except (TypeError, ValueError) as exc:
        raise PriceFetchError(f"Binance kline: close price not a number ({first[4]!r})") from exc


def _parse_bybit_kline(payload: Any) -> float:
    if not isinstance(payload, dict):
        raise PriceFetchError(f"Bybit kline: expected object, got {type(payload).__name__}")
    if payload.get("retCode") != 0:
        raise PriceFetchError(f"Bybit kline: retCode={payload.get('retCode')!r} msg={payload.get('retMsg')!r}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise PriceFetchError("Bybit kline: missing 'result' object")
    rows = result.get("list")
    if not isinstance(rows, list) or not rows:
        raise PriceFetchError("Bybit kline: 'list' missing or empty")
    first = rows[0]
    if not isinstance(first, list) or len(first) < 5:
        raise PriceFetchError("Bybit kline: candle must have >=5 fields")
    try:
        return float(first[4])
    except (TypeError, ValueError) as exc:
        raise PriceFetchError(f"Bybit kline: close price not a number ({first[4]!r})") from exc


def _parse_binance_ticker(payload: Any) -> float:
    if not isinstance(payload, dict):
        raise PriceFetchError(f"Binance ticker: expected object, got {type(payload).__name__}")
    raw = payload.get("price")
    if raw is None:
        raise PriceFetchError("Binance ticker: missing 'price' field")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise PriceFetchError(f"Binance ticker: price not a number ({raw!r})") from exc


def _parse_bybit_ticker(payload: Any) -> float:
    if not isinstance(payload, dict):
        raise PriceFetchError(f"Bybit ticker: expected object, got {type(payload).__name__}")
    if payload.get("retCode") != 0:
        raise PriceFetchError(
            f"Bybit ticker: retCode={payload.get('retCode')!r} msg={payload.get('retMsg')!r}"
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise PriceFetchError("Bybit ticker: missing 'result' object")
    rows = result.get("list")
    if not isinstance(rows, list) or not rows:
        raise PriceFetchError("Bybit ticker: 'list' missing or empty")
    first = rows[0]
    if not isinstance(first, dict):
        raise PriceFetchError("Bybit ticker: list element must be an object")
    raw = first.get("lastPrice")
    if raw is None:
        raise PriceFetchError("Bybit ticker: missing 'lastPrice' field")
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise PriceFetchError(f"Bybit ticker: lastPrice not a number ({raw!r})") from exc


# ---------------------------------------------------------------------------
# Low-level fetchers
# ---------------------------------------------------------------------------


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        raise PriceFetchError(f"HTTP error for {url}: {exc}") from exc
    if response.status_code != 200:
        raise PriceFetchError(f"Non-200 from {url}: status={response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise PriceFetchError(f"Invalid JSON from {url}: {exc}") from exc


def _due_at_ms(due_at: datetime) -> int:
    if due_at.tzinfo is None:
        raise PriceFetchError("due_at must be timezone-aware (UTC)")
    return int(due_at.timestamp() * 1000)


async def fetch_binance_kline(asset: Asset, due_at: datetime) -> float:
    """Fetch the 1-minute candle at or after ``due_at`` from Binance."""
    settings = get_settings()
    url = (
        f"{settings.binance_base_url}/api/v3/klines"
        f"?symbol={SYMBOL_MAP[asset]}&interval=1m&startTime={_due_at_ms(due_at)}&limit=1"
    )
    return _parse_binance_kline(await _get_json(get_http_client(), url))


async def fetch_bybit_kline(asset: Asset, due_at: datetime) -> float:
    """Fetch the 1-minute candle at or after ``due_at`` from Bybit."""
    settings = get_settings()
    url = (
        f"{settings.bybit_base_url}/v5/market/kline"
        f"?category=linear&symbol={SYMBOL_MAP[asset]}&interval=1&start={_due_at_ms(due_at)}&limit=1"
    )
    return _parse_bybit_kline(await _get_json(get_http_client(), url))


async def fetch_binance_ticker(asset: Asset) -> float:
    """Current price for ``asset`` from Binance's ticker endpoint."""
    settings = get_settings()
    url = f"{settings.binance_base_url}/api/v3/ticker/price?symbol={SYMBOL_MAP[asset]}"
    return _parse_binance_ticker(await _get_json(get_http_client(), url))


async def fetch_bybit_ticker(asset: Asset) -> float:
    """Current price for ``asset`` from Bybit's ticker endpoint."""
    settings = get_settings()
    url = (
        f"{settings.bybit_base_url}/v5/market/tickers"
        f"?category=linear&symbol={SYMBOL_MAP[asset]}"
    )
    return _parse_bybit_ticker(await _get_json(get_http_client(), url))


# ---------------------------------------------------------------------------
# High-level orchestrators
# ---------------------------------------------------------------------------


async def fetch_historical_price(
    asset: Asset, due_at: datetime
) -> tuple[float, PriceSource]:
    """Try cache → Binance → Bybit. Returns ``(price, source)``."""
    cache = get_kline_cache()
    if cached := cache.get(asset, due_at):
        return cached

    last_error: Exception | None = None
    for fetcher, source in (
        (fetch_binance_kline, PriceSource.BINANCE),
        (fetch_bybit_kline, PriceSource.BYBIT),
    ):
        try:
            price = await fetcher(asset, due_at)
        except PriceFetchError as exc:
            logger.warning("Historical price fetch from %s failed for %s: %s", source.value, asset.value, exc)
            last_error = exc
            continue
        cache.set(asset, due_at, price, source)
        return price, source

    raise PriceFetchError(
        f"Both Binance and Bybit failed for {asset.value} at {due_at.isoformat()}: {last_error}"
    )


async def fetch_current_price(asset: Asset) -> tuple[float, PriceSource]:
    """Try Binance → Bybit. Returns ``(price, source)``. No caching."""
    last_error: Exception | None = None
    for fetcher, source in (
        (fetch_binance_ticker, PriceSource.BINANCE),
        (fetch_bybit_ticker, PriceSource.BYBIT),
    ):
        try:
            price = await fetcher(asset)
        except PriceFetchError as exc:
            logger.warning("Current price fetch from %s failed for %s: %s", source.value, asset.value, exc)
            last_error = exc
            continue
        return price, source

    raise PriceFetchError(
        f"Both Binance and Bybit failed for current price of {asset.value}: {last_error}"
    )


async def fetch_current_prices() -> dict[Asset, PriceQuote]:
    """Fetch all four assets' current prices in parallel."""
    fetched_at = datetime.now(timezone.utc)
    pairs = await asyncio.gather(
        *(fetch_current_price(asset) for asset in Asset),
    )
    return {
        asset: PriceQuote(
            asset=asset,
            price=price,
            source=source,
            fetched_at=fetched_at,
        )
        for asset, (price, source) in zip(Asset, pairs)
    }
