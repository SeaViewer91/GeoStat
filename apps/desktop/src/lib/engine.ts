// 분석 엔진(Python) HTTP 클라이언트
//
// Tauri 앱에서는 Rust 셸이 엔진을 띄우고 주소·토큰을 `engine_info` 명령으로 알려줌.
// 브라우저 개발 모드(npm run dev)에서는 VITE_ENGINE_URL / VITE_ENGINE_TOKEN 환경변수를 씀.

import { invoke, isTauri } from "@tauri-apps/api/core";
import { tableFromIPC, type Table } from "apache-arrow";

import { decodeFloat64, decodeInt16, decodeUint32, encodeUint32 } from "./binary";

export interface EngineConnection {
  url: string;
  token: string;
}

export interface CrsInfo {
  epsg: number | null;
  name: string;
  is_geographic: boolean;
}

export type ColumnKind = "numeric" | "string" | "boolean" | "datetime" | "other";

export interface ColumnInfo {
  name: string;
  dtype: string;
  kind: ColumnKind;
  derived: boolean;
  expression: string | null;
  origin: "data" | "expression" | "analysis";
}

export type GeometryType = "point" | "line" | "polygon";

export interface TableOptions {
  x: string;
  y: string;
  epsg: number;
  sheet?: string | null;
}

export interface DatasetInfo {
  id: string;
  name: string;
  path: string;
  layer: string | null;
  layers: string[];
  encoding: string | null;
  n_rows: number;
  geometry_type: GeometryType;
  crs: CrsInfo | null;
  bounds_wgs84: [number, number, number, number] | null;
  columns: ColumnInfo[];
  table: TableOptions | null;
}

export interface HealthInfo {
  status: string;
  version: string;
  python: string;
  gdal: string;
  proj: string;
}

export interface TableInspection {
  encoding: string | null;
  sheets: string[];
  sheet: string | null;
  columns: { name: string; numeric: boolean }[];
  sample: unknown[][];
  n_rows: number;
  guess_x: string | null;
  guess_y: string | null;
  guess_epsg: number | null;
}

export interface FileInspection {
  path: string;
  kind: "vector" | "table" | "raster";
  layers: string[];
  table: TableInspection | null;
}

export type ClassifyMethod =
  | "quantile"
  | "equal_interval"
  | "natural_breaks"
  | "std_mean"
  | "percentile"
  | "box_plot"
  | "zero_centered"
  | "unique_values"
  | "lisa_cluster"
  | "gi_cluster"
  | "geary_cluster"
  | "significance";

export type SchemeType = "sequential" | "diverging" | "qualitative";

export interface Classification {
  column: string;
  method: ClassifyMethod;
  scheme: SchemeType;
  breaks: number[];
  labels: string[];
  counts: number[];
  n_missing: number;
  /** 고정 색 (군집·유의성 지도). 전체가 null이거나 항목이 null이면 색상표로 칠함 */
  colors: (string | null)[] | null;
  /** 피처별 계급 번호 (-1 = 값 없음) */
  classes: Int16Array;
}

export type WeightsType = "queen" | "rook" | "knn" | "distance" | "kernel";

export interface WeightsSpec {
  type: WeightsType;
  name?: string;
  order?: number;
  include_lower?: boolean;
  k?: number;
  threshold?: number | null;
  inverse?: boolean;
  power?: number;
  function?: "triangular" | "uniform" | "quadratic" | "quartic" | "gaussian";
  fixed?: boolean;
}

export interface WeightsSummary {
  n: number;
  min_neighbors: number;
  max_neighbors: number;
  mean_neighbors: number;
  median_neighbors: number;
  pct_nonzero: number;
  n_islands: number;
  islands: number[];
  histogram: { neighbors: number; count: number }[];
  symmetric: boolean;
}

export interface WeightsInfo {
  id: string;
  name: string;
  type: string;
  description: string;
  spec: Record<string, unknown>;
  summary: WeightsSummary;
}

export interface MoranResult {
  column: string;
  column_y: string | null;
  weights: string;
  I: number;
  expected: number;
  variance_norm: number | null;
  z_norm: number | null;
  p_norm: number | null;
  z_sim: number | null;
  p_sim: number | null;
  permutations: number;
  n: number;
  sim_hist: { counts: number[]; edges: number[] } | null;
  z: Float64Array;
  lag: Float64Array;
}

export type LocalMethod = "lisa" | "lisa_bv" | "gi_star" | "local_geary";

export interface LocalParams {
  method: LocalMethod;
  column: string;
  column_y?: string | null;
  weights_id: string;
  permutations: number;
  seed?: number | null;
  alpha: number;
  correction: "none" | "fdr" | "bonferroni";
  prefix?: string | null;
}

export interface LocalResult {
  info: DatasetInfo;
  analysis_id: string;
  outputs: [string, string, string];
  cluster_method: ClassifyMethod;
  description: string;
  threshold: number;
  counts: Record<string, number>;
  n_islands: number;
}

export type RegressionModel = "ols" | "lag" | "error" | "lag_gm" | "error_gm" | "gwr" | "mgwr";

export interface RegressionSpec {
  model: RegressionModel;
  y: string;
  x: string[];
  weights_id?: string | null;
  kernel?: "bisquare" | "gaussian" | "exponential";
  fixed?: boolean;
  criterion?: "AICc" | "AIC" | "BIC" | "CV";
  bandwidth?: number | null;
  alpha?: number;
  robust?: "white" | null;
  prefix?: string | null;
}

export interface CoefRow {
  name: string;
  coef: number | null;
  se: number | null;
  stat: number | null;
  p: number | null;
}

export interface LocalCoefRow {
  name: string;
  bandwidth: number;
  mean: number | null;
  sd: number | null;
  min: number | null;
  q1: number | null;
  median: number | null;
  q3: number | null;
  max: number | null;
  pct_significant: number | null;
}

export interface DiagRow {
  group: string;
  name: string;
  value: number | null;
  p: number | null;
  df: number | null;
}

/** 공간시차 모형의 직접·간접·총 효과 */
export interface ImpactRow {
  name: string;
  direct: number | null;
  indirect: number | null;
  total: number | null;
}

/** 모형 비교표용 공통 적합도. GM 추정은 로그우도·AICc가 없음 */
export interface FitMetrics {
  r2: number | null;
  r2_label: string;
  loglik: number | null;
  aicc: number | null;
  n_params: number | null;
  moran_i: number | null;
  moran_z: number | null;
  moran_p: number | null;
}

export interface RegressionReport {
  model: RegressionModel;
  title: string;
  y: string;
  x: string[];
  n: number;
  summary: [string, number | string | null][];
  coefficients: CoefRow[];
  stat_label: "t" | "z";
  diagnostics: DiagRow[];
  local: LocalCoefRow[] | null;
  impacts: { method: string; rows: ImpactRow[] } | null;
  fit: FitMetrics | null;
  notes: string[];
}

export type ClusterMethod =
  | "skater"
  | "maxp"
  | "azp"
  | "region_kmeans"
  | "ward_spatial"
  | "kmeans"
  | "hierarchical";

export interface ClusterSpec {
  method: ClusterMethod;
  variables: string[];
  n_clusters?: number;
  weights_id?: string | null;
  standardize?: boolean;
  floor?: number | null;
  threshold_column?: string | null;
  threshold?: number | null;
  prefix?: string | null;
}

export interface ClusterRow {
  id: number;
  size: number;
  within_ss: number | null;
  /** 변수 순서대로 원래 값 평균 */
  means: (number | null)[];
  /** 변수별 표준화(z) 평균. 군집 프로필 색칠용 */
  z_means: (number | null)[];
  /** 공간적으로 이어진 조각 수 (가중치가 없으면 null) */
  fragments: number | null;
}

export interface ClusterReport {
  kind: "cluster";
  method: ClusterMethod;
  title: string;
  variables: string[];
  n: number;
  k: number;
  summary: [string, number | string | null][];
  clusters: ClusterRow[];
  ratio: number | null;
  notes: string[];
}

export interface AnalysisInfo {
  id: string;
  method: string;
  description: string;
  outputs: string[];
  params: Record<string, unknown>;
  report: RegressionReport | ClusterReport | null;
}

export function isClusterReport(r: AnalysisInfo["report"]): r is ClusterReport {
  return !!r && (r as ClusterReport).kind === "cluster";
}

export function isRegressionReport(r: AnalysisInfo["report"]): r is RegressionReport {
  return !!r && (r as ClusterReport).kind !== "cluster";
}

export interface JobInfo {
  id: string;
  kind: string;
  title: string;
  dataset_id: string;
  status: "running" | "done" | "failed" | "cancelled";
  progress: number | null;
  message: string;
  elapsed: number;
  result: { info: DatasetInfo; analysis: AnalysisInfo } | null;
  error: { code: string; message: string } | null;
}

export interface JoinCountResult {
  bb: number;
  bw: number;
  ww: number;
  joins: number;
  p_sim_bb?: number;
  p_sim_bw?: number;
  mean_bb?: number;
  mean_bw?: number;
}

export interface RowsPage {
  offset: number;
  total: number;
  columns: string[];
  row_ids: number[];
  rows: unknown[][];
}

export interface RowsQuery {
  offset?: number;
  limit?: number;
  sort?: string | null;
  descending?: boolean;
  /** 이 행 번호들만 조회 (선택 항목만 보기) */
  ids?: Uint32Array | null;
}

export interface ExportResult {
  path: string;
  format: string;
  n_rows: number;
  warnings: string[];
}

export interface OpenedProjectDataset<U = unknown> {
  info: DatasetInfo | null;
  ui: U;
  error: string | null;
  warnings: string[];
}

export interface OpenedProject<U = unknown, D = unknown, R = unknown> {
  path: string;
  ui: U;
  datasets: OpenedProjectDataset<D>[];
  rasters: { info: RasterInfo | null; ui: R; error: string | null }[];
}

// ---- 래스터 ----

export interface BandStats {
  min: number | null;
  max: number | null;
  p2: number | null;
  p98: number | null;
  mean: number | null;
  std: number | null;
}

export interface RasterInfo {
  id: string;
  name: string;
  path: string;
  width: number;
  height: number;
  count: number;
  dtype: string;
  crs: string;
  crs_name: string;
  res: [number, number];
  nodata: number | null;
  bounds: [number, number, number, number];
  bounds_wgs84: [number, number, number, number];
  overviews: number[];
  needs_overviews: boolean;
  band_names: string[];
  stats: BandStats[];
  categorical: boolean;
}

export type RasterColormap = "viridis" | "magma" | "terrain" | "gray" | "rdylgn" | "spectral" | "blues" | "rdbu_r";

/** 래스터 표시 설정. bands가 3개면 RGB 합성, 1개면 색상표를 씀 */
export interface RasterStyle {
  bands: number[];
  vmin: number[];
  vmax: number[];
  colormap: RasterColormap;
  opacity: number;
  resampling: "bilinear" | "nearest";
}

export type ZonalStat =
  | "mean"
  | "sum"
  | "min"
  | "max"
  | "stdev"
  | "median"
  | "q25"
  | "q75"
  | "count"
  | "majority"
  | "variety";

export interface ZonalSpec {
  raster_id: string;
  band: number;
  stats: ZonalStat[];
  prefix?: string | null;
}

export interface FishnetSpec {
  dataset_id?: string | null;
  raster_id?: string | null;
  cell_size: number;
  shape: "square" | "hexagon";
  clip: boolean;
  path: string;
  name?: string | null;
}

/** 엔진이 돌려준 오류. code로 UI 분기(예: crs_missing → 좌표계 지정 창)를 함 */
export class EngineError extends Error {
  constructor(
    public code: string,
    message: string,
    public status?: number,
  ) {
    super(message);
    this.name = "EngineError";
  }
}

let connection: Promise<EngineConnection> | null = null;

/** 엔진 연결 정보를 얻음. 엔진이 준비될 때까지 기다리며 결과는 캐시함 */
export function getEngine(): Promise<EngineConnection> {
  if (!connection) {
    connection = resolveConnection().catch((err) => {
      connection = null; // 실패하면 다음 호출에서 다시 시도함
      throw err;
    });
  }
  return connection;
}

async function resolveConnection(): Promise<EngineConnection> {
  if (isTauri()) {
    try {
      return await invoke<EngineConnection>("engine_info");
    } catch (err) {
      throw new EngineError("engine_unavailable", `분석 엔진을 시작하지 못함: ${String(err)}`);
    }
  }
  const url = import.meta.env.VITE_ENGINE_URL;
  const token = import.meta.env.VITE_ENGINE_TOKEN;
  if (!url || !token) {
    throw new EngineError(
      "engine_unconfigured",
      "브라우저 모드에서는 VITE_ENGINE_URL, VITE_ENGINE_TOKEN 환경변수가 필요함",
    );
  }
  return { url: url.replace(/\/$/, ""), token };
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const { url, token } = await getEngine();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(`${url}${path}`, { ...init, headers });
  } catch (err) {
    throw new EngineError("engine_unreachable", `엔진에 연결할 수 없음: ${String(err)}`);
  }
  if (!res.ok) throw await toEngineError(res);
  return res;
}

async function toEngineError(res: Response): Promise<EngineError> {
  try {
    const body = await res.json();
    if (body?.error) return new EngineError(body.error.code, body.error.message, res.status);
    if (body?.detail) {
      const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      return new EngineError(`http_${res.status}`, detail, res.status);
    }
  } catch {
    // JSON이 아닌 응답은 아래 기본 메시지로 처리함
  }
  return new EngineError(`http_${res.status}`, `엔진 요청 실패 (HTTP ${res.status})`, res.status);
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

function post<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  return json<T>(path, { method, body: JSON.stringify(body) });
}

const ds = (id: string) => `/datasets/${encodeURIComponent(id)}`;

export const engine = {
  health: () => json<HealthInfo>("/health"),

  inspect: (path: string, opts: { encoding?: string; sheet?: string } = {}) =>
    post<FileInspection>("/files/inspect", { path, ...opts }),

  openDataset: (
    path: string,
    opts: { layer?: string | null; encoding?: string | null; table?: TableOptions | null } = {},
  ) => post<DatasetInfo>("/datasets/open", { path, ...opts }),

  closeDataset: (id: string) => request(ds(id), { method: "DELETE" }),

  assignCrs: (id: string, epsg: number) => post<DatasetInfo>(`${ds(id)}/crs`, { epsg }, "PUT"),

  /** WGS84 GeoArrow 지오메트리 + 중심점(cx, cy). 행 순서 = 피처 ID */
  geometry: async (id: string): Promise<Table> => {
    const res = await request(`${ds(id)}/geometry`);
    return tableFromIPC(new Uint8Array(await res.arrayBuffer()));
  },

  rows: (id: string, q: RowsQuery = {}) =>
    post<RowsPage>(`${ds(id)}/rows`, {
      offset: q.offset ?? 0,
      limit: q.limit ?? 200,
      sort: q.sort ?? null,
      descending: q.descending ?? false,
      ids: q.ids ? encodeUint32(q.ids) : null,
    }),

  classify: async (
    id: string,
    column: string,
    method: ClassifyMethod,
    k: number,
    mask?: string | null,
  ): Promise<Classification> => {
    const body = await post<Omit<Classification, "classes"> & { classes: string }>(
      `${ds(id)}/classify`,
      { column, method, k, mask: mask ?? null },
    );
    return { ...body, classes: decodeInt16(body.classes) };
  },

  addField: (id: string, name: string, expression: string) =>
    post<DatasetInfo>(`${ds(id)}/fields`, { name, expression }),

  deleteField: (id: string, name: string) =>
    json<DatasetInfo>(`${ds(id)}/fields/${encodeURIComponent(name)}`, { method: "DELETE" }),

  exportDataset: (id: string, path: string, opts: { epsg?: number | null; encoding?: string | null }) =>
    post<ExportResult>(`${ds(id)}/export`, { path, ...opts }),

  saveProject: (
    path: string,
    datasets: { id: string; ui: unknown }[],
    ui: unknown,
    rasters: { id: string; ui: unknown }[] = [],
  ) => post<{ path: string; n_datasets: number }>("/project/save", { path, datasets, ui, rasters }),

  openProject: <U, D, R>(path: string) => post<OpenedProject<U, D, R>>("/project/open", { path }),

  // ---- 래스터 ----
  openRaster: (path: string, name?: string) => post<RasterInfo>("/rasters/open", { path, name }),
  closeRaster: (id: string) => request(`/rasters/${encodeURIComponent(id)}`, { method: "DELETE" }),
  buildOverviews: (id: string) => post<RasterInfo>(`/rasters/${encodeURIComponent(id)}/overviews`, {}),
  /** 타일 하나를 이미지로 받음. 래스터 밖이면 null */
  rasterTile: async (
    id: string,
    tile: { x: number; y: number; z: number },
    style: RasterStyle,
    signal?: AbortSignal,
  ): Promise<ImageBitmap | null> => {
    const q = new URLSearchParams({
      bands: style.bands.join(","),
      vmin: style.vmin.join(","),
      vmax: style.vmax.join(","),
      colormap: style.colormap,
      resampling: style.resampling,
    });
    const res = await request(`/rasters/${encodeURIComponent(id)}/tiles/${tile.z}/${tile.x}/${tile.y}.png?${q}`, {
      signal,
    });
    if (res.status === 204) return null;
    return createImageBitmap(await res.blob());
  },
  startZonal: (id: string, spec: ZonalSpec) => post<JobInfo>(`${ds(id)}/zonal`, spec),
  fishnet: (spec: FishnetSpec) => post<DatasetInfo>("/grid/fishnet", spec),

  // ---- 공간가중치 ----
  weights: (id: string) => json<WeightsInfo[]>(`${ds(id)}/weights`),
  createWeights: (id: string, spec: WeightsSpec) => post<WeightsInfo>(`${ds(id)}/weights`, spec),
  loadWeights: (id: string, path: string, name?: string) =>
    post<WeightsInfo>(`${ds(id)}/weights/load`, { path, name }),
  saveWeights: (id: string, wid: string, path: string) =>
    post<{ path: string }>(`${ds(id)}/weights/${wid}/save`, { path }),
  deleteWeights: (id: string, wid: string) => request(`${ds(id)}/weights/${wid}`, { method: "DELETE" }),
  weightsThreshold: (id: string) => json<{ threshold: number; note: string }>(`${ds(id)}/weights-threshold`),
  neighbors: async (id: string, wid: string, ids: Uint32Array): Promise<Uint32Array> => {
    const r = await post<{ ids: string; count: number }>(`${ds(id)}/weights/${wid}/neighbors`, {
      ids: encodeUint32(ids),
    });
    return decodeUint32(r.ids);
  },

  // ---- ESDA ----
  moran: async (
    id: string,
    p: { column: string; column_y?: string | null; weights_id: string; permutations: number },
  ): Promise<MoranResult> => {
    const r = await post<Omit<MoranResult, "z" | "lag"> & { z: string; lag: string }>(
      `${ds(id)}/esda/moran`,
      p,
    );
    return { ...r, z: decodeFloat64(r.z), lag: decodeFloat64(r.lag) };
  },
  joinCount: (id: string, p: { column: string; weights_id: string; permutations: number }) =>
    post<JoinCountResult>(`${ds(id)}/esda/joincount`, p),
  local: (id: string, p: LocalParams) => post<LocalResult>(`${ds(id)}/esda/local`, p),

  // ---- 회귀·작업 ----
  startRegression: (id: string, spec: RegressionSpec) => post<JobInfo>(`${ds(id)}/regression`, spec),
  startCluster: (id: string, spec: ClusterSpec) => post<JobInfo>(`${ds(id)}/cluster`, spec),
  job: (jobId: string) => json<JobInfo>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => json<JobInfo>(`/jobs/${jobId}`, { method: "DELETE" }),
  analyses: (id: string) => json<AnalysisInfo[]>(`${ds(id)}/analyses`),
  saveReport: (id: string, analysisId: string, path: string) =>
    post<{ path: string }>(`${ds(id)}/analyses/${analysisId}/report`, { path }),

  /** 숫자 열 값 (Float64, 값 없음은 NaN). 차트용 */
  columns: async (id: string, names: string[]): Promise<Record<string, Float64Array>> => {
    const res = await request(`${ds(id)}/columns`, { method: "POST", body: JSON.stringify({ names }) });
    const table = tableFromIPC(new Uint8Array(await res.arrayBuffer()));
    const out: Record<string, Float64Array> = {};
    for (const name of names) out[name] = table.getChild(name)!.toArray() as Float64Array;
    return out;
  },
};
