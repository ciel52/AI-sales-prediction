export type Granularity = "daily" | "weekly" | "monthly";

export type ShopInfo = {
  shop_id: string;
  n_days: number;
  date_min: string;
  date_max: string;
};

/**
 * 予測に使ったモデル。
 * lag = 前日・前週の実績を使う高精度モデル、calendar = カレンダーのみ、
 * calendar_dow = 学習データに無い月（曜日ベース・精度は最も低い）。
 */
export type ModelKind = "lag" | "calendar" | "calendar_dow";

export const MODEL_LABELS: Record<ModelKind, string> = {
  lag: "実績ラグあり（高精度）",
  calendar: "カレンダー予測",
  calendar_dow: "曜日ベース予測（学習外の時期）",
};

export type DailyPoint = {
  shop_id: string;
  date: string;
  pred_receipts: number;
  pred_avg_spend: number;
  pred_net_sales: number;
  actual_receipts: number | null;
  actual_net_sales: number | null;
  /** 同月日の過去実績を参照した日付（前年・前々年など）。無ければ null */
  ref_date: string | null;
  ref_receipts: number | null;
  ref_net_sales: number | null;
  model: ModelKind;
};

export type AggregatePoint = {
  shop_id: string;
  period: string;
  pred_receipts: number;
  pred_avg_spend: number;
  pred_net_sales: number;
  actual_receipts: number | null;
  actual_net_sales: number | null;
  n_actual_days: number;
  ref_receipts: number | null;
  ref_net_sales: number | null;
  n_ref_days: number;
  n_days: number;
};

export type PredictResponse = {
  granularity: Granularity;
  train_end: string;
  data_end: string;
  start_date: string;
  end_date: string;
  summary: {
    n_shops: number;
    n_points: number;
    pred_receipts_total: number;
    pred_net_sales_total: number;
    actual_receipts_total: number | null;
    actual_net_sales_total: number | null;
    n_actual_days: number;
    ref_receipts_total: number | null;
    ref_net_sales_total: number | null;
    n_ref_days: number;
    models_used: ModelKind[];
  };
  daily: DailyPoint[];
  aggregates: AggregatePoint[];
};

export type ForecastContext = {
  shop_id?: string | null;
  date?: string | null;
  granularity?: Granularity | null;
  pred_receipts?: number | null;
  pred_avg_spend?: number | null;
  pred_net_sales?: number | null;
  actual_receipts?: number | null;
  ref_date?: string | null;
  ref_receipts?: number | null;
  model?: ModelKind | null;
  is_weekend?: boolean | null;
  is_holiday?: boolean | null;
  is_payday?: boolean | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export function fetchShops() {
  return request<ShopInfo[]>("/shops");
}

export function runPredict(body: {
  granularity: Granularity;
  shop_ids?: string[];
  start_date?: string;
  end_date?: string;
}) {
  return request<PredictResponse>("/predict", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function runChat(body: {
  message: string;
  context?: ForecastContext | null;
  history?: ChatMessage[];
}) {
  return request<{ reply: string; used_llm: boolean; context_used: boolean }>(
    "/chat",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export { API_BASE };
