// 오른쪽 패널: 활성 레이어의 연동 차트 목록

import { useEffect, useState } from "react";

import { t } from "../../i18n";
import { engine, isClusterReport } from "../../lib/engine";
import { useActive, useApp, type ChartKind, type ChartSpec, type LoadedDataset } from "../../store";
import { BoxPlot, Histogram, MoranReference, Scatter } from "./Charts";
import { ClusterReportCard } from "./ClusterReportCard";
import { ModelComparison } from "./ModelComparison";
import { ReportCard } from "./ReportCard";

const KINDS: { kind: ChartKind; label: string }[] = [
  { kind: "histogram", label: "히스토그램" },
  { kind: "scatter", label: "산점도" },
  { kind: "box", label: "박스플롯" },
  { kind: "moran", label: "Moran 산점도" },
];

export function ChartsPanel({ onClose }: { onClose: () => void }) {
  const ds = useActive();
  const charts = useApp((s) => s.charts);
  const reports = useApp((s) => s.reports);
  const showDialog = useApp((s) => s.showDialog);
  const mine = ds ? charts.filter((c) => c.datasetId === ds.info.id) : [];
  const myReports = ds ? reports.filter((r) => r.datasetId === ds.info.id) : [];

  return (
    <aside className="charts-panel" data-testid="charts-panel">
      <div className="charts-head">
        <h2>{t("결과·차트")}</h2>
        <div className="spacer" />
        <button className="link" onClick={onClose} title={t("차트 패널 닫기")}>
          {t("닫기")}
        </button>
      </div>
      <div className="charts-add">
        {KINDS.map((k) => (
          <button
            key={k.kind}
            disabled={!ds}
            onClick={() => ds && showDialog({ kind: "chart", datasetId: ds.info.id, chart: k.kind })}
          >
            + {t(k.label)}
          </button>
        ))}
      </div>
      {!ds && <p className="muted pad">{t("데이터를 열면 차트를 추가할 수 있음")}</p>}
      {ds && <ModelComparison entries={myReports} />}
      {ds &&
        [...myReports]
          .reverse()
          .map((r) =>
            isClusterReport(r.analysis.report) ? (
              <ClusterReportCard key={r.analysis.id} ds={ds} entry={r} />
            ) : (
              <ReportCard key={r.analysis.id} ds={ds} entry={r} />
            ),
          )}
      {ds && mine.length === 0 && myReports.length === 0 && (
        <p className="muted pad">
          {t("차트에서 끌어 선택하면 지도·테이블에도 반영됨. 지도에서 선택해도 차트에 강조됨.")}
        </p>
      )}
      {ds && mine.map((c) => <ChartCard key={c.id} ds={ds} chart={c} />)}
    </aside>
  );
}

function useColumns(ds: LoadedDataset, names: string[]): Record<string, Float64Array> | null {
  const [data, setData] = useState<Record<string, Float64Array> | null>(null);
  const fail = useApp((s) => s.fail);
  const key = `${ds.info.id}|${ds.revision}|${names.join("|")}`;
  useEffect(() => {
    let alive = true;
    setData(null);
    engine
      .columns(ds.info.id, names)
      .then((d) => alive && setData(d))
      .catch(fail);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return data;
}

function ChartCard({ ds, chart }: { ds: LoadedDataset; chart: ChartSpec }) {
  const removeChart = useApp((s) => s.removeChart);
  const title =
    chart.kind === "histogram"
      ? `${t("히스토그램")} · ${chart.x}`
      : chart.kind === "scatter"
        ? `${t("산점도")} · ${chart.x} × ${chart.y}`
        : chart.kind === "box"
          ? `${t("박스플롯")} · ${chart.x}`
          : `${t("Moran 산점도")} · ${chart.x}${chart.y ? ` × ${chart.y}` : ""}`;
  return (
    <section className="chart-card" data-testid="chart-card">
      <header>
        <span className="title" title={title}>
          {title}
        </span>
        <button className="link" onClick={() => removeChart(chart.id)} aria-label={t("차트 닫기")}>
          ✕
        </button>
      </header>
      {chart.kind === "moran" ? <MoranBody ds={ds} chart={chart} /> : <ColumnChart ds={ds} chart={chart} />}
    </section>
  );
}

function ColumnChart({ ds, chart }: { ds: LoadedDataset; chart: ChartSpec }) {
  const names = chart.kind === "scatter" ? [chart.x, chart.y!] : [chart.x];
  const data = useColumns(ds, names);
  if (!data) return <div className="chart-loading muted">{t("불러오는 중…")}</div>;
  if (chart.kind === "histogram") return <Histogram ds={ds} values={data[chart.x]} bins={chart.bins ?? 10} />;
  if (chart.kind === "box") return <BoxPlot ds={ds} values={data[chart.x]} />;
  return <Scatter ds={ds} xs={data[chart.x]} ys={data[chart.y!]} xLabel={chart.x} yLabel={chart.y!} />;
}

function MoranBody({ ds, chart }: { ds: LoadedDataset; chart: ChartSpec }) {
  const m = chart.moran;
  if (!m) return <div className="chart-loading muted">{t("계산 중…")}</div>;
  const lagLabel = t("W·{col} (표준화)", { col: m.column_y ?? m.column });
  const p = (v: number | null) => (v === null ? "–" : v < 0.001 ? v.toExponential(1) : v.toFixed(3));
  return (
    <>
      <div className="stat-row" data-testid="moran-stats">
        <div className="stat">
          <span className="label">Moran&apos;s I</span>
          <strong>{m.I.toFixed(4)}</strong>
        </div>
        <div className="stat">
          <span className="label">E[I]</span>
          {m.expected.toFixed(4)}
        </div>
        <div className="stat">
          <span className="label">{t("유사 p ({n}회)", { n: m.permutations })}</span>
          {p(m.p_sim)}
        </div>
        <div className="stat">
          <span className="label">z</span>
          {m.z_sim === null ? "–" : m.z_sim.toFixed(2)}
        </div>
      </div>
      <Scatter ds={ds} xs={m.z} ys={m.lag} xLabel={t("{col} (표준화)", { col: m.column })} yLabel={lagLabel} moran />
      <div className="muted small pad-x">
        {t("가중치 {w} · 순열 기준 분포 (노란 선이 관측값 I)", { w: m.weights })}
      </div>
      <MoranReference moran={m} />
    </>
  );
}
