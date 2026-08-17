"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  MODEL_LABELS,
  type Granularity,
  type ModelKind,
  type PredictResponse,
  type ShopInfo,
  fetchShops,
  runPredict,
} from "@/lib/api";
import { ForecastChart } from "@/components/ForecastChart";

const GRANULARITIES: { id: Granularity; label: string }[] = [
  { id: "daily", label: "日次" },
  { id: "weekly", label: "週次" },
  { id: "monthly", label: "月次" },
];

const MODEL_SHORT: Record<ModelKind, string> = {
  lag: "実績ラグ",
  calendar: "カレンダー",
  calendar_dow: "曜日ベース",
};

const WEEKDAY_JP = ["日", "月", "火", "水", "木", "金", "土"];

function formatYen(n: number) {
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

function withWeekday(isoDate: string) {
  const d = new Date(`${isoDate}T00:00:00`);
  return `${isoDate}（${WEEKDAY_JP[d.getDay()]}）`;
}

/** 実績の有無と使用モデルから、結果の読み方を1〜2文で説明する。 */
function buildNotice(result: PredictResponse): string | null {
  const { summary, data_end } = result;
  const parts: string[] = [];
  if (summary.n_actual_days === 0) {
    parts.push(
      `実績データは ${data_end} までのため、この期間の実績はありません`,
    );
  }
  if (summary.models_used.includes("calendar_dow")) {
    parts.push(
      "学習データに含まれない時期を含むため、曜日・祝日から算出した参考値です（季節変動は反映されません）",
    );
  } else if (summary.models_used.includes("calendar")) {
    parts.push("直近実績が使えないため、カレンダー特徴量のみで予測しています");
  }
  if (summary.n_ref_days > 0) {
    parts.push("同月日の過去実績を参考値として併記しています（曜日は異なる場合があります）");
  }
  return parts.length > 0 ? `${parts.join("。")}。` : null;
}

export function PredictPanel({
  shops,
  shopId,
  setShopId,
  granularity,
  setGranularity,
  result,
  setResult,
  loading,
  setLoading,
}: {
  shops: ShopInfo[];
  shopId: string | null;
  setShopId: (id: string) => void;
  granularity: Granularity;
  setGranularity: (g: Granularity) => void;
  result: PredictResponse | null;
  setResult: (r: PredictResponse | null) => void;
  loading: boolean;
  setLoading: (v: boolean) => void;
}) {
  const [targetDate, setTargetDate] = useState("2024-12-02");
  const [startDate, setStartDate] = useState("2024-12-02");
  const [endDate, setEndDate] = useState("2024-12-15");
  const [error, setError] = useState<string | null>(null);

  const isDaily = granularity === "daily";
  const resultIsDaily = result?.granularity === "daily";

  const tableRows = useMemo(() => {
    if (!result || !shopId) return [];
    if (result.granularity === "daily") {
      return result.daily
        .filter((d) => d.shop_id === shopId)
        .map((d) => ({
          key: d.date,
          label: withWeekday(d.date),
          sublabel: MODEL_SHORT[d.model],
          pred: d.pred_receipts,
          actual: d.actual_receipts,
          ref: d.ref_receipts,
          refLabel: d.ref_date ? withWeekday(d.ref_date) : null,
          sales: d.pred_net_sales,
        }));
    }
    return result.aggregates
      .filter((a) => a.shop_id === shopId)
      .map((a) => ({
        key: a.period,
        label: a.period,
        sublabel: `${a.n_days}日分`,
        pred: a.pred_receipts,
        actual: a.actual_receipts,
        ref: a.ref_receipts,
        refLabel: a.n_ref_days > 0 ? `${a.n_ref_days}日分` : null,
        sales: a.pred_net_sales,
      }));
  }, [result, shopId]);

  const notice = result ? buildNotice(result) : null;

  async function onPredict() {
    if (!shopId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runPredict({
        granularity,
        shop_ids: [shopId],
        start_date: isDaily ? targetDate : startDate,
        end_date: isDaily ? targetDate : endDate,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-2xl border border-[var(--line)] bg-[var(--panel)]">
      <header className="border-b border-[var(--line)] px-5 py-4">
        <h2 className="font-display text-lg text-[var(--ink)]">来店・売上予測</h2>
        <p className="mt-1 text-xs text-[var(--muted)]">
          {isDaily
            ? "店舗と対象日を選んで、その1日の予測を実行します（学習期間外の将来日も指定できます）"
            : "粒度を選び、期間を指定して予測を実行します（学習期間外の将来も指定できます）"}
          {" "}
          <Link href="/algorithm" className="text-[var(--accent)] underline-offset-2 hover:underline">
            予測方式の説明
          </Link>
        </p>
      </header>

      <div className="space-y-4 px-5 py-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs text-[var(--muted)]">
            店舗
            <select
              value={shopId ?? ""}
              onChange={(e) => setShopId(e.target.value)}
              disabled={shops.length === 0}
              className="mt-1 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm text-[var(--ink)] outline-none ring-[var(--accent)] focus:ring-2 disabled:opacity-50"
            >
              {shops.length === 0 ? (
                <option value="">店舗データなし</option>
              ) : (
                shops.map((s) => (
                  <option key={s.shop_id} value={s.shop_id}>
                    {s.shop_id}（{s.n_days}日）
                  </option>
                ))
              )}
            </select>
          </label>
          <div>
            <p className="text-xs text-[var(--muted)]">粒度</p>
            <div className="mt-1 flex gap-2">
              {GRANULARITIES.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setGranularity(g.id)}
                  className={
                    granularity === g.id
                      ? "rounded-full bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
                      : "rounded-full border border-[var(--line)] bg-white px-4 py-2 text-sm text-[var(--ink)]"
                  }
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {isDaily ? (
          <label className="block max-w-xs text-xs text-[var(--muted)]">
            対象日
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="mt-1 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs text-[var(--muted)]">
              開始日
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
              />
            </label>
            <label className="block text-xs text-[var(--muted)]">
              終了日
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
              />
            </label>
          </div>
        )}

        <button
          type="button"
          onClick={() => void onPredict()}
          disabled={loading || !shopId}
          className="w-full rounded-xl bg-[var(--ink)] px-4 py-3 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-40 sm:w-auto sm:px-8"
        >
          {loading ? "予測中…" : "予測実行"}
        </button>

        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

        {result && (
          <div className="space-y-4 border-t border-[var(--line)] pt-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl bg-[var(--wash)] px-3 py-3">
                <p className="text-[11px] text-[var(--muted)]">
                  {resultIsDaily ? "予測来店" : "予測来店合計"}
                </p>
                <p className="m-plus-rounded-1c-regular mt-1 text-xl text-[var(--ink)]">
                  {Math.round(result.summary.pred_receipts_total).toLocaleString()}
                </p>
              </div>
              <div className="rounded-xl bg-[var(--wash)] px-3 py-3">
                {result.summary.n_actual_days > 0 ? (
                  <>
                    <p className="text-[11px] text-[var(--muted)]">
                      {resultIsDaily ? "実績来店" : "実績来店合計"}
                    </p>
                    <p className="m-plus-rounded-1c-regular mt-1 text-xl text-[var(--ink)]">
                      {Math.round(
                        result.summary.actual_receipts_total ?? 0,
                      ).toLocaleString()}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-[11px] text-[var(--muted)]">
                      同月日の過去実績（参考）
                    </p>
                    <p className="m-plus-rounded-1c-regular mt-1 text-xl text-[var(--ink)]">
                      {result.summary.n_ref_days > 0
                        ? Math.round(
                            result.summary.ref_receipts_total ?? 0,
                          ).toLocaleString()
                        : "—"}
                    </p>
                    <p className="mt-0.5 text-[10px] text-[var(--muted)]">
                      {result.summary.n_ref_days > 0
                        ? `${result.summary.n_ref_days}日分の過去実績`
                        : "参照できる過去実績なし"}
                    </p>
                  </>
                )}
              </div>
              <div className="rounded-xl bg-[var(--wash)] px-3 py-3">
                <p className="text-[11px] text-[var(--muted)]">
                  {resultIsDaily ? "予測売上" : "予測売上合計"}
                </p>
                <p className="m-plus-rounded-1c-regular mt-1 text-lg text-[var(--ink)]">
                  {formatYen(result.summary.pred_net_sales_total)}
                </p>
              </div>
              <div className="rounded-xl bg-[var(--wash)] px-3 py-3">
                <p className="text-[11px] text-[var(--muted)]">予測方式</p>
                <p className="mt-1 text-sm font-medium text-[var(--ink)]">
                  {result.summary.models_used
                    .map((m) => MODEL_LABELS[m])
                    .join(" / ") || "—"}
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--muted)]">
                  学習終了日 {result.train_end}
                </p>
              </div>
            </div>

            {notice && (
              <p className="rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-[11px] leading-relaxed text-[var(--muted)]">
                {notice}
              </p>
            )}

            {!resultIsDaily && (
              <ForecastChart
                granularity={result.granularity}
                daily={result.daily}
                aggregates={result.aggregates}
              />
            )}

            <div className="max-h-56 overflow-auto rounded-xl border border-[var(--line)]">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-[var(--wash)] text-xs text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">
                      {resultIsDaily ? "日付" : "期間"}
                    </th>
                    <th className="px-3 py-2 font-medium">予測来店</th>
                    <th className="px-3 py-2 font-medium">実績来店</th>
                    <th className="px-3 py-2 font-medium">同月日の過去実績</th>
                    <th className="px-3 py-2 font-medium">予測売上</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((r) => (
                    <tr key={r.key} className="border-t border-[var(--line)]">
                      <td className="whitespace-nowrap px-3 py-2">
                        {r.label}
                        <span className="ml-1 text-[10px] text-[var(--muted)]">
                          {r.sublabel}
                        </span>
                      </td>
                      <td className="px-3 py-2">{Math.round(r.pred).toLocaleString()}</td>
                      <td className="px-3 py-2">
                        {r.actual != null ? Math.round(r.actual).toLocaleString() : "—"}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {r.ref != null ? (
                          <>
                            {Math.round(r.ref).toLocaleString()}
                            {r.refLabel && (
                              <span className="ml-1 text-[10px] text-[var(--muted)]">
                                {r.refLabel}
                              </span>
                            )}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-2">{formatYen(r.sales)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export function useShopsBootstrap() {
  const [shops, setShops] = useState<ShopInfo[]>([]);
  const [shopId, setShopId] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  async function reload() {
    const list = await fetchShops();
    setShops(list);
    setShopId((current) =>
      current && list.some((s) => s.shop_id === current)
        ? current
        : (list[0]?.shop_id ?? null),
    );
    setBootError(null);
    return list;
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await fetchShops();
        if (cancelled) return;
        setShops(list);
        setShopId(list[0]?.shop_id ?? null);
        setBootError(null);
      } catch (e) {
        if (!cancelled) {
          setBootError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { shops, shopId, setShopId, bootError, booting, reload };
}
