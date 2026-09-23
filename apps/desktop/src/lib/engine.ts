// 분석 엔진(Python) HTTP 클라이언트
//
// Tauri 앱에서는 Rust 셸이 엔진을 띄우고 주소·토큰을 `engine_info` 명령으로 알려줌.
// 브라우저 개발 모드(npm run dev)에서는 VITE_ENGINE_URL / VITE_ENGINE_TOKEN 환경변수를 씀.

import { invoke, isTauri } from "@tauri-apps/api/core";
import { tableFromIPC, type Table } from "apache-arrow";

import { decodeInt16, encodeUint32 } from "./binary";

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
  kind: "vector" | "table";
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
  | "unique_values";

export type SchemeType = "sequential" | "diverging" | "qualitative";

export interface Classification {
  column: string;
  method: ClassifyMethod;
  scheme: SchemeType;
  breaks: number[];
  labels: string[];
  counts: number[];
  n_missing: number;
  /** 피처별 계급 번호 (-1 = 값 없음) */
  classes: Int16Array;
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

export interface OpenedProject<U = unknown, D = unknown> {
  path: string;
  ui: U;
  datasets: OpenedProjectDataset<D>[];
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
  ): Promise<Classification> => {
    const body = await post<Omit<Classification, "classes"> & { classes: string }>(
      `${ds(id)}/classify`,
      { column, method, k },
    );
    return { ...body, classes: decodeInt16(body.classes) };
  },

  addField: (id: string, name: string, expression: string) =>
    post<DatasetInfo>(`${ds(id)}/fields`, { name, expression }),

  deleteField: (id: string, name: string) =>
    json<DatasetInfo>(`${ds(id)}/fields/${encodeURIComponent(name)}`, { method: "DELETE" }),

  exportDataset: (id: string, path: string, opts: { epsg?: number | null; encoding?: string | null }) =>
    post<ExportResult>(`${ds(id)}/export`, { path, ...opts }),

  saveProject: (path: string, datasets: { id: string; ui: unknown }[], ui: unknown) =>
    post<{ path: string; n_datasets: number }>("/project/save", { path, datasets, ui }),

  openProject: <U, D>(path: string) => post<OpenedProject<U, D>>("/project/open", { path }),
};
