"""小売・サービス業 ポイントシステム向け 来店・売上予測デモ用の擬似データ生成モジュール.

実データが揃う前に「来店予測 → 売上予測が良い精度でできるか」を検証するため、
1店舗・日次・2年分のデータを、現実的な関係性を意図的に埋め込んで生成する。

目的変数:
  - visitors      : 来店客数（主たる予測対象）
  - sales_amount  : 売上金額（= visitors × avg_spend, 従たる予測対象）

説明変数（指定の4ソース + 追加提案データ）:
  ① CSPM購買情報  : 会員来店数・新規/リピート比率・客単価・カテゴリ構成（集計値）
  ② 天候情報      : 最高/最低気温・降水量・天気区分（当日の予報値という想定）
  ③ 人流予測      : 店舗周辺の人出指数（潜在需要と相関する説明変数）
  ④ SNS情報       : 言及数・感情スコア（前日までの値が翌日来店の先行指標になる）
  + 販促系        : ポイント◯倍デー・特売・クーポン配信
  + カレンダー    : 曜日・祝日・給料日・月初/月末

埋め込んだ関係（フェーズ2のモデルが学習・再現できれば成功）:
  - 週末・金曜は来店増（曜日周期）
  - 季節性（年末商戦・行楽期に増加）
  - 祝日・連休で増加
  - 給料日（25日前後）・月末で増加
  - 雨で減少、快適な気温で微増（天候影響）
  - 人流が多い日は来店増（人流連動）
  - 翌日の需要を先取りしてSNS言及が増える（SNS先行効果）
  - ポイント◯倍デー・特売・クーポンで来店増（販促効果）
  - 客単価は特売・週末で上昇
  - ランダムなバズ（突発的話題）と観測ノイズ
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


def generate_retail_data(
    start: str = "2024-01-01",
    days: int = 730,
    seed: int = 42,
    base_visitors: int = 800,
    base_spend: int = 2500,
) -> pd.DataFrame:
    """小売ポイントシステム想定の擬似データを生成して DataFrame で返す."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start=start, periods=days, freq="D")

    dow = dates.dayofweek.to_numpy()          # 0=月 ... 6=日
    doy = dates.dayofyear.to_numpy()
    dom = dates.day.to_numpy()
    month = dates.month.to_numpy()
    is_holiday = np.array([_is_holiday(d) for d in dates])
    is_weekend = dow >= 5

    # ===== カレンダー由来の需要係数 =====
    # 季節性: 年末(12月)商戦と春・秋の行楽期にピーク
    seasonal = (
        1.0
        + 0.18 * np.sin(2 * np.pi * (doy - 80) / 365.25)   # 春・秋の波
        + 0.30 * np.exp(-((doy - 350) ** 2) / (2 * 18 ** 2))  # 年末ピーク
    )
    # 曜日係数: 週末・金曜が高い
    dow_factor = np.array([0.90, 0.85, 0.88, 0.92, 1.12, 1.45, 1.32])[dow]
    # 祝日効果
    holiday_factor = np.where(is_holiday, 1.25, 1.0)
    # 給料日効果: 25日前後 ＋ 月末
    payday = (np.abs(dom - 25) <= 1) | (dom >= 29)
    payday_factor = np.where(payday, 1.15, 1.0)

    # ===== 天候 =====
    temp_mean = 16 + 11 * np.sin(2 * np.pi * (doy - 110) / 365.25)
    temp_max = (temp_mean + 5 + rng.normal(0, 1.5, days)).round(1)
    temp_min = (temp_mean - 5 + rng.normal(0, 1.5, days)).round(1)
    rain_prob = 0.20 + 0.25 * np.isin(month, [6, 7, 9, 10])
    is_rainy = rng.random(days) < rain_prob
    precipitation_mm = np.where(
        is_rainy, rng.gamma(shape=2.0, scale=8.0, size=days), 0.0
    ).round(1)
    weather = np.where(
        precipitation_mm >= 1.0, "rain",
        np.where(rng.random(days) < 0.5, "cloudy", "sunny"),
    )
    # 売上への天候影響: 雨で減少（屋外移動が減る）、快適気温(20〜26度)で微増
    rain_effect = 1.0 - np.clip(precipitation_mm / 50.0, 0, 0.35)
    comfort = np.exp(-((temp_max - 23) ** 2) / (2 * 9.0 ** 2))
    weather_effect = rain_effect * (0.90 + 0.18 * comfort)

    # ===== 販促系 =====
    # ポイント◯倍デー: 「5のつく日(5,15,25)」は5倍、毎月10日は10倍デー
    point_multiplier = np.ones(days)
    point_multiplier[np.isin(dom, [5, 15, 25])] = 5.0
    point_multiplier[dom == 10] = 10.0
    # 特売: 毎月第1金土日 + 不定期週末セール
    week_of_month = (dom - 1) // 7 + 1
    is_sale = ((week_of_month == 1) & is_weekend) | (
        is_weekend & (rng.random(days) < 0.15)
    )
    is_sale = is_sale.astype(bool)
    # クーポン配信: 不定期（配信日とその後2日に来店押し上げ効果）
    coupon_sent = rng.random(days) < 0.08
    coupon_effect_window = (
        coupon_sent.astype(float)
        + np.roll(coupon_sent, 1) * 0.6
        + np.roll(coupon_sent, 2) * 0.3
    )

    promo_factor = (
        1.0
        + 0.06 * (point_multiplier == 5.0)
        + 0.16 * (point_multiplier == 10.0)
        + 0.22 * is_sale
        + 0.08 * coupon_effect_window
    )

    # ===== 潜在需要（人流・SNS・来店が共有するドライバー）=====
    latent = seasonal * dow_factor * holiday_factor * payday_factor * weather_effect

    # 突発的なバズ（数%の日に発生し、SNSと来店を同時に押し上げる）
    viral = np.where(rng.random(days) < 0.04, rng.uniform(0.2, 0.5, days), 0.0)

    # ===== 人流予測（潜在需要と相関する説明変数）=====
    foot_traffic = (
        10000 * latent * (1 + 0.10 * viral) * (1 + rng.normal(0, 0.10, days))
    ).clip(min=1000).round().astype(int)

    # ===== SNS（翌日の需要を先取り = 先行指標）=====
    latent_next = np.append(latent[1:], latent[-1])
    promo_next = np.append(promo_factor[1:], promo_factor[-1])
    viral_next = np.append(viral[1:], viral[-1])
    sns_base = 300 * latent_next * promo_next * (1 + 0.8 * viral_next)
    sns_mentions = (sns_base * (1 + rng.normal(0, 0.15, days))).clip(min=20).round().astype(int)
    sns_sentiment = np.clip(
        0.55 + 0.5 * viral - 0.15 * (precipitation_mm > 10) + rng.normal(0, 0.08, days),
        0, 1,
    ).round(3)

    # ===== 来店客数（目的変数）=====
    visitors = (
        base_visitors
        * latent
        * promo_factor
        * (1 + 0.25 * viral)
        * (1 + rng.normal(0, 0.07, days))
    ).clip(min=50).round().astype(int)

    # ===== 客単価（特売・週末で上昇、ポイント倍デーは買い回りで微増）=====
    avg_spend = (
        base_spend
        * (1 + 0.12 * is_sale + 0.05 * is_weekend + 0.03 * (point_multiplier >= 5))
        * (1 + rng.normal(0, 0.05, days))
    ).clip(min=800).round().astype(int)

    sales_amount = (visitors * avg_spend).astype(int)

    # ===== 会員（CSPM）集計値 =====
    member_ratio = np.clip(0.62 + 0.05 * (point_multiplier >= 5) + rng.normal(0, 0.03, days), 0.4, 0.9)
    member_visitors = (visitors * member_ratio).round().astype(int)
    new_member_ratio = np.clip(0.05 + 0.03 * is_sale + rng.normal(0, 0.01, days), 0.01, 0.2).round(3)
    repeat_ratio = (1 - new_member_ratio).round(3)

    df = pd.DataFrame(
        {
            "date": dates,
            # --- 目的変数 ---
            "visitors": visitors,
            "sales_amount": sales_amount,
            "avg_spend": avg_spend,
            # --- ① CSPM購買情報（会員集計）---
            "member_visitors": member_visitors,
            "member_ratio": member_ratio.round(3),
            "new_member_ratio": new_member_ratio,
            "repeat_ratio": repeat_ratio,
            # --- ② 天候 ---
            "temp_max": temp_max,
            "temp_min": temp_min,
            "precipitation_mm": precipitation_mm,
            "weather": weather,
            # --- ③ 人流予測 ---
            "foot_traffic": foot_traffic,
            # --- ④ SNS ---
            "sns_mentions": sns_mentions,
            "sns_sentiment": sns_sentiment,
            # --- 販促系 ---
            "point_multiplier": point_multiplier.astype(int),
            "is_sale": is_sale.astype(int),
            "coupon_sent": coupon_sent.astype(int),
            # --- カレンダー ---
            "is_holiday": is_holiday.astype(int),
            "is_weekend": is_weekend.astype(int),
            "is_payday": payday.astype(int),
        }
    )
    return df


if __name__ == "__main__":
    df = generate_retail_data()
    print(df.head(10).to_string(index=False))
    print("\n--- 概要統計 ---")
    print(df.describe().round(2).to_string())
