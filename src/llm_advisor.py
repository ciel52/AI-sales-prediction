"""来店・売上予測の結果を解釈し、店舗運営の施策を提案するLLMアドバイザー.

役割分担:
  - 予測の数値（精度の中核）  : 機械学習モデル（visit_forecast.py）
  - 予測の解釈・施策提案      : 本モジュール（LLMプロンプト）

構成:
  1. build_context()        : 予測結果＋当日の条件を構造化した「文脈」を作る
  2. SYSTEM_PROMPT / render_user_prompt() : LLMへ渡すプロンプト（本MVPの主成果物）
  3. generate_advice()      : APIキーがあればLLMを呼び、無ければルールベースの下書きを返す
  4. rule_based_advice()    : APIなしでも出力を確認できるローカル生成

※ プロンプトのみで予測精度を出す構成ではなく、MLの予測を「解釈・行動提案」へ翻訳する位置づけ。
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]


def build_context(
    row: pd.Series,
    pred: dict,
    dow_avg_visitors: float,
    recent_avg_visitors: float,
) -> dict:
    """予測対象日の予測結果と条件を、LLMに渡しやすい構造化辞書にまとめる."""
    date = pd.Timestamp(row["date"])
    pv = pred["pred_visitors"]
    weather_label = {"sunny": "晴れ", "cloudy": "曇り", "rain": "雨"}.get(
        str(row.get("weather", "")), str(row.get("weather", ""))
    )
    point_mult = int(row.get("point_multiplier", 1))
    return {
        "対象日": date.strftime("%Y-%m-%d"),
        "曜日": WEEKDAY_JP[date.dayofweek],
        "予測来店客数": round(pv),
        "予測売上": round(pred["pred_sales"]),
        "予測客単価": round(pred["pred_avg_spend"]),
        "曜日平均比": round(pv / dow_avg_visitors, 2) if dow_avg_visitors else None,
        "直近7日平均比": round(pv / recent_avg_visitors, 2) if recent_avg_visitors else None,
        "祝日": bool(row.get("is_holiday", 0)),
        "週末": bool(row.get("is_weekend", 0)),
        "給料日前後": bool(row.get("is_payday", 0)),
        "ポイント倍率": point_mult,
        "特売日": bool(row.get("is_sale", 0)),
        "クーポン配信": bool(row.get("coupon_sent", 0)),
        "天気": weather_label,
        "最高気温": float(row.get("temp_max", float("nan"))),
        "最低気温": float(row.get("temp_min", float("nan"))),
        "降水量mm": float(row.get("precipitation_mm", 0.0)),
        "SNS言及_前日": None if pd.isna(row.get("sns_lag1")) else round(float(row["sns_lag1"])),
        "SNS言及_7日平均": None if pd.isna(row.get("sns_ma7")) else round(float(row["sns_ma7"])),
        "SNS急増": bool(row.get("sns_surge", 0)),
    }


# ============================================================
# プロンプト（本MVPの主成果物）
# ============================================================
SYSTEM_PROMPT = """あなたは小売・サービス業の店舗運営を支援する熟練アドバイザーAIです。
ポイントシステムの購買データと、天候・人流・SNSをもとにした機械学習の来店・売上予測を受け取り、
店長が翌日の準備に使える、具体的で実行可能な助言を行います。

出力のルール:
- 数値予測は与えられた値を尊重し、勝手に作り変えない（解釈と行動提案に集中する）
- 次の見出しで簡潔にまとめる:
  【明日の見通し】予測と、その背景（なぜそうなるか）を2〜3文で
  【人員・シフト】来店予測に応じた人員配置の提案
  【発注・在庫】売上・天候・販促をふまえた商品準備の提案
  【販促・接客】ポイントデー/特売/クーポン/SNSをふまえた当日の打ち手
  【注意点】見落としやすいリスクや不確実性
- 専門用語は避け、店舗スタッフが理解できる平易な日本語で書く
- 根拠（曜日・天候・販促・SNSなど）を必ず添える"""


def render_user_prompt(context: dict) -> str:
    """文脈辞書を、LLMに渡すユーザープロンプト文字列に変換する."""
    lines = ["以下は明日の店舗の予測と条件です。これをもとに助言してください。", "", "## 予測"]
    for k in ["対象日", "曜日", "予測来店客数", "予測売上", "予測客単価", "曜日平均比", "直近7日平均比"]:
        lines.append(f"- {k}: {context.get(k)}")
    lines.append("")
    lines.append("## 当日の条件")
    for k in ["祝日", "週末", "給料日前後", "ポイント倍率", "特売日", "クーポン配信"]:
        lines.append(f"- {k}: {context.get(k)}")
    lines.append("")
    lines.append("## 天候（予報）")
    for k in ["天気", "最高気温", "最低気温", "降水量mm"]:
        lines.append(f"- {k}: {context.get(k)}")
    lines.append("")
    lines.append("## SNS動向（前日まで）")
    for k in ["SNS言及_前日", "SNS言及_7日平均", "SNS急増"]:
        lines.append(f"- {k}: {context.get(k)}")
    return "\n".join(lines)


def rule_based_advice(context: dict) -> str:
    """APIキーが無くても出力を確認できる、ルールベースの下書き提案."""
    pv = context["予測来店客数"]
    dow_ratio = context.get("曜日平均比") or 1.0
    reasons = []
    if context["週末"]:
        reasons.append("週末")
    if context["祝日"]:
        reasons.append("祝日")
    if context["給料日前後"]:
        reasons.append("給料日前後")
    if context["特売日"]:
        reasons.append("特売日")
    if context["ポイント倍率"] >= 5:
        reasons.append(f"ポイント{context['ポイント倍率']}倍デー")
    if context["クーポン配信"]:
        reasons.append("クーポン配信中")
    if context["SNS急増"]:
        reasons.append("SNSで話題が急増")
    if context["天気"] == "雨":
        reasons.append("雨予報")
    reason_text = "・".join(reasons) if reasons else "平常の条件"

    trend = "増加" if dow_ratio >= 1.05 else ("減少" if dow_ratio <= 0.95 else "平年並み")

    # 人員
    if dow_ratio >= 1.2:
        staff = "来店増が見込まれるため、レジ・品出しを通常より増員し、ピーク時間帯のシフトを厚くしてください。"
    elif dow_ratio <= 0.85:
        staff = "来店は控えめの見込み。最小限の人員で回し、品出しや棚卸など店内作業に時間を充てましょう。"
    else:
        staff = "通常通りの人員配置で対応可能です。"

    # 発注・在庫
    stock = []
    if dow_ratio >= 1.1 or context["特売日"]:
        stock.append("来店・売上増に備え、主力商品と日配品を多めに発注")
    if context["天気"] == "雨":
        stock.append("雨予報のため傘・レイングッズ、惣菜・中食など『濡れずに済む需要』を強化")
    if context["最高気温"] >= 28:
        stock.append("高温予報のため冷たい飲料・アイス・冷食を増量")
    elif context["最高気温"] <= 8:
        stock.append("冷え込み予報のため鍋材料・温かい飲料・おでんを強化")
    if not stock:
        stock.append("通常の発注計画で問題ありません")
    stock_text = "／".join(stock)

    # 販促・接客
    promo = []
    if context["ポイント倍率"] >= 5:
        promo.append(f"ポイント{context['ポイント倍率']}倍を店頭・レジで告知し、会員カードの提示を促す")
    if context["特売日"]:
        promo.append("特売目玉商品をエンド（売場端）に大きく展開し、関連商品を併せ買い提案")
    if context["クーポン配信"]:
        promo.append("配信クーポンの対象商品を見やすく陳列し、利用を促進")
    if context["SNS急増"]:
        promo.append("SNSで話題の商品・サービスを目立つ場所に配置し、当日もSNS発信")
    if not promo:
        promo.append("特別な販促はなし。基本の接客と欠品防止を徹底")
    promo_text = "／".join(promo)

    # 注意点
    notes = []
    if context.get("SNS急増"):
        notes.append("SNS起因の来店は読みづらいので、品切れに即対応できる体制を")
    if context["天気"] == "雨" and context["週末"]:
        notes.append("週末×雨は予測がぶれやすい。客足を見ながら柔軟に調整を")
    if not notes:
        notes.append("大きな不確実要因はなし。予測はあくまで目安として活用を")
    notes_text = "／".join(notes)

    return f"""【明日の見通し】
{context['対象日']}（{context['曜日']}）の来店は約{pv:,}人、売上は約{context['予測売上']:,}円の見込みです（曜日平均比 {dow_ratio}）。
来店は{trend}傾向で、主な要因は{reason_text}です。

【人員・シフト】
{staff}

【発注・在庫】
{stock_text}。

【販促・接客】
{promo_text}。

【注意点】
{notes_text}。

※ これはルールベースの下書きです。OpenAI APIキーを設定すると、より自然で文脈に応じた提案をLLMが生成します。"""


def generate_advice(
    context: dict,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
) -> str:
    """施策提案を生成する。OPENAI_API_KEY があればLLMを、無ければルールベースを使う."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return rule_based_advice(context)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": render_user_prompt(context)},
            ],
        )
        return resp.choices[0].message.content
    except Exception as e:  # pragma: no cover
        return f"[LLM呼び出しに失敗したためルールベースを使用: {e}]\n\n" + rule_based_advice(context)
