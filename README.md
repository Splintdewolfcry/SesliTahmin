# SesliTahmin — Voice Prediction Journal

A web app that captures voice predictions about crypto prices, extracts trade details via AI, and tracks what actually happened at 8 time intervals (15min, 45min, 1h, 6h, 12h, 1d, 3d, 1w) after each prediction.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- API keys: Groq (for speech-to-text) and OpenAI-compatible (for extraction)

### 1. Configure

```bash
cd backend
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```
ASR_API_KEY=gsk_...          # Groq API key
LLM_API_KEY=sk-...           # OpenAI-compatible API key
AUTH_TOKEN=your-secret       # Optional; leave empty for dev mode (no auth)
```

### 2. Start the backend

```bash
make dev-backend
# or manually:
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
```

### 3. Start the frontend

```bash
make dev-frontend
# or manually:
cd frontend && npm install && npm run dev
```

### 4. Open

Navigate to **http://localhost:5173**

If you set an `AUTH_TOKEN`, enter it when prompted. If left empty, the app runs without authentication (dev mode).

## How It Works

### Making a Prediction

1. Click **Record** and speak your prediction (e.g. "I think Bitcoin will pump to 70k by tomorrow")
2. The audio is sent to Groq Whisper for transcription
3. The transcript is sent to an LLM which extracts: asset (BTC/ETH/SOL/BNB), direction (up/down/neutral), target price, timeframe
4. You review and edit the extracted details, then confirm
5. The prediction is saved with the current price as the entry price

### Checking Results

- **Refresh** a prediction to backfill historical prices at each check-in mark (15min, 45min, 1h, 6h, 12h, 1d, 3d, 1w)
- Prices are fetched from Binance (primary) or Bybit (fallback) using historical kline data — the price at the exact check-in time, not just the current price
- **Refresh All** updates all predictions at once
- A **verdict** (Hit / Partial / Miss / Pending) is computed based on direction accuracy and target price

### Viewing the Journal

- Each prediction can be viewed as a markdown journal (click "View Journal")
- The journal shows the voice transcript, entry price, target price, and a table of all check-in marks with price changes

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/predictions/transcribe` | Audio → transcript (Groq Whisper) |
| POST | `/api/predictions/` | Create prediction from transcript |
| GET | `/api/predictions/` | List all predictions |
| GET | `/api/predictions/{id}` | Get single prediction |
| PATCH | `/api/predictions/{id}` | Edit prediction fields |
| DELETE | `/api/predictions/{id}` | Delete prediction + audio |
| POST | `/api/predictions/{id}/refresh` | Backfill due check-in marks |
| POST | `/api/predictions/refresh-all` | Backfill all predictions |
| GET | `/api/predictions/{id}/journal.md` | Rendered markdown |
| GET | `/api/prices/` | Current BTC/ETH/SOL/BNB prices |

All endpoints require `Authorization: Bearer {token}` if `AUTH_TOKEN` is set.

## Configuration

All settings go in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ASR_BASE_URL` | `https://api.groq.com/openai/v1` | ASR endpoint |
| `ASR_API_KEY` | *(required)* | Groq API key |
| `ASR_MODEL` | `whisper-large-v3` | ASR model name |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM endpoint |
| `LLM_API_KEY` | *(required)* | OpenAI-compatible API key |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `AUTH_TOKEN` | *(empty = no auth)* | Bearer token for API access |
| `DATA_DIR` | `./data` | Storage directory |
| `BINANCE_BASE_URL` | `https://api.binance.com` | Binance API base |
| `BYBIT_BASE_URL` | `https://api.bybit.com` | Bybit API base |
| `KLINE_CACHE_TTL_SECONDS` | `30` | Kline cache TTL |
| `CORS_ORIGINS` | `["http://localhost:5173","http://localhost:8000"]` | Allowed origins |

## Project Structure

```
SesliTahmin/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── core/         # Config, auth
│   │   ├── models/       # Pydantic models
│   │   ├── routers/       # API endpoints
│   │   └── services/     # Business logic (prices, LLM, ASR, verdict, journal, storage)
│   └── tests/            # pytest (131 tests)
├── frontend/             # React + TypeScript + Tailwind
│   └── src/
│       ├── components/   # UI components
│       ├── hooks/        # usePredictions, useAudioRecorder
│       ├── pages/        # HomePage, DetailPage
│       └── types.ts      # TypeScript types
├── Makefile              # dev-backend, dev-frontend, dev, test, lint
└── .opencode/plans/      # Design spec
```

## Commands

```bash
make install        # Install backend + frontend deps
make dev-backend    # Start backend on :8000
make dev-frontend  # Start frontend on :5173
make dev           # Start both (background)
make test          # Run backend tests
make lint          # Run ruff linter
```

## Tech Stack

- **Backend:** Python 3.12, FastAPI, pydantic, httpx, openai SDK, uvicorn
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS v4
- **ASR:** Groq Whisper v3 Large
- **LLM:** OpenAI-compatible (GPT-4o-mini default)
- **Price data:** Binance REST API (primary), Bybit (fallback)
- **Storage:** JSON files + audio files (no database)