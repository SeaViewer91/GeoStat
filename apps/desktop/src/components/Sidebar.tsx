// 왼쪽 패널: 레이어 목록, 주제도 설정, 범례

import { useEffect, useState } from "react";

import type { ClassifyMethod } from "../lib/engine";
import { MISSING_COLOR, classColors, rgbaCss } from "../lib/palette";
import { useActive, useApp, type LoadedDataset, type StyleSpec } from "../store";

const METHODS: { id: ClassifyMethod; label: string; hasK: boolean; numeric: boolean }[] = [
  { id: "quantile", label: "분위수", hasK: true, numeric: true },
  { id: "equal_interval", label: "등간격", hasK: true, numeric: true },
  { id: "natural_breaks", label: "자연 분류 (Jenks)", hasK: true, numeric: true },
  { id: "std_mean", label: "표준편차", hasK: false, numeric: true },
  { id: "percentile", label: "백분위", hasK: false, numeric: true },
  { id: "box_plot", label: "박스 지도 (1.5 IQR)", hasK: false, numeric: true },
  { id: "unique_values", label: "고유값", hasK: false, numeric: false },
];

const GEOM_ICON = { point: "•", line: "╱", polygon: "▰" } as const;

export function Sidebar() {
  return (
    <aside className="sidebar">
      <LayerList />
      <StylePanel />
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
  const numericCols = ds.info.columns.filter((c) => c.kind === "numeric");
  const allCols = ds.info.columns;

  const [method, setMethod] = useState<ClassifyMethod>(ds.style?.method ?? "quantile");
  const meta = METHODS.find((m) => m.id === method)!;
  const candidates = meta.numeric ? numericCols : allCols;
  const [column, setColumn] = useState<string>(ds.style?.column ?? candidates[0]?.name ?? "");
  const [k, setK] = useState<number>(ds.style?.k ?? 5);

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
            {candidates.length === 0 && <option value="">(숫자 열 없음)</option>}
            {candidates.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
                {c.derived ? " (계산)" : ""}
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
  const colors = classColors(theme.scheme, theme.labels);
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
