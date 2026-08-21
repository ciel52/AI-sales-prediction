"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  MODEL_ACCURACY,
  MODEL_LABELS,
  type Granularity,
  type PredictResponse,
  type ShopInfo,
  fetchShops,
  runPredict,
} from "@/lib/api";
import { AlignToggle, ForecastChart, type AlignMode } from "@/components/ForecastChart";

const GRANULARITIES: { id: Granularity; label: string }[] = [
  { id: "daily", label: "日次" },
  { id: "weekly", label: "週次" },
  { id: "monthly", label: "月次" },
];

const WEEKDAY_JP = ["日", "月", "火", "水", "木", "金", "土"];

function formatYen(n: number) {
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

function withWeekday(isoDate: string) {
  const d = new Date(`${isoDate}T00:00:00`);
  return `${isoDate}（${WEEKDAY_JP[d.getDay()]}）`;
}

function todayIso() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(isoDate: string, days: number) {
  const d = new Date(`${isoDate}T00:00:00`);
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function daysBetween(from: string, to: string) {
  const a = new Date(`${from}T00:00:00`).getTime();
  const b = new Date(`${to}T00:00:00`).getTime();
  return Math.round((b - a) / 86_400_000);
}

type TableRow = {
  key: string;
  label: string;
  sublabel?: string;
  pred: number;
  actual: number | null;
  ref: number | null;
  refLabel: string | null;
  sales: number;
};

function pickRef(d: PredictResponse["daily"][number], align: AlignMode) {
  if (align === "weekday") {
    return { ref: d.dow_ref_receipts, refDate: d.dow_ref_date };
  }
  return { ref: d.ref_receipts, refDate: d.ref_date };
}

function refColumnLabel(align: AlignMode) {
  return align === "weekday" ? "同曜日の過去実績" : "同月日の過去実績";
}

/** 月次の表用。選択期間の先頭日から7日ごとに合計する。最後の枠は7日未満になり得る。 */
function chunkBySevenDays(
  daily: PredictResponse["daily"],
  align: AlignMode,
): TableRow[] {
  if (daily.length === 0) return [];
  const rows = [...daily].sort((a, b) => a.date.localeCompare(b.date));
  const origin = rows[0].date;
  const buckets = new Map<number, typeof rows>();
  for (const d of rows) {
    const i = Math.floor(daysBetween(origin, d.date) / 7);
    const list = buckets.get(i) ?? [];
    list.push(d);
    buckets.set(i, list);
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([i, group]) => {
      const start = addDays(origin, i * 7);
      const end = group[group.length - 1].date;
      const pred = group.reduce((s, d) => s + d.pred_receipts, 0);
      const sales = group.reduce((s, d) => s + d.pred_net_sales, 0);
      const actuals = group
        .map((d) => d.actual_receipts)
        .filter((v): v is number => v != null);
      const refs = group
        .map((d) => pickRef(d, align).ref)
        .filter((v): v is number => v != null);
      return {
        key: start,
        label: `${start}〜${end.slice(5)}`,
        sublabel: `${group.length}日分`,
        pred,
        actual: actuals.length > 0 ? actuals.reduce((s, v) => s + v, 0) : null,
        ref: refs.length > 0 ? refs.reduce((s, v) => s + v, 0) : null,
        refLabel: refs.length > 0 ? `${refs.length}日分` : null,
        sales,
      };
    });
}

/** 実績の有無と使用モデルから、結果の読み方を1〜2文で説明する。 */
function buildNotice(
  result: PredictResponse,
  align: AlignMode,
): string | null {
  const { summary, data_end } = result;
  const parts: string[] = [];
  if (summary.n_actual_days === 0) {
    parts.push(
      `実績データは ${data_end} までのため、この期間の実績はありません`,
    );
  }
  if (summary.models_used.includes("calendar_dow")) {
    parts.push(
      "学習データに含まれない時期を含むため、曜日・祝日から算出しています",
    );
  } else if (summary.models_used.includes("calendar")) {
    parts.push("直近実績が使えないため、カレンダー特徴量のみで予測しています");
  }
  if (align === "weekday") {
    parts.push("同曜日の過去実績を参考値として併記しています（日付はずらしている場合があります）");
  } else if (summary.n_ref_days > 0) {
    parts.push("同月日の過去実績を参考値として併記しています（曜日は異なる場合があります）");
  }
  return parts.length > 0 ? `${parts.join("。")}。` : null;
}

const FIELD =
  "mt-1 w-full min-w-0 rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-base text-[var(--ink)] outline-none ring-[var(--accent)] focus:ring-2 disabled:opacity-50 sm:text-sm";

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
  const [targetDate, setTargetDate] = useState(todayIso);
  const [startDate, setStartDate] = useState(todayIso);
  const [endDate, setEndDate] = useState(todayIso);
  const [error, setError] = useState<string | null>(null);
  const [align, setAlign] = useState<AlignMode>("calendar");

  const isDaily = granularity === "daily";
  const resultIsDaily = result?.granularity === "daily";
  const tableIsDaily =
    result?.granularity === "daily" || result?.granularity === "weekly";

  const tableRows = useMemo((): TableRow[] => {
    if (!result || !shopId) return [];
    const daily = result.daily.filter((d) => d.shop_id === shopId);
    if (result.granularity === "monthly") {
      return chunkBySevenDays(daily, align);
    }
    return daily.map((d) => {
      const { ref, refDate } = pickRef(d, align);
      return {
        key: d.date,
        label: withWeekday(d.date),
        pred: d.pred_receipts,
        actual: d.actual_receipts,
        ref,
        refLabel: refDate ? withWeekday(refDate) : null,
        sales: d.pred_net_sales,
      };
    });
  }, [result, shopId, align]);

  const notice = result ? buildNotice(result, align) : null;
  const refLabel = refColumnLabel(align);
  const refTotals = useMemo(() => {
    if (!result || !shopId) return { total: null as number | null, n: 0 };
    const daily = result.daily.filter((d) => d.shop_id === shopId);
    const refs = daily
      .map((d) => pickRef(d, align).ref)
      .filter((v): v is number => v != null);
    return {
      total: refs.length > 0 ? refs.reduce((s, v) => s + v, 0) : null,
      n: refs.length,
    };
  }, [result, shopId, align]);
  const trainRange = useMemo(() => {
    if (shops.length === 0) return null;
    let start = shops[0].date_min;
    let end = shops[0].date_max;
    for (const s of shops) {
      if (s.date_min < start) start = s.date_min;
      if (s.date_max > end) end = s.date_max;
    }
    return { start, end };
  }, [shops]);

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
    <section className="min-w-0 rounded-2xl border border-[var(--line)] bg-[var(--panel)]">
      <header className="border-b border-[var(--line)] px-4 py-3 sm:px-5 sm:py-4">
        <h2 className="font-mplus-rounded-1c-regular font-bold text-[var(--ink)] sm:text-lg">分析・予測チャート</h2>
        {trainRange && (
          <p className="mt-1 text-xs text-[var(--ink)]">
            学習期間 {trainRange.start}〜{trainRange.end}
          </p>
        )}
        <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">
          {isDaily
            ? "店舗と対象日を選んで、その1日の予測を実行します（学習期間外の将来日も指定できます）"
            : "粒度を選び、期間を指定して予測を実行します（学習期間外の将来も指定できます）"}
          {" "}
          <Link href="/algorithm" className="text-[var(--accent)] underline-offset-2 hover:underline">
            予測方式の説明
          </Link>
        </p>
      </header>

      <div className="space-y-4 px-4 py-4 sm:px-5">
        <div className="grid min-w-0 gap-3 sm:grid-cols-2">
          <label className="block min-w-0 text-xs text-[var(--muted)]">
            店舗
            <select
              value={shopId ?? ""}
              onChange={(e) => setShopId(e.target.value)}
              disabled={shops.length === 0}
              className={FIELD}
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
          <div className="min-w-0">
            <p className="text-xs text-[var(--muted)]">粒度</p>
            <div className="mt-1 grid grid-cols-3 gap-2">
              {GRANULARITIES.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setGranularity(g.id)}
                  className={
                    granularity === g.id
                      ? "rounded-full bg-[var(--accent)] px-2 py-2 text-sm font-medium text-white sm:px-4"
                      : "rounded-full border border-[var(--line)] bg-white px-2 py-2 text-sm text-[var(--ink)] sm:px-4"
                  }
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {isDaily ? (
          <label className="block max-w-full text-xs text-[var(--muted)] sm:max-w-xs">
            対象日
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className={FIELD}
            />
          </label>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block min-w-0 text-xs text-[var(--muted)]">
              開始日
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className={FIELD}
              />
            </label>
            <label className="block min-w-0 text-xs text-[var(--muted)]">
              終了日
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className={FIELD}
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
            <div className="grid grid-cols-2 gap-2 sm:gap-3 md:grid-cols-4">
              <div className="min-w-0 rounded-xl bg-[var(--wash)] px-3 py-3">
                <p className="text-[11px] text-[var(--pred)] font-bold">
                  {resultIsDaily ? "予測来店" : "予測来店合計"}
                </p>
                <p className="tone-pred m-plus-rounded-1c-regular mt-1 break-all text-lg sm:text-xl">
                  {Math.round(result.summary.pred_receipts_total).toLocaleString()}
                </p>
              </div>
              <div className="min-w-0 rounded-xl bg-[var(--wash)] px-3 py-3">
                {result.summary.n_actual_days > 0 ? (
                  <>
                    <p className="text-[11px] text-[var(--actual)] font-bold">
                      {resultIsDaily ? "実績来店" : "実績来店合計"}
                    </p>
                    <p className="tone-actual m-plus-rounded-1c-regular mt-1 break-all text-lg sm:text-xl">
                      {Math.round(
                        result.summary.actual_receipts_total ?? 0,
                      ).toLocaleString()}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-[11px] leading-snug text-[var(--ref)] font-bold">
                      {refLabel}
                    </p>
                    <p className="tone-ref m-plus-rounded-1c-regular mt-1 break-all text-lg sm:text-xl">
                      {refTotals.n > 0
                        ? Math.round(refTotals.total ?? 0).toLocaleString()
                        : "—"}
                    </p>
                    <p className="mt-0.5 text-[10px] leading-snug text-[var(--muted)]">
                      {refTotals.n > 0
                        ? `${refTotals.n}日分の過去実績あり`
                        : "参照できる過去実績なし"}
                    </p>
                  </>
                )}
              </div>
              <div className="min-w-0 rounded-xl bg-[var(--wash)] px-3 py-3">
                <p className="text-[11px] text-[var(--pred)] font-bold">
                  {resultIsDaily ? "予測売上" : "予測売上合計"}
                </p>
                <p className="tone-pred m-plus-rounded-1c-regular mt-1 break-all text-base sm:text-lg">
                  {formatYen(result.summary.pred_net_sales_total)}
                </p>
              </div>
              <div className="min-w-0 rounded-xl bg-[var(--wash)] px-3 py-3">
                <p className="text-[11px] text-[var(--muted)] font-bold">予測方式</p>
                <ul className="mt-1 space-y-2">
                  {(result.summary.models_used.length > 0
                    ? result.summary.models_used
                    : []
                  ).map((m) => {
                    const acc = MODEL_ACCURACY[m];
                    return (
                      <li key={m}>
                        <p className="text-[11px] font-medium leading-snug text-[var(--ink)]">
                          {MODEL_LABELS[m]}
                        </p>
                        <p className="tone-pred m-plus-rounded-1c-regular mt-0.5 text-lg leading-tight">
                          平均 約{acc.pct}%
                        </p>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>

            {notice && (
              <p className="rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-[11px] leading-relaxed text-[var(--muted)]">
                {notice}
              </p>
            )}

            {resultIsDaily && (
              <div className="flex justify-end">
                <AlignToggle align={align} onChange={setAlign} />
              </div>
            )}

            {!resultIsDaily && (
              <ForecastChart
                granularity={result.granularity}
                daily={result.daily}
                aggregates={result.aggregates}
                align={align}
                onAlignChange={setAlign}
              />
            )}

            <div className="space-y-2 md:hidden">
              {tableRows.map((r) => (
                <div
                  key={r.key}
                  className="rounded-xl border border-[var(--line)] bg-white px-3 py-3"
                >
                  <p className="text-sm font-medium text-[var(--ink)]">{r.label}</p>
                  {r.sublabel && (
                    <p className="mt-0.5 text-[11px] text-[var(--muted)]">{r.sublabel}</p>
                  )}
                  <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                    <div>
                      <dt className="text-[var(--pred)]">予測来店</dt>
                      <dd className="tone-pred mt-0.5 text-sm">
                        {Math.round(r.pred).toLocaleString()}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[var(--actual)]">実績来店</dt>
                      <dd className="tone-actual mt-0.5 text-sm">
                        {r.actual != null ? Math.round(r.actual).toLocaleString() : "—"}
                      </dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-[var(--ref)]">{refLabel}</dt>
                      <dd className="tone-ref mt-0.5 break-words text-sm">
                        {r.ref != null ? Math.round(r.ref).toLocaleString() : "—"}
                        {r.ref != null && r.refLabel && (
                          <span className="mt-0.5 block text-[10px] font-normal text-[var(--muted)]">
                            {r.refLabel}
                          </span>
                        )}
                      </dd>
                    </div>
                    <div className="min-w-0">
                      <dt className="text-[var(--pred)]">予測売上</dt>
                      <dd className="tone-pred mt-0.5 break-all text-sm">{formatYen(r.sales)}</dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>

            <div className="hidden max-h-72 overflow-auto rounded-xl border border-[var(--line)] md:block">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="sticky top-0 bg-[var(--wash)] text-xs text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">
                      {tableIsDaily ? "日付" : "期間（7日）"}
                    </th>
                    <th className="px-3 py-2 font-medium text-[var(--pred)]">予測来店</th>
                    <th className="px-3 py-2 font-medium text-[var(--actual)]">実績来店</th>
                    <th className="px-3 py-2 font-medium text-[var(--ref)]">{refLabel}</th>
                    <th className="px-3 py-2 font-medium text-[var(--pred)]">予測売上</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((r) => (
                    <tr key={r.key} className="border-t border-[var(--line)]">
                      <td className="whitespace-nowrap px-3 py-2">
                        {r.label}
                      </td>
                      <td className="tone-pred px-3 py-2">{Math.round(r.pred).toLocaleString()}</td>
                      <td className="tone-actual px-3 py-2">
                        {r.actual != null ? Math.round(r.actual).toLocaleString() : "—"}
                      </td>
                      <td className="tone-ref whitespace-nowrap px-3 py-2">
                        {r.ref != null ? (
                          <>
                            {Math.round(r.ref).toLocaleString()}
                            {r.refLabel && (
                              <span className="ml-1 text-[10px] font-normal text-[var(--muted)]">
                                {r.refLabel}
                              </span>
                            )}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="tone-pred px-3 py-2">{formatYen(r.sales)}</td>
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
