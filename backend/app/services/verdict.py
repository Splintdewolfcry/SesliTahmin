"""Pure verdict logic for predictions.

Verdicts are computed on-demand when displaying a prediction. The rules are
deterministic and side-effect free, so they can be applied retroactively to any
prediction as new price data arrives.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.models.prediction import Direction, Prediction


class VerdictStatus(StrEnum):
    HIT = "hit"
    PARTIAL = "partial"
    MISS = "miss"
    PENDING = "pending"


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerdictStatus
    reason: str
    pct_change: float | None = None
    target_hit: bool = False


def compute_verdict(prediction: Prediction, latest_price: float | None) -> Verdict:
    if latest_price is None:
        return Verdict(
            status=VerdictStatus.PENDING,
            reason="not_enough_data",
            pct_change=None,
        )
    pct_change = (latest_price - prediction.entry_price) / prediction.entry_price * 100
    direction_correct = (
        (prediction.direction == Direction.UP and pct_change > 0)
        or (prediction.direction == Direction.DOWN and pct_change < 0)
        or (prediction.direction == Direction.NEUTRAL and abs(pct_change) < 1.0)
    )
    target_hit = prediction.target_price is not None and (
        (prediction.direction == Direction.UP and latest_price >= prediction.target_price)
        or (prediction.direction == Direction.DOWN and latest_price <= prediction.target_price)
    )
    if target_hit:
        return Verdict(
            status=VerdictStatus.HIT,
            reason="target_reached",
            pct_change=pct_change,
            target_hit=True,
        )
    if direction_correct and abs(pct_change) >= 1.0:
        return Verdict(
            status=VerdictStatus.PARTIAL,
            reason="direction_correct",
            pct_change=pct_change,
        )
    if not direction_correct:
        return Verdict(
            status=VerdictStatus.MISS,
            reason="direction_wrong",
            pct_change=pct_change,
        )
    return Verdict(
        status=VerdictStatus.PENDING,
        reason="awaiting_significant_move",
        pct_change=pct_change,
    )
