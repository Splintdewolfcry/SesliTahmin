# SesliTahmin — Voice Prediction Journal

## Summary

A web app that captures voice predictions about crypto prices (BTC, ETH, SOL, BNB), transcribes them via Groq Whisper v3 Large, extracts structured trade details via an LLM, and tracks what actually happened at 8 historical time intervals after each prediction. The journal is viewable as markdown-style cards with check-in timelines showing the price that occurred at each mark, not the current price.

## Stack

- **Backend:** Python 3.12, FastAPI, uvicorn, httpx, openai SDK, pydantic
- **Frontend:** React 18+, TypeScript, Vite, Tailwind CSS
- **Voice capture:** Browser `MediaRecorder` API (audio blob)
- **ASR:** Groq Whisper v3 Large (`https://api.groq.com/openai/v1/audio/transcriptions`)
- **LLM extraction:** OpenAI-compatible endpoint (configurable base URL and model)
- **Price data:**
  - Binance REST API: kline for historical, ticker for current
  - Bybit REST API: kline/ticker fallback
- **Storage:** JSON files (one per prediction) + audio files; MD journals rendered on-demand
- **Package manager:** uv (Python), npm/pnpm (frontend)

## Architecture

```
Browser (React SPA)
  │
  ├── MediaRecorder API → audio blob
  ├── POST /api/predictions/transcribe  → transcript
  ├── Confirm/correct extracted prediction
  ├── View journal entries
  └── Refresh → fetch historical prices for due check-in marks
        │
        ▼
FastAPI Backend
  ├── POST /api/predictions/transcribe          (audio blob → Groq Whisper → transcript)
  ├── POST /api/predictions/                    (transcript → LLM → parsed prediction, saved immediately)
  ├── GET  /api/predictions/                    (list all predictions, newest first)
  ├── GET  /api/predictions/{id}                (single prediction + check-in data)
  ├── PATCH /api/predictions/{id}               (edit after creation: asset/direction/target/note)
  ├── DELETE /api/predictions/{id}              (remove prediction + audio file)
  ├── POST /api/predictions/{id}/refresh        (backfill due check-in marks from kline)
  ├── POST /api/predictions/refresh-all         (bulk backfill across all predictions)
  ├── GET  /api/predictions/{id}/journal.md     (rendered markdown)
  └── GET  /api/prices/                         (current BTC/ETH/SOL/BNB prices)
        │
        ├── Groq Whisper v3 Large       (transcription)
        ├── OpenAI-compatible LLM        (extraction)
        ├── Binance REST API             (primary: kline + ticker)
        ├── Bybit REST API               (fallback: kline + ticker)
        └── JSON files + audio files + on-demand MD render (storage)
```

## Data Model

### Prediction (`data/predictions/{id}.json`)

```json
{
  "id": "uuid-v4",
  "created_at": "2026-06-07T14:30:00Z",
  "voice_started_at": "2026-06-07T14:30:00Z",
  "confirmed_at": "2026-06-07T14:30:08Z",
  "raw_transcript": "I think Bitcoin will pump to 70k by tomorrow",
  "audio_path": "data/audio/2026-06-07-1430-btc.wav",
  "language": "en-US",
  "asset": "BTC",
  "direction": "up",
  "target_price": 70000.0,
  "timeframe": "1d",
  "entry_price": 67500.0,
  "note": null,
  "checkins": {}
}
```

Fields:
- `id`: UUID v4
- `voice_started_at`: UTC timestamp when the user pressed record (used to anchor `due_at`)
- `created_at`: alias of `voice_started_at` (kept for compatibility with cards/lists)
- `confirmed_at`: UTC timestamp when the user confirmed the prediction
- `raw_transcript`: full transcript from Groq
- `audio_path`: relative path to stored audio file (kept for journal re-listening)
- `language`: BCP 47 language tag
- `asset`: BTC | ETH | SOL | BNB
- `direction`: up | down | neutral
- `target_price`: optional float
- `timeframe`: optional string from the standard set
- `entry_price`: price fetched from Binance/Bybit at `created_at` (within 60s window)
- `note`: optional free-text
- `checkins`: object keyed by mark name → Checkin

**Time semantics:** `due_at` for every check-in is computed from `voice_started_at`, not `confirmed_at`. This ensures the timeline is honest to when you actually spoke, not when you hit confirm.

### Checkin

Keys: `"15min"`, `"45min"`, `"1h"`, `"6h"`, `"12h"`, `"1d"`, `"3d"`, `"1w"`

```json
{
  "mark": "15min",
  "due_at": "2026-06-07T14:45:00Z",
  "price": 67650.0,
  "fetched_at": "2026-06-07T15:02:11Z",
  "source": "binance"
}
```

- `mark`: interval label
- `due_at`: `voice_started_at` + duration
- `price`: historical close price at `due_at` (from kline, NOT current price)
- `fetched_at`: when backfill ran
- `source`: "binance" or "bybit"

### Check-in intervals

| Mark   | Duration     |
|--------|-------------|
| 15min  | 15 minutes  |
| 45min  | 45 minutes  |
| 1h     | 1 hour      |
| 6h     | 6 hours     |
| 12h    | 12 hours     |
| 1d     | 1 day        |
| 3d     | 3 days       |
| 1w     | 7 days       |

## Voice → Prediction Flow (one-shot)

The previous POST-then-PUT pattern is removed. Single POST creates the final record.

1. User clicks mic on the React frontend
2. `MediaRecorder` captures audio (webm/opus or wav), shows recording state
3. User stops recording, audio blob is sent to `POST /api/predictions/transcribe`
4. Backend forwards blob to Groq Whisper v3 Large, returns transcript
5. Frontend shows transcript, sends `POST /api/predictions/` with `{ transcript, language, voice_started_at, audio_blob }`
6. Backend:
   a. Saves audio to `data/audio/{timestamp}-{asset}.wav`
   b. Sends transcript to LLM with structured extraction prompt
   c. Fetches current price from Binance (Bybit fallback) for entry_price
   d. Builds the prediction record with `voice_started_at` and computed `due_at` for all 8 marks
   e. Saves JSON
   f. Returns the full prediction
7. Frontend shows the parsed/extracted prediction with edit affordance
8. If user wants to correct details, frontend sends `PATCH /api/predictions/{id}`

No more draft state. No orphan records.

## LLM Extraction Prompt

The system prompt instructs the LLM to:

- Identify which asset is being discussed (BTC, ETH, SOL, BNB; default to BTC if ambiguous but flag ambiguity)
- Determine direction (up, down, neutral)
- Extract target price if mentioned (null if not)
- Extract timeframe if mentioned (null if not)
- Normalize timeframe to the standard set: 15min, 45min, 1h, 6h, 12h, 1d, 3d, 1w
- Return strict JSON matching `{ asset, direction, target_price, timeframe, ambiguity_flags }`

## Refresh Check-in Flow (historical kline backfill)

The app is not always running. The refresh button drives all price updates and **backfills historical prices**, not current prices.

1. User clicks "Refresh" on a prediction (or "Refresh All" on the list)
2. Frontend sends `POST /api/predictions/{id}/refresh` (or `/api/predictions/refresh-all`)
3. Backend:
   a. Finds all check-in marks where `due_at <= now` and `price is null`
   b. For each such mark, calls `fetch_historical_price(asset, due_at)`:
      - Binance: `GET /api/v3/klines?symbol={SYMBOL}&interval=1m&startTime={due_at_ms}&limit=1`
      - Returns the 1-minute candle containing the mark; we use its `close` price
      - Fallback: Bybit `GET /v5/market/kline?category=linear&symbol={SYMBOL}&interval=1&start={due_at_ms}&limit=1`
   c. Parallelizes all calls with `asyncio.gather`
   d. Updates JSON with fetched prices, `fetched_at`, and `source`
   e. Returns updated prediction

### In-memory kline cache

- Key: `(asset, due_at // 60s)` — 60s buckets to coalesce nearby requests
- TTL: 30 seconds
- Avoids redundant calls when user clicks refresh multiple times or refreshes one prediction while another with the same asset/mark is also due

## Price Fetching

### Binance (Primary)

- **Current ticker:** `GET https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}`
- **Historical kline:** `GET https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval=1m&startTime={ms}&limit=1`
- Symbols: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`
- Returns `[openTime, open, high, low, close, volume, closeTime, ...]` — we use index 4 (close)
- No auth required for public endpoints
- Rate limit: 1200 req/min — well within our usage

### Bybit (Fallback)

- **Current ticker:** `GET https://api.bybit.com/v5/market/tickers?category=linear&symbol={SYMBOL}`
- **Historical kline:** `GET https://api.bybit.com/v5/market/kline?category=linear&symbol={SYMBOL}&interval=1&start={ms}&limit=1`
- Same symbol mapping, response shape `[startTime, open, high, low, close, ...]`
- No auth required

### Price Fetching Logic

```python
async def fetch_historical_price(asset: str, due_at: datetime) -> tuple[float, str]:
    if cached := kline_cache.get(asset, due_at):
        return cached
    try:
        price = await fetch_binance_kline(asset, due_at)
        src = "binance"
    except Exception:
        price, src = await fetch_bybit_kline(asset, due_at), "bybit"
    kline_cache.set(asset, due_at, (price, src))
    return price, src
```

If both fail, the check-in stays `price: null` and the user sees a "fetch failed, retry" affordance.

## Verdict Logic

Computed on-demand when displaying a prediction. Not stored in JSON.

```python
def compute_verdict(prediction: Prediction, latest_price: float | None) -> Verdict:
    if latest_price is None:
        return Verdict(status="pending", reason="not_enough_data")
    pct_change = (latest_price - prediction.entry_price) / prediction.entry_price * 100
    direction_correct = (
        (prediction.direction == "up" and pct_change > 0)
        or (prediction.direction == "down" and pct_change < 0)
        or (prediction.direction == "neutral" and abs(pct_change) < 1.0)
    )
    target_hit = (
        prediction.target_price is not None
        and (
            (prediction.direction == "up" and latest_price >= prediction.target_price)
            or (prediction.direction == "down" and latest_price <= prediction.target_price)
        )
    )
    if target_hit:
        return Verdict(status="hit", pct_change=pct_change, reason="target_reached")
    if direction_correct and abs(pct_change) >= 1.0:
        return Verdict(status="partial", pct_change=pct_change, reason="direction_correct")
    if not direction_correct:
        return Verdict(status="miss", pct_change=pct_change, reason="direction_wrong")
    return Verdict(status="pending", pct_change=pct_change, reason="awaiting_significant_move")
```

Verdict rules are deterministic and pure (no I/O), so they're trivial to test and to apply retroactively to any prediction.

## Markdown Journal (on-demand render)

JSON is the source of truth. MD is generated when requested — never written to disk by the app. This avoids drift between JSON and MD files.

Endpoint: `GET /api/predictions/{id}/journal.md` returns rendered markdown.

```markdown
# BTC Up — 2026-06-07 14:30 UTC

**Voice:** "I think Bitcoin will pump to 70k by tomorrow"
**Entry price:** $67,500.00
**Target:** $70,000.00 (1d)
**Direction:** Up
**Audio:** [recording](data/audio/2026-06-07-1430-btc.wav)

## Check-ins

| Mark   | Due (UTC)          | Price       | Δ from entry | Source   |
|--------|--------------------|-------------|--------------|----------|
| 15min  | 2026-06-07 14:45  | $67,650.00 | +0.22%       | binance  |
| 45min  | 2026-06-07 15:15  | $67,800.00 | +0.44%       | binance  |
| 1h     | 2026-06-07 15:30  | —           | —            | —        |
| ...    | ...                | ...         | ...          | ...      |

**Verdict:** Hit (target reached at 1d mark, +3.7%)
```

## UI Components

### Frontend Structure

```
src/
  components/
    AudioRecorder.tsx      — MediaRecorder UI with waveform/length indicator
    TranscriptPreview.tsx  — shows transcript after ASR, before extraction
    PredictionForm.tsx     — confirm/edit form after LLM extraction
    PredictionCard.tsx     — card for list view
    PredictionDetail.tsx   — full detail with timeline + verdict
    CheckinTimeline.tsx    — 8-mark visual timeline
    PriceDisplay.tsx       — asset price with Δ indicator
    VerdictBadge.tsx       — hit / partial / miss / pending badge
    ErrorBoundary.tsx      — catches render errors
    LoadingSpinner.tsx     — used during ASR/extraction/refresh
  hooks/
    useAudioRecorder.ts    — MediaRecorder wrapper
    usePredictions.ts      — API client
  pages/
    HomePage.tsx           — list + "Refresh All" + new recording button
    DetailPage.tsx         — single prediction
  App.tsx
  main.tsx
```

### Loading & Error States

- **Recording:** red pulsing mic, elapsed-time counter
- **Transcribing:** spinner + "Transcribing with Whisper..." text
- **Extracting:** spinner + "Extracting prediction..."
- **Saving:** spinner + "Saving..."
- **Refreshing:** per-mark spinner, "Backfilling N marks..." text
- **Network error:** toast at top-right with retry button
- **No predictions:** empty state with "Record your first prediction" CTA
- **ASR failure:** error banner with "Try again" button (audio is preserved for replay)
- **LLM failure:** partial form with manual entry of asset/direction/target/timeframe
- **Price fetch failure (both APIs):** check-in shows "fetch failed" with retry icon

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/predictions/transcribe` | audio blob → transcript (proxies to Groq) |
| POST | `/api/predictions/` | transcript + audio → saved prediction |
| PATCH | `/api/predictions/{id}` | edit asset/direction/target/note |
| DELETE | `/api/predictions/{id}` | remove prediction + audio file |
| GET | `/api/predictions/` | list all (newest first) |
| GET | `/api/predictions/{id}` | single prediction with check-ins |
| POST | `/api/predictions/{id}/refresh` | backfill due marks for one prediction |
| POST | `/api/predictions/refresh-all` | backfill all predictions with due marks |
| GET | `/api/predictions/{id}/journal.md` | rendered markdown |
| GET | `/api/prices/` | current BTC/ETH/SOL/BNB prices |

## Authentication

Single-user app, but Groq + LLM cost money. Bearer token from env:

```
AUTH_TOKEN=...   # required, generated on first run, stored in .env
```

Frontend stores token in localStorage on first load (or in env-baked config for the SPA). Every request sends `Authorization: Bearer {token}`. Backend rejects with 401 on mismatch.

For a VPS deployment, also recommend IP allowlist in nginx if the app is only used from known networks.

## Timezone Handling

- All timestamps in JSON are UTC ISO 8601 with `Z` suffix
- All server-side `datetime` operations use `datetime.now(timezone.utc)`
- Frontend formats to user locale via `Intl.DateTimeFormat` with `{ timeZone: undefined }` (browser default)
- "Time ago" formatting via small client utility (e.g. `formatDistanceToNow` from `date-fns`)

## Error Handling

- **Microphone permission denied:** show clear error in recorder UI, link to browser settings
- **ASR failure (Groq):** show error, preserve audio for retry/manual entry
- **LLM extraction failure:** return partial result, render form with empty fields for manual entry
- **Kline fetch failure (Binance):** fall back to Bybit
- **Kline fetch failure (both):** mark check-in as `price: null` with `fetch_error: "..."`, show retry
- **Invalid transcript:** LLM returns `null` asset → form forces manual asset selection
- **Audio save failure:** abort the prediction creation, surface error
- **JSON corruption:** top-level try/except around reads returns 500; backups are not in scope

## Configuration (Environment Variables)

```
ASR_BASE_URL=https://api.groq.com/openai/v1
ASR_API_KEY=gsk_...
ASR_MODEL=whisper-large-v3

LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

AUTH_TOKEN=...
DATA_DIR=./data
HOST=0.0.0.0
PORT=8000

BINANCE_BASE_URL=https://api.binance.com
BYBIT_BASE_URL=https://api.bybit.com
KLINE_CACHE_TTL_SECONDS=30
```

All configurable, defaults provided for local dev.

## Testing Strategy

Integration tests (pytest + httpx.AsyncClient), no real network calls — all external APIs mocked:

- `test_kline_parsing.py` — Binance + Bybit kline response shapes parsed correctly
- `test_price_fallback.py` — Binance failure → Bybit success; both failure → None
- `test_price_cache.py` — same `(asset, due_at)` within TTL returns cached value
- `test_llm_extraction.py` — various transcripts produce correct asset/direction/target/timeframe
- `test_prediction_roundtrip.py` — save JSON → load JSON → equal data
- `test_verdict_logic.py` — all branches of verdict function
- `test_due_at_computation.py` — `voice_started_at` + duration produces correct `due_at` for all 8 marks
- `test_auth.py` — missing/invalid token → 401
- `test_journal_rendering.py` — JSON → MD matches expected output

Frontend: minimal — component smoke tests for recorder/form using Vitest + React Testing Library.

## Deployment

- Backend served via uvicorn behind nginx reverse proxy on VPS
- React SPA built with `vite build`, served as static files by nginx
- Single systemd service for backend, nginx for static + proxy
- `data/` directory persisted via symlink or volume, included in backup
- `.env` file with secrets, not committed

## Future Considerations (Not in Scope)

- Multi-user support
- Push notifications for check-in marks
- Historical accuracy statistics / charts
- Export all predictions to CSV
- Dark/light theme toggle
- Mobile native app
- Streaming transcription (Whisper streaming vs. batch)
