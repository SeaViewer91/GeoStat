import { useEffect, useState } from "react";

import { MapCanvas } from "./components/MapCanvas";
import { StatusBar } from "./components/StatusBar";
import { Toolbar } from "./components/Toolbar";
import { useApp } from "./store";

export function App() {
  const [boxMode, setBoxMode] = useState(false);
  const error = useApp((s) => s.error);
  const dismissError = useApp((s) => s.dismissError);

  // 단축키: B = 사각형 선택 토글, Esc = 사각형 선택 해제
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "b" || e.key === "B") setBoxMode((v) => !v);
      if (e.key === "Escape") setBoxMode(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="app">
      <Toolbar boxMode={boxMode} onToggleBoxMode={() => setBoxMode((v) => !v)} />
      <main className="workspace">
        <MapCanvas boxMode={boxMode} />
        {error && (
          <div className="error-banner" role="alert">
            <strong>{error.message}</strong>
            <code>{error.code}</code>
            <button onClick={dismissError}>닫기</button>
          </div>
        )}
      </main>
      <StatusBar />
    </div>
  );
}
