// 하단 상태 표시줄: 피처 수, 선택 수, 좌표계, 인코딩, 엔진 버전

import { useEffect, useState } from "react";

import { engine, type HealthInfo } from "../lib/engine";
import { useApp } from "../store";

export function StatusBar() {
  const ds = useApp((s) => (s.activeId ? s.datasets[s.activeId] : undefined));
  const busy = useApp((s) => s.busy);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);

  useEffect(() => {
    engine
      .health()
      .then(setHealth)
      .catch((err) => setEngineError(String(err?.message ?? err)));
  }, []);

  const crs = ds?.info.crs;
  return (
    <footer className="statusbar">
      {busy ? (
        <span className="busy">{busy}</span>
      ) : ds ? (
        <>
          <span>{ds.info.name}</span>
          <span data-testid="feature-count">피처 {ds.info.n_rows.toLocaleString()}개</span>
          <span data-testid="selected-count">선택 {ds.selectedCount.toLocaleString()}개</span>
          <span>{crs ? `EPSG:${crs.epsg ?? "?"} ${crs.name}` : "좌표계 없음"}</span>
          {ds.info.encoding && <span>인코딩 {ds.info.encoding}</span>}
        </>
      ) : (
        <span>파일을 열어 시작함</span>
      )}
      <div className="spacer" />
      {health ? (
        <span className="engine ok" data-testid="engine-status">
          엔진 {health.version} · GDAL {health.gdal}
        </span>
      ) : (
        <span className="engine" data-testid="engine-status">
          {engineError ? `엔진 오류: ${engineError}` : "엔진 연결 중…"}
        </span>
      )}
    </footer>
  );
}
