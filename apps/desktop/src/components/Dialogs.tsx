// 대화상자 모음: 레이어 선택, 표 불러오기(X·Y), 좌표계 지정, 계산 필드, 내보내기

import { useEffect, useState, type ReactNode } from "react";

import { CRS_PRESETS } from "../lib/crs";
import { EXPORT_FILTERS, dirname, pickOpenPath, pickSavePath } from "../lib/dialogs";
import {
  engine,
  type FileInspection,
  type JoinCountResult,
  type LocalMethod,
  type ClusterMethod,
  type ClusterSpec,
  type ZonalStat,
  type RegressionModel,
  type RegressionSpec,
  type WeightsSpec,
  type WeightsType,
} from "../lib/engine";
import { useApp, type ChartKind, type Dialog, type LoadedDataset } from "../store";

export function DialogHost() {
  const dialog = useApp((s) => s.dialog);
  if (!dialog) return null;
  switch (dialog.kind) {
    case "layers":
      return <LayerPickDialog dialog={dialog} />;
    case "table":
      return <TableImportDialog dialog={dialog} />;
    case "crs":
      return <CrsDialog dialog={dialog} />;
    case "field":
      return <FieldDialog dialog={dialog} />;
    case "export":
      return <ExportDialog dialog={dialog} />;
    case "weights":
      return <WeightsDialog dialog={dialog} />;
    case "local":
      return <LocalDialog dialog={dialog} />;
    case "joincount":
      return <JoinCountDialog dialog={dialog} />;
    case "regression":
      return <RegressionDialog dialog={dialog} />;
    case "cluster":
      return <ClusterDialog dialog={dialog} />;
    case "zonal":
      return <ZonalDialog datasetId={dialog.datasetId} />;
    case "fishnet":
      return <FishnetDialog />;
    case "chart":
    case "moran":
      return <ChartDialog dialog={dialog.kind === "moran" ? { ...dialog, kind: "chart", chart: "moran" } : dialog} />;
  }
}

function Modal({
  title,
  children,
  onClose,
  footer,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer: ReactNode;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      >
        <h3>{title}</h3>
        <div className="modal-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>
  );
}

const close = () => useApp.getState().showDialog(null);

// ---- 레이어 선택 ---------------------------------------------------------------

function LayerPickDialog({ dialog }: { dialog: Extract<Dialog, { kind: "layers" }> }) {
  const [layer, setLayer] = useState(dialog.layers[0]);
  const openDataset = useApp((s) => s.openDataset);
  const submit = () => {
    close();
    void openDataset(dialog.path, { layer });
  };
  return (
    <Modal
      title="레이어 선택"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit}>
            열기
          </button>
        </>
      }
    >
      <p className="muted">이 파일에는 레이어가 {dialog.layers.length}개 있음.</p>
      <select size={Math.min(10, dialog.layers.length)} value={layer} onChange={(e) => setLayer(e.target.value)}>
        {dialog.layers.map((l) => (
          <option key={l}>{l}</option>
        ))}
      </select>
    </Modal>
  );
}

// ---- 표(CSV·엑셀) 불러오기 --------------------------------------------------------

function TableImportDialog({ dialog }: { dialog: Extract<Dialog, { kind: "table" }> }) {
  const [inspection, setInspection] = useState<FileInspection>(dialog.inspection);
  const t = inspection.table!;
  const numeric = t.columns.filter((c) => c.numeric);
  const [x, setX] = useState(t.guess_x ?? numeric[0]?.name ?? "");
  const [y, setY] = useState(t.guess_y ?? numeric[1]?.name ?? "");
  const [epsg, setEpsg] = useState<number>(t.guess_epsg ?? 4326);
  const openDataset = useApp((s) => s.openDataset);
  const fail = useApp((s) => s.fail);

  const changeSheet = async (sheet: string) => {
    try {
      setInspection(await engine.inspect(dialog.path, { sheet }));
    } catch (err) {
      fail(err);
    }
  };

  const submit = () => {
    close();
    void openDataset(dialog.path, { table: { x, y, epsg, sheet: t.sheet } });
  };

  return (
    <Modal
      title="표를 점 레이어로 불러오기"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={!x || !y || x === y}>
            불러오기
          </button>
        </>
      }
    >
      <p className="muted">
        {t.n_rows.toLocaleString()}행 · {t.encoding ?? "엑셀"}
      </p>
      <div className="form grid2">
        {t.sheets.length > 1 && (
          <label>
            시트
            <select value={t.sheet ?? ""} onChange={(e) => changeSheet(e.target.value)}>
              {t.sheets.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          X (경도·동향)
          <select value={x} onChange={(e) => setX(e.target.value)} aria-label="X 열">
            {numeric.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </label>
        <label>
          Y (위도·북향)
          <select value={y} onChange={(e) => setY(e.target.value)} aria-label="Y 열">
            {numeric.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="span2">
          좌표계
          <CrsSelect value={epsg} onChange={setEpsg} />
        </label>
      </div>
      {t.guess_epsg && t.guess_epsg !== 4326 && (
        <p className="hint">좌표 범위로 추정한 좌표계임. 원자료의 좌표계를 꼭 확인해야 함.</p>
      )}
      <div className="preview">
        <table>
          <thead>
            <tr>
              {t.columns.map((c) => (
                <th key={c.name} className={c.name === x || c.name === y ? "hl" : ""}>
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {t.sample.slice(0, 8).map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => (
                  <td key={j}>{v === null ? "" : String(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

// ---- 좌표계 선택 ---------------------------------------------------------------

function CrsSelect({ value, onChange }: { value: number; onChange: (epsg: number) => void }) {
  const isPreset = CRS_PRESETS.some((p) => p.epsg === value);
  const [custom, setCustom] = useState(!isPreset);
  return (
    <div className="crs-select">
      <select
        value={custom ? "custom" : String(value)}
        onChange={(e) => {
          if (e.target.value === "custom") setCustom(true);
          else {
            setCustom(false);
            onChange(Number(e.target.value));
          }
        }}
        aria-label="좌표계"
      >
        {CRS_PRESETS.map((p) => (
          <option key={p.epsg} value={p.epsg}>
            EPSG:{p.epsg} — {p.label}
          </option>
        ))}
        <option value="custom">직접 입력…</option>
      </select>
      {custom && (
        <input
          type="number"
          placeholder="EPSG 코드"
          value={Number.isFinite(value) ? value : ""}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label="EPSG 코드"
        />
      )}
    </div>
  );
}

function CrsDialog({ dialog }: { dialog: Extract<Dialog, { kind: "crs" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const assignCrs = useApp((s) => s.assignCrs);
  const [epsg, setEpsg] = useState<number>(ds?.info.crs?.epsg ?? 5186);
  if (!ds) return null;
  return (
    <Modal
      title="좌표계 지정"
      onClose={close}
      footer={
        <>
          <button onClick={close}>{dialog.reason === "missing" ? "나중에" : "취소"}</button>
          <button className="primary" onClick={() => assignCrs(dialog.datasetId, epsg)} disabled={!epsg}>
            지정
          </button>
        </>
      }
    >
      {dialog.reason === "missing" ? (
        <p>
          <strong>{ds.info.name}</strong>에 좌표계 정보(.prj)가 없어 지도에 표시할 수 없음. 원자료의 좌표계를
          지정해야 함.
        </p>
      ) : (
        <p>
          좌표 값은 바꾸지 않고 좌표계 정보만 바꿈. 좌표계를 <em>변환</em>하려면 내보내기에서 저장 좌표계를
          고르면 됨.
        </p>
      )}
      <CrsSelect value={epsg} onChange={setEpsg} />
    </Modal>
  );
}

// ---- 계산 필드 ---------------------------------------------------------------

function FieldDialog({ dialog }: { dialog: Extract<Dialog, { kind: "field" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const updateInfo = useApp((s) => s.updateInfo);
  const [name, setName] = useState("");
  const [expression, setExpression] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!ds) return null;

  const insert = (text: string) => setExpression((e) => (e ? `${e} ${text}` : text));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const info = await engine.addField(ds.info.id, name, expression);
      await updateInfo(info);
      close();
      useApp.getState().notify(`계산 필드 추가함: ${name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const derived = ds.info.columns.filter((c) => c.derived);

  return (
    <Modal
      title="계산 필드 추가"
      onClose={close}
      footer={
        <>
          <button onClick={close}>닫기</button>
          <button className="primary" onClick={submit} disabled={!name.trim() || !expression.trim() || busy}>
            계산
          </button>
        </>
      }
    >
      <div className="form">
        <label>
          새 변수 이름
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 인구밀도" aria-label="새 변수 이름" />
        </label>
        <label>
          식
          <textarea
            rows={3}
            value={expression}
            onChange={(e) => setExpression(e.target.value)}
            placeholder="예: `인구` / `면적` * 1000"
            aria-label="식"
          />
        </label>
      </div>
      <div className="chips">
        {ds.info.columns.map((c) => (
          <button key={c.name} className="chip" onClick={() => insert(`\`${c.name}\``)}>
            {c.name}
          </button>
        ))}
      </div>
      <p className="hint">
        사칙연산, 비교(<code>&gt;</code>, <code>==</code>), <code>log</code>·<code>sqrt</code>·<code>abs</code> 등 수학
        함수를 쓸 수 있음. 비교식은 0/1 변수가 됨. 계산 필드는 프로젝트에 식으로 저장돼 다시 열 때 재계산함.
      </p>
      {error && <p className="error-text">{error}</p>}
      {derived.length > 0 && (
        <>
          <h4>계산 필드</h4>
          <ul className="derived-list">
            {derived.map((c) => (
              <li key={c.name}>
                <code>
                  {c.name} = {c.expression}
                </code>
                <button
                  className="link"
                  onClick={async () => {
                    try {
                      await updateInfo(await engine.deleteField(ds.info.id, c.name));
                    } catch (err) {
                      setError(String(err));
                    }
                  }}
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Modal>
  );
}

// ---- 내보내기 ---------------------------------------------------------------

function ExportDialog({ dialog }: { dialog: Extract<Dialog, { kind: "export" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const notify = useApp((s) => s.notify);
  const fail = useApp((s) => s.fail);
  const [reproject, setReproject] = useState(false);
  const [epsg, setEpsg] = useState<number>(ds?.info.crs?.epsg ?? 5186);
  const [encoding, setEncoding] = useState("UTF-8");
  const [busy, setBusy] = useState(false);
  if (!ds) return null;

  const submit = async () => {
    const path = await pickSavePath(
      EXPORT_FILTERS,
      "내보내기",
      `${dirname(ds.info.path)}/${ds.info.name}_export.gpkg`,
    );
    if (!path) return;
    setBusy(true);
    try {
      const result = await engine.exportDataset(ds.info.id, path, {
        epsg: reproject ? epsg : null,
        encoding: path.toLowerCase().endsWith(".shp") ? encoding : null,
      });
      close();
      notify(`${result.n_rows.toLocaleString()}행을 저장함: ${result.path}`);
      result.warnings.forEach(notify);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="내보내기"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={busy}>
            저장 위치 선택…
          </button>
        </>
      }
    >
      <p className="muted">
        계산 필드를 포함해 저장함. 형식은 파일 확장자로 정함 (gpkg, shp, geojson, fgb, csv).
      </p>
      <div className="form">
        <label className="check">
          <input type="checkbox" checked={reproject} onChange={(e) => setReproject(e.target.checked)} />
          다른 좌표계로 변환해 저장
        </label>
        {reproject && <CrsSelect value={epsg} onChange={setEpsg} />}
        <label>
          shapefile 인코딩
          <select value={encoding} onChange={(e) => setEncoding(e.target.value)}>
            <option value="UTF-8">UTF-8 (권장)</option>
            <option value="CP949">CP949 (구형 국내 프로그램 호환)</option>
          </select>
        </label>
      </div>
    </Modal>
  );
}

// ---- 공간가중치 ---------------------------------------------------------------

const WEIGHT_TYPES: { id: WeightsType; label: string; hint: string }[] = [
  { id: "queen", label: "퀸 인접 (Queen)", hint: "경계나 꼭짓점을 공유하면 이웃 (면 자료)" },
  { id: "rook", label: "룩 인접 (Rook)", hint: "경계를 공유해야 이웃 (면 자료)" },
  { id: "knn", label: "k-최근접 이웃 (KNN)", hint: "중심점 기준 가까운 k개 (점·면 모두)" },
  { id: "distance", label: "거리 임계값", hint: "중심점 거리가 임계값 이내면 이웃" },
  { id: "kernel", label: "커널", hint: "거리에 따라 줄어드는 가중치 (GWR 등에 사용)" },
];

function WeightsDialog({ dialog }: { dialog: Extract<Dialog, { kind: "weights" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const refreshWeights = useApp((s) => s.refreshWeights);
  const notify = useApp((s) => s.notify);
  const polygon = ds?.info.geometry_type === "polygon";
  const [type, setType] = useState<WeightsType>(polygon ? "queen" : "knn");
  const [order, setOrder] = useState(1);
  const [includeLower, setIncludeLower] = useState(true);
  const [k, setK] = useState(6);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [thresholdNote, setThresholdNote] = useState("");
  const [inverse, setInverse] = useState(false);
  const [power, setPower] = useState(1);
  const [fn, setFn] = useState<NonNullable<WeightsSpec["function"]>>("triangular");
  const [fixed, setFixed] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 거리 가중치를 고르면 모든 피처가 이웃을 갖는 최소 거리를 기본값으로 채움
  const datasetId = ds?.info.id;
  useEffect(() => {
    if (type !== "distance" || threshold !== null || !datasetId) return;
    engine
      .weightsThreshold(datasetId)
      .then((t) => {
        setThreshold(Math.ceil(t.threshold * 1000) / 1000);
        setThresholdNote(t.note);
      })
      .catch((e) => setError(String(e?.message ?? e)));
  }, [type, threshold, datasetId]);
  if (!ds) return null;

  const create = async () => {
    const spec: WeightsSpec = { type, name: name || undefined };
    if (type === "queen" || type === "rook") Object.assign(spec, { order, include_lower: includeLower });
    if (type === "knn") spec.k = k;
    if (type === "distance") Object.assign(spec, { threshold, inverse, power });
    if (type === "kernel") Object.assign(spec, { function: fn, k, fixed });
    setBusy(true);
    setError(null);
    try {
      const info = await engine.createWeights(ds.info.id, spec);
      await refreshWeights(ds.info.id, info.id);
      close();
      const s = info.summary;
      notify(
        `가중치 '${info.name}' 만듦: 평균 이웃 ${s.mean_neighbors.toFixed(1)}개` +
          (s.n_islands ? `, 이웃 없는 피처 ${s.n_islands}개 (주의)` : ""),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const load = async () => {
    const path = await pickOpenPath([{ name: "GeoDa 가중치", extensions: ["gal", "gwt", "kwt"] }], "가중치 파일 열기");
    if (!path) return;
    setBusy(true);
    try {
      const info = await engine.loadWeights(ds.info.id, path);
      await refreshWeights(ds.info.id, info.id);
      close();
      notify(`가중치 파일을 불러옴: ${info.name}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="공간가중치 만들기"
      onClose={close}
      footer={
        <>
          <button onClick={load} disabled={busy}>
            파일에서 불러오기 (.gal/.gwt)…
          </button>
          <div className="spacer" />
          <button onClick={close}>취소</button>
          <button className="primary" onClick={create} disabled={busy || (type === "distance" && !threshold)}>
            만들기
          </button>
        </>
      }
    >
      <div className="form">
        <label>
          유형
          <select value={type} onChange={(e) => setType(e.target.value as WeightsType)} aria-label="가중치 유형">
            {WEIGHT_TYPES.map((t) => (
              <option key={t.id} value={t.id} disabled={!polygon && (t.id === "queen" || t.id === "rook")}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">{WEIGHT_TYPES.find((t) => t.id === type)?.hint}</p>
        {(type === "queen" || type === "rook") && (
          <div className="grid2">
            <label>
              인접 차수
              <input type="number" min={1} max={10} value={order} onChange={(e) => setOrder(Number(e.target.value) || 1)} />
            </label>
            {order > 1 && (
              <label className="check">
                <input type="checkbox" checked={includeLower} onChange={(e) => setIncludeLower(e.target.checked)} />
                하위 차수 포함
              </label>
            )}
          </div>
        )}
        {(type === "knn" || type === "kernel") && (
          <label>
            이웃 수 k
            <input type="number" min={1} value={k} onChange={(e) => setK(Math.max(1, Number(e.target.value) || 1))} aria-label="이웃 수" />
          </label>
        )}
        {type === "distance" && (
          <>
            <label>
              거리 임계값
              <input
                type="number"
                value={threshold ?? ""}
                onChange={(e) => setThreshold(Number(e.target.value))}
                aria-label="거리 임계값"
              />
            </label>
            <p className="hint">기본값은 모든 피처가 이웃을 하나 이상 갖는 최소 거리임. {thresholdNote}</p>
            <label className="check">
              <input type="checkbox" checked={inverse} onChange={(e) => setInverse(e.target.checked)} />
              역거리 가중 (가까울수록 큰 가중치)
            </label>
            {inverse && (
              <label>
                거리 지수
                <select value={power} onChange={(e) => setPower(Number(e.target.value))}>
                  <option value={1}>1 (1/d)</option>
                  <option value={2}>2 (1/d²)</option>
                </select>
              </label>
            )}
          </>
        )}
        {type === "kernel" && (
          <div className="grid2">
            <label>
              커널 함수
              <select value={fn} onChange={(e) => setFn(e.target.value as typeof fn)}>
                <option value="triangular">삼각 (triangular)</option>
                <option value="uniform">균등 (uniform)</option>
                <option value="quadratic">이차 (Epanechnikov)</option>
                <option value="quartic">사차 (bisquare)</option>
                <option value="gaussian">가우시안</option>
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={fixed} onChange={(e) => setFixed(e.target.checked)} />
              고정 대역폭
            </label>
          </div>
        )}
        <label>
          이름 (선택)
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="비우면 자동으로 정함" />
        </label>
      </div>
      {error && <p className="error-text">{error}</p>}
    </Modal>
  );
}

// ---- 공통 선택 요소 ---------------------------------------------------------------

function NumericSelect({
  ds,
  value,
  onChange,
  label,
}: {
  ds: LoadedDataset;
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  const cols = ds.info.columns.filter((c) => c.kind === "numeric");
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {cols.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
            {c.origin !== "data" ? " (계산)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

function WeightsSelect({ ds, value, onChange }: { ds: LoadedDataset; value: string; onChange: (v: string) => void }) {
  return (
    <label>
      공간가중치
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="공간가중치">
        {ds.weights.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name} — {w.description}
          </option>
        ))}
      </select>
    </label>
  );
}

function NoWeights({ datasetId }: { datasetId: string }) {
  return (
    <div className="notice-box">
      공간가중치가 아직 없음.{" "}
      <button className="link" onClick={() => useApp.getState().showDialog({ kind: "weights", datasetId })}>
        가중치 만들기…
      </button>
    </div>
  );
}

const firstNumeric = (ds: LoadedDataset | undefined) =>
  ds?.info.columns.find((c) => c.kind === "numeric")?.name ?? "";

// ---- 차트 추가 (Moran 산점도 포함) --------------------------------------------------

const CHART_TITLES: Record<ChartKind, string> = {
  histogram: "히스토그램 추가",
  scatter: "산점도 추가",
  box: "박스플롯 추가",
  moran: "Moran's I · Moran 산점도",
};

function ChartDialog({ dialog }: { dialog: Extract<Dialog, { kind: "chart" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const addChart = useApp((s) => s.addChart);
  const [x, setX] = useState(firstNumeric(ds));
  const [y, setY] = useState(ds?.info.columns.filter((c) => c.kind === "numeric")[1]?.name ?? firstNumeric(ds));
  const [bins, setBins] = useState(10);
  const [bivariate, setBivariate] = useState(false);
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [permutations, setPermutations] = useState(999);
  if (!ds) return null;
  const kind = dialog.chart;
  const needsWeights = kind === "moran";

  const submit = () => {
    close();
    void addChart({
      datasetId: ds.info.id,
      kind,
      x,
      y: kind === "scatter" || (kind === "moran" && bivariate) ? y : null,
      bins,
      weightsId: needsWeights ? weightsId : undefined,
      permutations: needsWeights ? permutations : undefined,
    });
  };

  return (
    <Modal
      title={CHART_TITLES[kind]}
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={!x || (needsWeights && !weightsId)}>
            {kind === "moran" ? "계산" : "추가"}
          </button>
        </>
      }
    >
      <div className="form">
        <NumericSelect ds={ds} value={x} onChange={setX} label={kind === "scatter" ? "X 변수" : "변수"} />
        {kind === "scatter" && <NumericSelect ds={ds} value={y} onChange={setY} label="Y 변수" />}
        {kind === "histogram" && (
          <label>
            구간 수
            <input type="number" min={2} max={100} value={bins} onChange={(e) => setBins(Math.min(100, Math.max(2, Number(e.target.value) || 10)))} />
          </label>
        )}
        {kind === "moran" && (
          <>
            <label className="check">
              <input type="checkbox" checked={bivariate} onChange={(e) => setBivariate(e.target.checked)} />
              이변량 Moran&apos;s I (두 번째 변수의 공간 시차와 비교)
            </label>
            {bivariate && <NumericSelect ds={ds} value={y} onChange={setY} label="두 번째 변수 (공간 시차)" />}
            {ds.weights.length ? <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} /> : <NoWeights datasetId={ds.info.id} />}
            <PermutationSelect value={permutations} onChange={setPermutations} />
          </>
        )}
      </div>
    </Modal>
  );
}

function PermutationSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <label>
      순열 횟수 (유사 p값 계산)
      <select value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label="순열 횟수">
        {[99, 199, 499, 999, 9999].map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---- 국지 공간통계 -------------------------------------------------------------

const LOCAL_METHODS: { id: LocalMethod; label: string; prefix: string; hint: string }[] = [
  { id: "lisa", label: "Local Moran (LISA)", prefix: "LISA", hint: "High-High·Low-Low 군집과 High-Low·Low-High 이상치를 찾음" },
  { id: "lisa_bv", label: "이변량 LISA", prefix: "BLISA", hint: "한 변수 값과 주변의 다른 변수 값 사이의 국지적 연관" },
  { id: "gi_star", label: "Getis-Ord Gi*", prefix: "GISTAR", hint: "값이 높은 곳이 모인 핫스팟과 낮은 곳의 콜드스팟" },
  { id: "local_geary", label: "Local Geary", prefix: "LGEARY", hint: "주변과 값이 비슷한지(양의 연관) 다른지(음의 연관)" },
];

function LocalDialog({ dialog }: { dialog: Extract<Dialog, { kind: "local" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const runLocal = useApp((s) => s.runLocal);
  const busy = useApp((s) => s.busy);
  const [method, setMethod] = useState<LocalMethod>("lisa");
  const [x, setX] = useState(firstNumeric(ds));
  const [y, setY] = useState(ds?.info.columns.filter((c) => c.kind === "numeric")[1]?.name ?? firstNumeric(ds));
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [permutations, setPermutations] = useState(999);
  const [alpha, setAlpha] = useState(0.05);
  const [correction, setCorrection] = useState<"none" | "fdr" | "bonferroni">("none");
  const [prefix, setPrefix] = useState("");
  if (!ds) return null;
  const meta = LOCAL_METHODS.find((m) => m.id === method)!;

  const submit = async () => {
    const ok = await runLocal(ds.info.id, {
      method,
      column: x,
      column_y: method === "lisa_bv" ? y : null,
      weights_id: weightsId,
      permutations,
      alpha,
      correction,
      prefix: prefix.trim() || meta.prefix,
    });
    if (ok) close();
  };

  return (
    <Modal
      title="국지 공간자기상관"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={!x || !weightsId || !!busy}>
            {busy ? "계산 중…" : "실행"}
          </button>
        </>
      }
    >
      <div className="form">
        <label>
          방법
          <select value={method} onChange={(e) => setMethod(e.target.value as LocalMethod)} aria-label="국지 통계 방법">
            {LOCAL_METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">{meta.hint}</p>
        <NumericSelect ds={ds} value={x} onChange={setX} label={method === "lisa_bv" ? "변수 (자기 값)" : "변수"} />
        {method === "lisa_bv" && <NumericSelect ds={ds} value={y} onChange={setY} label="두 번째 변수 (주변 값)" />}
        {ds.weights.length ? <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} /> : <NoWeights datasetId={ds.info.id} />}
        <div className="grid2">
          <PermutationSelect value={permutations} onChange={setPermutations} />
          <label>
            유의수준 α
            <select value={alpha} onChange={(e) => setAlpha(Number(e.target.value))} aria-label="유의수준">
              {[0.1, 0.05, 0.01, 0.001].map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label>
            다중검정 보정
            <select value={correction} onChange={(e) => setCorrection(e.target.value as typeof correction)} aria-label="다중검정 보정">
              <option value="none">없음</option>
              <option value="fdr">FDR (Benjamini-Hochberg)</option>
              <option value="bonferroni">Bonferroni</option>
            </select>
          </label>
          <label>
            결과 열 접두어
            <input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder={meta.prefix} />
          </label>
        </div>
        <p className="hint">
          결과는 {prefix || meta.prefix}_I(통계량)·_CL(군집 코드)·_P(유사 p값) 열로 저장되고 군집 지도로 표시됨. 같은
          접두어로 다시 실행하면 이전 결과를 대체함. 난수 시드는 GeoDa 기본값(123456789)으로 고정해 결과가 재현됨.
        </p>
      </div>
    </Modal>
  );
}

// ---- Join Count (이진 변수) -------------------------------------------------------

function JoinCountDialog({ dialog }: { dialog: Extract<Dialog, { kind: "joincount" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const [x, setX] = useState(firstNumeric(ds));
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [permutations, setPermutations] = useState(999);
  const [result, setResult] = useState<JoinCountResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!ds) return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await engine.joinCount(ds.info.id, { column: x, weights_id: weightsId, permutations }));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const p = (v?: number) => (v === undefined ? "–" : v < 0.001 ? v.toExponential(1) : v.toFixed(3));

  return (
    <Modal
      title="Join Count (이진 변수)"
      onClose={close}
      footer={
        <>
          <button onClick={close}>닫기</button>
          <button className="primary" onClick={run} disabled={!x || !weightsId || busy}>
            {busy ? "계산 중…" : "계산"}
          </button>
        </>
      }
    >
      <div className="form">
        <NumericSelect ds={ds} value={x} onChange={setX} label="이진 변수 (0/1)" />
        {ds.weights.length ? <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} /> : <NoWeights datasetId={ds.info.id} />}
        <PermutationSelect value={permutations} onChange={setPermutations} />
      </div>
      <p className="hint">
        1끼리 이웃한 쌍(BB)이 무작위 배치일 때보다 많으면 1이 뭉쳐 있다는 뜻임. 이진 가중치(인접 여부)로 셈.
      </p>
      {error && <p className="error-text">{error}</p>}
      {result && (
        <table className="result-table" data-testid="joincount-result">
          <thead>
            <tr>
              <th>이웃 쌍</th>
              <th>관측</th>
              <th>기댓값(순열 평균)</th>
              <th>유사 p</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>1–1 (BB)</td>
              <td>{result.bb.toLocaleString()}</td>
              <td>{result.mean_bb?.toFixed(1) ?? "–"}</td>
              <td>{p(result.p_sim_bb)}</td>
            </tr>
            <tr>
              <td>1–0 (BW)</td>
              <td>{result.bw.toLocaleString()}</td>
              <td>{result.mean_bw?.toFixed(1) ?? "–"}</td>
              <td>{p(result.p_sim_bw)}</td>
            </tr>
            <tr>
              <td>0–0 (WW)</td>
              <td>{result.ww.toLocaleString()}</td>
              <td>–</td>
              <td>–</td>
            </tr>
          </tbody>
        </table>
      )}
    </Modal>
  );
}

// ---- 회귀 분석 ---------------------------------------------------------------

const REG_MODELS: { id: RegressionModel; label: string; hint: string }[] = [
  { id: "ols", label: "OLS (최소제곱)", hint: "기본 회귀. 가중치를 고르면 잔차 Moran's I와 LM 검정으로 공간 의존성을 진단함" },
  { id: "lag", label: "공간시차 모형 (Spatial Lag)", hint: "주변 지역의 종속변수 값이 영향을 주는 경우 (y = ρWy + Xβ + ε)" },
  { id: "error", label: "공간오차 모형 (Spatial Error)", hint: "빠진 변수 등으로 오차가 공간적으로 얽힌 경우 (u = λWu + ε)" },
  {
    id: "lag_gm",
    label: "공간시차 모형 — GM (2SLS)",
    hint: "공간시차 모형을 도구변수(WX)로 추정함. 정규성 가정이 없고 대용량에서 빠름. 로그우도·AICc는 없음",
  },
  {
    id: "error_gm",
    label: "공간오차 모형 — GM (이분산 강건)",
    hint: "공간오차 모형을 일반화 적률법으로 추정함. 이분산이 있어도 표준오차가 유효함. 로그우도·AICc는 없음",
  },
  { id: "gwr", label: "지리가중회귀 (GWR)", hint: "계수가 지역마다 다르다고 보고 위치별 회귀를 추정함. 모든 변수가 같은 대역폭을 씀" },
  { id: "mgwr", label: "다중척도 GWR (MGWR)", hint: "변수마다 다른 대역폭(영향 범위)을 추정함. 계산이 오래 걸림" },
];

function RegressionDialog({ dialog }: { dialog: Extract<Dialog, { kind: "regression" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const job = useApp((s) => s.job);
  const startRegression = useApp((s) => s.startRegression);
  const numeric = ds?.info.columns.filter((c) => c.kind === "numeric" && c.origin !== "analysis") ?? [];
  const [model, setModel] = useState<RegressionModel>("ols");
  const [y, setY] = useState(numeric[0]?.name ?? "");
  const [xs, setXs] = useState<string[]>([]);
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [useWeights, setUseWeights] = useState(true);
  const [kernel, setKernel] = useState<NonNullable<RegressionSpec["kernel"]>>("bisquare");
  const [fixed, setFixed] = useState(false);
  const [criterion, setCriterion] = useState<NonNullable<RegressionSpec["criterion"]>>("AICc");
  const [manualBw, setManualBw] = useState("");
  const [prefix, setPrefix] = useState("");
  const [robust, setRobust] = useState(false);
  if (!ds) return null;
  const meta = REG_MODELS.find((m) => m.id === model)!;
  const isGwr = model === "gwr" || model === "mgwr";
  const needsWeights = !isGwr && model !== "ols";
  const n = ds.info.n_rows;
  const heavy = (model === "gwr" && n > 10000) || (model === "mgwr" && n > 5000);

  const toggleX = (name: string) =>
    setXs((cur) => (cur.includes(name) ? cur.filter((c) => c !== name) : [...cur, name]));

  const submit = () => {
    const spec: RegressionSpec = {
      model,
      y,
      x: xs,
      weights_id: (needsWeights || useWeights) && weightsId ? weightsId : null,
      prefix: prefix.trim() || null,
    };
    if (model === "ols" && robust) spec.robust = "white";
    if (isGwr) {
      Object.assign(spec, { kernel, fixed, criterion });
      if (model === "gwr" && manualBw) spec.bandwidth = Number(manualBw);
    }
    close();
    void startRegression(ds.info.id, spec);
  };

  const canRun = !!y && xs.length > 0 && !xs.includes(y) && (!needsWeights || !!weightsId) && !job;

  return (
    <Modal
      title="회귀 분석"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={!canRun}>
            실행
          </button>
        </>
      }
    >
      <div className="form">
        <label>
          모형
          <select value={model} onChange={(e) => setModel(e.target.value as RegressionModel)} aria-label="회귀 모형">
            {REG_MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">{meta.hint}</p>
        <label>
          종속변수 (y)
          <select value={y} onChange={(e) => setY(e.target.value)} aria-label="종속변수">
            {numeric.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <div className="field-label">독립변수 (x) — {xs.length}개 선택</div>
        <div className="var-list" role="group" aria-label="독립변수">
          {numeric
            .filter((c) => c.name !== y)
            .map((c) => (
              <label key={c.name} className="check">
                <input type="checkbox" checked={xs.includes(c.name)} onChange={() => toggleX(c.name)} />
                {c.name}
                {c.origin === "expression" ? " (계산)" : ""}
              </label>
            ))}
        </div>
        {model === "ols" && (
          <label className="check">
            <input type="checkbox" checked={robust} onChange={(e) => setRobust(e.target.checked)} />
            White 이분산 강건 표준오차
          </label>
        )}
        {ds.weights.length ? (
          <>
            {!needsWeights && (
              <label className="check">
                <input type="checkbox" checked={useWeights} onChange={(e) => setUseWeights(e.target.checked)} />
                {isGwr ? "잔차 공간 자기상관 진단 (Moran's I)" : "공간 진단 (잔차 Moran's I, LM 검정)"}
              </label>
            )}
            {(needsWeights || useWeights) && <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} />}
          </>
        ) : needsWeights ? (
          <NoWeights datasetId={ds.info.id} />
        ) : (
          <p className="hint">공간가중치를 만들면 잔차의 공간 의존성도 진단할 수 있음 (모형 비교표에 표시됨).</p>
        )}
        {isGwr && (
          <div className="grid2">
            <label>
              커널
              <select value={kernel} onChange={(e) => setKernel(e.target.value as typeof kernel)} aria-label="커널">
                <option value="bisquare">bisquare (권장)</option>
                <option value="gaussian">gaussian</option>
                <option value="exponential">exponential</option>
              </select>
            </label>
            <label>
              대역폭 선택 기준
              <select value={criterion} onChange={(e) => setCriterion(e.target.value as typeof criterion)}>
                <option value="AICc">AICc (권장)</option>
                <option value="AIC">AIC</option>
                <option value="BIC">BIC</option>
                <option value="CV">교차검증 (CV)</option>
              </select>
            </label>
            <label className="check span2">
              <input type="checkbox" checked={fixed} onChange={(e) => setFixed(e.target.checked)} />
              고정 대역폭 (거리). 끄면 적응 대역폭 (이웃 수)
            </label>
            {model === "gwr" && (
              <label className="span2">
                대역폭 직접 지정 (비우면 자동 탐색)
                <input
                  type="number"
                  value={manualBw}
                  onChange={(e) => setManualBw(e.target.value)}
                  placeholder={fixed ? "거리 (m)" : "이웃 수"}
                />
              </label>
            )}
          </div>
        )}
        <label>
          결과 열 접두어
          <input
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            placeholder={
              { ols: "OLS", lag: "LAG", error: "ERR", lag_gm: "LAGGM", error_gm: "ERRGM", gwr: "GWR", mgwr: "MGWR" }[
                model
              ]
            }
          />
        </label>
      </div>
      {heavy && (
        <p className="hint warn-text">
          관측치가 {n.toLocaleString()}개라 계산이 오래 걸릴 수 있음. 진행 중에 하단 상태 표시줄에서 취소할 수 있음.
        </p>
      )}
      {job && <p className="hint">다른 분석이 실행 중임. 끝난 뒤에 실행할 수 있음.</p>}
      <p className="hint">
        예측값·잔차{isGwr ? "·지역 계수(_B_)·t값(_T_)·유의 여부(_SIG_)·지역 R²" : ""}가 새 열로 저장되고, 결과
        보고서는 오른쪽 결과 패널에 표시됨.
      </p>
    </Modal>
  );
}

// ---- 군집 분석 ---------------------------------------------------------------

const CLUSTER_METHODS: {
  id: ClusterMethod;
  label: string;
  spatial: boolean;
  hint: string;
}[] = [
  {
    id: "skater",
    label: "SKATER",
    spatial: true,
    hint: "이웃 그래프의 최소 신장 트리를 잘라 연결된 지역으로 나눔. 빠르고 안정적임",
  },
  {
    id: "maxp",
    label: "Max-p 지역화",
    spatial: true,
    hint: "지역마다 최소 합계(예: 인구 5만 이상)를 만족하면서 지역 수가 최대가 되게 나눔. 군집 수는 자동으로 정해짐. 계산이 무거움 (500개 이하 권장)",
  },
  {
    id: "azp",
    label: "AZP (자동 구역화)",
    spatial: true,
    hint: "경계 피처를 이웃 지역으로 옮겨 가며 지역 내 차이를 줄임. 시작점에 따라 결과가 달라질 수 있음 (시드 고정). 1,000개 이하 권장",
  },
  {
    id: "region_kmeans",
    label: "Region K-Means",
    spatial: true,
    hint: "연결 제약을 둔 K-평균. 관측치가 많으면 매우 느림 (1,000개 이하 권장)",
  },
  {
    id: "ward_spatial",
    label: "Ward 계층 군집 (공간 제약)",
    spatial: true,
    hint: "이웃끼리만 병합하는 Ward 계층 군집. 대용량에서도 빠름",
  },
  {
    id: "kmeans",
    label: "K-평균 (비공간)",
    spatial: false,
    hint: "위치를 고려하지 않는 K-평균. 공간 제약 결과와 비교하는 용도임",
  },
  {
    id: "hierarchical",
    label: "계층적 군집 Ward (비공간)",
    spatial: false,
    hint: "위치를 고려하지 않는 Ward 계층 군집",
  },
];

function ClusterDialog({ dialog }: { dialog: Extract<Dialog, { kind: "cluster" }> }) {
  const ds = useApp((s) => s.datasets[dialog.datasetId]);
  const job = useApp((s) => s.job);
  const startCluster = useApp((s) => s.startCluster);
  const numeric = ds?.info.columns.filter((c) => c.kind === "numeric" && c.origin !== "analysis") ?? [];
  const [method, setMethod] = useState<ClusterMethod>("skater");
  const [vars, setVars] = useState<string[]>([]);
  const [k, setK] = useState("5");
  const [weightsId, setWeightsId] = useState(ds?.activeWeightsId ?? ds?.weights[0]?.id ?? "");
  const [useWeights, setUseWeights] = useState(true);
  const [standardize, setStandardize] = useState(true);
  const [floor, setFloor] = useState("");
  const [thresholdColumn, setThresholdColumn] = useState("");
  const [threshold, setThreshold] = useState("");
  const [prefix, setPrefix] = useState("");
  if (!ds) return null;
  const meta = CLUSTER_METHODS.find((m) => m.id === method)!;
  const isMaxp = method === "maxp";
  const n = ds.info.n_rows;
  // 권장 관측치 수 (1,600개 격자 기준 AZP 약 3분, Max-p 10분 이상)
  const slowLimit: Partial<Record<ClusterMethod, number>> = { maxp: 500, azp: 1000, region_kmeans: 1000, skater: 5000 };
  const slow = n > (slowLimit[method] ?? Infinity);

  const toggle = (name: string) =>
    setVars((cur) => (cur.includes(name) ? cur.filter((c) => c !== name) : [...cur, name]));

  const kNum = Number(k);
  const thresholdNum = Number(threshold);
  const canRun =
    vars.length > 0 &&
    (!meta.spatial || !!weightsId) &&
    (isMaxp ? thresholdNum > 0 : Number.isInteger(kNum) && kNum >= 2 && kNum < n) &&
    !job;

  const submit = () => {
    const spec: ClusterSpec = {
      method,
      variables: vars,
      standardize,
      weights_id: (meta.spatial || useWeights) && weightsId ? weightsId : null,
      prefix: prefix.trim() || null,
    };
    if (isMaxp) {
      spec.threshold = thresholdNum;
      spec.threshold_column = thresholdColumn || null;
    } else {
      spec.n_clusters = kNum;
    }
    if (method === "skater" && floor) spec.floor = Number(floor);
    close();
    void startCluster(ds.info.id, spec);
  };

  return (
    <Modal
      title="군집 분석"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={!canRun}>
            실행
          </button>
        </>
      }
    >
      <div className="form">
        <label>
          방법
          <select value={method} onChange={(e) => setMethod(e.target.value as ClusterMethod)} aria-label="군집 방법">
            <optgroup label="공간 제약 (지역화)">
              {CLUSTER_METHODS.filter((m) => m.spatial).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </optgroup>
            <optgroup label="비공간 (비교용)">
              {CLUSTER_METHODS.filter((m) => !m.spatial).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
        <p className="hint">{meta.hint}</p>
        <div className="field-label">변수 — {vars.length}개 선택</div>
        <div className="var-list" role="group" aria-label="군집 변수">
          {numeric.map((c) => (
            <label key={c.name} className="check">
              <input type="checkbox" checked={vars.includes(c.name)} onChange={() => toggle(c.name)} />
              {c.name}
              {c.origin === "expression" ? " (계산)" : ""}
            </label>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={standardize} onChange={(e) => setStandardize(e.target.checked)} />
          변수 표준화 (z점수) — 단위가 다른 변수를 함께 쓸 때 권장
        </label>
        {isMaxp ? (
          <div className="grid2">
            <label>
              임계값 변수
              <select
                value={thresholdColumn}
                onChange={(e) => setThresholdColumn(e.target.value)}
                aria-label="임계값 변수"
              >
                <option value="">피처 수</option>
                {numeric.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              지역별 최소 합계
              <input
                type="number"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                placeholder={thresholdColumn ? "예: 50000" : "예: 10 (피처 수)"}
                aria-label="최소 합계"
              />
            </label>
          </div>
        ) : (
          <div className="grid2">
            <label>
              군집 수
              <input type="number" min={2} value={k} onChange={(e) => setK(e.target.value)} aria-label="군집 수" />
            </label>
            {method === "skater" && (
              <label>
                군집별 최소 피처 수
                <input
                  type="number"
                  min={1}
                  value={floor}
                  onChange={(e) => setFloor(e.target.value)}
                  placeholder="제한 없음"
                />
              </label>
            )}
          </div>
        )}
        {ds.weights.length ? (
          <>
            {!meta.spatial && (
              <label className="check">
                <input type="checkbox" checked={useWeights} onChange={(e) => setUseWeights(e.target.checked)} />
                공간 조각 수 계산 (군집이 몇 덩어리로 흩어졌는지)
              </label>
            )}
            {(meta.spatial || useWeights) && <WeightsSelect ds={ds} value={weightsId} onChange={setWeightsId} />}
          </>
        ) : meta.spatial ? (
          <NoWeights datasetId={ds.info.id} />
        ) : null}
        <label>
          결과 열 접두어
          <input
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            placeholder={
              {
                skater: "SKATER",
                maxp: "MAXP",
                azp: "AZP",
                region_kmeans: "RKM",
                ward_spatial: "WARDSP",
                kmeans: "KMEANS",
                hierarchical: "HCLUST",
              }[method]
            }
          />
        </label>
      </div>
      {slow && (
        <p className="hint warn-text">
          관측치가 {n.toLocaleString()}개라 계산이 오래 걸릴 수 있음. 진행 중에 하단 상태 표시줄에서 취소할 수 있음.
        </p>
      )}
      {job && <p className="hint">다른 분석이 실행 중임. 끝난 뒤에 실행할 수 있음.</p>}
      <p className="hint">군집 번호(_GRP, 큰 군집부터 1번)가 새 열로 저장되고, 요약은 오른쪽 결과 패널에 표시됨.</p>
    </Modal>
  );
}

// ---- 존 통계 -----------------------------------------------------------------

const ZONAL_STATS: { id: ZonalStat; label: string }[] = [
  { id: "mean", label: "평균" },
  { id: "min", label: "최솟값" },
  { id: "max", label: "최댓값" },
  { id: "stdev", label: "표준편차" },
  { id: "sum", label: "합계" },
  { id: "median", label: "중앙값" },
  { id: "q25", label: "하위 25%" },
  { id: "q75", label: "상위 25%" },
  { id: "count", label: "셀 수 (면적 가중)" },
  { id: "majority", label: "최빈값 (범주 자료)" },
  { id: "variety", label: "값 종류 수 (범주 자료)" },
];

function ZonalDialog({ datasetId }: { datasetId: string }) {
  const ds = useApp((s) => s.datasets[datasetId]);
  const rasters = useApp((s) => s.rasters);
  const rasterOrder = useApp((s) => s.rasterOrder);
  const job = useApp((s) => s.job);
  const startZonal = useApp((s) => s.startZonal);
  const [rasterId, setRasterId] = useState(rasterOrder[0] ?? "");
  const raster = rasters[rasterId];
  const [band, setBand] = useState(1);
  const [stats, setStats] = useState<ZonalStat[]>(
    raster?.info.categorical ? ["majority", "variety", "count"] : ["mean", "min", "max", "stdev", "count"],
  );
  const [prefix, setPrefix] = useState("");
  if (!ds) return null;
  const isPolygon = ds.info.geometry_type === "polygon";
  const toggle = (id: ZonalStat) => setStats((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const canRun = isPolygon && !!raster && stats.length > 0 && !job;

  const submit = () => {
    close();
    // 고른 순서가 아니라 목록 순서로 열을 만듦
    const ordered = ZONAL_STATS.map((s) => s.id).filter((id) => stats.includes(id));
    void startZonal(ds.info.id, { raster_id: rasterId, band, stats: ordered, prefix: prefix.trim() || null });
  };

  return (
    <Modal
      title="존 통계"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={submit} disabled={!canRun}>
            실행
          </button>
        </>
      }
    >
      <div className="form">
        <p className="hint">
          {ds.info.name}의 폴리곤마다 래스터 값을 요약해 새 열로 붙임. 셀이 폴리곤에 걸친 면적 비율로 가중함
          (exactextract).
        </p>
        {!isPolygon && <p className="hint warn-text">폴리곤 레이어에만 쓸 수 있음. 먼저 격자를 만들어 쓸 수 있음.</p>}
        <div className="grid2">
          <label>
            래스터
            <select
              value={rasterId}
              onChange={(e) => {
                setRasterId(e.target.value);
                setBand(1);
              }}
              aria-label="래스터"
            >
              {rasterOrder.map((id) => (
                <option key={id} value={id}>
                  {rasters[id]?.info.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            밴드
            <select value={band} onChange={(e) => setBand(Number(e.target.value))} aria-label="밴드">
              {raster?.info.band_names.map((name, i) => (
                <option key={i} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field-label">통계 — {stats.length}개 선택</div>
        <div className="var-list" role="group" aria-label="존 통계 항목">
          {ZONAL_STATS.map((s) => (
            <label key={s.id} className="check">
              <input type="checkbox" checked={stats.includes(s.id)} onChange={() => toggle(s.id)} />
              {s.label}
            </label>
          ))}
        </div>
        <label>
          결과 열 접두어
          <input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="ZS" />
        </label>
      </div>
      {job && <p className="hint">다른 분석이 실행 중임. 끝난 뒤에 실행할 수 있음.</p>}
      <p className="hint">결과 열: 접두어_MEAN, 접두어_MIN 등. 래스터 밖이거나 값이 없는 폴리곤은 빈 값이 됨.</p>
    </Modal>
  );
}

// ---- 격자 만들기 ---------------------------------------------------------------

function FishnetDialog() {
  const datasets = useApp((s) => s.datasets);
  const order = useApp((s) => s.order);
  const activeId = useApp((s) => s.activeId);
  const rasters = useApp((s) => s.rasters);
  const rasterOrder = useApp((s) => s.rasterOrder);
  const makeFishnet = useApp((s) => s.makeFishnet);
  const startZonal = useApp((s) => s.startZonal);
  const job = useApp((s) => s.job);
  // 범위 원본: "d:<데이터셋 id>" 또는 "r:<래스터 id>"
  const [source, setSource] = useState(
    rasterOrder[0] ? `r:${rasterOrder[0]}` : activeId ? `d:${activeId}` : `d:${order[0] ?? ""}`,
  );
  const [cellSize, setCellSize] = useState("1000");
  const [shape, setShape] = useState<"square" | "hexagon">("square");
  const [clip, setClip] = useState(true);
  const [zonalRaster, setZonalRaster] = useState(rasterOrder[0] ?? "");
  const [withZonal, setWithZonal] = useState(rasterOrder.length > 0);
  const [kind, id] = [source.slice(0, 1), source.slice(2)];
  const sourceDs = kind === "d" ? datasets[id] : undefined;
  const sourceRaster = kind === "r" ? rasters[id] : undefined;
  const size = Number(cellSize);
  const sourceName = sourceDs?.info.name ?? sourceRaster?.info.name ?? "격자";
  const basePath = sourceDs?.info.path ?? sourceRaster?.info.path ?? "";

  // 대략적인 셀 수 (m 단위 좌표계 기준 범위 / 셀 면적). 경위도 범위는 1도 ≈ 111 km로 환산함
  const estimate = (() => {
    const b = sourceDs?.info.bounds_wgs84 ?? sourceRaster?.info.bounds_wgs84;
    if (!b || !(size > 0)) return null;
    const lat = (b[1] + b[3]) / 2;
    const w = (b[2] - b[0]) * 111_320 * Math.cos((lat * Math.PI) / 180);
    const h = (b[3] - b[1]) * 110_540;
    const area = shape === "square" ? size * size : ((3 * Math.sqrt(3)) / 2) * size * size;
    return Math.round((w * h) / area);
  })();

  const submit = async () => {
    const path = await pickSavePath(
      [{ name: "GeoPackage", extensions: ["gpkg"] }],
      "격자 저장 위치",
      `${dirname(basePath)}/${sourceName}_${shape === "hexagon" ? "육각" : "격자"}${cellSize}m.gpkg`,
    );
    if (!path) return;
    close();
    const newId = await makeFishnet({
      dataset_id: kind === "d" ? id : null,
      raster_id: kind === "r" ? id : null,
      cell_size: size,
      shape,
      clip,
      path,
    });
    if (newId && withZonal && zonalRaster) {
      const info = rasters[zonalRaster]?.info;
      const stats: ZonalStat[] = info?.categorical ? ["majority", "variety", "count"] : ["mean", "min", "max", "stdev", "count"];
      await startZonal(newId, { raster_id: zonalRaster, band: 1, stats });
    }
  };

  return (
    <Modal
      title="격자 만들기"
      onClose={close}
      footer={
        <>
          <button onClick={close}>취소</button>
          <button className="primary" onClick={() => void submit()} disabled={!(size > 0) || !basePath || !!job}>
            만들기…
          </button>
        </>
      }
    >
      <div className="form">
        <p className="hint">
          자료 범위를 덮는 격자를 GeoPackage로 저장하고 새 레이어로 엶. 래스터를 격자로 집계하면 ESDA(LISA 등)를
          적용할 수 있음.
        </p>
        <label>
          범위
          <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="격자 범위">
            {rasterOrder.map((rid) => (
              <option key={rid} value={`r:${rid}`}>
                래스터: {rasters[rid]?.info.name}
              </option>
            ))}
            {order.map((did) => (
              <option key={did} value={`d:${did}`}>
                레이어: {datasets[did]?.info.name}
              </option>
            ))}
          </select>
        </label>
        <div className="grid2">
          <label>
            모양
            <select value={shape} onChange={(e) => setShape(e.target.value as typeof shape)} aria-label="격자 모양">
              <option value="square">정사각형</option>
              <option value="hexagon">육각형</option>
            </select>
          </label>
          <label>
            {shape === "square" ? "셀 크기 (m)" : "한 변 길이 (m)"}
            <input type="number" min={1} value={cellSize} onChange={(e) => setCellSize(e.target.value)} aria-label="셀 크기" />
          </label>
        </div>
        {estimate !== null && (
          <p className={`hint ${estimate > 500_000 ? "warn-text" : ""}`}>
            약 {estimate.toLocaleString()}개 셀{estimate > 500_000 ? " — 너무 많으면 표시·분석이 느려짐" : ""}
          </p>
        )}
        {sourceDs?.info.geometry_type === "polygon" && (
          <label className="check">
            <input type="checkbox" checked={clip} onChange={(e) => setClip(e.target.checked)} />
            폴리곤과 겹치는 셀만 남기기
          </label>
        )}
        {rasterOrder.length > 0 && (
          <>
            <label className="check">
              <input type="checkbox" checked={withZonal} onChange={(e) => setWithZonal(e.target.checked)} />
              만든 뒤 바로 존 통계 계산 (평균·최솟값·최댓값·표준편차)
            </label>
            {withZonal && (
              <label>
                존 통계 래스터
                <select value={zonalRaster} onChange={(e) => setZonalRaster(e.target.value)} aria-label="존 통계 래스터">
                  {rasterOrder.map((rid) => (
                    <option key={rid} value={rid}>
                      {rasters[rid]?.info.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
