// 차트 공통: 눈금 계산, 좌표 변환, 축 그리기 (Canvas 2D)
//
// 수십만 점을 그려야 하므로 SVG 대신 Canvas를 씀. 색은 CSS 변수에서 읽어 다크 모드를 따름.

export interface Frame {
  width: number;
  height: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface Scale {
  (v: number): number;
  invert: (px: number) => number;
  domain: [number, number];
}

export const MARGIN = { left: 48, right: 12, top: 10, bottom: 28 };

export function makeFrame(width: number, height: number): Frame {
  return {
    width,
    height,
    left: MARGIN.left,
    right: width - MARGIN.right,
    top: MARGIN.top,
    bottom: height - MARGIN.bottom,
  };
}

export function linear(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  const f = ((v: number) => r0 + (v - d0) * k) as Scale;
  f.invert = (px: number) => (k === 0 ? d0 : d0 + (px - r0) / k);
  f.domain = domain;
  return f;
}

/** 보기 좋은 눈금 값 (1·2·5 × 10^n 간격) */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const span = max - min;
  const raw = span / count;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => span / s <= count) ?? 10 * pow;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) {
    out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  }
  return out;
}

/** 여백을 약간 둔 범위 */
export function paddedExtent(values: ArrayLike<number>, pad = 0.04): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (!Number.isFinite(min)) return [0, 1];
  if (min === max) return [min - 1, max + 1];
  const d = (max - min) * pad;
  return [min - d, max + d];
}

export function formatTick(v: number): string {
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e6 || a < 1e-3)) return v.toExponential(1);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return Number(v.toPrecision(4)).toString();
}

export interface Theme {
  text: string;
  muted: string;
  grid: string;
  axis: string;
  surface: string;
}

export function readTheme(el: Element): Theme {
  const css = getComputedStyle(el);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    text: v("--text", "#1f2328"),
    muted: v("--muted", "#656d76"),
    grid: v("--border", "#d9dce1"),
    axis: v("--muted", "#656d76"),
    surface: v("--panel", "#ffffff"),
  };
}

/** 격자선과 축 눈금 라벨을 그림 (격자는 옅게, 데이터가 돋보이도록) */
export function drawAxes(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  x: Scale,
  y: Scale,
  theme: Theme,
  opts: { xTicks?: number[]; yTicks?: number[]; xLabel?: string; yLabel?: string } = {},
): void {
  const xTicks = opts.xTicks ?? niceTicks(x.domain[0], x.domain[1], 5);
  const yTicks = opts.yTicks ?? niceTicks(y.domain[0], y.domain[1], 4);
  ctx.save();
  ctx.font = "11px -apple-system, system-ui, sans-serif";
  ctx.lineWidth = 1;
  ctx.strokeStyle = theme.grid;
  ctx.fillStyle = theme.muted;

  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (const t of yTicks) {
    const py = Math.round(y(t)) + 0.5;
    if (py < frame.top - 1 || py > frame.bottom + 1) continue;
    ctx.globalAlpha = 0.6;
    ctx.beginPath();
    ctx.moveTo(frame.left, py);
    ctx.lineTo(frame.right, py);
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillText(formatTick(t), frame.left - 6, py);
  }
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  for (const t of xTicks) {
    const px = x(t);
    if (px < frame.left - 1 || px > frame.right + 1) continue;
    ctx.fillText(formatTick(t), px, frame.bottom + 6);
  }
  // 기준선
  ctx.strokeStyle = theme.axis;
  ctx.globalAlpha = 0.8;
  ctx.beginPath();
  ctx.moveTo(frame.left, frame.bottom + 0.5);
  ctx.lineTo(frame.right, frame.bottom + 0.5);
  ctx.stroke();
  ctx.restore();
}
