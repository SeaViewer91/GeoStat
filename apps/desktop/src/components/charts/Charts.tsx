// 연동 차트: 히스토그램, 산점도, 박스플롯, Moran 산점도
//
// 모두 지도와 같은 선택 마스크를 구독함. 차트에서 끌어 선택하면 지도·테이블에도 반영됨.

import { useMemo } from "react";

import { CHART_BASE, CHART_BASE_SOLID, CHART_SELECTED } from "../../lib/palette";
import { useApp, type ChartSpec, type LoadedDataset, type SelectMode } from "../../store";
import { ChartCanvas, type BrushRect } from "./ChartCanvas";
import { drawAxes, formatTick, linear, niceTicks, paddedExtent, type Frame } from "./plot";

const HEIGHT = 200;

function modeOf(rect: BrushRect): SelectMode {
  return rect.additive ? "add" : "replace";
}

function fmt(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  return Number(v.toPrecision(digits)).toLocaleString();
}

/** 둥근 윗모서리 막대 (Safari 15에는 roundRect가 없어 직접 그림) */
function bar(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r = 3) {
  if (h <= 0 || w <= 0) return;
  const rr = Math.min(r, w / 2, h);
  ctx.beginPath();
  ctx.moveTo(x, y + h);
  ctx.lineTo(x, y + rr);
  ctx.arcTo(x, y, x + rr, y, rr);
  ctx.lineTo(x + w - rr, y);
  ctx.arcTo(x + w, y, x + w, y + rr, rr);
  ctx.lineTo(x + w, y + h);
  ctx.closePath();
  ctx.fill();
}

/** 최소제곱 회귀선 (기울기, 절편, R²). 점이 3개 미만이면 null */
function regression(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  include: (i: number) => boolean,
): { slope: number; intercept: number; r2: number; n: number } | null {
  let n = 0, sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0;
  for (let i = 0; i < x.length; i++) {
    const xi = x[i], yi = y[i];
    if (!Number.isFinite(xi) || !Number.isFinite(yi) || !include(i)) continue;
    n++; sx += xi; sy += yi; sxx += xi * xi; sxy += xi * yi; syy += yi * yi;
  }
  if (n < 3) return null;
  const vx = sxx - (sx * sx) / n;
  const vy = syy - (sy * sy) / n;
  if (vx === 0) return null;
  const slope = (sxy - (sx * sy) / n) / vx;
  const intercept = (sy - slope * sx) / n;
  const r2 = vy === 0 ? 0 : ((sxy - (sx * sy) / n) ** 2) / (vx * vy);
  return { slope, intercept, r2, n };
}

// ---- 히스토그램 ---------------------------------------------------------------

export function Histogram({
  ds,
  values,
  bins,
}: {
  ds: LoadedDataset;
  values: Float64Array;
  bins: number;
}) {
  const select = useApp((s) => s.select);
  const { edges, binOf, counts } = useMemo(() => {
    const [min, max] = paddedExtent(values, 0);
    const width = (max - min) / bins || 1;
    const edges = Array.from({ length: bins + 1 }, (_, i) => min + i * width);
    const binOf = new Int32Array(values.length);
    const counts = new Array(bins).fill(0);
    for (let i = 0; i < values.length; i++) {
      const v = values[i];
      if (!Number.isFinite(v)) {
        binOf[i] = -1;
        continue;
      }
      const b = Math.min(bins - 1, Math.max(0, Math.floor((v - min) / width)));
      binOf[i] = b;
      counts[b]++;
    }
    return { edges, binOf, counts };
  }, [values, bins]);

  const selectedCounts = useMemo(() => {
    const out = new Array(bins).fill(0);
    if (ds.selectedCount === 0) return out;
    for (let i = 0; i < binOf.length; i++) if (ds.selection[i] && binOf[i] >= 0) out[binOf[i]]++;
    return out;
  }, [binOf, ds.selection, ds.selectedCount, bins]);

  const scales = (f: Frame) => {
    const x = linear([edges[0], edges[bins]], [f.left, f.right]);
    const y = linear([0, Math.max(1, ...counts) * 1.08], [f.bottom, f.top]);
    return { x, y };
  };

  const binAt = (px: number, f: Frame) => {
    const { x } = scales(f);
    const v = x.invert(px);
    const w = edges[1] - edges[0];
    return Math.min(bins - 1, Math.max(0, Math.floor((v - edges[0]) / w)));
  };

  return (
    <ChartCanvas
      height={HEIGHT}
      ariaLabel="히스토그램"
      deps={[edges, counts, selectedCounts]}
      brushAxis="x"
      draw={(ctx, f, theme) => {
        const { x, y } = scales(f);
        drawAxes(ctx, f, x, y, theme, { xTicks: niceTicks(edges[0], edges[bins], 5) });
        for (let b = 0; b < bins; b++) {
          const x0 = x(edges[b]) + 1; // 막대 사이 2px 간격
          const w = x(edges[b + 1]) - x(edges[b]) - 2;
          ctx.fillStyle = CHART_BASE;
          bar(ctx, x0, y(counts[b]), w, y(0) - y(counts[b]));
          if (selectedCounts[b] > 0) {
            ctx.fillStyle = CHART_SELECTED;
            bar(ctx, x0, y(selectedCounts[b]), w, y(0) - y(selectedCounts[b]));
          }
        }
      }}
      onBrush={(r, f) => {
        const b0 = binAt(r.x0, f);
        const b1 = r.click ? b0 : binAt(r.x1, f);
        const hits: number[] = [];
        for (let i = 0; i < binOf.length; i++) if (binOf[i] >= b0 && binOf[i] <= b1) hits.push(i);
        select(ds.info.id, hits, modeOf(r));
      }}
      onHover={(px, py, f) => {
        if (px < f.left || px > f.right || py < f.top || py > f.bottom) return null;
        const b = binAt(px, f);
        return {
          x: px,
          y: py,
          content: (
            <>
              <div>
                {formatTick(edges[b])} ~ {formatTick(edges[b + 1])}
              </div>
              <div>
                <strong>{counts[b].toLocaleString()}</strong>개
                {selectedCounts[b] > 0 && ` · 선택 ${selectedCounts[b].toLocaleString()}`}
              </div>
            </>
          ),
        };
      }}
    />
  );
}

// ---- 산점도 (Moran 산점도 포함) ---------------------------------------------------

export function Scatter({
  ds,
  xs,
  ys,
  xLabel,
  yLabel,
  moran,
}: {
  ds: LoadedDataset;
  xs: Float64Array;
  ys: Float64Array;
  xLabel: string;
  yLabel: string;
  /** Moran 산점도: 0 기준선을 그리고 사분면을 표시함 */
  moran?: boolean;
}) {
  const select = useApp((s) => s.select);
  const ext = useMemo(() => {
    let [x0, x1] = paddedExtent(xs);
    let [y0, y1] = paddedExtent(ys);
    if (moran) {
      // Moran 산점도는 원점이 가운데 오도록 대칭 범위를 씀
      const a = Math.max(Math.abs(x0), Math.abs(x1), Math.abs(y0), Math.abs(y1));
      [x0, x1, y0, y1] = [-a, a, -a, a];
    }
    return { x: [x0, x1] as [number, number], y: [y0, y1] as [number, number] };
  }, [xs, ys, moran]);

  const all = useMemo(() => regression(xs, ys, () => true), [xs, ys]);
  const sel = useMemo(
    () => (ds.selectedCount >= 3 ? regression(xs, ys, (i) => ds.selection[i] === 1) : null),
    [xs, ys, ds.selection, ds.selectedCount],
  );

  const scales = (f: Frame) => ({ x: linear(ext.x, [f.left, f.right]), y: linear(ext.y, [f.bottom, f.top]) });
  const n = xs.length;
  const size = n > 20000 ? 2 : n > 2000 ? 3 : 5;

  return (
    <>
      <ChartCanvas
        height={HEIGHT + 40}
        ariaLabel={`${xLabel}–${yLabel} 산점도`}
        deps={[xs, ys, ds.selection, ext]}
        draw={(ctx, f, theme) => {
          const { x, y } = scales(f);
          drawAxes(ctx, f, x, y, theme);
          ctx.save();
          ctx.beginPath();
          ctx.rect(f.left, f.top, f.right - f.left, f.bottom - f.top);
          ctx.clip();
          if (moran) {
            ctx.strokeStyle = theme.muted;
            ctx.setLineDash([4, 3]);
            ctx.beginPath();
            ctx.moveTo(x(0), f.top);
            ctx.lineTo(x(0), f.bottom);
            ctx.moveTo(f.left, y(0));
            ctx.lineTo(f.right, y(0));
            ctx.stroke();
            ctx.setLineDash([]);
          }
          const h = size / 2;
          ctx.fillStyle = CHART_BASE;
          for (let i = 0; i < n; i++) {
            if (ds.selection[i]) continue;
            const px = x(xs[i]), py = y(ys[i]);
            if (Number.isFinite(px) && Number.isFinite(py)) ctx.fillRect(px - h, py - h, size, size);
          }
          ctx.fillStyle = CHART_SELECTED;
          if (ds.selectedCount > 0) {
            for (let i = 0; i < n; i++) {
              if (!ds.selection[i]) continue;
              const px = x(xs[i]), py = y(ys[i]);
              if (Number.isFinite(px) && Number.isFinite(py)) ctx.fillRect(px - h - 0.5, py - h - 0.5, size + 1, size + 1);
            }
          }
          const line = (r: NonNullable<typeof all>, color: string) => {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(x(ext.x[0]), y(r.intercept + r.slope * ext.x[0]));
            ctx.lineTo(x(ext.x[1]), y(r.intercept + r.slope * ext.x[1]));
            ctx.stroke();
          };
          if (all) line(all, CHART_BASE_SOLID);
          if (sel) line(sel, CHART_SELECTED);
          ctx.restore();
        }}
        onBrush={(r, f) => {
          const { x, y } = scales(f);
          const hits: number[] = [];
          if (r.click) {
            // 클릭: 가장 가까운 점 하나 (6px 이내)
            let best = -1, bestD = 36;
            for (let i = 0; i < n; i++) {
              const d = (x(xs[i]) - r.x0) ** 2 + (y(ys[i]) - r.y0) ** 2;
              if (d < bestD) { bestD = d; best = i; }
            }
            if (best >= 0) hits.push(best);
          } else {
            const [vx0, vx1] = [x.invert(r.x0), x.invert(r.x1)];
            const [vy0, vy1] = [y.invert(r.y1), y.invert(r.y0)];
            for (let i = 0; i < n; i++) {
              if (xs[i] >= vx0 && xs[i] <= vx1 && ys[i] >= vy0 && ys[i] <= vy1) hits.push(i);
            }
          }
          select(ds.info.id, hits, r.click && r.additive ? "toggle" : modeOf(r));
        }}
        onHover={(px, py, f) => {
          const { x, y } = scales(f);
          let best = -1, bestD = 36;
          for (let i = 0; i < n; i++) {
            const d = (x(xs[i]) - px) ** 2 + (y(ys[i]) - py) ** 2;
            if (d < bestD) { bestD = d; best = i; }
          }
          if (best < 0) return null;
          return {
            x: px,
            y: py,
            content: (
              <>
                <div>행 {best + 1}</div>
                <div>{xLabel}: {fmt(xs[best])}</div>
                <div>{yLabel}: {fmt(ys[best])}</div>
              </>
            ),
          };
        }}
      />
      <div className="chart-foot">
        <span>
          x: {xLabel} · y: {yLabel}
        </span>
        {all && (
          <span>
            <i className="dot" style={{ background: CHART_BASE_SOLID }} />
            {moran ? "I" : "기울기"} {fmt(all.slope)} · R² {fmt(all.r2, 3)}
          </span>
        )}
        {sel && (
          <span>
            <i className="dot" style={{ background: CHART_SELECTED }} />
            선택 {fmt(sel.slope)}
          </span>
        )}
      </div>
    </>
  );
}

// ---- 박스플롯 ---------------------------------------------------------------

export function BoxPlot({ ds, values }: { ds: LoadedDataset; values: Float64Array }) {
  const select = useApp((s) => s.select);
  const stats = useMemo(() => {
    const v = Array.from(values).filter(Number.isFinite).sort((a, b) => a - b);
    const q = (p: number) => {
      const pos = (v.length - 1) * p;
      const lo = Math.floor(pos);
      return v[lo] + (v[Math.min(lo + 1, v.length - 1)] - v[lo]) * (pos - lo);
    };
    const q1 = q(0.25), q2 = q(0.5), q3 = q(0.75), iqr = q3 - q1;
    const lf = q1 - 1.5 * iqr, uf = q3 + 1.5 * iqr;
    const lw = v.find((x) => x >= lf) ?? v[0];
    const uw = [...v].reverse().find((x) => x <= uf) ?? v[v.length - 1];
    const mean = v.reduce((a, b) => a + b, 0) / v.length;
    return { q1, q2, q3, lw, uw, mean, min: v[0], max: v[v.length - 1], n: v.length };
  }, [values]);

  const scaleY = (f: Frame) => linear(paddedExtent([stats.min, stats.max]), [f.bottom, f.top]);
  // 점이 겹치지 않도록 행 번호로 정해지는 좌우 흔들림(jitter)을 줌
  const jitter = (i: number) => (((i * 2654435761) >>> 0) % 1000) / 1000 - 0.5;

  return (
    <>
      <ChartCanvas
        height={HEIGHT + 40}
        ariaLabel="박스플롯"
        deps={[values, ds.selection, stats]}
        brushAxis="y"
        draw={(ctx, f, theme) => {
          const y = scaleY(f);
          const x = linear([0, 1], [f.left, f.right]);
          drawAxes(ctx, f, x, y, theme, { xTicks: [] });
          const cx = (f.left + f.right) / 2;
          const bw = Math.min(80, (f.right - f.left) / 3);
          // 점 (박스 오른쪽)
          const px0 = cx + bw / 2 + 24;
          const spread = Math.min(40, f.right - px0 - 8);
          const size = values.length > 20000 ? 2 : 3;
          for (const pass of [0, 1]) {
            ctx.fillStyle = pass ? CHART_SELECTED : CHART_BASE;
            for (let i = 0; i < values.length; i++) {
              if (!Number.isFinite(values[i]) || (ds.selection[i] === 1) !== (pass === 1)) continue;
              ctx.fillRect(px0 + spread / 2 + jitter(i) * spread - size / 2, y(values[i]) - size / 2, size, size);
            }
          }
          // 박스와 수염
          ctx.strokeStyle = CHART_BASE_SOLID;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(cx, y(stats.lw));
          ctx.lineTo(cx, y(stats.q1));
          ctx.moveTo(cx, y(stats.q3));
          ctx.lineTo(cx, y(stats.uw));
          ctx.moveTo(cx - bw / 4, y(stats.lw));
          ctx.lineTo(cx + bw / 4, y(stats.lw));
          ctx.moveTo(cx - bw / 4, y(stats.uw));
          ctx.lineTo(cx + bw / 4, y(stats.uw));
          ctx.stroke();
          ctx.fillStyle = CHART_BASE;
          ctx.fillRect(cx - bw / 2, y(stats.q3), bw, y(stats.q1) - y(stats.q3));
          ctx.strokeRect(cx - bw / 2, y(stats.q3), bw, y(stats.q1) - y(stats.q3));
          ctx.beginPath();
          ctx.moveTo(cx - bw / 2, y(stats.q2));
          ctx.lineTo(cx + bw / 2, y(stats.q2));
          ctx.stroke();
          // 평균
          ctx.fillStyle = theme.text;
          ctx.beginPath();
          ctx.arc(cx, y(stats.mean), 3, 0, Math.PI * 2);
          ctx.fill();
        }}
        onBrush={(r, f) => {
          const y = scaleY(f);
          const hi = y.invert(r.y0), lo = y.invert(r.y1);
          const hits: number[] = [];
          for (let i = 0; i < values.length; i++) if (values[i] >= lo && values[i] <= hi) hits.push(i);
          select(ds.info.id, hits, modeOf(r));
        }}
      />
      <div className="chart-foot">
        <span>중앙값 {fmt(stats.q2)}</span>
        <span>Q1 {fmt(stats.q1)} · Q3 {fmt(stats.q3)}</span>
        <span>평균 {fmt(stats.mean)}</span>
        <span>n {stats.n.toLocaleString()}</span>
      </div>
    </>
  );
}

// ---- Moran 기준 분포 -------------------------------------------------------------

export function MoranReference({ moran }: { moran: NonNullable<ChartSpec["moran"]> }) {
  const hist = moran.sim_hist;
  if (!hist) return null;
  const { counts, edges } = hist;
  return (
    <ChartCanvas
      height={90}
      ariaLabel="순열 기준 분포"
      deps={[moran]}
      draw={(ctx, f, theme) => {
        const lo = Math.min(edges[0], moran.I), hi = Math.max(edges[edges.length - 1], moran.I);
        const pad = (hi - lo) * 0.05;
        const x = linear([lo - pad, hi + pad], [f.left, f.right]);
        const y = linear([0, Math.max(...counts) * 1.1], [f.bottom, f.top]);
        drawAxes(ctx, f, x, y, theme, { yTicks: [] });
        ctx.fillStyle = CHART_BASE;
        for (let b = 0; b < counts.length; b++) {
          const x0 = x(edges[b]) + 0.5;
          bar(ctx, x0, y(counts[b]), Math.max(1, x(edges[b + 1]) - x(edges[b]) - 1), y(0) - y(counts[b]), 1);
        }
        ctx.strokeStyle = CHART_SELECTED;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x(moran.I), f.top);
        ctx.lineTo(x(moran.I), f.bottom);
        ctx.stroke();
      }}
    />
  );
}
