"""来店予測の特徴量・学習・予測を再利用可能にまとめたモジュール（フェーズ2のロジックを共通化）.

フェーズ5（LLM施策提案）など、他のノートブックからも同じ予測パイプラインを使えるようにする。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# 来店予測に使う特徴量（予測時点で入手可能な情報のみ＝リーク対策済み）
FEATURES = [
    # カレンダー
    "dow", "month", "weekofyear", "is_weekend", "is_holiday", "is_payday",
    # 販促
    "point_multiplier", "is_sale", "coupon_sent",
    # 天候（予報値）
    "temp_max", "temp_min", "precipitation_mm", "rain_flag",
    "heavy_rain_flag", "comfortable_temp", "temp_range",
    # 人流（予測値）
    "foot_traffic",
    # SNS（前日まで）
    "sns_lag1", "sns_ma3", "sns_ma7", "sns_surge",
    # 来店ラグ
    "visitors_lag1", "visitors_lag7", "visitors_lag365", "visitors_ma7", "visitors_ma30",
]

# 客単価モデルの特徴量（事前に分かる情報のみ）
SPEND_FEATURES = ["dow", "month", "is_weekend", "is_holiday", "is_sale", "point_multiplier"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """生データから来店予測用の特徴量テーブルを作る."""
    d = df.copy().sort_values("date").reset_index(drop=True)
    dt = d["date"].dt

    d["dow"] = dt.dayofweek
    d["month"] = dt.month
    d["weekofyear"] = dt.isocalendar().week.astype(int)

    d["rain_flag"] = (d["precipitation_mm"] >= 1.0).astype(int)
    d["heavy_rain_flag"] = (d["precipitation_mm"] >= 20.0).astype(int)
    d["comfortable_temp"] = ((d["temp_max"] >= 20) & (d["temp_max"] <= 26)).astype(int)
    d["temp_range"] = d["temp_max"] - d["temp_min"]

    d["sns_lag1"] = d["sns_mentions"].shift(1)
    d["sns_ma3"] = d["sns_mentions"].shift(1).rolling(3).mean()
    d["sns_ma7"] = d["sns_mentions"].shift(1).rolling(7).mean()
    d["sns_surge"] = (d["sns_lag1"] > d["sns_ma7"] * 1.2).astype(int)

    d["visitors_lag1"] = d["visitors"].shift(1)
    d["visitors_lag7"] = d["visitors"].shift(7)
    d["visitors_lag365"] = d["visitors"].shift(365)
    d["visitors_ma7"] = d["visitors"].shift(1).rolling(7).mean()
    d["visitors_ma30"] = d["visitors"].shift(1).rolling(30).mean()

    return d


@dataclass
class ForecastModels:
    visit_model: HistGradientBoostingRegressor
    spend_model: HistGradientBoostingRegressor
    df_feat: pd.DataFrame
    train_end: pd.Timestamp


def train_models(df: pd.DataFrame, test_days: int = 90, random_state: int = 42) -> ForecastModels:
    """来店予測モデルと客単価モデルを学習して返す."""
    df_feat = build_features(df)
    need = [c for c in FEATURES if c != "visitors_lag365"]
    df_feat = df_feat.dropna(subset=need).reset_index(drop=True)

    split_idx = len(df_feat) - test_days
    train = df_feat.iloc[:split_idx]

    visit_model = HistGradientBoostingRegressor(
        max_iter=500, learning_rate=0.05, max_depth=6, l2_regularization=1.0,
        early_stopping=True, validation_fraction=0.15, random_state=random_state,
    )
    visit_model.fit(train[FEATURES], train["visitors"])

    spend_model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, max_depth=4, random_state=random_state,
    )
    spend_model.fit(train[SPEND_FEATURES], train["avg_spend"])

    return ForecastModels(
        visit_model=visit_model,
        spend_model=spend_model,
        df_feat=df_feat,
        train_end=train["date"].max(),
    )


def predict_row(models: ForecastModels, row: pd.Series) -> dict:
    """1日分の特徴量行から来店客数・客単価・売上を予測する."""
    X_visit = row[FEATURES].to_frame().T
    X_spend = row[SPEND_FEATURES].to_frame().T
    visitors = float(models.visit_model.predict(X_visit)[0])
    spend = float(models.spend_model.predict(X_spend)[0])
    return {
        "pred_visitors": visitors,
        "pred_avg_spend": spend,
        "pred_sales": visitors * spend,
    }
