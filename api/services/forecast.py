"""予測サービス: 既存 real_visit_forecast をラップし、日次/週次/月次を返す.

学習期間の内外どちらの日付でも予測できるよう、行ごとに3つのモデルを使い分ける。

- `lag` … 前日・前週の実績が揃う日に使う。最も精度が高いが実績が必要。
- `calendar` … 曜日・祝日・月・週番号だけで予測する。実績が無い将来日付でも使える。
- `calendar_dow` … 学習データに無い月を予測するとき。月・週番号を外して外挿を避ける。

実績は「予測対象日そのものの実績」と「同月日の過去実績（前年・前々年…）」を別々に返す。
将来日付を予測するときは前者が空になり、後者が参考値として入る。
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

import numpy as np
import pandas as pd

from real_visit_forecast import (
    FEATURES,
    FEATURES_REQUIRED,
    LAG_FEATURE_COLUMNS,
    SPEND_FEATURES,
    CalendarModels,
    build_calendar_frame,
    build_features_pooled,
    build_shop_code_map,
    load_pooled_panel,
    train_calendar_models,
    train_models_pooled,
)

from api.schemas import (
    AggregatePoint,
    DailyPoint,
    PredictRequest,
    PredictResponse,
    PredictSummary,
)

# 1リクエストで扱える上限（レスポンス肥大と学習の連打を防ぐ）
MAX_RANGE_DAYS = 400
MAX_PREDICT_ROWS = 20_000
# 同月日の過去実績を何年前まで遡って探すか
REFERENCE_YEARS_BACK = 3
# 学習期間キャッシュの保持数
MODEL_CACHE_SIZE = 8


def _num(value) -> float | None:
    """欠損・非有限値を None に落として丸める（JSON に NaN を出さないため）."""
    if value is None or pd.isna(value):
        return None
    v = float(value)
    return round(v, 2) if np.isfinite(v) else None


def _sum_optional(s: pd.Series) -> tuple[float | None, int]:
    """欠損を除いた合計と、値があった件数を返す（1件も無ければ None）."""
    v = s.dropna()
    return (round(float(v.sum()), 2) if len(v) else None, int(len(v)))


@dataclass
class ModelBundle:
    visit_model: object
    spend_model: object
    df_feat: pd.DataFrame
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    shop_ids: list[str]
    shop_code_map: dict[str, int]
    data_start: pd.Timestamp
    data_end: pd.Timestamp


class ForecastService:
    """プロセス内で学習済みモデルを保持し、予測リクエストに応答する."""

    def __init__(self, min_days: int = 60) -> None:
        self.min_days = min_days
        self._lock = Lock()
        self._bundle: ModelBundle | None = None
        self._raw: pd.DataFrame | None = None
        self._calendar_cache: dict[pd.Timestamp, CalendarModels] = {}
        self._lag_cache: dict[pd.Timestamp, tuple] = {}

    @property
    def ready(self) -> bool:
        return self._bundle is not None

    def load_and_train(
        self,
        test_days: int = 14,
        test_end: str | None = "2024-12-15",
    ) -> ModelBundle:
        """パネルを読み込み、既定の検証期間設定でモデルを学習してキャッシュする.

        パネルに preferred の検証終了日が無い（取り込みデータが別期間の）ときは、
        データの末尾 test_days 日を検証に使う。
        """
        raw, _ = load_pooled_panel(min_days=self.min_days)
        raw["shop_id"] = raw["shop_id"].astype(str)
        test_end, test_days = self._resolve_train_split(raw, test_days, test_end)
        models = train_models_pooled(raw, test_days=test_days, test_end=test_end)

        code_map = build_shop_code_map(raw["shop_id"])
        self._assert_code_map_matches(models.df_feat, code_map)

        bundle = ModelBundle(
            visit_model=models.visit_model,
            spend_model=models.spend_model,
            df_feat=models.df_feat,
            train_end=pd.Timestamp(models.train_end).normalize(),
            test_start=pd.Timestamp(models.test_start).normalize(),
            test_end=pd.Timestamp(models.test_end).normalize(),
            shop_ids=sorted(raw["shop_id"].unique().tolist()),
            shop_code_map=code_map,
            data_start=pd.Timestamp(raw["date"].min()).normalize(),
            data_end=pd.Timestamp(raw["date"].max()).normalize(),
        )
        with self._lock:
            self._raw = raw
            self._bundle = bundle
            self._calendar_cache.clear()
            self._lag_cache.clear()
        return bundle

    @staticmethod
    def _resolve_train_split(
        raw: pd.DataFrame,
        test_days: int,
        test_end: str | None,
    ) -> tuple[str | None, int]:
        dates = sorted(pd.Timestamp(d).normalize() for d in raw["date"].unique())
        if len(dates) < 2:
            raise ValueError("学習には2日以上の実績が必要です")
        test_days = min(max(1, test_days), len(dates) - 1)
        if test_end is not None:
            end = pd.Timestamp(test_end).normalize()
            if end not in dates:
                test_end = None
        return test_end, test_days

    def startup(self) -> None:
        """起動時: パネルが無ければ生データから作り、あれば学習する.

        生データもパネルも無いときは ready=False のままにし、取込APIを待って起動する。
        """
        from real_data_etl import PANEL_PATH, find_buying_file, ingest_buying_to_panel

        if not PANEL_PATH.is_file():
            raw_path = find_buying_file()
            if raw_path is None:
                return
            ingest_buying_to_panel(raw_path)
        self.load_and_train()

    @staticmethod
    def _assert_code_map_matches(df_feat: pd.DataFrame, code_map: dict[str, int]) -> None:
        """学習済みパネルの shop_id_code と、予測行に振るコードが一致することを確かめる.

        ここがズレると「別店舗として予測される」という気づきにくい不具合になる。
        """
        pairs = df_feat[["shop_id", "shop_id_code"]].drop_duplicates()
        for shop_id, code in pairs.itertuples(index=False):
            if code_map.get(str(shop_id)) != int(code):
                raise RuntimeError(
                    f"shop_id_code の対応が学習時とズレています: shop_id={shop_id}"
                )

    def ensure_ready(self) -> ModelBundle:
        if self._bundle is None:
            return self.load_and_train()
        return self._bundle

    def list_shops(self) -> list[dict]:
        bundle = self.ensure_ready()
        g = bundle.df_feat.groupby("shop_id")["date"]
        rows = []
        for shop_id, s in g:
            rows.append({
                "shop_id": str(shop_id),
                "n_days": int(s.nunique()),
                "date_min": pd.Timestamp(s.min()).strftime("%Y-%m-%d"),
                "date_max": pd.Timestamp(s.max()).strftime("%Y-%m-%d"),
            })
        return sorted(rows, key=lambda r: r["shop_id"])

    def predict(self, req: PredictRequest) -> PredictResponse:
        bundle = self.ensure_ready()
        start, end = self._resolve_range(bundle, req)

        shop_ids = sorted({str(s) for s in (req.shop_ids or bundle.shop_ids)})
        unknown = sorted(set(shop_ids) - set(bundle.shop_ids))
        if unknown:
            raise ValueError(f"未知の店舗IDです: {unknown[:5]}")

        dates = pd.date_range(start, end, freq="D")
        if len(dates) > MAX_RANGE_DAYS:
            raise ValueError(
                f"期間が長すぎます（{len(dates)}日）。{MAX_RANGE_DAYS}日以内で指定してください"
            )
        if len(dates) * len(shop_ids) > MAX_PREDICT_ROWS:
            raise ValueError(
                f"店舗数×日数が多すぎます（{len(shop_ids)}店×{len(dates)}日）。"
                "店舗または期間を絞ってください"
            )

        frame = build_calendar_frame(shop_ids, dates, bundle.shop_code_map)
        frame = self._attach_actuals(frame)
        frame = self._attach_lag_features(bundle, frame)
        frame = self._attach_reference_actuals(frame)

        use_lag = frame["has_lag"].to_numpy()
        pred_receipts = np.full(len(frame), np.nan)
        pred_spend = np.full(len(frame), np.nan)
        model_kind = np.full(len(frame), "", dtype=object)
        train_end: pd.Timestamp | None = None

        if use_lag.any():
            visit_model, spend_model, lag_train_end = self._lag_models(bundle, start, end)
            sub = frame.loc[use_lag]
            pred_receipts[use_lag] = visit_model.predict(sub[FEATURES])
            pred_spend[use_lag] = spend_model.predict(sub[SPEND_FEATURES])
            model_kind[use_lag] = "lag"
            train_end = lag_train_end

        if not use_lag.all():
            rest = ~use_lag
            calendar = self._calendar_models(bundle, start)
            receipts, spend, kind = calendar.predict_frame(frame.loc[rest])
            pred_receipts[rest] = receipts
            pred_spend[rest] = spend
            model_kind[rest] = kind
            train_end = train_end or calendar.train_end

        assert train_end is not None
        frame["pred_receipts"] = np.clip(pred_receipts, 0.0, None)
        frame["pred_avg_spend"] = np.clip(pred_spend, 0.0, None)
        frame["pred_net_sales"] = frame["pred_receipts"] * frame["pred_avg_spend"]
        frame["model"] = model_kind
        models_used = sorted(set(model_kind.tolist()))

        daily = [
            DailyPoint(
                shop_id=str(r.shop_id),
                date=pd.Timestamp(r.date).strftime("%Y-%m-%d"),
                pred_receipts=round(float(r.pred_receipts), 2),
                pred_avg_spend=round(float(r.pred_avg_spend), 2),
                pred_net_sales=round(float(r.pred_net_sales), 2),
                actual_receipts=_num(r.actual_receipts),
                actual_net_sales=_num(r.actual_net_sales),
                ref_date=(
                    pd.Timestamp(r.ref_date).strftime("%Y-%m-%d")
                    if pd.notna(r.ref_date)
                    else None
                ),
                ref_receipts=_num(r.ref_receipts),
                ref_net_sales=_num(r.ref_net_sales),
                model=str(r.model),
            )
            for r in frame.itertuples(index=False)
        ]

        aggregates: list[AggregatePoint] = []
        if req.granularity == "weekly":
            aggregates = self._aggregate(frame, "W-SUN")
        elif req.granularity == "monthly":
            aggregates = self._aggregate(frame, "M")

        actual_total, n_actual_days = _sum_optional(frame["actual_receipts"])
        actual_sales_total, _ = _sum_optional(frame["actual_net_sales"])
        ref_total, n_ref_days = _sum_optional(frame["ref_receipts"])
        ref_sales_total, _ = _sum_optional(frame["ref_net_sales"])

        summary = PredictSummary(
            n_shops=int(frame["shop_id"].nunique()),
            n_points=len(daily) if req.granularity == "daily" else len(aggregates),
            pred_receipts_total=round(float(frame["pred_receipts"].sum()), 2),
            pred_net_sales_total=round(float(frame["pred_net_sales"].sum()), 2),
            actual_receipts_total=actual_total,
            actual_net_sales_total=actual_sales_total,
            n_actual_days=n_actual_days,
            ref_receipts_total=ref_total,
            ref_net_sales_total=ref_sales_total,
            n_ref_days=n_ref_days,
            models_used=models_used,
        )

        return PredictResponse(
            granularity=req.granularity,
            train_end=train_end.strftime("%Y-%m-%d"),
            data_end=bundle.data_end.strftime("%Y-%m-%d"),
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            summary=summary,
            daily=daily,
            aggregates=aggregates,
        )

    def _resolve_range(
        self, bundle: ModelBundle, req: PredictRequest
    ) -> tuple[pd.Timestamp, pd.Timestamp]:
        if req.start_date and req.end_date:
            start = pd.Timestamp(req.start_date).normalize()
            end = pd.Timestamp(req.end_date).normalize()
        elif req.end_date:
            end = pd.Timestamp(req.end_date).normalize()
            start = end - pd.Timedelta(days=req.test_days - 1)
        elif req.start_date:
            start = pd.Timestamp(req.start_date).normalize()
            end = start + pd.Timedelta(days=req.test_days - 1)
        else:
            start, end = bundle.test_start, bundle.test_end
        if start > end:
            raise ValueError("start_date は end_date 以前である必要があります")
        if start <= bundle.data_start:
            raise ValueError(
                f"{bundle.data_start.date()} 以前は学習データが無いため予測できません"
                f"（利用可能な実績: {bundle.data_start.date()}〜{bundle.data_end.date()}）"
            )
        return start, end

    def _attach_actuals(self, frame: pd.DataFrame) -> pd.DataFrame:
        """予測対象日そのものの実績を紐づける（将来日付は欠損のまま）."""
        assert self._raw is not None
        actuals = (
            self._raw[["shop_id", "date", "receipts", "net_sales"]]
            .drop_duplicates(subset=["shop_id", "date"])
            .rename(
                columns={
                    "receipts": "actual_receipts",
                    "net_sales": "actual_net_sales",
                }
            )
        )
        return frame.merge(actuals, on=["shop_id", "date"], how="left")

    @staticmethod
    def _attach_lag_features(bundle: ModelBundle, frame: pd.DataFrame) -> pd.DataFrame:
        """ラグ特徴量が揃っている日にだけ引き当て、`has_lag` で使えるか印を付ける."""
        lag = bundle.df_feat[["shop_id", "date", *LAG_FEATURE_COLUMNS]].copy()
        lag["shop_id"] = lag["shop_id"].astype(str)
        lag["has_lag"] = True
        out = frame.merge(lag, on=["shop_id", "date"], how="left")
        out["has_lag"] = out["has_lag"].fillna(False).astype(bool)
        # ラグ以外の必須特徴量が欠けている行は念のためカレンダーモデルに回す
        missing = out[FEATURES_REQUIRED].isna().any(axis=1)
        out.loc[missing, "has_lag"] = False
        return out

    def _attach_reference_actuals(self, frame: pd.DataFrame) -> pd.DataFrame:
        """同月日の過去実績を1件だけ紐づける（前年 → 前々年 → … の順に探す）."""
        assert self._raw is not None
        actuals = (
            self._raw[["shop_id", "date", "receipts", "net_sales"]]
            .drop_duplicates(subset=["shop_id", "date"])
            .rename(
                columns={
                    "date": "ref_date",
                    "receipts": "ref_receipts",
                    "net_sales": "ref_net_sales",
                }
            )
        )

        out = frame.copy()
        out["ref_date"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
        out["ref_receipts"] = np.nan
        out["ref_net_sales"] = np.nan

        for years_back in range(1, REFERENCE_YEARS_BACK + 1):
            todo = out.index[out["ref_receipts"].isna()]
            if len(todo) == 0:
                break
            cand = out.loc[todo, ["shop_id", "date"]].copy()
            cand["ref_date"] = cand["date"] - pd.DateOffset(years=years_back)
            merged = cand.merge(actuals, on=["shop_id", "ref_date"], how="left")
            merged.index = todo
            hit = merged.index[merged["ref_receipts"].notna()]
            out.loc[hit, ["ref_date", "ref_receipts", "ref_net_sales"]] = merged.loc[
                hit, ["ref_date", "ref_receipts", "ref_net_sales"]
            ]
        return out

    def _lag_models(self, bundle: ModelBundle, start: pd.Timestamp, end: pd.Timestamp):
        """ラグモデルを返す。予測開始日以降の実績を学習に含めないよう必要なら再学習する."""
        if start <= bundle.train_end + pd.Timedelta(days=1) and end <= bundle.test_end:
            return bundle.visit_model, bundle.spend_model, bundle.train_end
        return self._train_lag_before(self._cache_cutoff(bundle, start))

    @staticmethod
    def _cache_cutoff(bundle: ModelBundle, start: pd.Timestamp) -> pd.Timestamp:
        """学習打ち切り日をキャッシュ用に丸める.

        データ最終日より先はどこを指定しても「全データで学習」と同じなので、
        将来日付のリクエストが1つのモデルを共有できるようにする。
        """
        return min(start, bundle.data_end + pd.Timedelta(days=1))

    def _train_lag_before(self, cutoff: pd.Timestamp):
        """cutoff より前の日付だけでラグモデルを学習し直す（結果はキャッシュする）."""
        with self._lock:
            cached = self._lag_cache.get(cutoff)
        if cached is not None:
            return cached

        assert self._raw is not None
        df_feat = build_features_pooled(self._raw)
        df_feat = df_feat.dropna(subset=FEATURES_REQUIRED).reset_index(drop=True)
        train = df_feat[df_feat["date"] < cutoff]
        if train.empty:
            raise ValueError(f"学習データが空です（cutoff={cutoff.date()}）")

        from sklearn.ensemble import HistGradientBoostingRegressor

        visit_model = HistGradientBoostingRegressor(
            max_iter=500,
            learning_rate=0.05,
            max_depth=6,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
            categorical_features=[FEATURES.index("shop_id_code")],
        )
        visit_model.fit(train[FEATURES], train["receipts"])
        spend_model = HistGradientBoostingRegressor(
            max_iter=300,
            learning_rate=0.05,
            max_depth=4,
            random_state=42,
            categorical_features=[SPEND_FEATURES.index("shop_id_code")],
        )
        spend_model.fit(train[SPEND_FEATURES], train["avg_spend"])

        result = (visit_model, spend_model, pd.Timestamp(train["date"].max()).normalize())
        with self._lock:
            self._trim_cache(self._lag_cache)
            self._lag_cache[cutoff] = result
        return result

    def _calendar_models(self, bundle: ModelBundle, start: pd.Timestamp) -> CalendarModels:
        """ラグ無しモデルを返す（start より前の実績だけで学習、結果はキャッシュする）."""
        cutoff = self._cache_cutoff(bundle, start)
        with self._lock:
            cached = self._calendar_cache.get(cutoff)
        if cached is not None:
            return cached

        assert self._raw is not None
        try:
            calendar = train_calendar_models(self._raw, train_end_exclusive=cutoff)
        except ValueError as e:
            raise ValueError(
                f"{start.date()} より前の実績が無いため予測できません"
                f"（利用可能な実績: {bundle.data_start.date()}〜{bundle.data_end.date()}）"
            ) from e
        with self._lock:
            self._trim_cache(self._calendar_cache)
            self._calendar_cache[cutoff] = calendar
        return calendar

    @staticmethod
    def _trim_cache(cache: dict) -> None:
        while len(cache) >= MODEL_CACHE_SIZE:
            cache.pop(next(iter(cache)))

    @staticmethod
    def _aggregate(frame: pd.DataFrame, freq: str) -> list[AggregatePoint]:
        d = frame.copy()
        d["period"] = d["date"].dt.to_period(freq).astype(str)
        rows: list[AggregatePoint] = []
        for (shop_id, period), g in d.groupby(["shop_id", "period"]):
            pred_r = float(g["pred_receipts"].sum())
            pred_s = float(g["pred_net_sales"].sum())
            pred_spend = pred_s / pred_r if pred_r else float("nan")
            actual_r, n_actual_days = _sum_optional(g["actual_receipts"])
            actual_s, _ = _sum_optional(g["actual_net_sales"])
            ref_r, n_ref_days = _sum_optional(g["ref_receipts"])
            ref_s, _ = _sum_optional(g["ref_net_sales"])
            rows.append(
                AggregatePoint(
                    shop_id=str(shop_id),
                    period=str(period),
                    pred_receipts=round(pred_r, 2),
                    pred_avg_spend=round(pred_spend, 2) if np.isfinite(pred_spend) else 0.0,
                    pred_net_sales=round(pred_s, 2),
                    actual_receipts=actual_r,
                    actual_net_sales=actual_s,
                    n_actual_days=n_actual_days,
                    ref_receipts=ref_r,
                    ref_net_sales=ref_s,
                    n_ref_days=n_ref_days,
                    n_days=int(len(g)),
                )
            )
        return rows


forecast_service = ForecastService()
