import { useCallback, useEffect, useRef, useState } from "react";

import { AttributeTable } from "./components/AttributeTable";
import { ChartsPanel } from "./components/charts/ChartsPanel";
import { DialogHost } from "./components/Dialogs";
import { MapCanvas } from "./components/MapCanvas";
import { PanelSplitter, usePanelWidth } from "./components/PanelSplitter";
import { Sidebar } from "./components/Sidebar";
import { StatusBar } from "./components/StatusBar";
import { Toolbar, openDataFlow, openProjectFlow, saveProjectFlow } from "./components/Toolbar";
import { t } from "./i18n";
import { onEngineExited } from "./lib/engine";
import { useApp } from "./store";

const MIN_TABLE = 90;
const DEFAULT_TABLE = 240;
// 좌우 패널 너비 (px): 기본값, 최솟값, 최댓값
const LEFT = { initial: 280, min: 200, max: 560 };
const RIGHT = { initial: 360, min: 260, max: 900 };

export function App() {
  const error = useApp((s) => s.error);
  const dismissError = useApp((s) => s.dismissError);
  const notices = useApp((s) => s.notices);
  const dismissNotice = useApp((s) => s.dismissNotice);
  const [tableHeight, setTableHeight] = useState(DEFAULT_TABLE);
  const [tableOpen, setTableOpen] = useState(true);
  const [chartsOpen, setChartsOpen] = useState(false);
  const [leftWidth, setLeftWidth] = usePanelWidth("geostat.leftWidth", LEFT.initial, LEFT.min, LEFT.max);
  const [rightWidth, setRightWidth] = usePanelWidth("geostat.rightWidth", RIGHT.initial, RIGHT.min, RIGHT.max);
  const columns = `${leftWidth}px 5px minmax(0, 1fr)${chartsOpen ? ` 5px ${rightWidth}px` : ""}`;
  // 가운데 지도가 이 너비보다 좁아지지 않게 패널 너비를 제한함
  const MIN_CENTER = 320;
  const resizeLeft = (w: number) =>
    setLeftWidth(Math.min(w, window.innerWidth - MIN_CENTER - 5 - (chartsOpen ? rightWidth + 5 : 0)));
  const resizeRight = (w: number) => setRightWidth(Math.min(w, window.innerWidth - MIN_CENTER - 10 - leftWidth));
  const toggleCharts = useCallback((open?: boolean) => setChartsOpen((v) => open ?? !v), []);
  const dragStart = useRef<{ y: number; h: number } | null>(null);

  const toggleTable = useCallback(() => setTableOpen((v) => !v), []);
  const engineDown = useApp((s) => s.engineDown);
  const update = useApp((s) => s.update);
  const busy = useApp((s) => s.busy);

  // 엔진이 예기치 않게 끝나면 알림 띄움. 시작하고 조금 뒤 새 버전이 있는지 조용히 확인함
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void onEngineExited((message) => useApp.getState().setEngineDown(message)).then((f) => (unlisten = f));
    const timer = window.setTimeout(() => void useApp.getState().checkUpdate(false), 4000);
    return () => {
      unlisten?.();
      window.clearTimeout(timer);
    };
  }, []);
  useShortcuts(toggleTable, toggleCharts);
  // 차트가 추가되면 패널을 엶
  const chartCount = useApp((s) => s.charts.length + s.reports.length);
  useEffect(() => {
    if (chartCount > 0) setChartsOpen(true);
  }, [chartCount]);

  // 테이블 패널 높이 조절 (경계선을 끌어서)
  const onDividerDown = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    dragStart.current = { y: e.clientY, h: tableHeight };
  };
  const onDividerMove = (e: React.PointerEvent) => {
    if (!dragStart.current) return;
    const max = window.innerHeight - 200;
    setTableHeight(Math.min(max, Math.max(MIN_TABLE, dragStart.current.h - (e.clientY - dragStart.current.y))));
  };

  return (
    <div className="app">
      <Toolbar chartsOpen={chartsOpen} onToggleCharts={toggleCharts} />
      <div className="main" style={{ gridTemplateColumns: columns }}>
        <Sidebar />
        <PanelSplitter
          direction={1}
          width={leftWidth}
          onResize={resizeLeft}
          onReset={() => setLeftWidth(LEFT.initial)}
          label={t("왼쪽 패널 너비")}
        />
        <div className="center">
          <main className="workspace">
            <MapCanvas />
            {engineDown && (
              <div className="error-banner engine-down" role="alert" data-testid="engine-down">
                <strong>{t("분석 엔진이 멈춤")}</strong>
                <span className="detail">{engineDown}</span>
                <span className="muted">
                  {t("다시 시작하면 열려 있던 데이터는 닫힘. 프로젝트를 저장해 두었다면 다시 열면 됨")}
                </span>
                <button className="primary" disabled={!!busy} onClick={() => void useApp.getState().restartEngine()}>
                  {t("엔진 다시 시작")}
                </button>
              </div>
            )}
            {update && !engineDown && (
              <div className="update-banner" role="status" data-testid="update-banner">
                <span>{t("새 버전 {v}이(가) 있음", { v: update.version })}</span>
                <button className="primary" disabled={!!busy} onClick={() => void useApp.getState().installUpdate()}>
                  {t("설치 후 다시 시작")}
                </button>
                <button className="link" onClick={() => useApp.getState().dismissUpdate()}>
                  {t("나중에")}
                </button>
              </div>
            )}
            {error && (
              <div className="error-banner" role="alert">
                <strong>{error.message}</strong>
                <code>{error.code}</code>
                <button onClick={dismissError}>{t("닫기")}</button>
              </div>
            )}
            <div className="notices">
              {notices.map((n) => (
                <div key={n.id} className="notice" onClick={() => dismissNotice(n.id)}>
                  {n.text}
                </div>
              ))}
            </div>
            <button className="table-toggle" onClick={toggleTable} title={t("속성 테이블 (⌘T)")}>
              {tableOpen ? `${t("테이블 숨기기")} ▾` : `${t("테이블")} ▴`}
            </button>
          </main>
          {tableOpen && (
            <>
              <div
                className="divider"
                onPointerDown={onDividerDown}
                onPointerMove={onDividerMove}
                onPointerUp={() => (dragStart.current = null)}
              />
              <AttributeTable height={tableHeight} />
            </>
          )}
        </div>
        {chartsOpen && (
          <>
            <PanelSplitter
              direction={-1}
              width={rightWidth}
              onResize={resizeRight}
              onReset={() => setRightWidth(RIGHT.initial)}
              label={t("오른쪽 패널 너비")}
            />
            <ChartsPanel onClose={() => setChartsOpen(false)} />
          </>
        )}
      </div>
      <StatusBar />
      <DialogHost />
    </div>
  );
}

/** 단축키: ⌘O 데이터 열기, ⇧⌘O 프로젝트 열기, ⌘S 저장, ⇧⌘S 다른 이름으로, ⌘T 테이블, ⌘J 차트, B·L·Esc 선택 도구 */
function useShortcuts(toggleTable: () => void, toggleCharts: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useApp.getState();
      const typing =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement;
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "o") {
        e.preventDefault();
        void (e.shiftKey ? openProjectFlow() : openDataFlow());
      } else if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void saveProjectFlow(e.shiftKey);
      } else if (mod && e.key.toLowerCase() === "t") {
        e.preventDefault();
        toggleTable();
      } else if (mod && e.key.toLowerCase() === "j") {
        e.preventDefault();
        toggleCharts();
      } else if (!typing && !mod && !s.dialog) {
        if (e.key === "b" || e.key === "B") s.setTool(s.tool === "box" ? "pan" : "box");
        else if (e.key === "l" || e.key === "L") s.setTool(s.tool === "lasso" ? "pan" : "lasso");
        else if (e.key === "Escape") s.setTool("pan");
      } else if (e.key === "Escape" && s.dialog) {
        s.showDialog(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleTable, toggleCharts]);
}
