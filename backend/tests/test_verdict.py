"""Tests for verdict computation and markdown journal rendering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.prediction import (
    CHECK_IN_MARKS,
    Asset,
    Checkin,
    Direction,
    Prediction,
    PriceSource,
)
from app.services.journal import render_journal
from app.services.verdict import VerdictStatus, compute_verdict


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_prediction(
    *,
    entry_price: float = 100.0,
    target_price: float | None = 110.0,
    timeframe: str | None = "1d",
    direction: Direction = Direction.UP,
    asset: Asset = Asset.BTC,
    voice_started_at: datetime | None = None,
    audio_path: str | None = "data/audio/2026-06-07-1430-btc.wav",
    language: str = "en-US",
    checkins: dict[str, Checkin] | None = None,
) -> Prediction:
    voice_started_at = voice_started_at or datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    return Prediction(
        id="11111111-1111-1111-1111-111111111111",
        voice_started_at=voice_started_at,
        confirmed_at=voice_started_at + timedelta(seconds=8),
        raw_transcript="I think Bitcoin will pump to 110 by tomorrow",
        audio_path=audio_path,
        language=language,
        asset=asset,
        direction=direction,
        target_price=target_price,
        timeframe=timeframe,
        entry_price=entry_price,
        note=None,
        checkins=checkins or {},
    )


# ---------------------------------------------------------------------------
# Verdict tests
# ---------------------------------------------------------------------------


def test_verdict_no_price_returns_pending():
    p = _make_prediction()
    v = compute_verdict(p, latest_price=None)
    assert v.status == VerdictStatus.PENDING
    assert v.reason == "not_enough_data"
    assert v.pct_change is None
    assert v.target_hit is False


def test_verdict_target_hit_up():
    p = _make_prediction(direction=Direction.UP, target_price=110.0, entry_price=100.0)
    v = compute_verdict(p, latest_price=115.0)
    assert v.status == VerdictStatus.HIT
    assert v.reason == "target_reached"
    assert v.target_hit is True
    assert v.pct_change == pytest.approx(15.0)


def test_verdict_target_hit_down():
    p = _make_prediction(direction=Direction.DOWN, target_price=90.0, entry_price=100.0)
    v = compute_verdict(p, latest_price=85.0)
    assert v.status == VerdictStatus.HIT
    assert v.reason == "target_reached"
    assert v.target_hit is True
    assert v.pct_change == pytest.approx(-15.0)


def test_verdict_no_target_up_partial():
    p = _make_prediction(direction=Direction.UP, target_price=None, entry_price=100.0)
    v = compute_verdict(p, latest_price=102.0)
    assert v.status == VerdictStatus.PARTIAL
    assert v.reason == "direction_correct"
    assert v.pct_change == pytest.approx(2.0)


def test_verdict_no_target_down_partial():
    p = _make_prediction(direction=Direction.DOWN, target_price=None, entry_price=100.0)
    v = compute_verdict(p, latest_price=98.0)
    assert v.status == VerdictStatus.PARTIAL
    assert v.reason == "direction_correct"
    assert v.pct_change == pytest.approx(-2.0)


def test_verdict_no_target_up_miss():
    p = _make_prediction(direction=Direction.UP, target_price=None, entry_price=100.0)
    v = compute_verdict(p, latest_price=98.0)
    assert v.status == VerdictStatus.MISS
    assert v.reason == "direction_wrong"
    assert v.pct_change == pytest.approx(-2.0)


def test_verdict_neutral_small_move_pending():
    """neutral with |pct|<1.0 → direction_correct, but not significant → pending."""
    p = _make_prediction(direction=Direction.NEUTRAL, target_price=None, entry_price=100.0)
    v = compute_verdict(p, latest_price=100.5)
    assert v.status == VerdictStatus.PENDING
    assert v.reason == "awaiting_significant_move"
    assert v.pct_change == pytest.approx(0.5)


def test_verdict_neutral_large_move_partial():
    """neutral with |pct|>=1.0 → direction is wrong (not <1.0 anymore) → miss."""
    p = _make_prediction(direction=Direction.NEUTRAL, target_price=None, entry_price=100.0)
    v = compute_verdict(p, latest_price=102.0)
    # Direction "correct" for neutral only when |pct| < 1.0; 2% breaks that
    assert v.status == VerdictStatus.MISS
    assert v.reason == "direction_wrong"


def test_verdict_up_small_move_pending():
    """direction=up, price up 0.5% (direction correct, but <1%) → pending."""
    p = _make_prediction(direction=Direction.UP, target_price=None, entry_price=100.0)
    v = compute_verdict(p, latest_price=100.5)
    assert v.status == VerdictStatus.PENDING
    assert v.reason == "awaiting_significant_move"
    assert v.pct_change == pytest.approx(0.5)


def test_verdict_pct_change_signed():
    p_up = _make_prediction(direction=Direction.UP, target_price=None, entry_price=100.0)
    v_up = compute_verdict(p_up, latest_price=110.0)
    assert v_up.pct_change > 0

    p_down = _make_prediction(direction=Direction.DOWN, target_price=None, entry_price=100.0)
    v_down = compute_verdict(p_down, latest_price=90.0)
    assert v_down.pct_change < 0


def test_verdict_target_not_hit_uses_direction():
    """direction=up, target=110, latest=105 → direction correct, >=1% → partial."""
    p = _make_prediction(direction=Direction.UP, target_price=110.0, entry_price=100.0)
    v = compute_verdict(p, latest_price=105.0)
    assert v.status == VerdictStatus.PARTIAL
    assert v.reason == "direction_correct"
    assert v.target_hit is False
    assert v.pct_change == pytest.approx(5.0)


def test_verdict_target_not_hit_miss():
    """direction=up, target=110, latest=95 (down) → direction wrong → miss."""
    p = _make_prediction(direction=Direction.UP, target_price=110.0, entry_price=100.0)
    v = compute_verdict(p, latest_price=95.0)
    assert v.status == VerdictStatus.MISS
    assert v.reason == "direction_wrong"
    assert v.target_hit is False
    assert v.pct_change == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# Journal tests
# ---------------------------------------------------------------------------


def test_journal_renders_minimal():
    p = _make_prediction(
        entry_price=100.0,
        target_price=None,
        timeframe=None,
        audio_path=None,
    )
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    assert isinstance(md, str)
    assert md.startswith("# BTC")
    assert "Check-ins" in md


def test_journal_heading_capitalizes_direction():
    p = _make_prediction(direction=Direction.UP)
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    assert md.splitlines()[0] == "# BTC Up — 2026-06-07 14:30 UTC"


def test_journal_includes_voice_transcript():
    p = _make_prediction()
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    assert '"I think Bitcoin will pump to 110 by tomorrow"' in md


def test_journal_includes_entry_price():
    p = _make_prediction(entry_price=67500.0)
    v = compute_verdict(p, latest_price=67500.0)
    md = render_journal(p, v, latest_price=67500.0)
    assert "$67,500.00" in md


def test_journal_includes_target_when_set():
    p = _make_prediction(target_price=70000.0, timeframe="1d")
    v = compute_verdict(p, latest_price=70000.0)
    md = render_journal(p, v, latest_price=70000.0)
    assert "**Target:** $70,000.00 (1d)" in md


def test_journal_omits_target_when_none():
    p = _make_prediction(target_price=None, timeframe=None)
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    assert "**Target:**" not in md


def test_journal_includes_audio_link():
    p = _make_prediction(audio_path="data/audio/2026-06-07-1430-btc.wav")
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    assert "[recording](data/audio/2026-06-07-1430-btc.wav)" in md


def test_journal_omits_audio_when_none():
    p = _make_prediction(audio_path=None)
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    assert "**Audio:**" not in md


def test_journal_checkins_in_canonical_order():
    voice = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    checkins = {}
    # Add a checkin for each mark with the same price so we can grep them
    for mark in CHECK_IN_MARKS:
        checkins[mark] = Checkin(
            mark=mark,
            due_at=voice + timedelta(minutes=15 * (CHECK_IN_MARKS.index(mark) + 1)),
            price=100.0,
            fetched_at=voice + timedelta(minutes=15 * (CHECK_IN_MARKS.index(mark) + 1) + 5),
            source=PriceSource.BINANCE,
        )
    p = _make_prediction(checkins=checkins)
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)

    # Find the positions of each mark in the table
    positions = []
    for mark in CHECK_IN_MARKS:
        # the line begins with "| <mark> "
        idx = md.find(f"| {mark} ")
        assert idx != -1, f"mark {mark} not found in markdown"
        positions.append(idx)
    assert positions == sorted(positions)


def test_journal_checkin_with_price():
    voice = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    checkin = Checkin(
        mark="15min",
        due_at=voice + timedelta(minutes=15),
        price=101.0,
        fetched_at=voice + timedelta(minutes=20),
        source=PriceSource.BINANCE,
    )
    p = _make_prediction(checkins={"15min": checkin})
    v = compute_verdict(p, latest_price=101.0)
    md = render_journal(p, v, latest_price=101.0)
    # row should include the price, pct delta, and capitalized source
    assert "$101.00" in md
    assert "+1.00%" in md
    assert "Binance" in md


def test_journal_checkin_without_price():
    voice = datetime(2026, 6, 7, 14, 30, tzinfo=timezone.utc)
    checkin = Checkin(
        mark="1h",
        due_at=voice + timedelta(hours=1),
        price=None,
        fetched_at=None,
        source=None,
    )
    p = _make_prediction(checkins={"1h": checkin})
    v = compute_verdict(p, latest_price=100.0)
    md = render_journal(p, v, latest_price=100.0)
    # 1h row should show em-dashes
    row = next(line for line in md.splitlines() if line.startswith("| 1h "))
    assert "—" in row
    # The em-dash should appear at least 3 times in that row (price, pct, source)
    assert row.count("—") == 3


def test_journal_verdict_hit_renders():
    p = _make_prediction(direction=Direction.UP, target_price=110.0, entry_price=100.0)
    v = compute_verdict(p, latest_price=115.0)
    md = render_journal(p, v, latest_price=115.0)
    assert "**Verdict:** Hit" in md
    assert "target reached" in md
    assert "+15.00%" in md


def test_journal_verdict_pending_renders():
    p = _make_prediction()
    v = compute_verdict(p, latest_price=None)
    md = render_journal(p, v, latest_price=None)
    assert "**Verdict:** Pending" in md
    assert "not enough data" in md
