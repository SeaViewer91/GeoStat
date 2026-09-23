// 파일 선택·저장 대화상자
//
// Tauri 앱에서는 macOS 기본 대화상자를 쓰고, 브라우저 개발 모드에서는 경로를 직접 입력받음.

import { isTauri } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";

export const DATA_FILTER = {
  name: "공간 데이터",
  extensions: ["shp", "gpkg", "geojson", "json", "fgb", "kml", "gml", "csv", "tsv", "txt", "xlsx", "xls"],
};
export const PROJECT_FILTER = { name: "GeoStat 프로젝트", extensions: ["gstproj"] };
export const EXPORT_FILTERS = [
  { name: "GeoPackage", extensions: ["gpkg"] },
  { name: "Shapefile", extensions: ["shp"] },
  { name: "GeoJSON", extensions: ["geojson"] },
  { name: "FlatGeobuf", extensions: ["fgb"] },
  { name: "CSV (속성만)", extensions: ["csv"] },
];

type Filter = { name: string; extensions: string[] };

export async function pickOpenPath(filters: Filter[], title: string): Promise<string | null> {
  if (!isTauri()) return promptPath(`${title} — 파일 절대 경로`);
  const picked = await open({ title, multiple: false, directory: false, filters });
  return typeof picked === "string" ? picked : null;
}

export async function pickSavePath(
  filters: Filter[],
  title: string,
  defaultPath?: string,
): Promise<string | null> {
  if (!isTauri()) return promptPath(`${title} — 저장할 절대 경로`, defaultPath);
  return (await save({ title, filters, defaultPath })) ?? null;
}

function promptPath(message: string, defaultValue?: string): string | null {
  const value = window.prompt(message, defaultValue ?? "");
  return value?.trim() ? value.trim() : null;
}

/** 경로에서 폴더 부분만 (저장 대화상자 기본 위치용) */
export function dirname(path: string): string {
  const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return i > 0 ? path.slice(0, i) : path;
}
