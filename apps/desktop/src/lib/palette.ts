// 주제도 색상표 (ColorBrewer 기반)

import type { SchemeType } from "./engine";
import type { RGBA } from "./geoarrow";

type Hex = string;

// 순차: YlOrRd 9단계
const SEQUENTIAL: Hex[] = [
  "#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#bd0026", "#800026",
];
// 발산: RdBu 역순 6단계 (낮음=파랑, 높음=빨강). GeoDa 박스·백분위·표준편차 지도와 같은 배치임
const DIVERGING6: Hex[] = ["#2166ac", "#67a9cf", "#d1e5f0", "#fddbc7", "#ef8a62", "#b2182b"];
// 범주: Tableau 10 + 2색, 마지막 "기타"는 회색으로 따로 줌
const QUALITATIVE: Hex[] = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948",
  "#b07aa1", "#ff9da7", "#9c755f", "#86bcb6", "#8cd17d", "#d4a6c8",
];
const OTHER: Hex = "#bab0ac";

export const MISSING_COLOR: RGBA = [200, 200, 200, 160];
export const DEFAULT_FILL: RGBA = [70, 130, 180, 210];
export const SELECTED_FILL: RGBA = [255, 196, 0, 235];

function hexToRgb(hex: Hex): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lerp(a: [number, number, number], b: [number, number, number], t: number) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t)) as [number, number, number];
}

/** 순차 색상표에서 k개를 고르게 뽑음 (9개를 넘으면 보간함) */
function sequential(k: number): [number, number, number][] {
  const stops = SEQUENTIAL.map(hexToRgb);
  if (k === 1) return [stops[4]];
  return Array.from({ length: k }, (_, i) => {
    const pos = (i / (k - 1)) * (stops.length - 1);
    const lo = Math.floor(pos);
    const hi = Math.min(lo + 1, stops.length - 1);
    return lerp(stops[lo], stops[hi], pos - lo);
  });
}

/** 계급 수와 색상표 종류에 맞는 RGBA 목록. 고정 색(fixed)이 있으면 그대로 씀 */
export function classColors(
  scheme: SchemeType,
  labels: string[],
  alpha = 225,
  fixed?: string[] | null,
): RGBA[] {
  const k = labels.length;
  let rgb: [number, number, number][];
  if (fixed && fixed.length === k) {
    rgb = fixed.map(hexToRgb);
  } else if (scheme === "diverging") {
    rgb = (k === 6 ? DIVERGING6 : DIVERGING6.slice(0, k)).map(hexToRgb);
  } else if (scheme === "qualitative") {
    rgb = labels.map((label, i) =>
      hexToRgb(label.startsWith("기타 (") ? OTHER : QUALITATIVE[i % QUALITATIVE.length]),
    );
  } else {
    rgb = sequential(k);
  }
  return rgb.map(([r, g, b]) => [r, g, b, alpha]);
}

/** 차트 색: 지도와 같은 기본색·선택색을 씀 */
export const CHART_BASE = "rgba(70, 130, 180, 0.55)";
export const CHART_BASE_SOLID = "rgb(70, 130, 180)";
export const CHART_SELECTED = "rgb(242, 180, 0)";

export function rgbaCss([r, g, b, a]: RGBA): string {
  return `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(2)})`;
}
