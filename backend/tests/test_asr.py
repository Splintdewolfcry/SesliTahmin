"""Tests for the ASR (Groq Whisper proxy) service."""

from __future__ import annotations

import httpx
import pytest
import respx
from python_multipart.multipart import parse_form

from app.core.config import get_settings
from app.services.asr import (
    ASRError,
    ASRResult,
    close_asr_client,
    get_asr_client,
    transcribe_audio,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Avoid env leakage between tests."""
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _close_client() -> None:
    """Reset the ASR httpx client between tests so each builds a fresh one.

    Some tests monkeypatch ``ASR_BASE_URL`` and then call ``transcribe_audio``
    — the cached singleton would otherwise be locked to the previous base URL.
    """
    await close_asr_client()
    yield
    await close_asr_client()


def _decode_multipart_fields(request: httpx.Request) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
    """Decode a multipart httpx request body into ``(fields, files)``.

    We delegate to ``python_multipart``'s ``parse_form`` which is the same
    library httpx uses internally, so round-trip is faithful.
    """
    from io import BytesIO

    content_type = request.headers["Content-Type"]

    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes, str]] = {}

    def _on_field(field: object) -> None:
        # python_multipart Field: name=field_name (bytes), value (bytes)
        name = field.field_name.decode("ascii")  # type: ignore[attr-defined]
        value = field.value  # type: ignore[attr-defined]
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        fields[name] = value

    def _on_file(file: object) -> None:
        name = file.field_name.decode("ascii")  # type: ignore[attr-defined]
        raw_name = file.file_name  # type: ignore[attr-defined]
        if isinstance(raw_name, bytes):
            raw_name = raw_name.decode("utf-8")
        ctype = file.content_type or ""  # type: ignore[attr-defined]
        fobj = file.file_object  # type: ignore[attr-defined]
        # Prefer ``getvalue()`` (BytesIO) so we don't fight the file position;
        # fall back to a read-with-seek for on-disk files.
        if hasattr(fobj, "getvalue"):
            body = fobj.getvalue()
        else:
            fobj.seek(0)
            body = fobj.read()
        files[name] = (raw_name, body, ctype)

    # ``parse_form`` looks up ``Content-Type`` in a case-sensitive dict.
    parse_form(
        headers={"Content-Type": content_type.encode("ascii")},
        input_stream=BytesIO(request.content),
        on_field=_on_field,
        on_file=_on_file,
    )
    return fields, files


# ---------------------------------------------------------------------------
# ASRResult model
# ---------------------------------------------------------------------------


def test_asr_result_full() -> None:
    r = ASRResult(transcript="hi", language="en", duration_seconds=2.5)
    assert r.transcript == "hi"
    assert r.language == "en"
    assert r.duration_seconds == 2.5


def test_asr_result_minimal() -> None:
    r = ASRResult(transcript="hi")
    assert r.transcript == "hi"
    assert r.language is None
    assert r.duration_seconds is None


def test_asr_result_extra_field_forbidden() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ASRResult(transcript="hi", garbage="nope")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# transcribe_audio — happy path
# ---------------------------------------------------------------------------


async def test_transcribe_audio_happy_path() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(
                200,
                json={"text": "Hello world", "language": "en", "duration": 2.5},
            )
        )
        result = await transcribe_audio(b"fake-audio", filename="clip.webm")

    assert route.called
    assert result.transcript == "Hello world"
    assert result.language == "en"
    assert result.duration_seconds == 2.5


async def test_transcribe_audio_minimal_response() -> None:
    """If the API returns only ``text``, the other fields must default to None."""
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "hi"})
        )
        result = await transcribe_audio(b"fake-audio")

    assert result.transcript == "hi"
    assert result.language is None
    assert result.duration_seconds is None


# ---------------------------------------------------------------------------
# transcribe_audio — request shape
# ---------------------------------------------------------------------------


async def test_transcribe_audio_sends_correct_files() -> None:
    """The audio bytes, filename, and content type must be on the multipart file part."""
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    audio = b"\x52\x49\x46\x46-fake-webm-bytes"

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(
            audio_bytes=audio,
            filename="my-clip.webm",
            content_type="audio/webm",
        )

    assert route.called
    request = route.calls.last.request
    assert request.headers["Content-Type"].startswith("multipart/form-data")

    fields, files = _decode_multipart_fields(request)
    assert "file" in files
    name, data, ctype = files["file"]
    assert name == "my-clip.webm"
    assert data == audio
    assert ctype == "audio/webm"


async def test_transcribe_audio_sends_model() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(b"x")

    request = route.calls.last.request
    fields, _ = _decode_multipart_fields(request)
    assert fields.get("model") == settings.asr_model
    assert fields.get("model") == "whisper-large-v3"
    assert fields.get("response_format") == "verbose_json"


async def test_transcribe_audio_passes_language() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(b"x", language="en-US")

    request = route.calls.last.request
    fields, _ = _decode_multipart_fields(request)
    assert fields.get("language") == "en-US"


async def test_transcribe_audio_no_language_param() -> None:
    """When ``language`` is not provided, it must NOT appear in the multipart data."""
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(b"x")

    request = route.calls.last.request
    fields, _ = _decode_multipart_fields(request)
    assert "language" not in fields


# ---------------------------------------------------------------------------
# transcribe_audio — auth + base URL wiring
# ---------------------------------------------------------------------------


async def test_transcribe_audio_auth_header_set() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(b"x")

    request = route.calls.last.request
    auth = request.headers.get("Authorization", "")
    assert auth.startswith("Bearer ")
    # The Authorization header should not be empty / masked
    assert auth != "Bearer "
    assert "****" not in auth


async def test_transcribe_audio_uses_asr_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A custom ASR_BASE_URL should drive where the request is sent."""
    monkeypatch.setenv("ASR_BASE_URL", "https://asr.example.test/v1")
    get_settings.cache_clear()

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("https://asr.example.test/v1/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(b"x")

    assert route.called


async def test_transcribe_audio_uses_secret_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SecretStr-wrapped key must be unwrapped to its real value before send."""
    monkeypatch.setenv("ASR_API_KEY", "gsk-test-secret-xyz")
    get_settings.cache_clear()

    base = get_settings().asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "ok"})
        )
        await transcribe_audio(b"x")

    request = route.calls.last.request
    auth = request.headers.get("Authorization", "")
    assert auth == "Bearer gsk-test-secret-xyz"
    # And the masked SecretStr rendering must NOT appear
    assert "**********" not in auth
    assert "SecretStr" not in auth


# ---------------------------------------------------------------------------
# transcribe_audio — error paths
# ---------------------------------------------------------------------------


async def test_transcribe_audio_non_200_raises() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(500, text="server error")
        )
        with pytest.raises(ASRError):
            await transcribe_audio(b"x")


async def test_transcribe_audio_bad_json_raises() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, text="not json {{{")
        )
        with pytest.raises(ASRError):
            await transcribe_audio(b"x")


async def test_transcribe_audio_empty_text_raises() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{base}/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": ""})
        )
        with pytest.raises(ASRError):
            await transcribe_audio(b"x")


async def test_transcribe_audio_network_error_raises() -> None:
    settings = get_settings()
    base = settings.asr_base_url.rstrip("/")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{base}/audio/transcriptions").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(ASRError):
            await transcribe_audio(b"x")


# ---------------------------------------------------------------------------
# Singleton lifecycle
# ---------------------------------------------------------------------------


def test_get_asr_client_singleton() -> None:
    a = get_asr_client()
    b = get_asr_client()
    assert a is b


def test_get_asr_client_carries_auth_and_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The underlying httpx client should be configured with auth + base_url + UA."""
    monkeypatch.setenv("ASR_BASE_URL", "https://asr.example.test/v1")
    monkeypatch.setenv("ASR_API_KEY", "gsk-direct-123")
    get_settings.cache_clear()

    client = get_asr_client()
    assert str(client.base_url).rstrip("/") == "https://asr.example.test/v1"
    assert client.headers.get("Authorization") == "Bearer gsk-direct-123"
    assert "SesliTahmin" in client.headers.get("User-Agent", "")


async def test_close_asr_client_idempotent() -> None:
    get_asr_client()
    await close_asr_client()
    await close_asr_client()  # must not raise
    new_client = get_asr_client()
    assert new_client is not None
    await close_asr_client()
