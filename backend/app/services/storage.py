"""File-based persistence for predictions and audio blobs."""

from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.models.prediction import Prediction

logger = logging.getLogger(__name__)


class PredictionStore:
    """JSON-file-backed store for predictions.

    Concurrency model: this is a single-user app (see spec). FastAPI handles
    requests serially per worker, and we expect a single uvicorn worker for
    the MVP. No internal locking is performed — if/when we move to multiple
    workers or async writers, switch to ``fcntl`` file locks or a real DB.

    Scale: ``list()`` reads and parses every JSON in the directory, and the
    in-memory representation is a parsed Pydantic object. This is fine for
    a single-user journal that will hold at most a few hundred entries. If
    that ceiling changes, switch to a sidecar index or a real DB.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.predictions_dir = data_dir / "predictions"
        self.audio_dir = data_dir / "audio"
        self.predictions_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, prediction_id: str) -> Path:
        return self.predictions_dir / f"{prediction_id}.json"

    def _resolve_audio(self, audio_path: str) -> Path | None:
        """Resolve an audio path safely, refusing anything outside ``audio_dir``.

        Returns the resolved path if it lives under ``audio_dir``, else None.
        This prevents a malformed prediction from causing us to unlink an
        arbitrary file on the host.
        """
        audio = Path(audio_path)
        try:
            audio_resolved = audio.resolve(strict=False)
        except OSError:
            return None
        audio_dir_resolved = self.audio_dir.resolve()
        if not audio_resolved.is_relative_to(audio_dir_resolved):
            return None
        return audio_resolved

    def save(self, prediction: Prediction) -> None:
        """Atomically write a prediction's JSON to disk."""
        target = self._path_for(prediction.id)
        # NamedTemporaryFile on the same volume as target so the os.replace is
        # atomic (POSIX rename within the same filesystem).
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{prediction.id}.", suffix=".json.tmp", dir=self.predictions_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(prediction.model_dump_json())
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_name, target)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    def get(self, prediction_id: str) -> Prediction:
        try:
            raw = self._path_for(prediction_id).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise KeyError(prediction_id) from exc
        return Prediction.model_validate_json(raw)

    def list(self) -> list[Prediction]:
        results: list[Prediction] = []
        for path in self.predictions_dir.glob("*.json"):
            try:
                raw = path.read_text(encoding="utf-8")
                results.append(Prediction.model_validate_json(raw))
            except (ValueError, OSError) as exc:
                # Skip-and-log: a single corrupt file must not break the list.
                logger.warning("Skipping corrupt prediction file %s: %s", path, exc)
                continue
        results.sort(key=lambda p: p.voice_started_at, reverse=True)
        return results

    def delete(self, prediction_id: str) -> None:
        """Remove the JSON file and any associated audio file.

        Order: JSON first, then audio. If audio cleanup fails (e.g. file
        already gone), we still consider the prediction removed — the
        prediction record is the source of truth.
        """
        path = self._path_for(prediction_id)
        audio_path: str | None = None
        if path.exists():
            try:
                prediction = Prediction.model_validate_json(path.read_text(encoding="utf-8"))
                audio_path = prediction.audio_path
            except (ValueError, OSError) as exc:
                logger.warning("Prediction %s JSON corrupt on delete: %s", prediction_id, exc)
            path.unlink()
        if audio_path:
            audio = self._resolve_audio(audio_path)
            if audio and audio.is_file():
                try:
                    audio.unlink()
                except OSError as exc:
                    logger.warning("Failed to remove audio %s: %s", audio, exc)


@lru_cache
def get_store() -> PredictionStore:
    return PredictionStore(get_settings().data_dir)
