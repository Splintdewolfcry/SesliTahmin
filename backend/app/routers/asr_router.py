"""ASR transcription endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.core.auth import require_auth
from app.services.asr import ASRError, transcribe_audio

router = APIRouter(prefix="/api/predictions", tags=["asr"])


@router.post("/transcribe", dependencies=[Depends(require_auth)])
async def transcribe(file: UploadFile) -> dict:
    audio_bytes = await file.read()
    content_type = file.content_type or "audio/webm"
    filename = file.filename or "audio.webm"

    try:
        result = await transcribe_audio(
            audio_bytes,
            filename=filename,
            content_type=content_type,
            language=None,
        )
    except ASRError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ASR error: {exc}",
        )

    return {
        "transcript": result.transcript,
        "language": result.language,
        "duration_seconds": result.duration_seconds,
    }