// 하단 상태 표시줄: 작업 상태, 활성 레이어 요약, 엔진 버전

import { useEffect, useState } from "react";

import { t } from "../i18n";
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
  const engineGeneration = useApp((s) => s.engineGeneration);
  const engineDown = useApp((s) => s.engineDown);

  // 엔진을 다시 띄우면(세대 번호가 바뀌면) 버전 정보를 다시 받음
  useEffect(() => {
    setHealth(null);
    setEngineError(null);
    engine
      .health()
      .then(setHealth)
      .catch((err) => setEngineError(String(err?.message ?? err)));
  }, [engineGeneration]);

  return (
    <footer className="statusbar">
      {busy ? (
        <span className="busy">{busy}</span>
      ) : ds ? (
        <>
          <span>{ds.info.name}</span>
          <span data-testid="feature-count">{t("피처 {n}개", { n: ds.info.n_rows })}</span>
          <span data-testid="selected-count">{t("선택 {n}개", { n: ds.selectedCount })}</span>
        </>
      ) : (
        <span>{t("데이터를 열어 시작함 (⌘O)")}</span>
      )}
      <div className="spacer" />
      {job && (
        <span className="job" data-testid="job-status">
          <span className="job-title">{job.title}</span>
          <span className="progress" aria-label={t("진행률")}>
            <span
              className={job.progress === null ? "bar indeterminate" : "bar"}
              style={job.progress === null ? undefined : { width: `${Math.round(job.progress * 100)}%` }}
            />
          </span>
          <span className="muted">
            {job.message} · {t("{s}초", { s: Math.round(job.elapsed) })}
          </span>
          <button className="link" onClick={cancelJob}>
            {t("취소")}
          </button>
        </span>
      )}
      {projectPath && <span className="muted" title={projectPath}>{projectPath.split(/[\\/]/).pop()}</span>}
      {engineDown ? (
        <span className="engine" data-testid="engine-status">
          {t("엔진 멈춤")}
        </span>
      ) : health ? (
        <span className="engine ok" data-testid="engine-status">
          {t("엔진 {version} · GDAL {gdal}", { version: health.version, gdal: health.gdal })}
        </span>
      ) : (
        <span className="engine" data-testid="engine-status">
          {engineError ? t("엔진 오류: {error}", { error: engineError }) : t("엔진 연결 중…")}
        </span>
      )}
    </footer>
  );
}
