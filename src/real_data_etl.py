"""実データ（test_data/）取込・集計ETL（フェーズ6）.

提供された実データ（TSV）を、予測モデルが扱える日次パネルに集計する。

来店（通行人）と購買は店舗単位でリンクできない（端末→店舗マッピング未提供）ため、
2系統を別々のパネルとして出力する。

  A系統（主軸・リンク良好）: CSPM 購買 → 店舗×日 パネル
    - receipts     : 売上伝票数（RCPT件数）＝購買来店数の代理
    - members      : 会員ユニーク数（RCPT・会員IDありのみ）
    - gross_sales  : 総売上（RCPTの購入額合計の合計）
    - return_amount: 返品額（RETNは負値で格納されるため正の大きさに変換）
    - net_sales    : 純売上（gross_sales − return_amount）
    - discount     : 値引額合計（RCPT）
    - returns      : 返品伝票数（RETN件数）
    - avg_spend    : 客単価（net_sales / receipts）

  B系統（単店・独立デモ）: 通行人カウント → 端末×日 パネル
    - visitors_in  : 入店数（C_EVENT_TYPE='IN' の日次件数）
    - events_out   : 退室数（'OUT' の日次件数）

使い方:
    python src/real_data_etl.py
出力:
    data/real_store_daily.csv   （購買・店舗×日）
    data/real_flow_daily.csv    （通行人・端末×日）
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "test_data"
OUT_DIR = ROOT / "data"
PANEL_PATH = OUT_DIR / "real_store_daily.csv"

BUYING = TEST_DATA / "buying_data" / "buying_history.csv"
FLOW = TEST_DATA / "flow_counter_data" / "flow_counter_event_data.csv"

REQUIRED_BUYING_COLUMNS = [
    "V_ACCOUNT_ID",
    "D_TRANSACTION_DT",
    "V_SHOP_ID",
    "C_SLIP_TYPE",
    "N_PURCHASED_AMOUNT",
    "N_DISCOUNT_AMOUNT",
]


def sniff_separator(path: Path) -> str:
    """先頭行のタブ／カンマの数から区切り文字を決める（提供データはTSV）。"""
    with path.open("rb") as f:
        first = f.readline().decode("utf-8", errors="replace")
    if first.count("\t") >= first.count(","):
        return "\t"
    return ","


def find_buying_file(explicit: str | Path | None = None) -> Path | None:
    """生の購買ファイルを探す。明示パス → 環境変数 → test_data の順。"""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    env = os.environ.get("RAW_BUYING_PATH", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(BUYING)
    seen: set[Path] = set()
    for path in candidates:
        path = path.resolve()
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def _read_buying(path: Path) -> pd.DataFrame:
    sep = sniff_separator(path)
    last_err: Exception | None = None
    header: pd.DataFrame | None = None
    encoding_used = "utf-8-sig"
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            header = pd.read_csv(path, sep=sep, nrows=0, encoding=encoding)
            encoding_used = encoding
            break
        except UnicodeDecodeError as e:
            last_err = e
    if header is None:
        raise ValueError(f"文字コードを判定できませんでした: {path} ({last_err})")

    header.columns = [str(c).replace("\ufeff", "").strip() for c in header.columns]
    missing = [c for c in REQUIRED_BUYING_COLUMNS if c not in header.columns]
    if missing:
        raise ValueError(
            "購買ファイルに必要な列がありません: "
            f"{missing}。先頭の列: {list(header.columns)[:12]}"
        )

    df = pd.read_csv(
        path,
        sep=sep,
        usecols=REQUIRED_BUYING_COLUMNS,
        dtype={
            "V_ACCOUNT_ID": "string",
            "D_TRANSACTION_DT": "string",
            "V_SHOP_ID": "string",
            "C_SLIP_TYPE": "string",
        },
        encoding=encoding_used,
        low_memory=False,
    )
    df["N_PURCHASED_AMOUNT"] = pd.to_numeric(df["N_PURCHASED_AMOUNT"], errors="coerce").fillna(0)
    df["N_DISCOUNT_AMOUNT"] = pd.to_numeric(df["N_DISCOUNT_AMOUNT"], errors="coerce").fillna(0)

    raw_date = df["D_TRANSACTION_DT"].astype(str).str.slice(0, 10)
    yyyymmdd = raw_date.str.match(r"^\d{8}$", na=False)
    if bool(yyyymmdd.mean() > 0.5):
        parsed = pd.to_datetime(raw_date, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(raw_date, errors="coerce")
    df["date"] = parsed.dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["date", "V_SHOP_ID"])
    if df.empty:
        raise ValueError("有効な取引日・店舗IDを持つ行がありません")
    return df


def build_store_daily(path: Path | str | None = None) -> pd.DataFrame:
    """購買履歴を店舗×日に集計する（A系統）。"""
    source = Path(path) if path is not None else find_buying_file()
    if source is None:
        raise FileNotFoundError(
            "生の購買ファイルが見つかりません。"
            f" {BUYING} に置くか、"
            "RAW_BUYING_PATH を設定してください。"
        )
    df = _read_buying(source)

    rcpt = df[df["C_SLIP_TYPE"] == "RCPT"]
    retn = df[df["C_SLIP_TYPE"] == "RETN"]

    g_rcpt = rcpt.groupby(["V_SHOP_ID", "date"], observed=True).agg(
        receipts=("C_SLIP_TYPE", "size"),
        members=("V_ACCOUNT_ID", "nunique"),
        gross_sales=("N_PURCHASED_AMOUNT", "sum"),
        discount=("N_DISCOUNT_AMOUNT", "sum"),
    )
    g_retn = retn.groupby(["V_SHOP_ID", "date"], observed=True).agg(
        returns=("C_SLIP_TYPE", "size"),
        return_amount=("N_PURCHASED_AMOUNT", "sum"),
    )

    panel = g_rcpt.join(g_retn, how="left").reset_index()
    for col in ["returns", "return_amount"]:
        panel[col] = panel[col].fillna(0)
    # RETN の購入額は負値で格納されるため、返品額は正の大きさに直す
    panel["return_amount"] = -panel["return_amount"]
    panel["net_sales"] = panel["gross_sales"] - panel["return_amount"]
    panel["avg_spend"] = (panel["net_sales"] / panel["receipts"]).round(1)
    panel = panel.rename(columns={"V_SHOP_ID": "shop_id"})
    panel = panel.sort_values(["shop_id", "date"]).reset_index(drop=True)
    return panel


def write_store_daily(
    panel: pd.DataFrame,
    dest: Path | str = PANEL_PATH,
) -> Path:
    """店舗×日パネルをCSVに保存する。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(dest, index=False)
    return dest


def ingest_buying_to_panel(
    source: Path | str | None = None,
    dest: Path | str = PANEL_PATH,
) -> dict:
    """生の購買ファイルを店舗×日CSVへ変換して保存し、件数を返す."""
    src = Path(source) if source is not None else find_buying_file()
    if src is None:
        raise FileNotFoundError(
            "生の購買ファイルが見つかりません。"
            f" {BUYING} に置くか、"
            "RAW_BUYING_PATH を設定してください。"
        )
    panel = build_store_daily(src)
    if panel.empty:
        raise ValueError("集計結果が空です。C_SLIP_TYPE=RCPT の行があるか確認してください")
    out = write_store_daily(panel, dest)
    return {
        "source_path": str(src),
        "panel_path": str(out),
        "n_rows": int(len(panel)),
        "n_shops": int(panel["shop_id"].nunique()),
        "date_min": str(panel["date"].min()),
        "date_max": str(panel["date"].max()),
    }


def build_flow_daily() -> pd.DataFrame:
    """通行人カウントを端末×日に集計する（B系統）。"""
    df = pd.read_csv(
        FLOW,
        sep="\t",
        usecols=["V_DEVICE_ID", "D_EVENT_DT", "C_EVENT_TYPE"],
        dtype="string",
    )
    df["date"] = df["D_EVENT_DT"].str.slice(0, 8)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["date"])

    grp = df.groupby(["V_DEVICE_ID", "date", "C_EVENT_TYPE"], observed=True).size().unstack(fill_value=0)
    grp = grp.rename(columns={"IN": "visitors_in", "OUT": "events_out"}).reset_index()
    for col in ["visitors_in", "events_out"]:
        if col not in grp.columns:
            grp[col] = 0
    grp = grp.rename(columns={"V_DEVICE_ID": "device_id"})
    grp = grp.sort_values(["device_id", "date"]).reset_index(drop=True)
    return grp


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    print("[A] 購買 → 店舗×日 集計中 ...")
    stats = ingest_buying_to_panel()
    print(
        f"  -> {Path(stats['panel_path']).name}: {stats['n_rows']:,} 行 / "
        f"{stats['n_shops']} 店舗 / "
        f"{stats['date_min']}〜{stats['date_max']}"
    )

    print("[B] 通行人 → 端末×日 集計中 ...")
    flow_daily = build_flow_daily()
    flow_path = OUT_DIR / "real_flow_daily.csv"
    flow_daily.to_csv(flow_path, index=False)
    print(
        f"  -> {flow_path.name}: {len(flow_daily):,} 行 / "
        f"{flow_daily['device_id'].nunique()} 端末 / "
        f"{flow_daily['date'].min()}〜{flow_daily['date'].max()}"
    )

    print("完了。")


if __name__ == "__main__":
    main()
