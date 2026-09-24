// 하단 상태 표시줄: 작업 상태, 활성 레이어 요약, 엔진 버전

import { useEffect, useState } from "react";

import { engine, type HealthInfo } from "../lib/engine";
import { useActive, useApp } from "../store";

export function StatusBar() {
  const ds = useActive();
  const busy = useApp((s) => s.busy);
  const projectPath = useApp((s) => s.projectPath);
  const job = useApp((s) => s.job);
  const cancelJob = useApp((s) => s.cancelJob);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);

  useEffect(() => {
    engine
      .health()
      .then(setHealth)
      .catch((err) => setEngineError(String(err?.message ?? err)));
  }, []);

  return (
    <footer className="statusbar">
      {busy ? (
        <span className="busy">{busy}</span>
      ) : ds ? (
        <>
          <span>{ds.info.name}</span>
          <span data-testid="feature-count">피처 {ds.info.n_rows.toLocaleString()}개</span>
          <span data-testid="selected-count">선택 {ds.selectedCount.toLocaleString()}개</span>
        </>
      ) : (
        <span>데이터를 열어 시작함 (⌘O)</span>
      )}
      <div className="spacer" />
      {job && (
        <span className="job" data-testid="job-status">
          <span className="job-title">{job.title}</span>
          <span className="progress" aria-label="진행률">
            <span
              className={job.progress === null ? "bar indeterminate" : "bar"}
              style={job.progress === null ? undefined : { width: `${Math.round(job.progress * 100)}%` }}
            />
          </span>
          <span className="muted">
            {job.message} · {Math.round(job.elapsed)}초
          </span>
          <button className="link" onClick={cancelJob}>
            취소
          </button>
        </span>
      )}
      {projectPath && <span className="muted" title={projectPath}>{projectPath.split(/[\\/]/).pop()}</span>}
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
