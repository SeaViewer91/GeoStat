// 차트용 Canvas: 크기 맞춤(고해상도), 영역 선택(브러시), 마우스오버 툴팁을 공통 처리함

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { makeFrame, readTheme, type Frame, type Theme } from "./plot";

export interface BrushRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  /** 거의 움직이지 않은 클릭 */
  click: boolean;
  additive: boolean;
}

export interface Tooltip {
  x: number;
  y: number;
  content: ReactNode;
}

interface Props {
  height: number;
  /** 다시 그려야 하는 조건 (데이터·선택 등) */
  deps: unknown[];
  draw: (ctx: CanvasRenderingContext2D, frame: Frame, theme: Theme) => void;
  onBrush?: (rect: BrushRect, frame: Frame) => void;
  onHover?: (x: number, y: number, frame: Frame) => Tooltip | null;
  /** 브러시를 가로 방향으로만 (히스토그램) 또는 세로 방향으로만 (박스플롯) 제한 */
  brushAxis?: "x" | "y" | "xy";
  ariaLabel: string;
}

export function ChartCanvas({ height, deps, draw, onBrush, onHover, brushAxis = "xy", ariaLabel }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [tip, setTip] = useState<Tooltip | null>(null);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.floor(el.clientWidth)));
    ro.observe(el);
    setWidth(Math.floor(el.clientWidth));
    return () => ro.disconnect();
  }, []);

  const frame = makeFrame(width, height);

  useEffect(() => {
    const c = canvas.current;
    if (!c || width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = width * dpr;
    c.height = height * dpr;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    draw(ctx, frame, readTheme(c));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, height, ...deps]);

  const local = (e: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const onDown = (e: React.PointerEvent) => {
    if (!onBrush || e.button !== 0) return;
    const { x, y } = local(e);
    (e.target as Element).setPointerCapture(e.pointerId);
    setDrag({ x0: x, y0: y, x1: x, y1: y });
    setTip(null);
  };
  const onMove = (e: React.PointerEvent) => {
    const { x, y } = local(e);
    if (drag) {
      setDrag({ ...drag, x1: x, y1: y });
      return;
    }
    if (onHover) setTip(onHover(x, y, frame));
  };
  const onUp = (e: React.PointerEvent) => {
    if (!drag || !onBrush) return;
    const click = Math.abs(drag.x1 - drag.x0) < 3 && Math.abs(drag.y1 - drag.y0) < 3;
    onBrush(
      {
        x0: Math.min(drag.x0, drag.x1),
        x1: Math.max(drag.x0, drag.x1),
        y0: Math.min(drag.y0, drag.y1),
        y1: Math.max(drag.y0, drag.y1),
        click,
        additive: e.metaKey || e.ctrlKey,
      },
      frame,
    );
    setDrag(null);
  };

  // 브러시 사각형 표시 (한 방향 제한이면 반대 방향은 그림 영역 전체)
  let box: React.CSSProperties | null = null;
  if (drag) {
    const x0 = brushAxis === "y" ? frame.left : Math.min(drag.x0, drag.x1);
    const x1 = brushAxis === "y" ? frame.right : Math.max(drag.x0, drag.x1);
    const y0 = brushAxis === "x" ? frame.top : Math.min(drag.y0, drag.y1);
    const y1 = brushAxis === "x" ? frame.bottom : Math.max(drag.y0, drag.y1);
    box = { left: x0, top: y0, width: x1 - x0, height: y1 - y0 };
  }

  return (
    <div ref={wrap} className="chart-canvas" style={{ height }}>
      <canvas
        ref={canvas}
        style={{ width, height }}
        role="img"
        aria-label={ariaLabel}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={() => setTip(null)}
      />
      {box && <div className="drag-box" style={box} />}
      {tip && (
        <div
          className="chart-tip"
          style={{ left: Math.min(tip.x + 12, width - 160), top: Math.max(0, tip.y - 36) }}
        >
          {tip.content}
        </div>
      )}
    </div>
  );
}
