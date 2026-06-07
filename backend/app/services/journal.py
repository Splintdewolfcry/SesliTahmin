"""Render a Prediction + Verdict pair as a markdown journal document.

The journal is generated on demand; the JSON prediction is the source of truth
and the markdown is never written to disk by the app. This function is pure
(no I/O, no async) so it's trivial to test.
"""

from __future__ import annotations

from app.models.prediction import CHECK_IN_MARKS, Direction, Prediction
from app.services.verdict import Verdict, VerdictStatus


_STATUS_WORDS: dict[VerdictStatus, str] = {
    VerdictStatus.HIT: "Hit",
    VerdictStatus.PARTIAL: "Partial",
    VerdictStatus.MISS: "Miss",
    VerdictStatus.PENDING: "Pending",
}

_REASON_LABELS: dict[str, str] = {
    "target_reached": "target reached",
    "direction_correct": "direction correct",
    "direction_wrong": "direction wrong",
    "awaiting_significant_move": "awaiting significant move",
    "not_enough_data": "not enough data",
}


def _fmt_price(price: float | None) -> str:
    return "—" if price is None else f"${price:,.2f}"


def _fmt_pct(pct: float | None) -> str:
    return "—" if pct is None else f"{pct:+.2f}%"


def _fmt_source(source: str | None) -> str:
    if source is None:
        return "—"
    return source.capitalize()


def _delta_pct(checkin_price: float | None, entry_price: float) -> str:
    if checkin_price is None:
        return "—"
    return f"{(checkin_price - entry_price) / entry_price * 100:+.2f}%"


def _verdict_text(verdict: Verdict, latest_price: float | None) -> str:
    status_word = _STATUS_WORDS[verdict.status]
    if verdict.status == VerdictStatus.PENDING and latest_price is None:
        return f"**Verdict:** {status_word} (not enough data)"
    reason_label = _REASON_LABELS.get(verdict.reason, verdict.reason)
    pct_text = "—" if verdict.pct_change is None else f"{verdict.pct_change:+.2f}%"
    return f"**Verdict:** {status_word} ({reason_label}, {pct_text})"


def render_journal(prediction: Prediction, verdict: Verdict, latest_price: float | None) -> str:
    voice_iso = prediction.voice_started_at.strftime("%Y-%m-%d %H:%M UTC")
    if prediction.direction == Direction.UP:
        direction_word = "Up"
    elif prediction.direction == Direction.DOWN:
        direction_word = "Down"
    else:
        direction_word = "Neutral"

    lines: list[str] = [
        f"# {prediction.asset.value} {direction_word} — {voice_iso}",
        "",
        f'**Voice:** "{prediction.raw_transcript}"',
        f"**Entry price:** {_fmt_price(prediction.entry_price)}",
    ]
    if prediction.target_price is not None:
        timeframe = prediction.timeframe or "—"
        lines.append(f"**Target:** {_fmt_price(prediction.target_price)} ({timeframe})")
    lines.append(f"**Direction:** {direction_word}")
    if prediction.audio_path is not None:
        lines.append(f"**Audio:** [recording]({prediction.audio_path})")
    if prediction.language != "en-US":
        lines.append(f"**Language:** {prediction.language}")
    lines.extend(["", "## Check-ins", ""])

    header = (
        "| Mark   | Due (UTC)          | Price       | Δ from entry | Source   |\n"
        "|--------|--------------------|-------------|--------------|----------|"
    )
    lines.append(header)

    for mark in CHECK_IN_MARKS:
        checkin = prediction.checkins.get(mark)
        if checkin is None:
            due_str = prediction.due_at_for(mark).strftime("%Y-%m-%d %H:%M")
            lines.append(f"| {mark:<6} | {due_str:<18} | —           | —            | —        |")
            continue
        due_str = checkin.due_at.strftime("%Y-%m-%d %H:%M")
        price_str = _fmt_price(checkin.price)
        delta_str = _delta_pct(checkin.price, prediction.entry_price)
        source_str = _fmt_source(checkin.source.value if checkin.source is not None else None)
        lines.append(
            f"| {mark:<6} | {due_str:<18} | {price_str:<11} | {delta_str:<12} | {source_str:<8} |"
        )

    lines.extend(["", _verdict_text(verdict, latest_price), ""])
    return "\n".join(lines)
