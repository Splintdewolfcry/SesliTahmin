"""File-based persistence for predictions and audio blobs."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.models.prediction import Prediction


class PredictionStore:
    """JSON-file-backed store for predictions.

    Concurrency model: this is a single-user app (see spec). FastAPI handles
    requests serially per worker, and we expect a single uvicorn worker for
    the MVP. No internal locking is performed — if/when we move to multiple
    workers or async writers, switch to ``fcntl`` file locks or a real DB.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.predictions_dir = data_dir / "predictions"
        self.audio_dir = data_dir / "audio"
        self.predictions_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, prediction_id: str) -> Path:
        return self.predictions_dir / f"{prediction_id}.json"

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
            raw = path.read_text(encoding="utf-8")
            results.append(Prediction.model_validate_json(raw))
        results.sort(key=lambda p: p.voice_started_at, reverse=True)
        return results

    def delete(self, prediction_id: str) -> None:
        """Remove the JSON file and any associated audio file."""
        path = self._path_for(prediction_id)
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            prediction = Prediction.model_validate_json(raw)
            if prediction.audio_path:
                audio = Path(prediction.audio_path)
                if audio.exists() and audio.is_file():
                    audio.unlink()
            path.unlink()


@lru_cache
def get_store() -> PredictionStore:
    return PredictionStore(get_settings().data_dir)
