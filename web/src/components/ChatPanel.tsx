"use client";

import { useMemo, useState } from "react";
import {
  type ChatMessage,
  type ForecastContext,
  type Granularity,
  type PredictResponse,
  runChat,
} from "@/lib/api";

function buildContext(
  result: PredictResponse | null,
  shopId: string | null,
): ForecastContext | null {
  if (!result || !shopId) return null;
  if (result.granularity === "daily") {
    const rows = result.daily.filter((d) => d.shop_id === shopId);
    if (rows.length === 0) return null;
    const last = rows[rows.length - 1];
    const date = new Date(`${last.date}T00:00:00`);
    return {
      shop_id: shopId,
      date: last.date,
      granularity: "daily",
      pred_receipts: last.pred_receipts,
      pred_avg_spend: last.pred_avg_spend,
      pred_net_sales: last.pred_net_sales,
      actual_receipts: last.actual_receipts,
      ref_date: last.ref_date,
      ref_receipts: last.ref_receipts,
      model: last.model,
      is_weekend: date.getDay() === 0 || date.getDay() === 6,
      is_payday: date.getDate() >= 24 && date.getDate() <= 26,
    };
  }
  const rows = result.aggregates.filter((a) => a.shop_id === shopId);
  if (rows.length === 0) return null;
  const last = rows[rows.length - 1];
  return {
    shop_id: shopId,
    date: result.end_date,
    granularity: result.granularity,
    pred_receipts: last.pred_receipts,
    pred_avg_spend: last.pred_avg_spend,
    pred_net_sales: last.pred_net_sales,
    actual_receipts: last.actual_receipts,
    ref_receipts: last.ref_receipts,
    model: result.summary.models_used[0] ?? null,
  };
}

export function ChatPanel({
  result,
  shopId,
  granularity,
}: {
  result: PredictResponse | null;
  shopId: string | null;
  granularity: Granularity;
}) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const context = useMemo(
    () => buildContext(result, shopId),
    [result, shopId],
  );

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setError(null);
    setInput("");
    const nextHistory = [...messages, { role: "user" as const, content: text }];
    setMessages(nextHistory);
    setLoading(true);
    try {
      const res = await runChat({
        message: text,
        context,
        history: messages,
      });
      setMessages([...nextHistory, { role: "assistant", content: res.reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="flex h-full min-h-[420px] flex-col rounded-2xl border border-[var(--line)] bg-[var(--panel)]">
      <header className="border-b border-[var(--line)] px-5 py-4">
        <h2 className="font-display text-lg text-[var(--ink)]">施策提案AI</h2>
        <p className="mt-1 text-xs text-[var(--muted)]">
          {context
            ? `店舗 ${context.shop_id} / ${granularity} の予測を文脈として使用`
            : "先に予測を実行すると、結果を踏まえて助言します"}
        </p>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <div className="rounded-xl bg-[var(--wash)] px-4 py-3 text-sm text-[var(--muted)]">
            例:「この予測なら人員はどう配分すべき？」「売上を上げる打ち手は？」
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={`${m.role}-${i}`}
            className={
              m.role === "user"
                ? "ml-8 rounded-2xl bg-[var(--accent)] px-4 py-3 text-sm text-white"
                : "mr-4 whitespace-pre-wrap rounded-2xl bg-[var(--wash)] px-4 py-3 text-sm text-[var(--ink)]"
            }
          >
            {m.content}
          </div>
        ))}
        {loading && (
          <p className="text-xs text-[var(--muted)]">回答を生成しています…</p>
        )}
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      </div>

      <form
        className="border-t border-[var(--line)] p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="施策について質問する"
            className="min-w-0 flex-1 rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-xl bg-[var(--ink)] px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40"
          >
            送信
          </button>
        </div>
      </form>
    </section>
  );
}
