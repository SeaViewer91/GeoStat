// 지도 이미지(PNG) 내보내기: 배경지도·deck.gl 캔버스를 합치고 범례·출처를 그려 넣음

import { t } from "../i18n";
import type { Classification } from "./engine";
import { classColors, rgbaCss } from "./palette";

type Capture = () => { base: HTMLCanvasElement | null; deck: HTMLCanvasElement | null; background: string };

let capture: Capture | null = null;

/** MapCanvas가 자기 캔버스를 꺼낼 수 있는 함수를 등록함 */
export function registerMapCapture(fn: Capture | null): void {
  capture = fn;
}

export interface MapImageOptions {
  legend: { title: string; theme: Classification } | null;
  attribution: string | null;
  title?: string;
}

/** 현재 지도 화면을 PNG base64로 만듦 */
export function renderMapPng(opts: MapImageOptions): string {
  const parts = capture?.();
  if (!parts?.deck) throw new Error(t("지도가 아직 그려지지 않음"));
  const { base, deck, background } = parts;
  const w = deck.width;
  const h = deck.height;
  const scale = w / deck.clientWidth || window.devicePixelRatio || 1;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, w, h);
  if (base) ctx.drawImage(base, 0, 0, w, h);
  ctx.drawImage(deck, 0, 0, w, h);
  ctx.scale(scale, scale);
  const cssW = w / scale;
  const cssH = h / scale;
  const font = '-apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';

  if (opts.title) {
    ctx.font = `600 16px ${font}`;
    const tw = ctx.measureText(opts.title).width;
    ctx.fillStyle = "rgba(255,255,255,0.88)";
    ctx.fillRect(12, 12, tw + 20, 30);
    ctx.fillStyle = "#1d2330";
    ctx.fillText(opts.title, 22, 33);
  }

  if (opts.legend) {
    const { title, theme } = opts.legend;
    const colors = classColors(theme.scheme, theme.labels, 225, theme.colors);
    const rows = theme.labels.map((label, i) => ({ label, color: rgbaCss(colors[i]), count: theme.counts[i] ?? 0 }));
    ctx.font = `12px ${font}`;
    const labelW = Math.max(...rows.map((r) => ctx.measureText(r.label).width), 60);
    ctx.font = `600 12px ${font}`;
    const titleW = ctx.measureText(title).width;
    const boxW = Math.max(labelW + 44, titleW + 20);
    const boxH = 30 + rows.length * 18 + 6;
    const x0 = 12;
    const y0 = cssH - boxH - 12;
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillRect(x0, y0, boxW, boxH);
    ctx.strokeStyle = "rgba(0,0,0,0.15)";
    ctx.strokeRect(x0 + 0.5, y0 + 0.5, boxW - 1, boxH - 1);
    ctx.fillStyle = "#1d2330";
    ctx.fillText(title, x0 + 10, y0 + 20);
    ctx.font = `12px ${font}`;
    rows.forEach((r, i) => {
      const y = y0 + 32 + i * 18;
      ctx.fillStyle = r.color;
      ctx.fillRect(x0 + 10, y, 16, 12);
      ctx.strokeStyle = "rgba(0,0,0,0.25)";
      ctx.strokeRect(x0 + 10.5, y + 0.5, 15, 11);
      ctx.fillStyle = "#1d2330";
      ctx.fillText(r.label, x0 + 34, y + 11);
    });
  }

  if (opts.attribution) {
    ctx.font = `10px ${font}`;
    const aw = ctx.measureText(opts.attribution).width;
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    ctx.fillRect(cssW - aw - 12, cssH - 18, aw + 12, 18);
    ctx.fillStyle = "#333";
    ctx.fillText(opts.attribution, cssW - aw - 6, cssH - 5);
  }
  return canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, "");
}
