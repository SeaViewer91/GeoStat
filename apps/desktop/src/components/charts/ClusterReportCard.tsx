// 군집 분석 결과 카드 (결과 패널): 요약, 군집별 크기·조각 수·변수 평균(프로필), 지도 연동

import { dirname, pickSavePath } from "../../lib/dialogs";
import { t } from "../../i18n";
import { engine, type ClusterReport } from "../../lib/engine";
import { classColors, rgbaCss } from "../../lib/palette";
import { useApp, type LoadedDataset, type ReportEntry } from "../../store";
import { num } from "./ReportCard";

/** 표준화 평균(z)을 파랑(낮음)–흰색–빨강(높음) 배경색으로 바꿈. |z| ≥ 1.5면 가장 진함 */
function zColor(z: number | null): string | undefined {
  if (z === null || !Number.isFinite(z)) return undefined;
  const frac = Math.min(1, Math.abs(z) / 1.5);
  const alpha = (0.08 + 0.5 * frac).toFixed(2);
  return z >= 0 ? `rgba(214, 96, 77, ${alpha})` : `rgba(67, 147, 195, ${alpha})`;
}

export function ClusterReportCard({ ds, entry }: { ds: LoadedDataset; entry: ReportEntry }) {
  const { analysis } = entry;
  const report = analysis.report as ClusterReport;
  const dismissReport = useApp((s) => s.dismissReport);
  const showResultMap = useApp((s) => s.showResultMap);
  const selectClass = useApp((s) => s.selectClass);
  const notify = useApp((s) => s.notify);
  const fail = useApp((s) => s.fail);
  const column = analysis.outputs[0];
  const theme = ds.theme && ds.theme.column === column ? ds.theme : null;
  const colors = theme ? classColors(theme.scheme, theme.labels, 225, theme.colors) : null;
  const hasFragments = report.clusters.some((c) => c.fragments !== null);

  /** 지도 범례에서 이 군집의 계급 번호 (고유값 지도는 라벨이 군집 번호 문자열임) */
  const classOf = (clusterId: number) => theme?.labels.indexOf(String(clusterId)) ?? -1;

  const selectCluster = async (clusterId: number, add: boolean) => {
    if (!theme) await showResultMap(ds.info.id, analysis);
    const th = useApp.getState().datasets[ds.info.id]?.theme;
    const k = th ? th.labels.indexOf(String(clusterId)) : -1;
    if (k >= 0) selectClass(ds.info.id, k, add ? "add" : "replace");
  };

  const save = async () => {
    const path = await pickSavePath(
      [{ name: t("텍스트"), extensions: ["txt"] }],
      t("보고서 저장"),
      `${dirname(ds.info.path)}/${ds.info.name}_${report.method}_${t("보고서")}.txt`,
    );
    if (!path) return;
    try {
      const r = await engine.saveReport(ds.info.id, analysis.id, path);
      notify(t("보고서를 저장함: {path}", { path: r.path }));
    } catch (err) {
      fail(err);
    }
  };

  return (
    <section className="chart-card report-card" data-testid="cluster-card">
      <header>
        <span className="title" title={analysis.description}>
          {t(report.title)}
        </span>
        <button className="link" onClick={() => dismissReport(analysis.id)} aria-label={t("보고서 닫기")}>
          ✕
        </button>
      </header>
      <div className="muted small">
        {report.variables.join(", ")} · n={report.n.toLocaleString()} · {t("{k}개 군집", { k: report.k })}
      </div>

      <dl className="summary-grid">
        {report.summary.map(([label, value]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{num(value)}</dd>
          </div>
        ))}
      </dl>

      <h4>{t("군집별 요약 (행을 누르면 지도에서 선택, ⌘ 누르고 누르면 추가)")}</h4>
      <div className="table-scroll">
        <table className="result-table compact nowrap clickable" data-testid="cluster-table">
          <thead>
            <tr>
              <th>{t("군집")}</th>
              <th>{t("크기")}</th>
              {hasFragments && <th title={t("공간적으로 이어진 조각 수 (1이면 한 덩어리)")}>{t("조각")}</th>}
              <th title={t("군집 내 제곱합")}>SS</th>
              {report.variables.map((v) => (
                <th key={v} title={t("{v} 평균 (원래 값). 배경색은 표준화 평균", { v })}>
                  {v}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.clusters.map((c) => {
              const k = classOf(c.id);
              return (
                <tr key={c.id} onClick={(e) => void selectCluster(c.id, e.metaKey || e.ctrlKey)}>
                  <td>
                    {colors && k >= 0 && <span className="swatch inline" style={{ background: rgbaCss(colors[k]) }} />}
                    {c.id}
                  </td>
                  <td>{c.size.toLocaleString()}</td>
                  {hasFragments && <td className={c.fragments && c.fragments > 1 ? "warn-text" : ""}>{c.fragments}</td>}
                  <td>{num(c.within_ss, 3)}</td>
                  {c.means.map((m, j) => (
                    <td key={j} style={{ background: zColor(c.z_means[j]) }}>
                      {num(m, 4)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="muted small">
        {t("평균 칸 배경: 전체 평균보다 높으면 빨강, 낮으면 파랑 (표준화 평균 기준)")}
      </div>

      {report.notes.filter(Boolean).length > 0 && (
        <ul className="notes">
          {report.notes.filter(Boolean).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      <div className="row wrap">
        <button onClick={() => showResultMap(ds.info.id, analysis)}>{t("군집 지도")}</button>
        <button onClick={save}>{t("보고서 저장…")}</button>
      </div>
    </section>
  );
}
