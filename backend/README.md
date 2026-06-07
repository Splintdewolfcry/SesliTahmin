# SesliTahmin backend

FastAPI service powering the SesliTahmin voice-prediction journal: takes voice notes,
transcribes them via an OpenAI-compatible ASR endpoint, reasons over them with an LLM,
and stores results locally.

## Dev server

```bash
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Tests: `uv run pytest`. Lint: `uv run ruff check .`.
