export type Asset = "BTC" | "ETH" | "SOL" | "BNB";
export type Direction = "up" | "down" | "neutral";
export type PriceSource = "binance" | "bybit";
export type VerdictStatus = "hit" | "partial" | "miss" | "pending";

export interface Checkin {
  mark: string;
  due_at: string;
  price: number | null;
  fetched_at: string | null;
  source: PriceSource | null;
  fetch_error: string | null;
}

export interface Prediction {
  id: string;
  voice_started_at: string;
  created_at: string;
  confirmed_at: string;
  raw_transcript: string;
  audio_path: string | null;
  language: string;
  asset: Asset;
  direction: Direction;
  target_price: number | null;
  timeframe: string | null;
  entry_price: number;
  note: string | null;
  checkins: Record<string, Checkin>;
}

export interface Verdict {
  status: VerdictStatus;
  reason: string;
  pct_change: number | null;
  target_hit: boolean;
}

export interface PriceQuote {
  asset: Asset;
  price: number;
  source: PriceSource;
  fetched_at: string;
}

export interface AsrResult {
  transcript: string;
  language: string | null;
  duration_seconds: number | null;
}

export interface ExtractedPrediction {
  asset: Asset | null;
  direction: Direction | null;
  target_price: number | null;
  timeframe: string | null;
  ambiguity_flags: string[];
}

export interface CreatePredictionRequest {
  transcript: string;
  language: string;
  voice_started_at: string;
}

export interface PatchPredictionRequest {
  asset?: Asset;
  direction?: Direction;
  target_price?: number | null;
  timeframe?: string | null;
  note?: string | null;
}