"""施策提案チャット: 既存 llm_advisor を対話向けにラップ.

対応プロバイダ（.env の LLM_PROVIDER）:
  - openai … OPENAI_API_KEY
  - gemini … GEMINI_API_KEY または GOOGLE_API_KEY
  - auto   … geminiキーがあれば Gemini、なければ OpenAI、どちらも無ければルールベース
"""

from __future__ import annotations

import os
from datetime import datetime

from llm_advisor import SYSTEM_PROMPT, generate_advice, render_user_prompt, rule_based_advice

from api.schemas import ChatMessage, ChatRequest, ChatResponse, ForecastContext

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


def _context_from_forecast(ctx: ForecastContext) -> dict:
    """実データ予測コンテキストを llm_advisor が扱う辞書に変換する."""
    date = None
    weekday = None
    if ctx.date:
        date = datetime.strptime(ctx.date, "%Y-%m-%d")
        weekday = WEEKDAY_JP[date.weekday()]

    pv = ctx.pred_receipts or 0.0
    dow_avg = ctx.dow_avg_receipts or pv or 1.0
    recent_avg = ctx.recent_avg_receipts or pv or 1.0

    ref_weekday = None
    if ctx.ref_date:
        ref_weekday = WEEKDAY_JP[datetime.strptime(ctx.ref_date, "%Y-%m-%d").weekday()]

    return {
        "対象日": ctx.date or "（未指定）",
        "曜日": weekday or "（未指定）",
        "予測来店客数": round(pv),
        "予測売上": round(ctx.pred_net_sales or 0.0),
        "予測客単価": round(ctx.pred_avg_spend or 0.0),
        "曜日平均比": round(pv / dow_avg, 2) if dow_avg else None,
        "直近7日平均比": round(pv / recent_avg, 2) if recent_avg else None,
        "祝日": bool(ctx.is_holiday) if ctx.is_holiday is not None else False,
        "週末": bool(ctx.is_weekend) if ctx.is_weekend is not None else False,
        "給料日前後": bool(ctx.is_payday) if ctx.is_payday is not None else False,
        "ポイント倍率": 1,
        "特売日": False,
        "クーポン配信": False,
        "天気": "（データなし）",
        "最高気温": float("nan"),
        "最低気温": float("nan"),
        "降水量mm": 0.0,
        "SNS言及_前日": None,
        "SNS言及_7日平均": None,
        "SNS急増": False,
        "店舗ID": ctx.shop_id,
        "粒度": ctx.granularity,
        "実績来店客数": ctx.actual_receipts,
        "同月日過去実績_日付": ctx.ref_date,
        "同月日過去実績_曜日": ref_weekday,
        "同月日過去実績_来店客数": ctx.ref_receipts,
        "同月日過去実績比": (
            round(pv / ctx.ref_receipts, 2)
            if ctx.ref_receipts and ctx.ref_receipts > 0
            else None
        ),
        "予測モデル": ctx.model,
    }


def _build_system_prompt() -> str:
    return (
        SYSTEM_PROMPT
        + "\n\n追加ルール:\n"
        "- ユーザーからの追加質問にも、上記の見出し形式または簡潔な箇条書きで答える\n"
        "- 天候・SNS・販促が「データなし」の場合は、その前提で無理に触れない\n"
        "- 与えられた予測数値を勝手に作り変えない\n"
        "- 「同月日過去実績」は前年などの同じ月日の実績。曜日が異なる場合があるので、"
        "単純比較せず曜日の違いに触れる\n"
        "- 予測モデルが calendar の場合は直近実績を使えない期間の予測であり、"
        "lag（前日・前週の実績を使う）より精度が落ちる前提で幅を持たせて述べる"
    )


def _forecast_user_blob(structured: dict) -> str:
    lines = [
        render_user_prompt(structured),
        "",
        "## 追加メタ",
        f"- 店舗ID: {structured.get('店舗ID')}",
        f"- 粒度: {structured.get('粒度')}",
        f"- 実績来店客数: {structured.get('実績来店客数')}",
        f"- 予測モデル: {structured.get('予測モデル')}",
    ]
    if structured.get("同月日過去実績_来店客数") is not None:
        lines += [
            "",
            "## 同月日の過去実績（参考）",
            f"- 参照日: {structured.get('同月日過去実績_日付')}"
            f"（{structured.get('同月日過去実績_曜日')}）",
            f"- 来店客数: {structured.get('同月日過去実績_来店客数')}",
            f"- 予測/過去実績比: {structured.get('同月日過去実績比')}",
        ]
    return "\n".join(lines)


def _openai_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    return key or None


def _gemini_key() -> str | None:
    key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    return key or None


def _resolve_provider() -> str | None:
    """使うプロバイダ名を返す。キーが無ければ None（ルールベース）."""
    preferred = os.environ.get("LLM_PROVIDER", "auto").strip().lower()
    gemini = _gemini_key()
    openai = _openai_key()

    if preferred in {"gemini", "google"}:
        return "gemini" if gemini else None
    if preferred == "openai":
        return "openai" if openai else None
    # auto
    if gemini:
        return "gemini"
    if openai:
        return "openai"
    return None


def _rule_based_reply(structured: dict | None, message: str) -> str:
    base = rule_based_advice(structured) if structured else (
        "予測コンテキストが未設定です。先に予測を実行するか、"
        "店舗・日付・予測値を指定してから質問してください。"
    )
    return (
        f"{base}\n\n"
        f"---\n【ご質問への補足】\n{message}\n\n"
        "※ LLM APIキー未設定のためルールベース応答です。"
        "`.env` に GEMINI_API_KEY または OPENAI_API_KEY を設定してください。"
    )


def _call_openai(
    structured: dict | None,
    history: list[ChatMessage],
    message: str,
) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=_openai_key())
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    messages: list[dict] = [{"role": "system", "content": _build_system_prompt()}]
    if structured:
        messages.append({"role": "user", "content": _forecast_user_blob(structured)})
        messages.append({
            "role": "assistant",
            "content": "予測内容を把握しました。ご質問にお答えします。",
        })
    for m in history[-10:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": message})

    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=messages,
    )
    return resp.choices[0].message.content or ""


def _call_gemini(
    structured: dict | None,
    history: list[ChatMessage],
    message: str,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_key())
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL

    contents: list[types.Content] = []
    if structured:
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=_forecast_user_blob(structured))],
            )
        )
        contents.append(
            types.Content(
                role="model",
                parts=[types.Part.from_text(text="予測内容を把握しました。ご質問にお答えします。")],
            )
        )
    for m in history[-10:]:
        role = "user" if m.role == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=m.content)],
            )
        )
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=message)],
        )
    )

    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_build_system_prompt(),
            temperature=0.3,
        ),
    )
    return resp.text or ""


def chat(req: ChatRequest) -> ChatResponse:
    """予測コンテキスト＋会話履歴を踏まえて返答する."""
    context_used = req.context is not None
    structured = _context_from_forecast(req.context) if req.context else None
    provider = _resolve_provider()

    if provider is None:
        return ChatResponse(
            reply=_rule_based_reply(structured, req.message),
            used_llm=False,
            context_used=context_used,
        )

    try:
        if provider == "gemini":
            reply = _call_gemini(structured, req.history, req.message)
        else:
            reply = _call_openai(structured, req.history, req.message)
        return ChatResponse(reply=reply, used_llm=True, context_used=context_used)
    except Exception as e:  # pragma: no cover
        fallback = generate_advice(structured) if structured else str(e)
        return ChatResponse(
            reply=f"[LLM呼び出し失敗 ({provider}): {e}]\n\n{fallback}",
            used_llm=False,
            context_used=context_used,
        )
