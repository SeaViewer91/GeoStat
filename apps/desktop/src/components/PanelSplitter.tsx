// 좌우 패널 너비를 끌어서 바꾸는 세로 경계선. 두 번 누르면 기본 너비로 돌아감

import { useCallback, useEffect, useRef, useState } from "react";

import { t } from "../i18n";

/** 저장해 둔 너비를 읽고 바꾸는 훅. 저장소를 못 쓰면(개인 정보 보호 모드 등) 기본값만 씀 */
export function usePanelWidth(key: string, initial: number, min: number, max: number) {
  const [width, setWidth] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      if (Number.isFinite(saved) && saved >= min && saved <= max) return saved;
    } catch {
      // 기본값을 씀
    }
    return initial;
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, String(Math.round(width)));
    } catch {
      // 저장하지 못해도 이번 실행에서는 그대로 씀
    }
  }, [key, width]);
  const set = useCallback((w: number) => setWidth(Math.min(max, Math.max(min, w))), [min, max]);
  return [width, set] as const;
}

interface Props {
  /** 경계선을 오른쪽으로 끌 때 너비가 늘어나면 1(왼쪽 패널), 줄어들면 -1(오른쪽 패널) */
  direction: 1 | -1;
  width: number;
  onResize: (width: number) => void;
  onReset: () => void;
  label: string;
}

export function PanelSplitter({ direction, width, onResize, onReset, label }: Props) {
  const start = useRef<{ x: number; w: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div
      className={`v-splitter${dragging ? " dragging" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      title={t("끌어서 너비 조절, 두 번 누르면 기본 너비")}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        (e.target as Element).setPointerCapture(e.pointerId);
        start.current = { x: e.clientX, w: width };
        setDragging(true);
      }}
      onPointerMove={(e) => {
        if (!start.current) return;
        onResize(start.current.w + direction * (e.clientX - start.current.x));
      }}
      onPointerUp={() => {
        start.current = null;
        setDragging(false);
      }}
      onDoubleClick={onReset}
    />
  );
}
