"""LLM-backed extraction service for voice prediction transcripts.

Owns:
- ``ExtractedPrediction`` (Pydantic model returned by the LLM)
- ``LLMExtractionError`` (custom exception)
- A lazy ``AsyncOpenAI`` singleton keyed off ``get_settings()``
- The chat-completion message builder
- ``extract_prediction`` (the only public extraction entry point)
- ``close_openai_client`` (FastAPI lifespan hook)

Scope: pure data-layer code. The route handler is responsible for fetching
the current entry price, persisting the prediction, and any other side effects.
This service never calls Binance/Bybit.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.models.prediction import CHECK_IN_MARKS, Asset, Direction

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = f"""You are a precise extractor for a voice-prediction app. Given a short \
transcript of what a trader just said, return a SINGLE JSON object with EXACTLY these \
five fields and nothing else:

  "asset": one of "BTC", "ETH", "SOL", "BNB" — or null if the transcript does not \
mention any asset. If the speaker is ambiguous (e.g. "the coin", "bitcoin or eth", \
"the top one") default to "BTC" and set the "asset_ambiguous" ambiguity flag.
  "direction": one of "up", "down", "neutral" — or null if not stated. \
"neutral" means "I don't think it will move much" / "sideways".
  "target_price": a positive float (e.g. 70000) — or null if no target is mentioned. \
Never invent a number. Parse spoken numbers like "seventy thousand" or "70k" as floats.
  "timeframe": one of the strings {CHECK_IN_MARKS} — or null if not mentioned. \
Normalize the speaker's phrasing to this exact vocabulary:
    "15min"  -> within 15 minutes, "in 15", "next 15"
    "45min"  -> within 45 minutes
    "1h"     -> within an hour, "in 1 hour", "in sixty minutes"
    "6h"     -> within six hours, "by tonight", "by end of day"
    "12h"    -> within twelve hours, "by morning", "overnight"
    "1d"     -> tomorrow, "by tomorrow", "in a day", "by EOD"
    "3d"     -> in three days, "by the weekend", "this week"
    "1w"     -> in a week, "next week", "in seven days"
  "ambiguity_flags": a JSON array of short snake_case strings describing what was \
unclear. Use an empty array [] if the transcript was fully clear. Recognised flags:
    "asset_ambiguous"      - asset not clearly identified
    "target_unclear"       - a target price was mentioned but it's vague ("around 70")
    "timeframe_ambiguous"  - timeframe could be interpreted multiple ways
    "direction_unclear"    - direction is not stated or hedged

Rules:
- Output STRICT JSON. No prose, no markdown, no code fences.
- The JSON must be valid and parseable.
- Prefer null over guessing. The downstream form will let the user confirm.
- Do NOT return the transcript, do NOT add extra fields.
"""


class LLMExtractionError(Exception):
    """Raised when the LLM extraction cannot be completed or parsed."""


class ExtractedPrediction(BaseModel):
    """The structured prediction the LLM extracts from a free-form transcript."""

    model_config = ConfigDict(extra="forbid")

    asset: Asset | None = None
    direction: Direction | None = None
    target_price: float | None = None
    timeframe: str | None = None
    ambiguity_flags: list[str] = Field(default_factory=list)

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, v: str | None) -> str | None:
        if v is not None and v not in CHECK_IN_MARKS:
            raise ValueError(
                f"timeframe must be one of {CHECK_IN_MARKS} or None, got {v!r}"
            )
        return v


# ---------------------------------------------------------------------------
# AsyncOpenAI singleton
# ---------------------------------------------------------------------------


_openai_client_singleton: AsyncOpenAI | None = None
_openai_client_lock = threading.Lock()


def get_openai_client() -> AsyncOpenAI:
    """Return a process-wide ``AsyncOpenAI`` (created on first use).

    Recreates the client if the previous one was closed. The API key is read
    from settings as a ``SecretStr`` and unwrapped via ``.get_secret_value()``
    before being passed to the SDK.
    """
    global _openai_client_singleton
    if _openai_client_singleton is None or _openai_client_singleton.is_closed():
        with _openai_client_lock:
            if _openai_client_singleton is None or _openai_client_singleton.is_closed():
                settings = get_settings()
                _openai_client_singleton = AsyncOpenAI(
                    api_key=settings.llm_api_key.get_secret_value() or "sk-no-key-set",
                    base_url=settings.llm_base_url,
                )
    return _openai_client_singleton


async def close_openai_client() -> None:
    """Close the shared client. Safe to call multiple times."""
    global _openai_client_singleton
    if _openai_client_singleton is not None:
        try:
            await _openai_client_singleton.close()
        except Exception as exc:  # noqa: BLE001 — shutdown must never crash
            logger.warning("Error closing OpenAI client: %s", exc)
    _openai_client_singleton = None


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------


def build_extraction_messages(transcript: str, language: str) -> list[dict[str, Any]]:
    """Build the chat messages for the LLM extraction call.

    Returns a list with a system prompt (defining the JSON schema and rules)
    and a user message that carries the transcript plus its language tag.
    """
    user_content = f"Language: {language}\n\nTranscript: {transcript}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


async def extract_prediction(transcript: str, language: str) -> ExtractedPrediction:
    """Call the configured OpenAI-compatible LLM and return a structured prediction.

    Raises ``LLMExtractionError`` on any failure (network, bad JSON, schema
    mismatch, missing choices, etc). Callers should treat the exception as
    "the form should fall back to manual entry".
    """
    settings = get_settings()
    messages = build_extraction_messages(transcript=transcript, language=language)
    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=500,
        )
    except Exception as exc:  # noqa: BLE001 — we want to wrap every failure mode
        raise LLMExtractionError(
            f"LLM request failed (model={settings.llm_model}): {exc}"
        ) from exc

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMExtractionError(
            f"LLM response missing message content: {exc}"
        ) from exc
    if not content:
        raise LLMExtractionError("LLM response had empty message content")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMExtractionError(
            f"LLM returned invalid JSON: {exc}; raw={content!r}"
        ) from exc

    if not isinstance(payload, dict):
        raise LLMExtractionError(
            f"LLM JSON must be an object, got {type(payload).__name__}"
        )

    try:
        return ExtractedPrediction.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise LLMExtractionError(
            f"LLM JSON failed schema validation: {exc}; payload={payload!r}"
        ) from exc
