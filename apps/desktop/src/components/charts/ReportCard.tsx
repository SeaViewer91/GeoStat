// 회귀 결과 보고서 카드 (결과 패널)

import { dirname, pickSavePath } from "../../lib/dialogs";
import { engine, type DiagRow } from "../../lib/engine";
import { useApp, type LoadedDataset, type ReportEntry } from "../../store";

function num(v: number | string | null | undefined, digits = 4): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "string") return v;
  if (!Number.isFinite(v)) return "–";
  if (Number.isInteger(v) && Math.abs(v) < 1e12) return v.toLocaleString();
  if (v !== 0 && Math.abs(v) < 1e-3) return v.toExponential(2);
  return Number(v.toPrecision(digits)).toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function pval(p: number | null): string {
  if (p === null) return "–";
  return p < 0.001 ? "<0.001" : p.toFixed(3);
}

/** p값 유의 표시 (* 0.05, ** 0.01, *** 0.001) */
function stars(p: number | null): string {
  if (p === null) return "";
  return p < 0.001 ? "***" : p < 0.01 ? "**" : p < 0.05 ? "*" : "";
}

export function ReportCard({ ds, entry }: { ds: LoadedDataset; entry: ReportEntry }) {
  const { analysis } = entry;
  const report = analysis.report!;
  const dismissReport = useApp((s) => s.dismissReport);
  const showResultMap = useApp((s) => s.showResultMap);
  const addChart = useApp((s) => s.addChart);
  const notify = useApp((s) => s.notify);
  const fail = useApp((s) => s.fail);
  const isGwr = report.model === "gwr" || report.model === "mgwr";
  const resid = analysis.outputs.find((c) => c.endsWith("_RESID"));
  const weightsId = ds.activeWeightsId;
  const currentMapColumn = ds.style?.column;

  const save = async () => {
    const path = await pickSavePath(
      [{ name: "텍스트", extensions: ["txt"] }],
      "보고서 저장",
      `${dirname(ds.info.path)}/${ds.info.name}_${report.model}_보고서.txt`,
    );
    if (!path) return;
    try {
      const r = await engine.saveReport(ds.info.id, analysis.id, path);
      notify(`보고서를 저장함: ${r.path}`);
    } catch (err) {
      fail(err);
    }
  };

  const groups = report.diagnostics.reduce<Record<string, DiagRow[]>>((acc, d) => {
    (acc[d.group] ??= []).push(d);
    return acc;
  }, {});

  return (
    <section className="chart-card report-card" data-testid="report-card">
      <header>
        <span className="title" title={analysis.description}>
          {report.title}
        </span>
        <button className="link" onClick={() => dismissReport(analysis.id)} aria-label="보고서 닫기">
          ✕
        </button>
      </header>
      <div className="muted small">
        {report.y} ~ {report.x.join(" + ")} · n={report.n.toLocaleString()}
      </div>

      <dl className="summary-grid">
        {report.summary.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{num(value)}</dd>
          </div>
        ))}
      </dl>

      {report.coefficients.length > 0 && (
        <table className="result-table compact" data-testid="coef-table">
          <thead>
            <tr>
              <th>변수</th>
              <th>계수</th>
              <th>표준오차</th>
              <th>{report.stat_label}</th>
              <th>p</th>
            </tr>
          </thead>
          <tbody>
            {report.coefficients.map((c) => (
              <tr key={c.name} className={c.p !== null && c.p < 0.05 ? "sig" : ""}>
                <td>{c.name}</td>
                <td>{num(c.coef)}</td>
                <td>{num(c.se)}</td>
                <td>{num(c.stat, 3)}</td>
                <td>
                  {pval(c.p)}
                  <span className="stars">{stars(c.p)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {report.local && (
        <>
          <h4>지역 계수 (행을 누르면 계수 지도로 바꿈)</h4>
          <table className="result-table compact clickable" data-testid="local-table">
            <thead>
              <tr>
                <th>변수</th>
                <th>대역폭</th>
                <th>평균</th>
                <th>최소</th>
                <th>중앙값</th>
                <th>최대</th>
                <th>유의%</th>
              </tr>
            </thead>
            <tbody>
              {report.local.map((r, j) => {
                const key = j === 0 ? "CONST" : undefined;
                const col = analysis.outputs.filter((c) => c.includes("_B_"))[j];
                return (
                  <tr
                    key={r.name}
                    className={col === currentMapColumn ? "on" : ""}
                    onClick={() => showResultMap(ds.info.id, analysis, key ?? col?.split("_B_")[1])}
                  >
                    <td>{r.name}</td>
                    <td>{num(r.bandwidth)}</td>
                    <td>{num(r.mean)}</td>
                    <td>{num(r.min)}</td>
                    <td>{num(r.median)}</td>
                    <td>{num(r.max)}</td>
                    <td>{num(r.pct_significant, 3)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {Object.entries(groups).map(([group, rows]) => (
        <div key={group}>
          <h4>{group}</h4>
          <table className="result-table compact">
            <tbody>
              {rows.map((d) => (
                <tr key={d.name} className={d.p !== null && d.p < 0.05 ? "sig" : ""}>
                  <td>
                    {d.name}
                    {d.df !== null && <span className="muted small"> (df {d.df})</span>}
                  </td>
                  <td>{num(d.value)}</td>
                  <td>
                    {d.p === null ? "" : `p ${pval(d.p)}`}
                    <span className="stars">{stars(d.p)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {report.notes.filter(Boolean).length > 0 && (
        <ul className="notes">
          {report.notes.filter(Boolean).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <div className="muted small">* p&lt;0.05 · ** p&lt;0.01 · *** p&lt;0.001</div>

      <div className="row wrap">
        {resid && (
          <button onClick={() => useApp.getState().applyStyle(ds.info.id, { column: resid, method: "std_mean", k: 5 })}>
            잔차 지도
          </button>
        )}
        {resid && (
          <button
            disabled={!weightsId}
            title={weightsId ? "활성 가중치로 잔차의 공간자기상관을 봄" : "공간가중치를 먼저 만들어야 함"}
            onClick={() =>
              weightsId &&
              addChart({ datasetId: ds.info.id, kind: "moran", x: resid, weightsId, permutations: 999 })
            }
          >
            잔차 Moran&apos;s I
          </button>
        )}
        {isGwr && <button onClick={() => showResultMap(ds.info.id, analysis)}>계수 지도</button>}
        <button onClick={save}>보고서 저장…</button>
      </div>
    </section>
  );
}
