"""生の購買データ取込: 店舗×日パネルへの変換と状態照会."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

import pandas as pd

from real_data_etl import PANEL_PATH, find_buying_file, ingest_buying_to_panel

_lock = Lock()
_ingesting = False


def data_status() -> dict:
    raw = find_buying_file()
    panel = PANEL_PATH
    exists = panel.is_file() and panel.stat().st_size > 0
    row: dict = {
        "ingesting": _ingesting,
        "panel_exists": exists,
        "panel_path": str(panel),
        "n_rows": None,
        "n_shops": None,
        "date_min": None,
        "date_max": None,
        "raw_found": raw is not None,
        "raw_path": str(raw) if raw else None,
        "hint": "",
    }
    if exists:
        df = pd.read_csv(panel, usecols=["shop_id", "date"], dtype=str)
        row["n_rows"] = int(len(df))
        row["n_shops"] = int(df["shop_id"].nunique())
        row["date_min"] = str(df["date"].min())
        row["date_max"] = str(df["date"].max())
    elif raw is not None:
        row["hint"] = (
            "集計済みパネルがありません。配置済みの生データから変換できます。"
        )
    else:
        row["hint"] = (
            "集計済みパネル（data/real_store_daily.csv）がありません。"
            "ファイルを配置するか、RAW_BUYING_PATH / test_data の生購買から変換してください。"
        )
    return row


def ingest_buying(source: Path | str | None = None) -> dict:
    """生ファイルを店舗×日に集計して保存する（学習は呼び出し側）。"""
    global _ingesting
    with _lock:
        _ingesting = True
        try:
            return ingest_buying_to_panel(source)
        finally:
            _ingesting = False
