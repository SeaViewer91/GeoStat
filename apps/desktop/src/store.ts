// 앱 전역 상태
//
// 선택(selection)은 프론트엔드가 소유함. 지도·테이블·범례가 같은 Uint8Array 비트마스크를 구독하므로
// 브러싱할 때 엔진과 통신하지 않음. 마스크를 바꿀 때마다 새 배열을 만들어 참조 비교로 갱신을 감지함.

import type { Table } from "apache-arrow";
import { create } from "zustand";

import { getLang, setLang as applyLang, t, type Lang } from "./i18n";
import { computeFeatureBounds, readCentroids } from "./lib/geoarrow";
import { findUpdate, type AvailableUpdate } from "./lib/updater";
import {
  EngineError,
  engine,
  restartEngine as restartEngineProcess,
  type Classification,
  type ClassifyMethod,
  type DatasetInfo,
  type FileInspection,
  type AnalysisInfo,
  type JobInfo,
  type LocalParams,
  type RegressionSpec,
  type ClusterSpec,
  type FishnetSpec,
  type RasterInfo,
  type RasterStyle,
  type ZonalSpec,
  isClusterReport,
  type MoranResult,
  type TableOptions,
  type WeightsInfo,
} from "./lib/engine";
import { maskToIds } from "./lib/binary";

export type SelectMode = "replace" | "add" | "toggle";
export type Tool = "pan" | "box" | "lasso";
export type Basemap = "none" | "positron" | "liberty";

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
}

export interface StyleSpec {
  column: string;
  method: ClassifyMethod;
  k: number;
  /** 이 열이 0인 피처를 '유의하지 않음'으로 가림 (GWR 계수 지도) */
  mask?: string | null;
}

/** 결과 패널에 띄울 회귀·군집 보고서 */
export interface ReportEntry {
  datasetId: string;
  analysis: AnalysisInfo;
}

export interface LoadedDataset {
  info: DatasetInfo;
  /** 지도 표시용 지오메트리. 좌표계가 없어 표시할 수 없으면 null */
  table: Table | null;
  /** 피처별 경위도 범위 (행 수 × 4) */
  bounds: Float64Array | null;
  /** 피처별 중심점 경위도 (행 수 × 2) */
  centroids: Float64Array | null;
  /** 1 = 선택됨 */
  selection: Uint8Array;
  selectedCount: number;
  visible: boolean;
  style: StyleSpec | null;
  theme: Classification | null;
  /** 속성 열이 바뀔 때마다 증가함 (테이블 캐시 무효화용) */
  revision: number;
  weights: WeightsInfo[];
  activeWeightsId: string | null;
}

export interface LoadedRaster {
  info: RasterInfo;
  visible: boolean;
  style: RasterStyle;
}

/** 래스터 기본 표시: 밴드 3개 이상이면 1·2·3 RGB, 아니면 1밴드 색상표. 값 범위는 2~98% 백분위 */
export function defaultRasterStyle(info: RasterInfo): RasterStyle {
  const range = (b: number): [number, number] => {
    const st = info.stats[b - 1];
    if (info.categorical) return [st?.min ?? 0, st?.max ?? 1];
    return [st?.p2 ?? st?.min ?? 0, st?.p98 ?? st?.max ?? 1];
  };
  const bands = info.count >= 3 ? [1, 2, 3] : [1];
  return {
    bands,
    vmin: bands.map((b) => range(b)[0]),
    vmax: bands.map((b) => range(b)[1]),
    colormap: info.categorical ? "spectral" : "viridis",
    opacity: 0.85,
    resampling: info.categorical ? "nearest" : "bilinear",
  };
}

/** 이 개수를 넘으면 지도 표시가 느려질 수 있다고 알림 */
export const LARGE_FEATURES = 500_000;

export type ChartKind = "histogram" | "scatter" | "box" | "moran";

export interface ChartSpec {
  id: number;
  datasetId: string;
  kind: ChartKind;
  x: string;
  y?: string | null;
  bins?: number;
  /** Moran 산점도: 가중치와 결과 (결과는 저장하지 않고 다시 계산함) */
  weightsId?: string;
  permutations?: number;
  moran?: MoranResult | null;
}

export type Dialog =
  | { kind: "layers"; path: string; layers: string[] }
  | { kind: "table"; path: string; inspection: FileInspection }
  | { kind: "crs"; datasetId: string; reason: "missing" | "manual" }
  | { kind: "field"; datasetId: string }
  | { kind: "export"; datasetId: string }
  | { kind: "weights"; datasetId: string }
  | { kind: "moran"; datasetId: string }
  | { kind: "local"; datasetId: string }
  | { kind: "joincount"; datasetId: string }
  | { kind: "regression"; datasetId: string }
  | { kind: "cluster"; datasetId: string }
  | { kind: "zonal"; datasetId: string }
  | { kind: "fishnet" }
  | { kind: "query"; datasetId: string }
  | { kind: "about" }
  | { kind: "chart"; datasetId: string; chart: ChartKind };

/** 프로젝트 파일에 저장하는 화면 설정 */
interface ProjectUi {
  basemap: Basemap;
  view: ViewState;
  activeIndex: number;
}
type SavedChart = Omit<ChartSpec, "id" | "datasetId" | "moran">;
type RasterUi = { visible: boolean; style: RasterStyle };
interface DatasetUi {
  visible: boolean;
  style: StyleSpec | null;
  activeWeightsId?: string | null;
  charts?: SavedChart[];
}

interface AppState {
  datasets: Record<string, LoadedDataset>;
  /** 레이어 목록 순서 (앞쪽이 위에 그려짐) */
  order: string[];
  activeId: string | null;
  tool: Tool;
  basemap: Basemap;
  view: ViewState;
  /** 지도가 이 범위로 이동해야 함 (값이 바뀔 때만 반응) */
  fitRequest: { bounds: [number, number, number, number]; nonce: number } | null;
  projectPath: string | null;
  dialog: Dialog | null;
  busy: string | null;
  error: EngineError | null;
  notices: { id: number; text: string }[];

  // 엔진 상태: 비정상 종료 메시지, 다시 띄울 때마다 증가하는 세대 번호
  engineDown: string | null;
  engineGeneration: number;
  setEngineDown: (message: string | null) => void;
  restartEngine: () => Promise<void>;

  // 업데이트: 새 버전 정보 (설치 버튼을 띄움)
  update: AvailableUpdate | null;
  checkUpdate: (manual: boolean) => Promise<void>;
  installUpdate: () => Promise<void>;
  dismissUpdate: () => void;

  // 언어
  lang: Lang;
  setLanguage: (lang: Lang) => void;

  // 조건 선택·샘플
  querySelect: (id: string, expression: string, mode: SelectMode) => Promise<boolean>;
  openSample: (sampleId: string) => Promise<void>;

  // 래스터 (벡터 레이어 아래에 그림)
  rasters: Record<string, LoadedRaster>;
  rasterOrder: string[];
  openRaster: (path: string) => Promise<void>;
  closeRaster: (id: string) => Promise<void>;
  toggleRasterVisible: (id: string) => void;
  setRasterStyle: (id: string, style: Partial<RasterStyle>) => void;
  buildOverviews: (id: string) => Promise<void>;
  zoomToRaster: (id: string) => void;
  startZonal: (id: string, spec: ZonalSpec) => Promise<boolean>;
  makeFishnet: (spec: FishnetSpec) => Promise<string | null>;

  // 파일·데이터셋
  openFile: (path: string) => Promise<void>;
  openDataset: (
    path: string,
    opts?: { layer?: string | null; table?: TableOptions | null },
  ) => Promise<void>;
  closeDataset: (id: string) => Promise<void>;
  setActive: (id: string) => void;
  toggleVisible: (id: string) => void;
  moveLayer: (id: string, delta: -1 | 1) => void;
  zoomTo: (id: string) => void;
  assignCrs: (id: string, epsg: number) => Promise<void>;
  updateInfo: (info: DatasetInfo) => Promise<void>;

  // 주제도
  applyStyle: (id: string, style: StyleSpec | null) => Promise<void>;

  // 공간가중치·분석
  refreshWeights: (id: string, activeId?: string | null) => Promise<void>;
  setActiveWeights: (id: string, weightsId: string) => void;
  removeWeights: (id: string, weightsId: string) => Promise<void>;
  selectNeighbors: (id: string) => Promise<void>;
  runLocal: (id: string, params: LocalParams) => Promise<boolean>;

  // 회귀·작업
  job: JobInfo | null;
  reports: ReportEntry[];
  startRegression: (id: string, spec: RegressionSpec) => Promise<boolean>;
  startCluster: (id: string, spec: ClusterSpec) => Promise<boolean>;
  /** 작업을 시작하고 끝날 때까지 진행률을 받은 뒤 결과를 반영함 */
  runJob: (id: string, start: () => Promise<JobInfo>) => Promise<boolean>;
  cancelJob: () => Promise<void>;
  loadReports: (id: string) => Promise<void>;
  dismissReport: (analysisId: string) => void;
  showResultMap: (id: string, analysis: AnalysisInfo, variable?: string) => Promise<void>;

  // 차트
  charts: ChartSpec[];
  addChart: (chart: Omit<ChartSpec, "id">) => Promise<void>;
  removeChart: (chartId: number) => void;

  // 선택
  select: (id: string, indices: ArrayLike<number>, mode: SelectMode) => void;
  selectClass: (id: string, klass: number, mode: SelectMode) => void;
  clearSelection: (id: string) => void;
  invertSelection: (id: string) => void;

  // 프로젝트
  saveProject: (path: string) => Promise<void>;
  openProject: (path: string) => Promise<void>;

  // 화면
  setTool: (tool: Tool) => void;
  setBasemap: (basemap: Basemap) => void;
  setView: (view: ViewState) => void;
  showDialog: (dialog: Dialog | null) => void;
  notify: (text: string) => void;
  dismissNotice: (id: number) => void;
  fail: (err: unknown) => void;
  dismissError: () => void;
}

let noticeSeq = 0;
let chartSeq = 0;

function toEngineError(err: unknown): EngineError {
  return err instanceof EngineError ? err : new EngineError("unknown", String(err));
}

function countOnes(mask: Uint8Array): number {
  let n = 0;
  for (let i = 0; i < mask.length; i++) n += mask[i];
  return n;
}

/** 지오메트리를 받아 지도 표시 준비를 함. 좌표계가 없으면 table=null로 둠 */
async function loadGeometry(
  info: DatasetInfo,
): Promise<Pick<LoadedDataset, "table" | "bounds" | "centroids">> {
  try {
    const t0 = performance.now();
    const table = await engine.geometry(info.id);
    const bounds = computeFeatureBounds(table);
    const centroids = readCentroids(table);
    console.info(
      `[geostat] ${info.name}: ${info.n_rows}개 피처 로드 ${Math.round(performance.now() - t0)}ms`,
    );
    return { table, bounds, centroids };
  } catch (err) {
    if (err instanceof EngineError && err.code === "crs_missing") {
      return { table: null, bounds: null, centroids: null };
    }
    throw err;
  }
}

function newDataset(info: DatasetInfo, geo: Awaited<ReturnType<typeof loadGeometry>>): LoadedDataset {
  return {
    info,
    ...geo,
    selection: new Uint8Array(info.n_rows),
    selectedCount: 0,
    visible: true,
    style: null,
    theme: null,
    revision: 0,
    weights: [],
    activeWeightsId: null,
  };
}

export const useApp = create<AppState>((set, get) => {
  /** 데이터셋 하나를 부분 갱신함 */
  const patch = (id: string, change: Partial<LoadedDataset>) =>
    set((s) => {
      const ds = s.datasets[id];
      return ds ? { datasets: { ...s.datasets, [id]: { ...ds, ...change } } } : {};
    });

  const requestFit = (bounds: [number, number, number, number] | null) => {
    if (bounds) set({ fitRequest: { bounds, nonce: Date.now() } });
  };

  /** 엔진 호출을 busy 표시·오류 처리로 감쌈 */
  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    set({ busy: label, error: null });
    try {
      return await fn();
    } catch (err) {
      set({ error: toEngineError(err) });
      return undefined;
    } finally {
      set({ busy: null });
    }
  }

  async function addLoaded(info: DatasetInfo, extra: Partial<LoadedDataset> = {}) {
    const geo = await loadGeometry(info);
    const loaded = { ...newDataset(info, geo), ...extra };
    set((s) => ({
      datasets: { ...s.datasets, [info.id]: loaded },
      order: [info.id, ...s.order.filter((x) => x !== info.id)],
      activeId: info.id,
    }));
    if (!geo.table) {
      set({ dialog: { kind: "crs", datasetId: info.id, reason: "missing" } });
    }
    return loaded;
  }

  return {
    datasets: {},
    order: [],
    activeId: null,
    rasters: {},
    rasterOrder: [],
    engineDown: null,
    engineGeneration: 0,
    update: null,
    lang: getLang(),
    tool: "pan",
    basemap: "none",
    view: { longitude: 127.8, latitude: 36.3, zoom: 6 },
    fitRequest: null,
    projectPath: null,
    dialog: null,
    busy: null,
    error: null,
    notices: [],

    // ---- 엔진·언어·조건 선택·샘플 -------------------------------------------------

    setEngineDown: (message) => set({ engineDown: message, job: null, busy: null }),

    restartEngine: async () => {
      const ok = await run(t("분석 엔진을 다시 시작하는 중…"), async () => {
        await restartEngineProcess();
        await engine.health(); // 새 엔진이 준비될 때까지 기다림
        return true;
      });
      if (!ok) return;
      // 새 엔진은 이전에 열었던 데이터를 모르므로 화면 상태도 비움
      set((s) => ({
        datasets: {},
        order: [],
        activeId: null,
        rasters: {},
        rasterOrder: [],
        charts: [],
        reports: [],
        job: null,
        engineDown: null,
        engineGeneration: s.engineGeneration + 1,
      }));
      get().notify(t("분석 엔진을 다시 시작함. 데이터나 프로젝트를 다시 열어야 함"));
    },

    checkUpdate: async (manual) => {
      try {
        const update = await findUpdate();
        set({ update });
        if (!update && manual) get().notify(t("최신 버전을 쓰고 있음"));
      } catch (err) {
        // 자동 확인은 조용히 넘어감 (오프라인 등). 직접 확인할 때만 알림
        if (manual) get().notify(t("업데이트를 확인하지 못함: {msg}", { msg: String((err as Error)?.message ?? err) }));
      }
    },

    installUpdate: async () => {
      const update = get().update;
      if (!update) return;
      set({ busy: t("업데이트 받는 중…") });
      try {
        await update.install((f) =>
          set({ busy: f === null ? t("업데이트 받는 중…") : t("업데이트 받는 중… {p}%", { p: Math.round(f * 100) }) }),
        );
      } catch (err) {
        set({ busy: null, error: toEngineError(err) });
      }
    },

    dismissUpdate: () => set({ update: null }),

    setLanguage: (lang) => {
      applyLang(lang);
      set({ lang });
    },

    querySelect: async (id, expression, mode) => {
      const ids = await run(t("조건으로 찾는 중…"), () => engine.query(id, expression));
      if (!ids) return false;
      get().select(id, ids, mode);
      get().notify(t("조건에 맞는 피처 {n}개를 선택함", { n: ids.length }));
      return true;
    },

    openSample: async (sampleId) => {
      const r = await run(t("샘플 데이터 준비 중…"), () => engine.copySample(sampleId));
      if (r) await get().openFile(r.path);
    },

    // ---- 래스터 ----------------------------------------------------------------

    openRaster: async (path) => {
      const info = await run(t("래스터 여는 중…"), () => engine.openRaster(path));
      if (!info) return;
      set((s) => ({
        rasters: { ...s.rasters, [info.id]: { info, visible: true, style: defaultRasterStyle(info) } },
        rasterOrder: [info.id, ...s.rasterOrder],
      }));
      requestFit(info.bounds_wgs84);
      if (info.needs_overviews) {
        get().notify(
          t(
            "{name}: {w}×{h} 크기에 오버뷰가 없어 축소 표시가 느림. 래스터 패널에서 '오버뷰 만들기'를 권함",
            { name: info.name, w: info.width, h: info.height },
          ),
        );
      }
    },

    closeRaster: async (id) => {
      await run(t("래스터 닫는 중…"), () => engine.closeRaster(id));
      set((s) => {
        const { [id]: _removed, ...rest } = s.rasters;
        return { rasters: rest, rasterOrder: s.rasterOrder.filter((x) => x !== id) };
      });
    },

    toggleRasterVisible: (id) =>
      set((s) => {
        const r = s.rasters[id];
        return r ? { rasters: { ...s.rasters, [id]: { ...r, visible: !r.visible } } } : {};
      }),

    setRasterStyle: (id, style) =>
      set((s) => {
        const r = s.rasters[id];
        return r ? { rasters: { ...s.rasters, [id]: { ...r, style: { ...r.style, ...style } } } } : {};
      }),

    buildOverviews: async (id) => {
      const info = await run(t("오버뷰 만드는 중… (크기에 따라 수십 초 걸릴 수 있음)"), () =>
        engine.buildOverviews(id),
      );
      if (!info) return;
      set((s) => {
        const r = s.rasters[id];
        return r ? { rasters: { ...s.rasters, [id]: { ...r, info } } } : {};
      });
      get().notify(
        t("{name}: 오버뷰 {n}단계를 만듦 (원본 옆 .ovr 파일)", { name: info.name, n: info.overviews.length }),
      );
    },

    zoomToRaster: (id) => requestFit(get().rasters[id]?.info.bounds_wgs84 ?? null),

    startZonal: (id, spec) => get().runJob(id, () => engine.startZonal(id, spec)),

    makeFishnet: async (spec) => {
      const info = await run(t("격자 만드는 중…"), () => engine.fishnet(spec));
      if (!info) return null;
      await run(t("지오메트리 불러오는 중… ({n}개)", { n: info.n_rows }), () => addLoaded(info));
      requestFit(info.bounds_wgs84);
      get().notify(t("격자 {n}개를 만듦: {path}", { n: info.n_rows, path: info.path }));
      return info.id;
    },

    // ---- 파일·데이터셋 -------------------------------------------------------

    openFile: async (path) => {
      const inspection = await run(t("파일 확인 중…"), () => engine.inspect(path));
      if (!inspection) return;
      if (inspection.kind === "raster") {
        await get().openRaster(path);
      } else if (inspection.kind === "table") {
        set({ dialog: { kind: "table", path, inspection } });
      } else if (inspection.layers.length > 1) {
        set({ dialog: { kind: "layers", path, layers: inspection.layers } });
      } else {
        await get().openDataset(path);
      }
    },

    openDataset: async (path, opts = {}) => {
      await run(t("파일을 여는 중…"), async () => {
        const info = await engine.openDataset(path, opts);
        set({ busy: t("지오메트리 불러오는 중… ({n}개)", { n: info.n_rows }) });
        const loaded = await addLoaded(info);
        if (loaded.table) requestFit(info.bounds_wgs84);
        if (info.n_rows > LARGE_FEATURES) {
          get().notify(
            t("피처가 {n}개라 지도 이동·선택이 느릴 수 있음 (권장 {max}개 이하)", {
              n: info.n_rows,
              max: LARGE_FEATURES,
            }),
          );
        }
      });
    },

    closeDataset: async (id) => {
      await engine.closeDataset(id).catch(() => undefined); // 엔진에 없어도 화면에서는 닫음
      set((s) => {
        const { [id]: _removed, ...rest } = s.datasets;
        const order = s.order.filter((x) => x !== id);
        return {
          datasets: rest,
          order,
          activeId: s.activeId === id ? (order[0] ?? null) : s.activeId,
          charts: s.charts.filter((c) => c.datasetId !== id),
          reports: s.reports.filter((r) => r.datasetId !== id),
        };
      });
    },

    setActive: (id) => set({ activeId: id }),

    toggleVisible: (id) => {
      const ds = get().datasets[id];
      if (ds) patch(id, { visible: !ds.visible });
    },

    moveLayer: (id, delta) =>
      set((s) => {
        const order = [...s.order];
        const i = order.indexOf(id);
        const j = i + delta;
        if (i < 0 || j < 0 || j >= order.length) return {};
        [order[i], order[j]] = [order[j], order[i]];
        return { order };
      }),

    zoomTo: (id) => requestFit(get().datasets[id]?.info.bounds_wgs84 ?? null),

    assignCrs: async (id, epsg) => {
      await run(t("좌표계 지정 중…"), async () => {
        const info = await engine.assignCrs(id, epsg);
        const geo = await loadGeometry(info);
        patch(id, { info, ...geo });
        set({ dialog: null });
        if (geo.table) requestFit(info.bounds_wgs84);
      });
    },

    updateInfo: async (info) => {
      const ds = get().datasets[info.id];
      if (!ds) return;
      patch(info.id, { info, revision: ds.revision + 1 });
      // 주제도에 쓰던 계산 필드가 바뀌었으면 다시 분류함
      if (ds.style && info.columns.some((c) => c.name === ds.style!.column)) {
        await get().applyStyle(info.id, ds.style);
      } else if (ds.style) {
        patch(info.id, { style: null, theme: null });
      }
    },

    // ---- 주제도 --------------------------------------------------------------

    applyStyle: async (id, style) => {
      if (!style) {
        patch(id, { style: null, theme: null });
        return;
      }
      await run(t("단계 구분 중…"), async () => {
        const theme = await engine.classify(id, style.column, style.method, style.k, style.mask);
        patch(id, { style, theme });
      });
    },

    // ---- 공간가중치·분석 ---------------------------------------------------------

    refreshWeights: async (id, activeId) => {
      const list = await engine.weights(id);
      const ds = get().datasets[id];
      if (!ds) return;
      const keep = activeId ?? ds.activeWeightsId;
      patch(id, {
        weights: list,
        activeWeightsId: list.some((w) => w.id === keep) ? keep! : (list[list.length - 1]?.id ?? null),
      });
    },

    setActiveWeights: (id, weightsId) => patch(id, { activeWeightsId: weightsId }),

    removeWeights: async (id, weightsId) => {
      await run(t("가중치 삭제 중…"), async () => {
        await engine.deleteWeights(id, weightsId);
        await get().refreshWeights(id);
      });
    },

    selectNeighbors: async (id) => {
      const ds = get().datasets[id];
      if (!ds?.activeWeightsId || ds.selectedCount === 0) return;
      const ids = await run(t("이웃 찾는 중…"), () =>
        engine.neighbors(id, ds.activeWeightsId!, maskToIds(ds.selection)),
      );
      if (ids) {
        get().select(id, ids, "add");
        get().notify(t("이웃 {n}개를 선택에 추가함", { n: ids.length }));
      }
    },

    runLocal: async (id, params) => {
      const label = { lisa: "LISA", lisa_bv: t("이변량 LISA"), gi_star: "Gi*", local_geary: "Local Geary" }[
        params.method
      ];
      const result = await run(t("{label} 계산 중… (순열 {n}회)", { label, n: params.permutations }), () =>
        engine.local(id, params),
      );
      if (!result) return false;
      await get().updateInfo(result.info);
      await get().applyStyle(id, { column: result.outputs[1], method: result.cluster_method, k: 5 });
      const sig = Object.entries(result.counts)
        .filter(([code]) => code !== "0" && code !== "5")
        .reduce((a, [, n]) => a + n, 0);
      get().notify(
        t("{desc}: 유의한 피처 {n}개 (p ≤ {p})", {
          desc: result.description,
          n: sig,
          p: result.threshold.toPrecision(3),
        }) + (result.n_islands ? t(", 이웃 없는 피처 {n}개", { n: result.n_islands }) : ""),
      );
      return true;
    },

    // ---- 회귀·작업 ---------------------------------------------------------------

    job: null,
    reports: [],

    startRegression: (id, spec) => get().runJob(id, () => engine.startRegression(id, spec)),
    startCluster: (id, spec) => get().runJob(id, () => engine.startCluster(id, spec)),

    runJob: async (id, start) => {
      let job: JobInfo;
      try {
        job = await start();
      } catch (err) {
        set({ error: toEngineError(err) });
        return false;
      }
      set({ job, error: null });
      // 작업이 끝날 때까지 진행률을 주기적으로 받음
      while (job.status === "running") {
        await new Promise((r) => setTimeout(r, 300));
        try {
          job = await engine.job(job.id);
        } catch (err) {
          set({ job: null, error: toEngineError(err) });
          return false;
        }
        if (get().job?.id !== job.id) return false; // 다른 작업으로 바뀜
        set({ job });
      }
      set({ job: null });
      if (job.status === "cancelled") {
        get().notify(t("{title} — 취소함", { title: t(job.title) }));
        return false;
      }
      if (job.status === "failed" || !job.result) {
        set({ error: new EngineError(job.error?.code ?? "job_failed", job.error?.message ?? t("작업 실패")) });
        return false;
      }
      const { info, analysis } = job.result;
      await get().updateInfo(info);
      if (analysis.report) {
        set((s) => ({
          reports: [...s.reports.filter((r) => r.analysis.id !== analysis.id), { datasetId: id, analysis }],
        }));
      }
      await get().showResultMap(id, analysis);
      get().notify(t("{desc} 완료 ({s}초)", { desc: analysis.description, s: job.elapsed.toFixed(1) }));
      return true;
    },

    cancelJob: async () => {
      const job = get().job;
      if (!job) return;
      try {
        await engine.cancelJob(job.id);
      } catch (err) {
        set({ error: toEngineError(err) });
      }
    },

    loadReports: async (id) => {
      const analyses = await engine.analyses(id);
      const mine = analyses.filter((a) => a.report).map((analysis) => ({ datasetId: id, analysis }));
      set((s) => ({ reports: [...s.reports.filter((r) => r.datasetId !== id), ...mine] }));
    },

    dismissReport: (analysisId) =>
      set((s) => ({ reports: s.reports.filter((r) => r.analysis.id !== analysisId) })),

    showResultMap: async (id, analysis, variable) => {
      const outs = analysis.outputs;
      const report = analysis.report;
      if (analysis.method === "zonal") {
        await get().applyStyle(id, { column: outs[0], method: "quantile", k: 5 });
        return;
      }
      if (!report) return;
      if (isClusterReport(report)) {
        await get().applyStyle(id, { column: outs[0], method: "unique_values", k: 5 });
        return;
      }
      if (report.model === "gwr" || report.model === "mgwr") {
        // 계수 지도: 지정한 변수(없으면 첫 독립변수)의 지역 계수, 유의하지 않은 곳은 가림
        const coefCols = outs.filter((c) => c.includes("_B_"));
        const col =
          (variable && coefCols.find((c) => c.endsWith(`_B_${variable}`))) ||
          coefCols.find((c) => !c.endsWith("_B_CONST")) ||
          coefCols[0];
        if (!col) return;
        await get().applyStyle(id, {
          column: col,
          // 계수는 부호가 중요하므로 0을 경계로 음수=파랑, 양수=빨강으로 칠함
          method: "zero_centered",
          k: 6,
          mask: col.replace("_B_", "_SIG_"),
        });
      } else {
        const resid = outs.find((c) => c.endsWith("_RESID"));
        if (resid) await get().applyStyle(id, { column: resid, method: "std_mean", k: 5 });
      }
    },

    // ---- 차트 ----------------------------------------------------------------

    charts: [],

    addChart: async (chart) => {
      let spec: ChartSpec = { ...chart, id: ++chartSeq };
      if (chart.kind === "moran") {
        const moran = await run(t("Moran's I 계산 중…"), () =>
          engine.moran(chart.datasetId, {
            column: chart.x,
            column_y: chart.y ?? null,
            weights_id: chart.weightsId!,
            permutations: chart.permutations ?? 999,
          }),
        );
        if (!moran) return;
        spec = { ...spec, moran };
      }
      set((s) => ({ charts: [...s.charts, spec] }));
    },

    removeChart: (chartId) => set((s) => ({ charts: s.charts.filter((c) => c.id !== chartId) })),

    // ---- 선택 ----------------------------------------------------------------

    select: (id, indices, mode) => {
      const ds = get().datasets[id];
      if (!ds) return;
      const next = mode === "replace" ? new Uint8Array(ds.selection.length) : ds.selection.slice();
      for (let k = 0; k < indices.length; k++) {
        const i = indices[k];
        next[i] = mode === "toggle" ? next[i] ^ 1 : 1;
      }
      patch(id, { selection: next, selectedCount: countOnes(next) });
    },

    selectClass: (id, klass, mode) => {
      const theme = get().datasets[id]?.theme;
      if (!theme) return;
      const hits: number[] = [];
      for (let i = 0; i < theme.classes.length; i++) if (theme.classes[i] === klass) hits.push(i);
      get().select(id, hits, mode === "toggle" ? "add" : mode);
    },

    clearSelection: (id) => get().select(id, [], "replace"),

    invertSelection: (id) => {
      const ds = get().datasets[id];
      if (!ds) return;
      const next = ds.selection.map((v) => v ^ 1);
      patch(id, { selection: next, selectedCount: countOnes(next) });
    },

    // ---- 프로젝트 -----------------------------------------------------------

    saveProject: async (path) => {
      const s = get();
      const ui: ProjectUi = {
        basemap: s.basemap,
        view: s.view,
        activeIndex: Math.max(0, s.order.indexOf(s.activeId ?? "")),
      };
      const datasets = s.order.map((id) => {
        const ds = s.datasets[id];
        const charts: SavedChart[] = s.charts
          .filter((c) => c.datasetId === id)
          .map(({ id: _i, datasetId: _d, moran: _m, ...rest }) => rest);
        const dsUi: DatasetUi = {
          visible: ds.visible,
          style: ds.style,
          activeWeightsId: ds.activeWeightsId,
          charts,
        };
        return { id, ui: dsUi };
      });
      const rasters = s.rasterOrder.map((id) => {
        const r = s.rasters[id];
        const rUi: RasterUi = { visible: r.visible, style: r.style };
        return { id, ui: rUi };
      });
      const result = await run(t("프로젝트 저장 중…"), () => engine.saveProject(path, datasets, ui, rasters));
      if (result) {
        set({ projectPath: result.path });
        get().notify(t("프로젝트를 저장함: {path}", { path: result.path }));
      }
    },

    openProject: async (path) => {
      await run(t("프로젝트 여는 중…"), async () => {
        const project = await engine.openProject<ProjectUi | null, DatasetUi | null, RasterUi | null>(path);
        set({
          datasets: {},
          order: [],
          activeId: null,
          rasters: {},
          rasterOrder: [],
          charts: [],
          reports: [],
          projectPath: project.path,
        });
        const rasters: Record<string, LoadedRaster> = {};
        const rasterOrder: string[] = [];
        for (const item of project.rasters ?? []) {
          if (!item.info) {
            get().notify(t("열지 못한 래스터: {error}", { error: String(item.error) }));
            continue;
          }
          // 밴드 수가 바뀌었으면 저장된 표시 설정 대신 기본값을 씀
          const saved = item.ui?.style;
          const valid = saved && saved.bands.every((b) => b >= 1 && b <= item.info!.count);
          rasters[item.info.id] = {
            info: item.info,
            visible: item.ui?.visible ?? true,
            style: valid ? saved : defaultRasterStyle(item.info),
          };
          rasterOrder.push(item.info.id);
        }
        set({ rasters, rasterOrder });
        // 목록 앞쪽이 위에 그려지므로 뒤에서부터 추가함
        const opened: string[] = [];
        for (const item of [...project.datasets].reverse()) {
          if (!item.info) {
            get().notify(t("열지 못한 데이터: {error}", { error: String(item.error) }));
            continue;
          }
          const dsUi = item.ui ?? { visible: true, style: null };
          await addLoaded(item.info, { visible: dsUi.visible });
          await get().refreshWeights(item.info.id, dsUi.activeWeightsId ?? null);
          await get().loadReports(item.info.id);
          if (dsUi.style) await get().applyStyle(item.info.id, dsUi.style);
          for (const c of dsUi.charts ?? []) await get().addChart({ ...c, datasetId: item.info.id });
          item.warnings.forEach((w) => get().notify(`${item.info!.name}: ${w}`));
          opened.unshift(item.info.id);
        }
        const ui = project.ui;
        if (ui) {
          set({ basemap: ui.basemap ?? "none", view: ui.view, activeId: opened[ui.activeIndex] ?? opened[0] ?? null });
        }
      });
    },

    // ---- 화면 ----------------------------------------------------------------

    setTool: (tool) => set({ tool }),
    setBasemap: (basemap) => set({ basemap }),
    setView: (view) => set({ view }),
    showDialog: (dialog) => set({ dialog }),
    notify: (text) => {
      const id = ++noticeSeq;
      set((s) => ({ notices: [...s.notices, { id, text }] }));
      setTimeout(() => get().dismissNotice(id), 6000);
    },
    dismissNotice: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),
    fail: (err) => set({ error: toEngineError(err) }),
    dismissError: () => set({ error: null }),
  };
});

/** 현재 활성 데이터셋 */
export const useActive = () => useApp((s) => (s.activeId ? s.datasets[s.activeId] : undefined));
