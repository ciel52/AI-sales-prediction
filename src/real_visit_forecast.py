"""実データ（A系統）購買パネル向け 来店・売上予測（フェーズ6.5）.

複数店舗をプールし、shop_id をカテゴリ特徴量として学習する。
天候・SNS・販促は当面なし。カレンダー＋ラグ特徴で予測する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

try:
    import jpholiday
except ImportError:  # pragma: no cover
    jpholiday = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = ROOT / "data" / "real_store_daily.csv"

# 予測時点で入手可能な特徴量（リーク対策：ラグは shift(1) 以上）
FEATURES = [
    "shop_id_code",
    "dow",
    "month",
    "weekofyear",
    "is_weekend",
    "is_holiday",
    "is_payday",
    "is_month_start",
    "is_month_end",
    "receipts_lag1",
    "receipts_lag7",
    "receipts_ma7",
    "receipts_ma30",
    "net_sales_lag1",
    "avg_spend_lag1",
    "members_lag1",
]

SPEND_FEATURES = [
    "shop_id_code",
    "dow",
    "month",
    "is_weekend",
    "is_holiday",
    "avg_spend_lag1",
    "avg_spend_ma7",
]

FEATURES_REQUIRED = [
    "shop_id_code",
    "dow",
    "month",
    "weekofyear",
    "is_weekend",
    "is_holiday",
    "is_payday",
    "is_month_start",
    "is_month_end",
    "receipts_lag1",
    "receipts_lag7",
    "receipts_ma7",
    "net_sales_lag1",
    "avg_spend_lag1",
    "members_lag1",
]


# --- 疎な店舗（連続日次でない店舗）も活用するための特徴量セット ---
# カレンダーのみ（B案）：ラグを使わないため全店舗・全行を学習に使える
CALENDAR_FEATURES = [
    "shop_id_code",
    "dow",
    "month",
    "weekofyear",
    "is_weekend",
    "is_holiday",
    "is_payday",
    "is_month_start",
    "is_month_end",
]

# 直近実績ラグ（A案）：「Nカレンダー日前」ではなく「直近の観測レコード」をラグに使い、
# 空白日数（gap_days）を明示的に特徴量化する。187店すべてでプールできる。
ASOF_FEATURES = CALENDAR_FEATURES + [
    "gap_days",
    "receipts_lag1_asof",
    "receipts_lag2_asof",
    "receipts_ma3_asof",
    "receipts_ma7_asof",
    "n_prior_records",
]


def _is_holiday(d: pd.Timestamp) -> bool:
    if jpholiday is None:
        return False
    return bool(jpholiday.is_holiday(d.date()))


def load_pooled_panel(
    path: Path | str = DEFAULT_PANEL,
    min_days: int = 60,
) -> tuple[pd.DataFrame, pd.Index]:
    """店舗×日パネルを読み込み、日次カバレッジが min_days 以上の店舗に絞る."""
    df = pd.read_csv(path, dtype={"shop_id": str}, parse_dates=["date"])
    cov = df.groupby("shop_id")["date"].nunique()
    dense_shops = cov[cov >= min_days].index
    pooled = df[df["shop_id"].isin(dense_shops)].copy()
    pooled = pooled.sort_values(["shop_id", "date"]).reset_index(drop=True)
    return pooled, dense_shops


def build_features_pooled(df: pd.DataFrame) -> pd.DataFrame:
    """店舗ごとにラグを計算し、カレンダー特徴を付与する."""
    d = df.copy()
    dt = d["date"].dt
    d["dow"] = dt.dayofweek
    d["month"] = dt.month
    d["weekofyear"] = dt.isocalendar().week.astype(int)
    d["is_weekend"] = (d["dow"] >= 5).astype(int)
    d["is_holiday"] = d["date"].map(_is_holiday).astype(int)
    d["is_payday"] = d["date"].dt.day.between(24, 26).astype(int)
    d["is_month_start"] = (d["date"].dt.day <= 3).astype(int)
    d["is_month_end"] = (d["date"].dt.day >= 28).astype(int)

    g = d.groupby("shop_id", sort=False)
    d["receipts_lag1"] = g["receipts"].shift(1)
    d["receipts_lag7"] = g["receipts"].shift(7)
    d["receipts_ma7"] = g["receipts"].shift(1).transform(lambda s: s.rolling(7, min_periods=3).mean())
    d["receipts_ma30"] = g["receipts"].shift(1).transform(lambda s: s.rolling(30, min_periods=7).mean())
    d["net_sales_lag1"] = g["net_sales"].shift(1)
    d["avg_spend_lag1"] = g["avg_spend"].shift(1)
    d["avg_spend_ma7"] = g["avg_spend"].shift(1).transform(lambda s: s.rolling(7, min_periods=3).mean())
    d["members_lag1"] = g["members"].shift(1)

    d["shop_id_code"] = d["shop_id"].astype("category").cat.codes.astype(int)
    return d


def load_full_panel(path: Path | str = DEFAULT_PANEL) -> pd.DataFrame:
    """店舗×日パネルを、日次カバレッジで絞らず全店舗そのまま読み込む."""
    df = pd.read_csv(path, dtype={"shop_id": str}, parse_dates=["date"])
    return df.sort_values(["shop_id", "date"]).reset_index(drop=True)


def build_features_full(df: pd.DataFrame) -> pd.DataFrame:
    """疎密問わず全店舗向けの特徴量。ラグは「直近の観測レコード」を採用し、
    前回レコードからの空白日数（gap_days）を明示的に特徴量化する。
    """
    d = df.copy().sort_values(["shop_id", "date"]).reset_index(drop=True)
    dt = d["date"].dt
    d["dow"] = dt.dayofweek
    d["month"] = dt.month
    d["weekofyear"] = dt.isocalendar().week.astype(int)
    d["is_weekend"] = (d["dow"] >= 5).astype(int)
    d["is_holiday"] = d["date"].map(_is_holiday).astype(int)
    d["is_payday"] = d["date"].dt.day.between(24, 26).astype(int)
    d["is_month_start"] = (d["date"].dt.day <= 3).astype(int)
    d["is_month_end"] = (d["date"].dt.day >= 28).astype(int)

    g = d.groupby("shop_id", sort=False)
    d["gap_days"] = g["date"].diff().dt.days
    d["receipts_lag1_asof"] = g["receipts"].shift(1)
    d["receipts_lag2_asof"] = g["receipts"].shift(2)
    d["receipts_ma3_asof"] = g["receipts"].shift(1).transform(lambda s: s.rolling(3, min_periods=1).mean())
    d["receipts_ma7_asof"] = g["receipts"].shift(1).transform(lambda s: s.rolling(7, min_periods=1).mean())
    d["n_prior_records"] = g.cumcount()

    d["shop_id_code"] = d["shop_id"].astype("category").cat.codes.astype(int)
    return d


@dataclass
class FullModelResult:
    model: HistGradientBoostingRegressor
    features: list[str]
    df_feat: pd.DataFrame
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_shops: int


def train_calendar_only_model(
    df: pd.DataFrame,
    test_days: int = 14,
    test_end: pd.Timestamp | str | None = None,
    random_state: int = 42,
) -> FullModelResult:
    """B案：ラグを使わず、カレンダー＋店舗IDのみで全店舗・全行を学習する."""
    d = build_features_full(df)
    dates = sorted(pd.Timestamp(x).normalize() for x in d["date"].unique())
    test_start, test_end_ts = _resolve_test_window(dates, test_days, test_end)
    train = d[d["date"] < test_start]
    if train.empty:
        raise ValueError("学習データが空です。test_days を減らすか test_end を調整してください。")

    cat_idx = [CALENDAR_FEATURES.index("shop_id_code")]
    model = HistGradientBoostingRegressor(
        max_iter=500,
        learning_rate=0.05,
        max_depth=6,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=random_state,
        categorical_features=cat_idx,
    )
    model.fit(train[CALENDAR_FEATURES], train["receipts"])

    return FullModelResult(
        model=model,
        features=CALENDAR_FEATURES,
        df_feat=d,
        train_end=train["date"].max(),
        test_start=test_start,
        test_end=test_end_ts,
        n_shops=d["shop_id"].nunique(),
    )


def train_asof_model(
    df: pd.DataFrame,
    test_days: int = 14,
    test_end: pd.Timestamp | str | None = None,
    random_state: int = 42,
    min_prior_records: int = 1,
) -> FullModelResult:
    """A案：直近実績ラグ＋空白日数を使い、187店すべてをプールして学習する.

    各店舗の最初の記録（ラグが取れない行）は自動的に除外される。
    """
    d = build_features_full(df)
    d = d[d["n_prior_records"] >= min_prior_records]
    d = d.dropna(subset=["receipts_lag1_asof"]).reset_index(drop=True)

    dates = sorted(pd.Timestamp(x).normalize() for x in d["date"].unique())
    test_start, test_end_ts = _resolve_test_window(dates, test_days, test_end)
    train = d[d["date"] < test_start]
    if train.empty:
        raise ValueError("学習データが空です。test_days を減らすか test_end を調整してください。")

    cat_idx = [ASOF_FEATURES.index("shop_id_code")]
    model = HistGradientBoostingRegressor(
        max_iter=500,
        learning_rate=0.05,
        max_depth=6,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=random_state,
        categorical_features=cat_idx,
    )
    model.fit(train[ASOF_FEATURES], train["receipts"])

    return FullModelResult(
        model=model,
        features=ASOF_FEATURES,
        df_feat=d,
        train_end=train["date"].max(),
        test_start=test_start,
        test_end=test_end_ts,
        n_shops=d["shop_id"].nunique(),
    )


def evaluate_full_model(result: FullModelResult, name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """FullModelResult の検証期間を評価する（テスト日は実際にレコードがある日のみ）."""
    df_feat = result.df_feat
    test = df_feat[
        (df_feat["date"] >= result.test_start) & (df_feat["date"] <= result.test_end)
    ].copy()
    pred = result.model.predict(test[result.features])
    test = test.assign(pred_receipts=pred)
    metrics = pd.DataFrame([evaluate(name, test["receipts"].values, pred)])
    return metrics, test


def compare_coverage_strategies(
    df_full: pd.DataFrame,
    test_days: int = 14,
    test_end: pd.Timestamp | str | None = None,
    min_days_dense: int = 60,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """密店舗限定プール（既存）と、疎データも使う2方式（A案/B案）を同じ検証期間で比較する."""
    rows: list[dict] = []
    test_frames: dict[str, pd.DataFrame] = {}

    dense_pooled, dense_shops = load_pooled_panel(min_days=min_days_dense)
    dense_models = train_models_pooled(
        dense_pooled, test_days=test_days, test_end=test_end, random_state=random_state
    )
    dense_visit, _, dense_test = run_evaluation(dense_models)
    ml_dense = dense_visit.loc[dense_visit["モデル"] == "勾配ブースティング"].iloc[0]
    rows.append({
        "方式": f"従来:密店舗のみ(min_days={min_days_dense})",
        "対象店舗数": len(dense_shops),
        "評価行数": len(dense_test),
        "MAPE(%)": round(ml_dense["MAPE(%)"], 1),
        "繁忙日MAPE(%)": round(ml_dense["繁忙日MAPE(%)"], 1),
    })
    test_frames["dense"] = dense_test

    cal_result = train_calendar_only_model(
        df_full, test_days=test_days, test_end=test_end, random_state=random_state
    )
    cal_metrics, cal_test = evaluate_full_model(cal_result, "B案:カレンダーのみ")
    rows.append({
        "方式": "B案:カレンダーのみ(全187店)",
        "対象店舗数": cal_result.n_shops,
        "評価行数": len(cal_test),
        "MAPE(%)": round(cal_metrics.iloc[0]["MAPE(%)"], 1),
        "繁忙日MAPE(%)": round(cal_metrics.iloc[0]["繁忙日MAPE(%)"], 1),
    })
    test_frames["calendar"] = cal_test

    asof_result = train_asof_model(
        df_full, test_days=test_days, test_end=test_end, random_state=random_state
    )
    asof_metrics, asof_test = evaluate_full_model(asof_result, "A案:直近実績ラグ")
    rows.append({
        "方式": "A案:直近実績ラグ+空白日数(全187店)",
        "対象店舗数": asof_result.n_shops,
        "評価行数": len(asof_test),
        "MAPE(%)": round(asof_metrics.iloc[0]["MAPE(%)"], 1),
        "繁忙日MAPE(%)": round(asof_metrics.iloc[0]["繁忙日MAPE(%)"], 1),
    })
    test_frames["asof"] = asof_test

    return pd.DataFrame(rows), test_frames


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true > 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def evaluate(name: str, y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_true - y_pred
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    overall_mape = mape(y_true, y_pred)
    peak_thr = np.quantile(y_true, 0.8)
    peak_mask = y_true >= peak_thr
    peak_mape = mape(y_true[peak_mask], y_pred[peak_mask]) if peak_mask.any() else float("nan")
    return {
        "モデル": name,
        "MAE": mae,
        "RMSE": rmse,
        "MAPE(%)": overall_mape,
        "繁忙日MAPE(%)": peak_mape,
    }


@dataclass
class PooledForecastModels:
    visit_model: HistGradientBoostingRegressor
    spend_model: HistGradientBoostingRegressor
    df_feat: pd.DataFrame
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    shop_categories: pd.Index


def _resolve_test_window(
    dates: list[pd.Timestamp],
    test_days: int,
    test_end: pd.Timestamp | str | None = None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """検証期間の開始日・終了日を決める（test_end 指定時はその日を検証最終日とする）."""
    if test_days < 1:
        raise ValueError("test_days は 1 以上を指定してください")
    if test_days >= len(dates):
        raise ValueError(f"test_days={test_days} がユニーク日数 {len(dates)} 以上です")

    if test_end is None:
        window = dates[-test_days:]
    else:
        end = pd.Timestamp(test_end).normalize()
        if end not in dates:
            raise ValueError(f"test_end={end.date()} はデータに存在しません")
        end_idx = dates.index(end)
        if end_idx + 1 < test_days:
            raise ValueError(
                f"test_end={end.date()} より前に test_days={test_days} 分の学習前データがありません"
            )
        window = dates[end_idx - test_days + 1 : end_idx + 1]

    return pd.Timestamp(window[0]), pd.Timestamp(window[-1])


def train_models_pooled(
    df: pd.DataFrame,
    test_days: int = 14,
    test_end: pd.Timestamp | str | None = None,
    random_state: int = 42,
) -> PooledForecastModels:
    """プールデータで来店（receipts）・客単価モデルを学習する（日付で時系列分割）."""
    df_feat = build_features_pooled(df)
    df_feat = df_feat.dropna(subset=FEATURES_REQUIRED).reset_index(drop=True)

    dates = sorted(pd.Timestamp(d).normalize() for d in df_feat["date"].unique())
    test_start, test_end = _resolve_test_window(dates, test_days, test_end)
    train = df_feat[df_feat["date"] < test_start]
    if train.empty:
        raise ValueError("学習データが空です。test_days を減らすか min_days を調整してください。")

    cat_idx = [FEATURES.index("shop_id_code")]
    visit_model = HistGradientBoostingRegressor(
        max_iter=500,
        learning_rate=0.05,
        max_depth=6,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=random_state,
        categorical_features=cat_idx,
    )
    visit_model.fit(train[FEATURES], train["receipts"])

    spend_cat_idx = [SPEND_FEATURES.index("shop_id_code")]
    spend_model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.05,
        max_depth=4,
        random_state=random_state,
        categorical_features=spend_cat_idx,
    )
    spend_model.fit(train[SPEND_FEATURES], train["avg_spend"])

    return PooledForecastModels(
        visit_model=visit_model,
        spend_model=spend_model,
        df_feat=df_feat,
        train_end=train["date"].max(),
        test_start=test_start,
        test_end=test_end,
        shop_categories=df_feat["shop_id"].astype("category").cat.categories,
    )


def predict_baselines(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    """店舗×曜日の学習平均など、プール向けベースラインを返す."""
    shop_dow_mean = train.groupby(["shop_id", "dow"])["receipts"].mean()
    shop_mean = train.groupby("shop_id")["receipts"].mean()

    base_lag7 = test["receipts_lag7"].fillna(test["receipts_lag1"]).values
    base_ma7 = test["receipts_ma7"].values
    base_dow = test.apply(
        lambda r: shop_dow_mean.get((r["shop_id"], r["dow"]), shop_mean.get(r["shop_id"], np.nan)),
        axis=1,
    ).astype(float).values

    shop_dow_spend = train.groupby(["shop_id", "dow"])["avg_spend"].mean()
    shop_spend_mean = train.groupby("shop_id")["avg_spend"].mean()
    base_spend_dow = test.apply(
        lambda r: shop_dow_spend.get((r["shop_id"], r["dow"]), shop_spend_mean.get(r["shop_id"], np.nan)),
        axis=1,
    ).astype(float).values

    return {
        "lag7": base_lag7,
        "ma7": base_ma7,
        "dow": base_dow,
        "spend_dow": base_spend_dow,
    }


def run_evaluation(
    models: PooledForecastModels,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """学習済みモデルで検証期間の精度を評価し、来店・売上の結果表を返す."""
    df_feat = models.df_feat
    train = df_feat[df_feat["date"] < models.test_start]
    test = df_feat[
        (df_feat["date"] >= models.test_start) & (df_feat["date"] <= models.test_end)
    ].copy()

    y_receipts = test["receipts"].values
    pred_receipts = models.visit_model.predict(test[FEATURES])
    pred_spend = models.spend_model.predict(test[SPEND_FEATURES])
    pred_sales = pred_receipts * pred_spend

    bases = predict_baselines(train, test)
    base_sales_lag7 = bases["lag7"] * bases["spend_dow"]
    base_sales_dow = bases["dow"] * bases["spend_dow"]

    visit_results = pd.DataFrame([
        evaluate("勾配ブースティング", y_receipts, pred_receipts),
        evaluate("ベースラインA(7日前)", y_receipts, bases["lag7"]),
        evaluate("ベースラインB(7日移動平均)", y_receipts, bases["ma7"]),
        evaluate("ベースラインC(店舗×曜日平均)", y_receipts, bases["dow"]),
    ])

    y_sales = test["net_sales"].values
    sales_results = pd.DataFrame([
        evaluate("来店×客単価", y_sales, pred_sales),
        evaluate("ベースライン(7日前×客単価)", y_sales, base_sales_lag7),
        evaluate("ベースライン(曜日平均×客単価)", y_sales, base_sales_dow),
    ])

    test = test.assign(
        pred_receipts=pred_receipts,
        pred_avg_spend=pred_spend,
        pred_net_sales=pred_sales,
    )
    return visit_results, sales_results, test


def compare_validation_periods(
    df: pd.DataFrame,
    scenarios: list[dict],
    test_days: int = 14,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """複数の検証期間設定で精度を比較する.

    scenarios の各要素は {"name": str, "test_end": "YYYY-MM-DD" | None}。
    test_end が None のときはデータ最終日を検証終了日とする。
    """
    summary_rows: list[dict] = []
    daily_errors: dict[str, pd.DataFrame] = {}

    for scenario in scenarios:
        name = scenario["name"]
        test_end = scenario.get("test_end")
        models = train_models_pooled(
            df, test_days=test_days, test_end=test_end, random_state=random_state
        )
        visit_results, sales_results, test_df = run_evaluation(models)

        test_end_ts = test_df["date"].max()
        test_start_ts = test_df["date"].min()
        ml_visit = visit_results.loc[visit_results["モデル"] == "勾配ブースティング"].iloc[0]
        ml_sales = sales_results.loc[sales_results["モデル"] == "来店×客単価"].iloc[0]

        daily = test_df.groupby("date").agg(
            actual=("receipts", "sum"),
            pred=("pred_receipts", "sum"),
        ).reset_index()
        daily["ape"] = (daily["pred"] - daily["actual"]).abs() / daily["actual"] * 100
        daily["scenario"] = name
        daily_errors[name] = daily

        mid = len(daily) // 2
        summary_rows.append({
            "検証設定": name,
            "検証期間": f"{test_start_ts.date()}〜{test_end_ts.date()}",
            "学習終了": models.train_end.date(),
            "来店MAPE(%)": round(ml_visit["MAPE(%)"], 1),
            "来店繁忙日MAPE(%)": round(ml_visit["繁忙日MAPE(%)"], 1),
            "売上MAPE(%)": round(ml_sales["MAPE(%)"], 1),
            "検証前半MAPE(%)": round(daily.iloc[:mid]["ape"].mean(), 1),
            "検証後半MAPE(%)": round(daily.iloc[mid:]["ape"].mean(), 1),
        })

    return pd.DataFrame(summary_rows), daily_errors
