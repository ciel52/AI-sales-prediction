"use client";

import type { DailyPoint, AggregatePoint, Granularity } from "@/lib/api";

type SeriesPoint = {
  label: string;
  pred: number;
  actual: number | null;
  ref: number | null;
};

type Bucket = { pred: number; actual: number | null; ref: number | null };

function addTo(bucket: Bucket, pred: number, actual: number | null, ref: number | null) {
  bucket.pred += pred;
  if (actual != null) bucket.actual = (bucket.actual ?? 0) + actual;
  if (ref != null) bucket.ref = (bucket.ref ?? 0) + ref;
}

function emptyBucket(): Bucket {
  return { pred: 0, actual: null, ref: null };
}

function toDailySeries(daily: DailyPoint[]): SeriesPoint[] {
  const byDate = new Map<string, Bucket>();
  for (const d of daily) {
    const cur = byDate.get(d.date) ?? emptyBucket();
    addTo(cur, d.pred_receipts, d.actual_receipts, d.ref_receipts);
    byDate.set(d.date, cur);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, v]) => ({ label: label.slice(5), ...v }));
}

function toPeriodSeries(aggregates: AggregatePoint[]): SeriesPoint[] {
  const byPeriod = new Map<string, Bucket>();
  for (const a of aggregates) {
    const cur = byPeriod.get(a.period) ?? emptyBucket();
    addTo(cur, a.pred_receipts, a.actual_receipts, a.ref_receipts);
    byPeriod.set(a.period, cur);
  }
  return [...byPeriod.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, v]) => ({ label, ...v }));
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
}: {
  granularity: Granularity;
  daily: DailyPoint[];
  aggregates: AggregatePoint[];
}) {
  const series = daily.length > 0 ? toDailySeries(daily) : toPeriodSeries(aggregates);
  if (series.length === 0) {
    return (
      <p className="text-sm text-[var(--muted)]">表示する予測点がありません。</p>
    );
  }
  const hasActual = series.some((s) => s.actual != null);
  const hasRef = series.some((s) => s.ref != null);
  const labelStep = Math.max(1, Math.ceil(series.length / 14));

  const width = 640;
  const height = 220;
  const pad = { top: 16, right: 12, bottom: 36, left: 48 };
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

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full min-w-[480px]"
        role="img"
        aria-label="来店予測と実績の推移"
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
                x={pad.left - 8}
                y={yy + 4}
                textAnchor="end"
                fontSize={10}
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
          stroke="var(--muted)"
          strokeWidth={1.5}
          strokeDasharray="2 3"
        />
        <path d={actualPath} fill="none" stroke="var(--ink)" strokeWidth={2} />
        <path
          d={predPath}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2.5}
          strokeDasharray="5 4"
        />
        {series.map((s, i) =>
          s.ref != null ? (
            <circle
              key={`ref-${s.label}`}
              cx={x(i)}
              cy={y(s.ref)}
              r={2}
              fill="var(--muted)"
            />
          ) : null,
        )}
        {series.map((s, i) =>
          s.actual != null ? (
            <circle
              key={`actual-${s.label}`}
              cx={x(i)}
              cy={y(s.actual)}
              r={2.5}
              fill="var(--ink)"
            />
          ) : null,
        )}
        {series.map((s, i) =>
          i % labelStep === 0 || i === series.length - 1 ? (
            <text
              key={s.label}
              x={x(i)}
              y={height - 10}
              textAnchor="middle"
              fontSize={9}
              fill="var(--muted)"
            >
              {s.label}
            </text>
          ) : null,
        )}
      </svg>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-[var(--muted)]">
        <span>
          {granularity === "daily" ? "日別推移" : "日別推移（合計は上部KPI・表を参照）"}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4 border-t-2 border-dashed border-[var(--accent)]"
          />
          予測
        </span>
        {hasActual && (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 bg-[var(--ink)]" />
            実績
          </span>
        )}
        {hasRef && (
          <span className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-4 border-t border-dotted border-[var(--muted)]"
            />
            同月日の過去実績
          </span>
        )}
      </div>
    </div>
  );
}
