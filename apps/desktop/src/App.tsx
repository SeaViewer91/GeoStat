import { useCallback, useEffect, useRef, useState } from "react";

import { AttributeTable } from "./components/AttributeTable";
import { DialogHost } from "./components/Dialogs";
import { MapCanvas } from "./components/MapCanvas";
import { Sidebar } from "./components/Sidebar";
import { StatusBar } from "./components/StatusBar";
import { Toolbar, openDataFlow, openProjectFlow, saveProjectFlow } from "./components/Toolbar";
import { useApp } from "./store";

const MIN_TABLE = 90;
const DEFAULT_TABLE = 240;

export function App() {
  const error = useApp((s) => s.error);
  const dismissError = useApp((s) => s.dismissError);
  const notices = useApp((s) => s.notices);
  const dismissNotice = useApp((s) => s.dismissNotice);
  const [tableHeight, setTableHeight] = useState(DEFAULT_TABLE);
  const [tableOpen, setTableOpen] = useState(true);
  const dragStart = useRef<{ y: number; h: number } | null>(null);

  const toggleTable = useCallback(() => setTableOpen((v) => !v), []);
  useShortcuts(toggleTable);

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
      <Toolbar />
      <div className="main">
        <Sidebar />
        <div className="center">
          <main className="workspace">
            <MapCanvas />
            {error && (
              <div className="error-banner" role="alert">
                <strong>{error.message}</strong>
                <code>{error.code}</code>
                <button onClick={dismissError}>닫기</button>
              </div>
            )}
            <div className="notices">
              {notices.map((n) => (
                <div key={n.id} className="notice" onClick={() => dismissNotice(n.id)}>
                  {n.text}
                </div>
              ))}
            </div>
            <button className="table-toggle" onClick={toggleTable} title="속성 테이블 (⌘T)">
              {tableOpen ? "테이블 숨기기 ▾" : "테이블 ▴"}
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
      </div>
      <StatusBar />
      <DialogHost />
    </div>
  );
}

/** 단축키: ⌘O 데이터 열기, ⇧⌘O 프로젝트 열기, ⌘S 저장, ⇧⌘S 다른 이름으로, ⌘T 테이블, B·L·Esc 선택 도구 */
function useShortcuts(toggleTable: () => void) {
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
  }, [toggleTable]);
}
