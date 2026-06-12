"""イベント・観光向け 販売予測デモ用の合成データ生成モジュール.

実データが無い段階で「AIが本当に学習・予測できるか」を検証するため、
現実的なパターンを意図的に埋め込んだ疑似データを生成する。

埋め込む構造（モデルが学習できれば成功）:
  - 曜日周期      : 週末・金曜は売上が高い
  - 季節性        : 春・秋（行楽シーズン）に需要が高まる
  - 祝日／連休効果: 祝日・連休はさらに上振れ
  - 天候影響      : 降水で減少、快適な気温で増加
  - SNS 先行効果  : 「翌日の需要」を先取りして当日の言及数が増える
                    → 前日のSNS言及数が翌日売上の先行指標になる
  - ノイズ        : 現実同様のランダム変動
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import jpholiday
except ImportError:  # pragma: no cover
    jpholiday = None


def _is_holiday(date: pd.Timestamp) -> bool:
    if jpholiday is not None:
        return jpholiday.is_holiday(date.date())
    return False


def generate_synthetic_data(
    start: str = "2024-01-01",
    days: int = 730,
    seed: int = 42,
) -> pd.DataFrame:
    """合成データを生成して DataFrame で返す.

    Returns に含まれる主な列:
      date              : 日付
      sales_amount      : 売上金額（=予測対象, 目的変数）
      temp_max/temp_min : 最高/最低気温（当日の予報値という想定）
      precipitation_mm  : 降水量(mm)（当日の予報値という想定）
      weather           : 天気区分（sunny / cloudy / rain）
      sns_mentions      : その日のSNS言及数（先行指標）
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start=start, periods=days, freq="D")

    # --- カレンダー属性 ---
    dow = dates.dayofweek.to_numpy()          # 0=月 ... 6=日
    doy = dates.dayofyear.to_numpy()
    is_holiday = np.array([_is_holiday(d) for d in dates])
    is_weekend = dow >= 5

    # --- 季節性: 春(4-5月)・秋(10-11月)にピークの行楽需要 ---
    seasonal = 1.0 + 0.35 * np.sin(2 * np.pi * (doy - 80) / 365.25) \
        + 0.20 * np.sin(4 * np.pi * (doy - 80) / 365.25)

    # --- 曜日係数: 週末が高く、金曜も少し高い ---
    dow_factor = np.array([0.85, 0.85, 0.88, 0.92, 1.05, 1.45, 1.35])[dow]

    # --- 祝日効果 ---
    holiday_factor = np.where(is_holiday, 1.4, 1.0)

    # --- 天候の生成 ---
    # 気温: 季節に沿った正弦波 + ノイズ
    temp_mean = 16 + 11 * np.sin(2 * np.pi * (doy - 110) / 365.25)
    temp_max = temp_mean + 5 + rng.normal(0, 1.5, days)
    temp_min = temp_mean - 5 + rng.normal(0, 1.5, days)
    # 降水: 梅雨(6-7月)・秋雨(9-10月)に降りやすい
    rain_prob = 0.20 + 0.25 * (np.isin(dates.month, [6, 7, 9, 10]))
    is_rainy = rng.random(days) < rain_prob
    precipitation_mm = np.where(
        is_rainy, rng.gamma(shape=2.0, scale=8.0, size=days), 0.0
    ).round(1)
    weather = np.where(
        precipitation_mm >= 1.0, "rain",
        np.where(rng.random(days) < 0.5, "cloudy", "sunny"),
    )

    # --- 天候による売上への影響 ---
    # 降水で減少（強雨ほど減る）、快適な気温(18-26度)で増加
    rain_effect = 1.0 - np.clip(precipitation_mm / 40.0, 0, 0.45)
    comfort = np.exp(-((temp_max - 23) ** 2) / (2 * 8.0 ** 2))  # 23度付近が最大
    weather_effect = rain_effect * (0.85 + 0.30 * comfort)

    # --- 需要ドライバー（潜在変数）---
    demand_driver = seasonal * dow_factor * holiday_factor

    # --- SNS 言及数: 「翌日の需要」を先取りして増える(先行指標) ---
    # 翌日の demand_driver が大きいほど当日に話題化する
    next_driver = np.append(demand_driver[1:], demand_driver[-1])
    sns_base = 400 * next_driver
    sns_mentions = (sns_base * (1 + rng.normal(0, 0.15, days))).clip(min=20)
    sns_mentions = sns_mentions.round().astype(int)

    # --- 売上金額の合成 ---
    base_sales = 500_000
    sales = base_sales * demand_driver * weather_effect
    sales = sales * (1 + rng.normal(0, 0.08, days))  # ノイズ
    sales = sales.clip(min=50_000).round().astype(int)

    df = pd.DataFrame(
        {
            "date": dates,
            "sales_amount": sales,
            "temp_max": temp_max.round(1),
            "temp_min": temp_min.round(1),
            "precipitation_mm": precipitation_mm,
            "weather": weather,
            "sns_mentions": sns_mentions,
        }
    )
    return df


if __name__ == "__main__":
    df = generate_synthetic_data()
    print(df.head(10).to_string(index=False))
    print("\n--- 概要統計 ---")
    print(df.describe(include="all").to_string())
