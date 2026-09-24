// 아래쪽 패널: 속성 테이블
//
// 수십만 행을 다루므로 화면에 보이는 행만 그리고(가상 스크롤), 엔진에서 200행 단위로 받아 캐시함.
// 행을 클릭하면 지도 선택과 연동되고, 지도에서 선택하면 테이블 행이 강조됨.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { t } from "../i18n";
import { maskToIds } from "../lib/binary";
import { engine, type RowsPage } from "../lib/engine";
import { useActive, useApp, type LoadedDataset } from "../store";

const ROW_HEIGHT = 24;
const PAGE_SIZE = 200;
const OVERSCAN = 10;

interface Props {
  height: number;
}

export function AttributeTable({ height }: Props) {
  const ds = useActive();
  if (!ds) {
    return (
      <section className="table-panel" style={{ height }}>
        <div className="muted pad">{t("데이터를 열면 속성 테이블이 표시됨")}</div>
      </section>
    );
  }
  return <TableView key={ds.info.id} ds={ds} height={height} />;
}

function TableView({ ds, height }: { ds: LoadedDataset; height: number }) {
  const select = useApp((s) => s.select);
  const showDialog = useApp((s) => s.showDialog);
  const fail = useApp((s) => s.fail);
  const [sort, setSort] = useState<{ column: string; desc: boolean } | null>(null);
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const [pages, setPages] = useState<Map<number, RowsPage>>(new Map());
  const [total, setTotal] = useState(ds.info.n_rows);
  const loading = useRef(new Set<number>());
  // 조회 조건이 바뀐 뒤 늦게 도착한 이전 응답을 버리기 위한 세대 번호
  const generation = useRef(0);
  const scroller = useRef<HTMLDivElement>(null);

  const id = ds.info.id;
  const columns = ds.info.columns;
  // "선택 항목만" 모드에서는 선택이 바뀔 때마다 조회 조건이 바뀜
  const filterIds = useMemo(
    () => (selectedOnly ? maskToIds(ds.selection) : null),
    [selectedOnly, ds.selection],
  );
  const queryKey = `${ds.revision}|${sort?.column}|${sort?.desc}|${selectedOnly ? ds.selection.length + ":" + ds.selectedCount : ""}`;

  // 조회 조건이 바뀌면 캐시를 비움
  useEffect(() => {
    generation.current += 1;
    setPages(new Map());
    loading.current.clear();
    setTotal(filterIds ? filterIds.length : ds.info.n_rows);
    scroller.current?.scrollTo({ top: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, filterIds]);

  const bodyHeight = height - 64; // 도구줄·머리행 높이 제외
  const first = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const last = Math.min(total, Math.ceil((scrollTop + bodyHeight) / ROW_HEIGHT) + OVERSCAN);

  // 보이는 범위의 페이지를 불러옴
  useEffect(() => {
    const needed = new Set<number>();
    for (let r = first; r < last; r += 1) needed.add(Math.floor(r / PAGE_SIZE));
    needed.forEach((p) => {
      if (pages.has(p) || loading.current.has(p)) return;
      loading.current.add(p);
      const gen = generation.current;
      engine
        .rows(id, {
          offset: p * PAGE_SIZE,
          limit: PAGE_SIZE,
          sort: sort?.column,
          descending: sort?.desc,
          ids: filterIds,
        })
        .then((page) => {
          if (gen !== generation.current) return;
          setPages((prev) => new Map(prev).set(p, page));
          setTotal(page.total);
        })
        .catch(fail)
        .finally(() => loading.current.delete(p));
    });
  }, [first, last, pages, id, sort, filterIds, fail]);

  const rowAt = useCallback(
    (r: number): { rowId: number; values: unknown[] } | null => {
      const page = pages.get(Math.floor(r / PAGE_SIZE));
      if (!page) return null;
      const k = r - page.offset;
      return { rowId: page.row_ids[k], values: page.rows[k] };
    },
    [pages],
  );

  const onRowClick = (rowId: number, e: React.MouseEvent) => {
    select(id, [rowId], e.metaKey || e.ctrlKey ? "toggle" : "replace");
  };

  const toggleSort = (column: string) =>
    setSort((s) => (s?.column !== column ? { column, desc: false } : s.desc ? null : { column, desc: true }));

  const rows = [];
  for (let r = first; r < last; r++) {
    const row = rowAt(r);
    const selected = row ? ds.selection[row.rowId] === 1 : false;
    rows.push(
      <div
        key={r}
        className={`tr${selected ? " selected" : ""}`}
        style={{ top: r * ROW_HEIGHT }}
        onClick={row ? (e) => onRowClick(row.rowId, e) : undefined}
      >
        <div className="td rownum">{row ? row.rowId + 1 : ""}</div>
        {columns.map((c, j) => (
          <div key={c.name} className={`td ${c.kind === "numeric" ? "num" : ""}`}>
            {row ? formatCell(row.values[j]) : "…"}
          </div>
        ))}
      </div>,
    );
  }

  return (
    <section className="table-panel" style={{ height }} data-testid="attribute-table">
      <div className="table-toolbar">
        <strong>{ds.info.name}</strong>
        <span className="muted">
          {selectedOnly ? t("선택 {n}행", { n: total }) : t("{n}행", { n: total })}
          {!selectedOnly && ds.selectedCount > 0 && ` · ${t("선택 {n}", { n: ds.selectedCount })}`}
        </span>
        <label className="check">
          <input
            type="checkbox"
            checked={selectedOnly}
            onChange={(e) => setSelectedOnly(e.target.checked)}
          />
          {t("선택 항목만")}
        </label>
        <div className="spacer" />
        <button onClick={() => showDialog({ kind: "query", datasetId: id })} title={t("속성 조건으로 피처를 선택함")}>
          {t("조건 선택…")}
        </button>
        <button onClick={() => showDialog({ kind: "field", datasetId: id })}>{t("계산 필드 추가…")}</button>
        <button onClick={() => showDialog({ kind: "export", datasetId: id })}>{t("내보내기…")}</button>
      </div>
      <div className="table-scroll" ref={scroller} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
        <div className="thead">
          <div className="th rownum">#</div>
          {columns.map((c) => (
            <div
              key={c.name}
              className={`th ${c.kind === "numeric" ? "num" : ""} ${c.derived ? "derived" : ""}`}
              onClick={() => toggleSort(c.name)}
              title={
                c.derived
                  ? t("계산 필드: {expr}", { expr: c.expression ?? "" })
                  : t("{dtype} · 클릭하면 정렬함", { dtype: c.dtype })
              }
            >
              {c.name}
              {sort?.column === c.name ? (sort.desc ? " ▼" : " ▲") : ""}
            </div>
          ))}
        </div>
        <div className="tbody" style={{ height: total * ROW_HEIGHT }}>
          {rows}
        </div>
      </div>
    </section>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return Math.abs(v) >= 1e6 || (v !== 0 && Math.abs(v) < 1e-3)
      ? v.toExponential(3)
      : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(v);
}
