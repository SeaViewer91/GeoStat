// 앱 전역 상태
//
// 선택(selection)은 프론트엔드가 소유함. 지도·차트·테이블이 같은 Uint8Array 비트마스크를 구독하므로
// 브러싱할 때 엔진과 통신하지 않음. 마스크를 바꿀 때마다 새 배열을 만들어 참조 비교로 갱신을 감지함.

import type { Table } from "apache-arrow";
import { create } from "zustand";

import { computeFeatureBounds } from "./lib/geoarrow";
import { EngineError, engine, type DatasetInfo } from "./lib/engine";

export type SelectMode = "replace" | "add" | "toggle";

export interface LoadedDataset {
  info: DatasetInfo;
  table: Table;
  /** 피처별 경위도 범위 (행 수 × 4) */
  bounds: Float64Array;
  /** 1 = 선택됨 */
  selection: Uint8Array;
  selectedCount: number;
}

interface AppState {
  datasets: Record<string, LoadedDataset>;
  activeId: string | null;
  busy: string | null;
  error: EngineError | null;

  openPath: (path: string) => Promise<void>;
  select: (id: string, indices: ArrayLike<number>, mode: SelectMode) => void;
  clearSelection: (id: string) => void;
  dismissError: () => void;
}

function toEngineError(err: unknown): EngineError {
  return err instanceof EngineError ? err : new EngineError("unknown", String(err));
}

export const useApp = create<AppState>((set, get) => ({
  datasets: {},
  activeId: null,
  busy: null,
  error: null,

  openPath: async (path) => {
    set({ busy: "파일을 여는 중…", error: null });
    try {
      const info = await engine.openDataset(path);
      set({ busy: `지오메트리 불러오는 중… (${info.n_rows.toLocaleString()}개)` });
      const t0 = performance.now();
      const table = await engine.geometry(info.id);
      const bounds = computeFeatureBounds(table);
      console.info(
        `[geostat] ${info.name}: ${info.n_rows}개 피처 로드 ${Math.round(performance.now() - t0)}ms`,
      );
      const loaded: LoadedDataset = {
        info,
        table,
        bounds,
        selection: new Uint8Array(info.n_rows),
        selectedCount: 0,
      };
      set((s) => ({ datasets: { ...s.datasets, [info.id]: loaded }, activeId: info.id }));
    } catch (err) {
      set({ error: toEngineError(err) });
    } finally {
      set({ busy: null });
    }
  },

  select: (id, indices, mode) => {
    const ds = get().datasets[id];
    if (!ds) return;
    const next = mode === "replace" ? new Uint8Array(ds.selection.length) : ds.selection.slice();
    for (let k = 0; k < indices.length; k++) {
      const i = indices[k];
      next[i] = mode === "toggle" ? (next[i] ^ 1) : 1;
    }
    let count = 0;
    for (let i = 0; i < next.length; i++) count += next[i];
    set((s) => ({
      datasets: { ...s.datasets, [id]: { ...ds, selection: next, selectedCount: count } },
    }));
  },

  clearSelection: (id) => get().select(id, [], "replace"),

  dismissError: () => set({ error: null }),
}));
