"""ASR (Automatic Speech Recognition) service — proxies audio to Groq Whisper.

Owns:
- ``ASRResult`` (Pydantic model returned by the transcribe call)
- ``ASRError`` (custom exception)
- A lazy ``httpx.AsyncClient`` singleton keyed off ``get_settings()``
- ``transcribe_audio`` (the only public transcription entry point)
- ``close_asr_client`` (FastAPI lifespan hook)

Scope: pure data-layer code. The route handler is responsible for accepting
the multipart upload from the browser, persisting the audio file, and any
other side effects. This service never touches disk and never calls the LLM.
"""

from __future__ import annotations

import logging
import threading

import httpx
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings

logger = logging.getLogger(__name__)


_USER_AGENT = "SesliTahmin/0.1 (+https://github.com/seslitahmin)"


class ASRError(Exception):
    """Raised when the ASR (Groq Whisper) call cannot be completed or parsed."""


class ASRResult(BaseModel):
    """The structured output of a single transcription call."""

    model_config = ConfigDict(extra="forbid")

    transcript: str
    language: str | None = None
    duration_seconds: float | None = None


# ---------------------------------------------------------------------------
# httpx.AsyncClient singleton
# ---------------------------------------------------------------------------


_asr_client_singleton: httpx.AsyncClient | None = None
_asr_client_lock = threading.Lock()


def get_asr_client() -> httpx.AsyncClient:
    """Return a process-wide ``httpx.AsyncClient`` (created on first use).

    Recreates the client if the previous one was closed. The API key is read
    from settings as a ``SecretStr`` and unwrapped via ``.get_secret_value()``
    before being put on the Authorization header.
    """
    global _asr_client_singleton
    if _asr_client_singleton is None or _asr_client_singleton.is_closed:
        with _asr_client_lock:
            if _asr_client_singleton is None or _asr_client_singleton.is_closed:
                settings = get_settings()
                api_key = settings.asr_api_key.get_secret_value() or "gsk-no-key-set"
                _asr_client_singleton = httpx.AsyncClient(
                    base_url=settings.asr_base_url,
                    timeout=httpx.Timeout(30.0, connect=10.0),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "User-Agent": _USER_AGENT,
                    },
                )
    return _asr_client_singleton


async def close_asr_client() -> None:
    """Close the shared client. Safe to call multiple times."""
    global _asr_client_singleton
    if _asr_client_singleton is not None and not _asr_client_singleton.is_closed:
        try:
            await _asr_client_singleton.aclose()
        except Exception as exc:  # noqa: BLE001 — shutdown must never crash
            logger.warning("Error closing ASR client: %s", exc)
    _asr_client_singleton = None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_transcription_response(payload: object) -> ASRResult:
    if not isinstance(payload, dict):
        raise ASRError(
            f"ASR response must be a JSON object, got {type(payload).__name__}"
        )
    raw_text = payload.get("text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ASRError(
            f"ASR response missing or empty 'text' field (got {raw_text!r})"
        )

    language: str | None = None
    raw_lang = payload.get("language")
    if raw_lang is not None:
        if not isinstance(raw_lang, str):
            raise ASRError(
                f"ASR response 'language' must be a string, got {type(raw_lang).__name__}"
            )
        language = raw_lang

    duration: float | None = None
    raw_dur = payload.get("duration")
    if raw_dur is not None:
        if isinstance(raw_dur, bool) or not isinstance(raw_dur, (int, float)):
            raise ASRError(
                f"ASR response 'duration' must be a number, got {type(raw_dur).__name__}"
            )
        duration = float(raw_dur)

    return ASRResult(
        transcript=raw_text.strip(),
        language=language,
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    content_type: str = "audio/webm",
    language: str | None = None,
) -> ASRResult:
    """Send ``audio_bytes`` to the configured ASR (Groq Whisper) and return the transcript.

    Uses ``verbose_json`` response_format so Groq includes detected language
    and audio duration. The optional ``language`` hint (BCP 47) biases
    recognition toward that language.

    Raises ``ASRError`` on any failure (network, non-200, bad JSON, empty
    transcript). Callers should treat the exception as "the form should
    fall back to manual entry".
    """
    settings = get_settings()
    client = get_asr_client()

    data: dict[str, str] = {
        "model": settings.asr_model,
        "response_format": "verbose_json",
    }
    if language is not None:
        data["language"] = language

    files = {"file": (filename, audio_bytes, content_type)}

    try:
        response = await client.post("/audio/transcriptions", data=data, files=files)
    except httpx.HTTPError as exc:
        raise ASRError(
            f"ASR request failed (model={settings.asr_model}): {exc}"
        ) from exc

    if response.status_code != 200:
        raise ASRError(
            f"ASR non-200 response: status={response.status_code} body={response.text[:500]!r}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ASRError(f"ASR returned invalid JSON: {exc}") from exc

    return _parse_transcription_response(payload)
