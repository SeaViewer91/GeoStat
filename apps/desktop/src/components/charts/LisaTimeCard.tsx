// 기간별 LISA 결과 카드 (결과 패널): 기간별 군집 수, 군집 전이표, 기간별 군집 지도 보기

import { dirname, pickSavePath } from "../../lib/dialogs";
import { t } from "../../i18n";
import { engine, type LisaTimeReport } from "../../lib/engine";
import { useApp, type LoadedDataset, type ReportEntry } from "../../store";

/** LISA 군집 색 (GeoDa 관례, 엔진의 lisa_cluster 지도와 같음) */
const LISA_COLORS = ["#eeeeee", "#ff0000", "#0000ff", "#a7adf9", "#f4ada8", "#464646"];

export function LisaTimeCard({ ds, entry }: { ds: LoadedDataset; entry: ReportEntry }) {
  const { analysis } = entry;
  const report = analysis.report as LisaTimeReport;
  const dismissReport = useApp((s) => s.dismissReport);
  const applyStyle = useApp((s) => s.applyStyle);
  const notify = useApp((s) => s.notify);
  const fail = useApp((s) => s.fail);
  // 한 번이라도 나온 군집만 보여줌
  const shown = report.categories.map((_, i) => i).filter((i) => report.counts.some((c) => c[i] > 0));
  const periodCols = analysis.outputs.slice(0, report.labels.length);
  const current = ds.style?.column;

  const save = async () => {
    const path = await pickSavePath(
      [{ name: t("텍스트"), extensions: ["txt"] }],
      t("보고서 저장"),
      `${dirname(ds.info.path)}/${ds.info.name}_${t("기간별LISA")}_${t("보고서")}.txt`,
    );
    if (!path) return;
    try {
      const r = await engine.saveReport(ds.info.id, analysis.id, path);
      notify(t("보고서를 저장함: {path}", { path: r.path }));
    } catch (err) {
      fail(err);
    }
  };

  const swatch = (i: number) => <span className="swatch inline" style={{ background: LISA_COLORS[i] }} />;

  return (
    <section className="chart-card report-card" data-testid="lisa-time-card">
      <header>
        <span className="title" title={analysis.description}>
          {t("기간별 LISA")} · {report.group}
        </span>
        <button className="link" onClick={() => dismissReport(analysis.id)} aria-label={t("보고서 닫기")}>
          ✕
        </button>
      </header>
      <div className="muted small">
        W={report.weights} · n={report.n.toLocaleString()} · α={report.alpha}
      </div>

      <h4>{t("기간별 군집 수 (기간을 누르면 그 기간의 군집 지도)")}</h4>
      <div className="table-scroll">
        <table className="result-table compact nowrap clickable">
          <thead>
            <tr>
              <th>{t("기간")}</th>
              {shown.map((i) => (
                <th key={i}>
                  {swatch(i)}
                  {t(report.categories[i])}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.labels.map((label, k) => (
              <tr
                key={label}
                className={current === periodCols[k] ? "on" : ""}
                onClick={() => void applyStyle(ds.info.id, { column: periodCols[k], method: "lisa_cluster", k: 5 })}
              >
                <td>{label}</td>
                {shown.map((i) => (
                  <td key={i}>{report.counts[k][i].toLocaleString()}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h4>{t("군집 전이표 (행: 앞 기간 → 열: 다음 기간, 모든 인접 기간 합)")}</h4>
      <div className="table-scroll">
        <table className="result-table compact nowrap" data-testid="transition-table">
          <thead>
            <tr>
              <th />
              {shown.map((j) => (
                <th key={j}>{t(report.categories[j])}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((i) => (
              <tr key={i}>
                <th>
                  {swatch(i)}
                  {t(report.categories[i])}
                </th>
                {shown.map((j) => (
                  <td key={j} className={i === j ? "diag" : report.matrix[i][j] > 0 ? "strong" : "muted"}>
                    {report.matrix[i][j].toLocaleString()}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="muted small">
        {t("군집이 한 번 이상 바뀐 피처 {a}개 · 모든 기간 같은 유의 군집 {b}개", {
          a: report.n_changed,
          b: report.n_stable_cluster,
        })}
      </div>

      <div className="row wrap">
        <button
          onClick={() =>
            void applyStyle(ds.info.id, {
              column: analysis.outputs[analysis.outputs.length - 1],
              method: "unique_values",
              k: 5,
            })
          }
        >
          {t("변화 횟수 지도")}
        </button>
        <button onClick={save}>{t("보고서 저장…")}</button>
      </div>
    </section>
  );
}
