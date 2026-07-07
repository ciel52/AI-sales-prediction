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

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "test_data"
OUT_DIR = ROOT / "data"

BUYING = TEST_DATA / "buying_data" / "buying_history.csv"
FLOW = TEST_DATA / "flow_counter_data" / "flow_counter_event_data.csv"


def build_store_daily() -> pd.DataFrame:
    """購買履歴を店舗×日に集計する（A系統）。"""
    usecols = [
        "V_ACCOUNT_ID",
        "D_TRANSACTION_DT",
        "V_SHOP_ID",
        "C_SLIP_TYPE",
        "N_PURCHASED_AMOUNT",
        "N_DISCOUNT_AMOUNT",
    ]
    df = pd.read_csv(
        BUYING,
        sep="\t",
        usecols=usecols,
        dtype={
            "V_ACCOUNT_ID": "string",
            "D_TRANSACTION_DT": "string",
            "V_SHOP_ID": "string",
            "C_SLIP_TYPE": "string",
        },
    )
    df["N_PURCHASED_AMOUNT"] = pd.to_numeric(df["N_PURCHASED_AMOUNT"], errors="coerce").fillna(0)
    df["N_DISCOUNT_AMOUNT"] = pd.to_numeric(df["N_DISCOUNT_AMOUNT"], errors="coerce").fillna(0)
    df["date"] = df["D_TRANSACTION_DT"].str.slice(0, 10)

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
    store_daily = build_store_daily()
    store_path = OUT_DIR / "real_store_daily.csv"
    store_daily.to_csv(store_path, index=False)
    print(
        f"  -> {store_path.name}: {len(store_daily):,} 行 / "
        f"{store_daily['shop_id'].nunique()} 店舗 / "
        f"{store_daily['date'].min()}〜{store_daily['date'].max()}"
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
