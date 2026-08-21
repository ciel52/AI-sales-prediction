"use client";

import { useEffect, useState, type PointerEvent } from "react";
import type { DailyPoint, AggregatePoint, Granularity } from "@/lib/api";

export type AlignMode = "calendar" | "weekday";

type SeriesPoint = {
  date: string;
  label: string;
  pred: number;
  predSales: number;
  actual: number | null;
  actualSales: number | null;
  ref: number | null;
  refSales: number | null;
  refDate: string | null;
};

type Bucket = {
  pred: number;
  predSales: number;
  actual: number | null;
  actualSales: number | null;
  ref: number | null;
  refSales: number | null;
  refDate: string | null;
};

const WEEKDAY_JP = ["日", "月", "火", "水", "木", "金", "土"];

export const ALIGN_OPTIONS: { id: AlignMode; label: string }[] = [
  { id: "calendar", label: "同月日で比較" },
  { id: "weekday", label: "同曜日で比較" },
];

export function AlignToggle({
  align,
  onChange,
}: {
  align: AlignMode;
  onChange: (id: AlignMode) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-1 sm:flex">
      {ALIGN_OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id)}
          className={
            align === opt.id
              ? "rounded-full bg-[var(--accent)] px-3 py-1.5 text-xs font-medium text-white"
              : "rounded-full border border-[var(--line)] bg-white px-3 py-1.5 text-xs text-[var(--ink)]"
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function weekdayLabel(isoDate: string) {
  const d = new Date(`${isoDate}T00:00:00`);
  return WEEKDAY_JP[d.getDay()];
}

function weekdayRangeNote(daily: DailyPoint[]): string | null {
  const refs = daily
    .map((d) => d.dow_ref_date)
    .filter((v): v is string => Boolean(v))
    .sort();
  if (refs.length === 0) return null;
  const first = daily.slice().sort((a, b) => a.date.localeCompare(b.date))[0];
  const shifted = first?.dow_ref_date;
  const sameCalendar = shifted != null && shifted === first.date;
  const range =
    refs[0] === refs[refs.length - 1]
      ? refs[0]
      : `${refs[0]}〜${refs[refs.length - 1]}`;
  if (sameCalendar) {
    return `※過去実績 ${range} を重ねています。`;
  }
  return `※過去実績は ${range} です。同じ月日ではなく、曜日が重なるように日付をずらしています。`;
}

function formatYen(n: number) {
  return `¥${Math.round(n).toLocaleString("ja-JP")}`;
}

function formatVisits(n: number) {
  return `${Math.round(n).toLocaleString("ja-JP")}人`;
}

function useIsNarrow(maxWidth = 639) {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const update = () => setNarrow(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [maxWidth]);
  return narrow;
}

function addTo(bucket: Bucket, d: DailyPoint, align: AlignMode) {
  const ref = align === "weekday" ? d.dow_ref_receipts : d.ref_receipts;
  const refSales = align === "weekday" ? d.dow_ref_net_sales : d.ref_net_sales;
  const refDate = align === "weekday" ? d.dow_ref_date : d.ref_date;
  bucket.pred += d.pred_receipts;
  bucket.predSales += d.pred_net_sales;
  if (d.actual_receipts != null) {
    bucket.actual = (bucket.actual ?? 0) + d.actual_receipts;
    bucket.actualSales = (bucket.actualSales ?? 0) + (d.actual_net_sales ?? 0);
  }
  if (ref != null) {
    bucket.ref = (bucket.ref ?? 0) + ref;
    bucket.refSales = (bucket.refSales ?? 0) + (refSales ?? 0);
    bucket.refDate = bucket.refDate ?? refDate;
  }
}

function emptyBucket(): Bucket {
  return {
    pred: 0,
    predSales: 0,
    actual: null,
    actualSales: null,
    ref: null,
    refSales: null,
    refDate: null,
  };
}

function toDailySeries(daily: DailyPoint[], align: AlignMode): SeriesPoint[] {
  const byDate = new Map<string, Bucket>();
  for (const d of daily) {
    const cur = byDate.get(d.date) ?? emptyBucket();
    addTo(cur, d, align);
    byDate.set(d.date, cur);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, v]) => ({
      date,
      label: `${date.slice(5)}（${weekdayLabel(date)}）`,
      ...v,
    }));
}

function toPeriodSeries(aggregates: AggregatePoint[]): SeriesPoint[] {
  const byPeriod = new Map<string, Bucket>();
  for (const a of aggregates) {
    const cur = byPeriod.get(a.period) ?? emptyBucket();
    cur.pred += a.pred_receipts;
    cur.predSales += a.pred_net_sales;
    if (a.actual_receipts != null) {
      cur.actual = (cur.actual ?? 0) + a.actual_receipts;
      cur.actualSales = (cur.actualSales ?? 0) + (a.actual_net_sales ?? 0);
    }
    if (a.ref_receipts != null) {
      cur.ref = (cur.ref ?? 0) + a.ref_receipts;
      cur.refSales = (cur.refSales ?? 0) + (a.ref_net_sales ?? 0);
    }
    byPeriod.set(a.period, cur);
  }
  return [...byPeriod.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, v]) => ({ date: label, label, ...v }));
}

/** 欠損点で線を途切れさせながらパスを組む（実績が無い将来日を0で結ばないため）。 */
function buildPath(
  series: SeriesPoint[],
  pick: (s: SeriesPoint) => number | null,
  x: (i: number) => number,
  y: (v: number) => number,
) {
  const parts: string[] = [];
  let connected = false;
  series.forEach((s, i) => {
    const v = pick(s);
    if (v == null) {
      connected = false;
      return;
    }
    parts.push(`${connected ? "L" : "M"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`);
    connected = true;
  });
  return parts.join(" ");
}

export function ForecastChart({
  granularity,
  daily,
  aggregates,
  align,
  onAlignChange,
}: {
  granularity: Granularity;
  daily: DailyPoint[];
  aggregates: AggregatePoint[];
  align: AlignMode;
  onAlignChange: (id: AlignMode) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const isNarrow = useIsNarrow();
  const series =
    daily.length > 0 ? toDailySeries(daily, align) : toPeriodSeries(aggregates);
  if (series.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">表示する予測点がありません。</p>
    );
  }
  const hasActual = series.some((s) => s.actual != null);
  const hasRef = series.some((s) => s.ref != null);
  const weekdayNote = align === "weekday" ? weekdayRangeNote(daily) : null;
  const labelStep = Math.max(1, Math.ceil(series.length / (isNarrow ? 4 : 10)));

  const width = 640;
  const height = isNarrow ? 260 : 220;
  const pad = { top: 16, right: 8, bottom: isNarrow ? 44 : 36, left: isNarrow ? 40 : 48 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const maxY = Math.max(
    ...series.flatMap((s) => [s.pred, s.actual ?? 0, s.ref ?? 0]),
    1,
  );
  const x = (i: number) =>
    pad.left + (series.length === 1 ? innerW / 2 : (i / (series.length - 1)) * innerW);
  const y = (v: number) => pad.top + innerH - (v / maxY) * innerH;

  const predPath = buildPath(series, (s) => s.pred, x, y);
  const actualPath = buildPath(series, (s) => s.actual, x, y);
  const refPath = buildPath(series, (s) => s.ref, x, y);
  const refLegend =
    align === "weekday" ? "同曜日の過去実績" : "同月日の過去実績";
  const hovered = hover != null ? series[hover] : null;

  function nearestIndex(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    let best = 0;
    let bestDist = Infinity;
    for (let i = 0; i < series.length; i += 1) {
      const dist = Math.abs(x(i) - svgX);
      if (dist < bestDist) {
        best = i;
        bestDist = dist;
      }
    }
    setHover(best);
  }

  return (
    <div className="w-full space-y-3">
      <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <p className="text-xs text-[var(--muted)]">
          {granularity === "daily" ? "日別推移" : "日別推移（合計は上部KPI・表を参照）"}
        </p>
        {daily.length > 0 && (
          <AlignToggle align={align} onChange={onAlignChange} />
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full touch-manipulation"
        role="img"
        aria-label="来店予測と実績の推移"
        onPointerDown={nearestIndex}
        onPointerMove={nearestIndex}
        onPointerLeave={(e) => {
          if (e.pointerType === "mouse") setHover(null);
        }}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const yy = pad.top + innerH * (1 - t);
          return (
            <g key={t}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={yy}
                y2={yy}
                stroke="var(--line)"
                strokeWidth={1}
              />
              <text
                x={pad.left - 6}
                y={yy + 4}
                textAnchor="end"
                fontSize={isNarrow ? 9 : 10}
                fill="var(--muted)"
              >
                {Math.round(maxY * t).toLocaleString()}
              </text>
            </g>
          );
        })}
        <path
          d={refPath}
          fill="none"
          stroke="var(--ref)"
          strokeWidth={1.5}
          strokeDasharray="2 3"
        />
        <path d={actualPath} fill="none" stroke="var(--actual)" strokeWidth={2} />
        <path
          d={predPath}
          fill="none"
          stroke="var(--pred)"
          strokeWidth={2.5}
          strokeDasharray="5 4"
        />
        {hover != null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={pad.top}
            y2={pad.top + innerH}
            stroke="var(--pred)"
            strokeWidth={1}
            strokeOpacity={0.35}
          />
        )}
        {series.map((s, i) =>
          s.ref != null ? (
            <circle
              key={`ref-${s.label}`}
              cx={x(i)}
              cy={y(s.ref)}
              r={hover === i ? 4 : 2}
              fill="var(--ref)"
            />
          ) : null,
        )}
        {series.map((s, i) =>
          s.actual != null ? (
            <circle
              key={`actual-${s.label}`}
              cx={x(i)}
              cy={y(s.actual)}
              r={hover === i ? 4.5 : 2.5}
              fill="var(--actual)"
            />
          ) : null,
        )}
        {series.map((s, i) => (
          <circle
            key={`pred-${s.date}`}
            cx={x(i)}
            cy={y(s.pred)}
            r={hover === i ? 4.5 : 2.5}
            fill="var(--pred)"
          />
        ))}
        {series.map((s, i) =>
          i % labelStep === 0 || i === series.length - 1 ? (
            <text
              key={`label-${s.date}`}
              x={x(i)}
              y={height - 10}
              textAnchor="middle"
              fontSize={isNarrow ? 8 : 9}
              fill="var(--muted)"
            >
              {isNarrow ? s.date.slice(5) : s.label}
            </text>
          ) : null,
        )}
      </svg>
      {!hovered && (
        <p className="text-[11px] text-[var(--muted)] sm:hidden">
          グラフをタップすると、その日の詳細が出ます
        </p>
      )}
      {hovered && (
        <div className="rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-xs leading-relaxed">
          <p className="font-medium text-[var(--ink)]">
            予測日 {hovered.date}（{weekdayLabel(hovered.date)}）
          </p>
          <p className="mt-1.5 break-words text-[var(--pred)]">
            予測　来店 {formatVisits(hovered.pred)}
            <span className="hidden sm:inline">　</span>
            <span className="block sm:inline">売上 {formatYen(hovered.predSales)}</span>
          </p>
          <p className="mt-1 break-words text-[var(--actual)]">
            実績　
            {hovered.actual != null ? (
              <>
                来店 {formatVisits(hovered.actual)}
                <span className="hidden sm:inline">　</span>
                <span className="block sm:inline">
                  売上 {formatYen(hovered.actualSales ?? 0)}
                </span>
              </>
            ) : (
              "なし"
            )}
          </p>
          <p className="mt-1 break-words text-[var(--ref)]">
            {refLegend}
            {hovered.refDate ? ` ${hovered.refDate}（${weekdayLabel(hovered.refDate)}）` : ""}
            {hovered.ref != null ? (
              <>
                <span className="hidden sm:inline">　</span>
                <span className="block sm:inline">
                  来店 {formatVisits(hovered.ref)}　売上 {formatYen(hovered.refSales ?? 0)}
                </span>
              </>
            ) : (
              "　なし"
            )}
          </p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <span className="inline-flex items-center gap-1.5 text-[var(--pred)]">
          <span
            className="inline-block h-0.5 w-4 border-t-2 border-dashed border-[var(--pred)]"
          />
          予測
        </span>
        {hasActual && (
          <span className="inline-flex items-center gap-1.5 text-[var(--actual)]">
            <span className="inline-block h-0.5 w-4 bg-[var(--actual)]" />
            実績
          </span>
        )}
        {hasRef && (
          <span className="inline-flex items-center gap-1.5 text-[var(--ref)]">
            <span
              className="inline-block h-0.5 w-4 border-t border-dotted border-[var(--ref)]"
            />
            {refLegend}
          </span>
        )}
        {!hasRef && daily.length > 0 && (
          <span className="text-[var(--muted)]">
            {align === "weekday"
              ? "同じ曜日の過去実績がこの期間にはありません"
              : "同月日の過去実績がこの期間にはありません"}
          </span>
        )}
      </div>
      {weekdayNote && (
        <p className="text-[11px] leading-relaxed text-[var(--muted)]">
          {weekdayNote}
        </p>
      )}
    </div>
  );
}
