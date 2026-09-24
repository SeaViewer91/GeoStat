// 왼쪽 패널: 레이어 목록, 주제도 설정, 범례

import { useEffect, useState } from "react";

import { dirname, pickSavePath } from "../lib/dialogs";
import { engine, type ClassifyMethod } from "../lib/engine";
import { MISSING_COLOR, classColors, rgbaCss } from "../lib/palette";
import { useActive, useApp, type LoadedDataset, type StyleSpec } from "../store";

type ColumnFilter = (c: { name: string; kind: string; origin: string }) => boolean;
const isNumeric: ColumnFilter = (c) => c.kind === "numeric";
const any: ColumnFilter = () => true;
// 분석 결과 열 이름 규칙: <접두어>_CL(군집 코드), <접두어>_P(p값)
const isCluster: ColumnFilter = (c) => c.origin === "analysis" && c.name.endsWith("_CL");
const isPValue: ColumnFilter = (c) => c.kind === "numeric" && (c.name.endsWith("_P") || /p_?val/i.test(c.name));

const METHODS: { id: ClassifyMethod; label: string; hasK: boolean; filter: ColumnFilter }[] = [
  { id: "quantile", label: "분위수", hasK: true, filter: isNumeric },
  { id: "equal_interval", label: "등간격", hasK: true, filter: isNumeric },
  { id: "natural_breaks", label: "자연 분류 (Jenks)", hasK: true, filter: isNumeric },
  { id: "std_mean", label: "표준편차", hasK: false, filter: isNumeric },
  { id: "percentile", label: "백분위", hasK: false, filter: isNumeric },
  { id: "box_plot", label: "박스 지도 (1.5 IQR)", hasK: false, filter: isNumeric },
  { id: "unique_values", label: "고유값", hasK: false, filter: any },
  { id: "lisa_cluster", label: "LISA 군집 지도", hasK: false, filter: isCluster },
  { id: "gi_cluster", label: "Gi* 핫스팟 지도", hasK: false, filter: isCluster },
  { id: "geary_cluster", label: "Local Geary 군집 지도", hasK: false, filter: isCluster },
  { id: "significance", label: "유의성 지도 (p값)", hasK: false, filter: isPValue },
];

const GEOM_ICON = { point: "•", line: "╱", polygon: "▰" } as const;

export function Sidebar() {
  return (
    <aside className="sidebar">
      <LayerList />
      <StylePanel />
      <WeightsPanel />
    </aside>
  );
}

function LayerList() {
  const order = useApp((s) => s.order);
  const datasets = useApp((s) => s.datasets);
  const activeId = useApp((s) => s.activeId);
  const { setActive, toggleVisible, moveLayer, zoomTo, closeDataset, showDialog } = useApp.getState();

  return (
    <section className="panel">
      <h2>레이어</h2>
      {order.length === 0 && <p className="muted">데이터를 열면 여기에 표시됨</p>}
      <ul className="layer-list">
        {order.map((id, i) => {
          const ds = datasets[id];
          if (!ds) return null;
          return (
            <li
              key={id}
              className={id === activeId ? "active" : ""}
              onClick={() => setActive(id)}
              data-testid="layer-item"
            >
              <input
                type="checkbox"
                checked={ds.visible}
                onChange={() => toggleVisible(id)}
                onClick={(e) => e.stopPropagation()}
                aria-label="표시"
              />
              <span className="geom">{GEOM_ICON[ds.info.geometry_type]}</span>
              <span className="name" title={ds.info.path}>
                {ds.info.name}
              </span>
              {!ds.table && (
                <button
                  className="warn"
                  title="좌표계가 없어 지도에 표시할 수 없음"
                  onClick={(e) => {
                    e.stopPropagation();
                    showDialog({ kind: "crs", datasetId: id, reason: "missing" });
                  }}
                >
                  좌표계 지정
                </button>
              )}
              <span className="actions">
                <button title="위로" disabled={i === 0} onClick={() => moveLayer(id, -1)}>
                  ↑
                </button>
                <button title="아래로" disabled={i === order.length - 1} onClick={() => moveLayer(id, 1)}>
                  ↓
                </button>
                <button title="전체 보기" onClick={() => zoomTo(id)}>
                  ⤢
                </button>
                <button title="닫기" onClick={() => closeDataset(id)}>
                  ✕
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function StylePanel() {
  const ds = useActive();
  if (!ds) return null;
  return <StyleEditor key={ds.info.id} ds={ds} />;
}

function StyleEditor({ ds }: { ds: LoadedDataset }) {
  const applyStyle = useApp((s) => s.applyStyle);
  const busy = useApp((s) => s.busy);
  const showDialog = useApp((s) => s.showDialog);
  const [method, setMethod] = useState<ClassifyMethod>(ds.style?.method ?? "quantile");
  const meta = METHODS.find((m) => m.id === method)!;
  const candidates = ds.info.columns.filter(meta.filter);
  const [column, setColumn] = useState<string>(ds.style?.column ?? candidates[0]?.name ?? "");
  const [k, setK] = useState<number>(ds.style?.k ?? 5);

  // 분석을 실행해 주제도가 바뀌면 설정 칸도 따라감
  useEffect(() => {
    if (ds.style) {
      setMethod(ds.style.method);
      setColumn(ds.style.column);
    }
  }, [ds.style]);

  // 방법을 바꿨을 때 현재 열이 맞지 않으면 첫 후보로 바꿈
  useEffect(() => {
    if (!candidates.some((c) => c.name === column)) setColumn(candidates[0]?.name ?? "");
  }, [method, candidates, column]);

  const apply = () => {
    if (!column) return;
    const style: StyleSpec = { column, method, k };
    void applyStyle(ds.info.id, style);
  };

  const crs = ds.info.crs;

  return (
    <section className="panel">
      <h2>주제도</h2>
      <div className="form">
        <label>
          변수
          <select value={column} onChange={(e) => setColumn(e.target.value)} aria-label="변수">
            {candidates.length === 0 && <option value="">(해당 열 없음)</option>}
            {candidates.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
                {c.origin === "expression" ? " (계산)" : c.origin === "analysis" ? " (분석)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          방법
          <select value={method} onChange={(e) => setMethod(e.target.value as ClassifyMethod)} aria-label="방법">
            {METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        {meta.hasK && (
          <label>
            계급 수
            <input
              type="number"
              min={2}
              max={12}
              value={k}
              onChange={(e) => setK(Math.min(12, Math.max(2, Number(e.target.value) || 5)))}
              aria-label="계급 수"
            />
          </label>
        )}
        <div className="row">
          <button className="primary" onClick={apply} disabled={!column || !!busy || !ds.table}>
            적용
          </button>
          <button onClick={() => applyStyle(ds.info.id, null)} disabled={!ds.theme}>
            단일 색
          </button>
        </div>
      </div>

      {ds.theme && <Legend ds={ds} />}

      <h2>정보</h2>
      <dl className="info">
        <dt>피처</dt>
        <dd>{ds.info.n_rows.toLocaleString()}개</dd>
        <dt>좌표계</dt>
        <dd>
          {crs ? `EPSG:${crs.epsg ?? "?"}` : "없음"}{" "}
          <button className="link" onClick={() => showDialog({ kind: "crs", datasetId: ds.info.id, reason: "manual" })}>
            지정…
          </button>
          {crs && <div className="muted small">{crs.name}</div>}
        </dd>
        {ds.info.encoding && (
          <>
            <dt>인코딩</dt>
            <dd>{ds.info.encoding}</dd>
          </>
        )}
        <dt>경로</dt>
        <dd className="path" title={ds.info.path}>
          {ds.info.path}
        </dd>
      </dl>
    </section>
  );
}

function Legend({ ds }: { ds: LoadedDataset }) {
  const theme = ds.theme!;
  const selectClass = useApp((s) => s.selectClass);
  const colors = classColors(theme.scheme, theme.labels, 225, theme.colors);
  const methodLabel = METHODS.find((m) => m.id === theme.method)?.label ?? theme.method;

  return (
    <div className="legend" data-testid="legend">
      <div className="legend-title">
        {theme.column} · {methodLabel}
      </div>
      <ul>
        {theme.labels.map((label, i) => (
          <li
            key={i}
            title="클릭하면 이 계급의 피처를 선택함 (⌘: 추가 선택)"
            onClick={(e) => selectClass(ds.info.id, i, e.metaKey || e.ctrlKey ? "add" : "replace")}
          >
            <span className="swatch" style={{ background: rgbaCss(colors[i]) }} />
            <span className="label">{label}</span>
            <span className="count">{theme.counts[i]?.toLocaleString()}</span>
          </li>
        ))}
        {theme.n_missing > 0 && (
          <li onClick={(e) => selectClass(ds.info.id, -1, e.metaKey || e.ctrlKey ? "add" : "replace")}>
            <span className="swatch" style={{ background: rgbaCss(MISSING_COLOR) }} />
            <span className="label">값 없음</span>
            <span className="count">{theme.n_missing.toLocaleString()}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

function WeightsPanel() {
  const ds = useActive();
  const showDialog = useApp((s) => s.showDialog);
  const setActiveWeights = useApp((s) => s.setActiveWeights);
  const removeWeights = useApp((s) => s.removeWeights);
  const selectNeighbors = useApp((s) => s.selectNeighbors);
  const notify = useApp((s) => s.notify);
  const fail = useApp((s) => s.fail);
  if (!ds || !ds.table) return null;
  const w = ds.weights.find((x) => x.id === ds.activeWeightsId);

  const save = async () => {
    if (!w) return;
    const binary = w.type === "queen" || w.type === "rook";
    const path = await pickSavePath(
      [binary ? { name: "GeoDa GAL", extensions: ["gal"] } : { name: "GeoDa GWT", extensions: ["gwt"] }],
      "가중치 저장",
      `${dirname(ds.info.path)}/${ds.info.name}_${w.name}.${binary ? "gal" : "gwt"}`,
    );
    if (!path) return;
    try {
      const r = await engine.saveWeights(ds.info.id, w.id, path);
      notify(`가중치를 저장함: ${r.path}`);
    } catch (err) {
      fail(err);
    }
  };

  return (
    <section className="panel" data-testid="weights-panel">
      <h2>공간가중치</h2>
      {ds.weights.length === 0 ? (
        <p className="muted">
          아직 없음.{" "}
          <button className="link" onClick={() => showDialog({ kind: "weights", datasetId: ds.info.id })}>
            만들기…
          </button>
        </p>
      ) : (
        <>
          <div className="row">
            <select
              value={ds.activeWeightsId ?? ""}
              onChange={(e) => setActiveWeights(ds.info.id, e.target.value)}
              aria-label="활성 가중치"
            >
              {ds.weights.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
            <button onClick={() => showDialog({ kind: "weights", datasetId: ds.info.id })} title="새 가중치">
              +
            </button>
          </div>
          {w && (
            <>
              <p className="muted small">{w.description}</p>
              <dl className="info">
                <dt>이웃 수</dt>
                <dd>
                  평균 {w.summary.mean_neighbors.toFixed(2)} · 최소 {w.summary.min_neighbors} · 최대{" "}
                  {w.summary.max_neighbors}
                </dd>
                <dt>비영 비율</dt>
                <dd>{w.summary.pct_nonzero.toFixed(2)}%</dd>
                {w.summary.n_islands > 0 && (
                  <>
                    <dt className="warn-text">섬</dt>
                    <dd className="warn-text">
                      이웃 없는 피처 {w.summary.n_islands}개{" "}
                      <button
                        className="link"
                        onClick={() => useApp.getState().select(ds.info.id, w.summary.islands, "replace")}
                      >
                        선택
                      </button>
                    </dd>
                  </>
                )}
              </dl>
              <ConnectivityBars histogram={w.summary.histogram} />
              <div className="row wrap">
                <button
                  onClick={() => selectNeighbors(ds.info.id)}
                  disabled={ds.selectedCount === 0}
                  title="선택한 피처의 이웃을 선택에 추가함"
                >
                  이웃 선택
                </button>
                <button onClick={save}>저장…</button>
                <button onClick={() => removeWeights(ds.info.id, w.id)}>삭제</button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

/** 이웃 수 분포 (연결성 히스토그램) */
function ConnectivityBars({ histogram }: { histogram: { neighbors: number; count: number }[] }) {
  const max = Math.max(...histogram.map((h) => h.count));
  return (
    <div className="conn-bars" aria-label="이웃 수 분포">
      {histogram.map((h) => (
        <div key={h.neighbors} className="conn-bar" title={`이웃 ${h.neighbors}개: ${h.count.toLocaleString()}개 피처`}>
          <div className="fill" style={{ height: `${Math.max(4, (h.count / max) * 100)}%` }} />
          <span>{h.neighbors}</span>
        </div>
      ))}
    </div>
  );
}
