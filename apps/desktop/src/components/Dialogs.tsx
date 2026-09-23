// 대화상자 모음: 레이어 선택, 표 불러오기(X·Y), 좌표계 지정, 계산 필드, 내보내기

import { useState, type ReactNode } from "react";

import { CRS_PRESETS } from "../lib/crs";
import { EXPORT_FILTERS, dirname, pickSavePath } from "../lib/dialogs";
import { engine, type FileInspection } from "../lib/engine";
import { useApp, type Dialog } from "../store";

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
