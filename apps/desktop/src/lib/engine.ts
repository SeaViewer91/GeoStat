// 분석 엔진(Python) HTTP 클라이언트
//
// Tauri 앱에서는 Rust 셸이 엔진을 띄우고 주소·토큰을 `engine_info` 명령으로 알려줌.
// 브라우저 개발 모드(npm run dev)에서는 VITE_ENGINE_URL / VITE_ENGINE_TOKEN 환경변수를 씀.

import { invoke, isTauri } from "@tauri-apps/api/core";
import { tableFromIPC, type Table } from "apache-arrow";

export interface EngineConnection {
  url: string;
  token: string;
}

export interface CrsInfo {
  epsg: number | null;
  name: string;
  is_geographic: boolean;
}

export interface ColumnInfo {
  name: string;
  dtype: string;
  kind: "numeric" | "string" | "boolean" | "datetime" | "other";
}

export type GeometryType = "point" | "line" | "polygon";

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
}

export interface HealthInfo {
  status: string;
  version: string;
  python: string;
  gdal: string;
  proj: string;
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

export const engine = {
  health: () => json<HealthInfo>("/health"),

  openDataset: (path: string, opts: { layer?: string; encoding?: string } = {}) =>
    json<DatasetInfo>("/datasets/open", {
      method: "POST",
      body: JSON.stringify({ path, ...opts }),
    }),

  assignCrs: (id: string, epsg: number) =>
    json<DatasetInfo>(`/datasets/${id}/crs`, { method: "PUT", body: JSON.stringify({ epsg }) }),

  /** WGS84 GeoArrow 지오메트리. 행 순서 = 피처 ID */
  geometry: async (id: string): Promise<Table> => {
    const res = await request(`/datasets/${id}/geometry`);
    return tableFromIPC(new Uint8Array(await res.arrayBuffer()));
  },

  rows: (id: string, offset = 0, limit = 200) =>
    json<{ offset: number; total: number; columns: string[]; rows: unknown[][] }>(
      `/datasets/${id}/rows?offset=${offset}&limit=${limit}`,
    ),
};
