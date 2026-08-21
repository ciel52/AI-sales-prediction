"""API リクエスト / レスポンス定義."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Granularity = Literal["daily", "weekly", "monthly"]


class PredictRequest(BaseModel):
    """予測リクエスト.

    - shop_ids 未指定時はプール対象の全店舗
    - start_date / end_date 未指定時は学習時の検証期間（直近）を使用
    """

    granularity: Granularity = "daily"
    shop_ids: list[str] | None = None
    start_date: str | None = Field(None, description="YYYY-MM-DD")
    end_date: str | None = Field(None, description="YYYY-MM-DD")
    test_days: int = Field(14, ge=1, le=90, description="end_date 未指定時の検証日数")


# 予測に使ったモデル。
#   lag          … 前日・前週の実績を使う高精度モデル
#   calendar     … 曜日・祝日・月などカレンダーのみ（実績が無い日でも予測できる）
#   calendar_dow … 学習データに無い月。月・週番号を外し曜日ベースで予測（精度は最も低い）
ModelKind = Literal["lag", "calendar", "calendar_dow"]


class DailyPoint(BaseModel):
    shop_id: str
    date: str
    pred_receipts: float
    pred_avg_spend: float
    pred_net_sales: float
    actual_receipts: float | None = None
    actual_net_sales: float | None = None
    ref_date: str | None = Field(None, description="参照した同月日の過去実績の日付")
    ref_receipts: float | None = None
    ref_net_sales: float | None = None
    dow_ref_date: str | None = Field(
        None,
        description="曜日揃えで参照した過去実績の日付（同月日をずらした日付）",
    )
    dow_ref_receipts: float | None = None
    dow_ref_net_sales: float | None = None
    model: ModelKind = "lag"


class AggregatePoint(BaseModel):
    shop_id: str
    period: str
    pred_receipts: float
    pred_avg_spend: float
    pred_net_sales: float
    actual_receipts: float | None = None
    actual_net_sales: float | None = None
    n_actual_days: int = 0
    ref_receipts: float | None = None
    ref_net_sales: float | None = None
    n_ref_days: int = 0
    n_days: int


class PredictSummary(BaseModel):
    n_shops: int
    n_points: int
    pred_receipts_total: float
    pred_net_sales_total: float
    actual_receipts_total: float | None = None
    actual_net_sales_total: float | None = None
    n_actual_days: int = 0
    ref_receipts_total: float | None = None
    ref_net_sales_total: float | None = None
    n_ref_days: int = 0
    models_used: list[ModelKind] = Field(default_factory=list)


class PredictResponse(BaseModel):
    granularity: Granularity
    train_end: str
    data_end: str = Field("", description="実績データの最終日")
    start_date: str
    end_date: str
    summary: PredictSummary
    daily: list[DailyPoint] = Field(default_factory=list)
    aggregates: list[AggregatePoint] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ForecastContext(BaseModel):
    """チャットに渡す予測コンテキスト（画面で選択中の予測結果）."""

    shop_id: str | None = None
    date: str | None = None
    granularity: Granularity | None = None
    pred_receipts: float | None = None
    pred_avg_spend: float | None = None
    pred_net_sales: float | None = None
    actual_receipts: float | None = None
    ref_date: str | None = None
    ref_receipts: float | None = None
    model: ModelKind | None = None
    dow_avg_receipts: float | None = None
    recent_avg_receipts: float | None = None
    is_weekend: bool | None = None
    is_holiday: bool | None = None
    is_payday: bool | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    context: ForecastContext | None = None
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    used_llm: bool
    context_used: bool


class ShopInfo(BaseModel):
    shop_id: str
    n_days: int
    date_min: str
    date_max: str


class HealthResponse(BaseModel):
    status: str
    model_ready: bool
    n_shops: int | None = None
    data_start: str | None = None
    data_end: str | None = None
    train_end: str | None = None


class DataStatusResponse(BaseModel):
    model_ready: bool
    ingesting: bool
    panel_exists: bool
    panel_path: str
    n_rows: int | None = None
    n_shops: int | None = None
    date_min: str | None = None
    date_max: str | None = None
    raw_found: bool
    raw_path: str | None = None
    hint: str = ""


class IngestRequest(BaseModel):
    """サーバ上の生購買ファイルを店舗×日に集計する（ブラウザアップロードは使わない）。

    source_path 未指定時は RAW_BUYING_PATH / test_data を探す。
    """

    source_path: str | None = None


class IngestResponse(BaseModel):
    source_path: str
    panel_path: str
    n_rows: int
    n_shops: int
    date_min: str
    date_max: str
    model_ready: bool
    n_predict_shops: int | None = None
