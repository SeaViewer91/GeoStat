// 모형 비교표: 같은 데이터셋에서 실행한 회귀 결과의 적합도를 한 표로 모음

import { t } from "../../i18n";
import { isRegressionReport, type RegressionModel, type RegressionReport } from "../../lib/engine";
import { useApp, type ReportEntry } from "../../store";
import { num, pval, stars } from "./ReportCard";

const SHORT: Record<RegressionModel, string> = {
  ols: "OLS",
  lag: "Lag (ML)",
  error: "Error (ML)",
  lag_gm: "Lag (GM)",
  error_gm: "Error (GM)",
  gwr: "GWR",
  mgwr: "MGWR",
};

const reg = (e: ReportEntry) => e.analysis.report as RegressionReport;

function label(entry: ReportEntry): string {
  const r = reg(entry);
  return SHORT[r.model] + (entry.analysis.params.robust === "white" ? " · White" : "");
}

/** 종속변수·관측치 수가 같은 모형끼리만 AICc를 비교할 수 있으므로 그 묶음에서 최솟값을 찾음 */
function bestByGroup(entries: ReportEntry[]): Set<string> {
  const best = new Map<string, { id: string; aicc: number }>();
  for (const e of entries) {
    const r = reg(e);
    const aicc = r.fit?.aicc;
    if (aicc === null || aicc === undefined) continue;
    const key = `${r.y}|${r.n}`;
    const cur = best.get(key);
    if (!cur || aicc < cur.aicc) best.set(key, { id: e.analysis.id, aicc });
  }
  return new Set([...best.values()].map((b) => b.id));
}

export function ModelComparison({ entries }: { entries: ReportEntry[] }) {
  const notify = useApp((s) => s.notify);
  const rows = entries.filter((e) => isRegressionReport(e.analysis.report) && e.analysis.report.fit);
  if (rows.length < 2) return null;
  const best = bestByGroup(rows);
  const ys = new Set(rows.map((e) => reg(e).y));

  const copy = async () => {
    const header = [t("모형"), t("종속변수"), t("독립변수"), "n", "R²", t("로그우도"), "AICc", t("잔차 Moran's I"), "p"];
    const lines = rows.map((e) => {
      const r = reg(e);
      const f = r.fit!;
      return [label(e), r.y, r.x.join(" + "), r.n, f.r2, f.loglik, f.aicc, f.moran_i, f.moran_p]
        .map((v) => (v === null || v === undefined ? "" : String(v)))
        .join("\t");
    });
    try {
      await navigator.clipboard.writeText([header.join("\t"), ...lines].join("\n"));
      notify(t("모형 비교표를 복사함 (엑셀에 붙여 넣을 수 있음)"));
    } catch {
      notify(t("클립보드에 복사하지 못함"));
    }
  };

  return (
    <section className="chart-card report-card" data-testid="model-comparison">
      <header>
        <span className="title">{t("모형 비교")}</span>
        <button className="link" onClick={copy} title={t("탭으로 구분한 표로 복사")}>
          {t("복사")}
        </button>
      </header>
      <div className="table-scroll">
        <table className="result-table compact nowrap">
          <thead>
            <tr>
              <th>{t("모형")}</th>
              {ys.size > 1 && <th>y</th>}
              <th title={t("GM·ML 공간 모형은 유사 R²")}>R²</th>
              <th>{t("로그우도")}</th>
              <th>AICc</th>
              <th>{t("잔차 I")}</th>
              <th>p</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => {
              const r = reg(e);
              const f = r.fit!;
              const isBest = best.has(e.analysis.id);
              return (
                <tr key={e.analysis.id} className={isBest ? "best" : ""} title={e.analysis.description}>
                  <td>
                    {label(e)}
                    {isBest && <span className="badge">{t("최적")}</span>}
                  </td>
                  {ys.size > 1 && <td>{r.y}</td>}
                  <td>{num(f.r2)}</td>
                  <td>{num(f.loglik, 6)}</td>
                  <td>{num(f.aicc, 6)}</td>
                  <td>{num(f.moran_i, 3)}</td>
                  <td>
                    {pval(f.moran_p)}
                    <span className="stars">{stars(f.moran_p)}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        {t(
          "AICc는 σ²를 모수로 포함해 계산함 (mgwr 방식). 종속변수·관측치가 같은 모형끼리 비교하며 낮을수록 좋음. " +
            "잔차 I는 순열 999회 검정이며, 유의하면 공간 의존성이 남아 있다는 뜻임. GM 추정은 우도가 없어 비교에서 빠짐.",
        )}
      </p>
    </section>
  );
}
